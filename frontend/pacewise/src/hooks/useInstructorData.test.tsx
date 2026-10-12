import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, fetchInstructorData, type InstructorData } from '../services/api';
import { readInstructorOverviewCache, writeInstructorOverviewCache } from '../services/instructorOverviewCache';
import { InstructorDataProvider, useInstructorData } from './useInstructorData';
import type { ReactNode } from 'react';

const wrapper = ({ children }: { children: ReactNode }) => <InstructorDataProvider>{children}</InstructorDataProvider>;
const show = () => renderHook(useInstructorData, { wrapper });

const mocks = vi.hoisted(() => ({
  state: { user: { id: 't', courseId: 'a' }, lmsRevision: 0, classGroups: [] }, dispatch: vi.fn(),
}));
vi.mock('../store/AppStore', () => ({ useAppStore: () => mocks }));
vi.mock('../services/api', async (original) => ({ ...await original<object>(), fetchInstructorData: vi.fn() }));

const data = (name: string): InstructorData => ({
  classGroups: [{ id: 'all', name, n: 8 }], groupStats: {}, reviewQueue: [], assessments: [], audit: [], guidance: [],
  privacy: { minimumGroupSize: 5, containsDirectIdentifiers: false }, lmsSummary: null,
  teacherWorkspace: { schedule: [], feedback: [], courseStructure: { modules: [], knowledgeComponents: [] },
    settings: { minimumGroupSize: 5, allowIndividualReview: false, requireStudentConsent: true, autoPublishApprovedResources: false } },
});

describe('instructor data scope and revalidation', () => {
  beforeEach(() => {
    sessionStorage.clear(); vi.mocked(fetchInstructorData).mockReset(); mocks.dispatch.mockClear();
    mocks.state = { user: { id: 't', courseId: 'a' }, lmsRevision: 0, classGroups: [] };
  });
  afterEach(() => vi.restoreAllMocks());

  it('revalidates an expired freshness window even if the revision did not change after course switch', async () => {
    const now = vi.spyOn(Date, 'now').mockReturnValue(1000);
    writeInstructorOverviewCache('t', 'a', data('old A'));
    now.mockReturnValue(40000);
    vi.mocked(fetchInstructorData).mockResolvedValue(data('new A'));
    const { result, rerender } = show();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchInstructorData).toHaveBeenCalledTimes(1);
    mocks.state.user.courseId = 'b';
    vi.mocked(fetchInstructorData).mockResolvedValue(data('B'));
    rerender();
    await waitFor(() => expect(fetchInstructorData).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(result.current.loading).toBe(false));
    now.mockReturnValue(80000);
    mocks.state.user.courseId = 'a'; rerender();
    await waitFor(() => expect(fetchInstructorData).toHaveBeenCalledTimes(3));
  });

  it('does not request course aggregates when the instructor has no active course', async () => {
    mocks.state.user.courseId = '0';
    const { result } = show();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(fetchInstructorData).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
  });

  it('discards an old course response after switching, including a manual refresh', async () => {
    let resolveOld!: (value: InstructorData) => void;
    vi.mocked(fetchInstructorData).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    const { result, rerender } = show();
    let pending!: Promise<void>;
    act(() => { pending = result.current.refresh(); });
    mocks.state.user.courseId = 'b';
    vi.mocked(fetchInstructorData).mockResolvedValue(data('B'));
    rerender();
    await waitFor(() => expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({ classGroups: data('B').classGroups })));
    mocks.dispatch.mockClear();
    await act(async () => { resolveOld(data('A')); await pending; });
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });

  it('catches manual refresh failure, retains error for UI, and allows retry', async () => {
    writeInstructorOverviewCache('t', 'a', data('cached'));
    const { result } = show();
    vi.mocked(fetchInstructorData).mockRejectedValueOnce(new ApiError('UNKNOWN', 'offline'));
    await act(async () => { await result.current.refresh(); });
    expect(result.current.error?.message).toBe('offline');
    vi.mocked(fetchInstructorData).mockResolvedValueOnce(data('fresh'));
    await act(async () => { await result.current.refresh(); });
    expect(result.current.error).toBeNull();
    expect(mocks.dispatch).toHaveBeenLastCalledWith(expect.objectContaining({ classGroups: data('fresh').classGroups }));
  });

  it('revalidates a fresh cache when a live LMS revision arrives', async () => {
    writeInstructorOverviewCache('t', 'a', data('cached'));
    const { rerender } = show();
    expect(fetchInstructorData).not.toHaveBeenCalled();
    vi.mocked(fetchInstructorData).mockResolvedValueOnce(data('fresh'));
    mocks.state.lmsRevision++; rerender();
    await waitFor(() => expect(fetchInstructorData).toHaveBeenCalledOnce());
  });

  it('clears cached aggregate and review data if live instructor access is revoked', async () => {
    writeInstructorOverviewCache('t', 'a', data('cached'));
    const { result } = show();
    vi.mocked(fetchInstructorData).mockRejectedValueOnce(new ApiError('FORBIDDEN', 'Enrollment removed'));
    await act(async () => { await result.current.refresh(); });
    expect(result.current.error?.code).toBe('FORBIDDEN');
    expect(readInstructorOverviewCache('t', 'a')).toBeNull();
    expect(mocks.dispatch).toHaveBeenLastCalledWith(expect.objectContaining({ classGroups: [], groupStats: {}, reviewQueue: [] }));
  });

  it('keeps one controller when tab consumers unmount, even when browser storage is blocked', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage disabled'); });
    vi.mocked(fetchInstructorData).mockResolvedValue(data('A'));
    function Tab({ name }: { name: string }) {
      const { loading } = useInstructorData();
      return <p>{name}: {loading ? 'loading' : 'ready'}</p>;
    }
    const tree = (name: string) => <InstructorDataProvider><Tab key={name} name={name} /></InstructorDataProvider>;
    const view = render(tree('overview'));
    await screen.findByText('overview: ready');
    mocks.dispatch.mockClear();
    view.rerender(tree('review'));
    expect(screen.getByText('review: ready')).toBeInTheDocument();
    view.rerender(tree('assessment'));
    expect(screen.getByText('assessment: ready')).toBeInTheDocument();
    expect(fetchInstructorData).toHaveBeenCalledOnce();
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });

  it('keeps a loaded empty cohort visible while manually refreshing', async () => {
    vi.mocked(fetchInstructorData).mockResolvedValue({ ...data('A'), classGroups: [] });
    const { result } = show();
    await waitFor(() => expect(result.current.loading).toBe(false));
    let resolve!: (value: InstructorData) => void;
    vi.mocked(fetchInstructorData).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    let pending!: Promise<void>;
    act(() => { pending = result.current.refresh(); });
    expect(result.current.loading).toBe(false);
    expect(result.current.refreshing).toBe(true);
    await act(async () => { resolve(data('A')); await pending; });
    expect(result.current.refreshing).toBe(false);
  });

  it('revalidates in the background without restoring old cache over local decisions', async () => {
    writeInstructorOverviewCache('t', 'a', data('old'));
    const { result, rerender } = show();
    mocks.dispatch.mockClear();
    let resolve!: (value: InstructorData) => void;
    vi.mocked(fetchInstructorData).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));
    mocks.state.lmsRevision++;
    rerender();
    expect(result.current.loading).toBe(false);
    expect(mocks.dispatch).not.toHaveBeenCalled();
    await act(async () => resolve(data('new')));
    expect(mocks.dispatch).toHaveBeenCalledOnce();
  });
});
