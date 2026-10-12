import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { initialState, reducer } from '../../store/AppStore';

const mocks = vi.hoisted(() => ({ get: vi.fn(), confirm: vi.fn(), dispatch: vi.fn() }));
vi.mock('../../services/api', () => ({ getRhythmProposal: mocks.get, confirmRhythmProposal: mocks.confirm }));
vi.mock('../../store/AppStore', async (original) => ({ ...await original<typeof import('../../store/AppStore')>(),
  useAppStore: () => ({ state: { workspaceReady: true, studyPreferences: { sessionMinutes: 60, breakMinutes: 10 } }, dispatch: mocks.dispatch }) }));
import { RhythmProposalCard } from './RhythmProposalCard';

beforeEach(() => {
  vi.clearAllMocks(); mocks.get.mockResolvedValue({ status: 'trial_proposed', excludedCount: 2,
    proposal: { id: 'trial', courseId: 1, activityType: 'concept', preferences: { sessionMinutes: 45, breakMinutes: 10 }, sourceRefs: ['do:s1', 'do:s2', 'do:s3'], assessmentEvidenceIds: [] } });
  mocks.confirm.mockResolvedValue({ scope: { courseId: 1, activityType: 'concept' }, preferences: { sessionMinutes: 45, breakMinutes: 10 }, planChanged: false });
});
describe('explicit rhythm trial consent', () => {
  it('does not apply on load and confirms only after clicking', async () => {
    render(<RhythmProposalCard />);
    const button = await screen.findByRole('button', { name: 'Xác nhận thử nhịp mới' });
    expect(mocks.dispatch).not.toHaveBeenCalled(); expect(mocks.confirm).not.toHaveBeenCalled();
    fireEvent.click(button);
    await waitFor(() => expect(mocks.dispatch).toHaveBeenCalledWith({ type: 'UPSERT_ACTIVITY_RHYTHM', rhythm: { courseId: 1, activityType: 'concept', sessionMinutes: 45, breakMinutes: 10 } }));
    expect(mocks.confirm).toHaveBeenCalledWith('trial');
  });
  it('keeps the preference when confirmation fails', async () => {
    mocks.confirm.mockRejectedValue(new Error('Evidence changed'));
    render(<RhythmProposalCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'Xác nhận thử nhịp mới' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Evidence changed');
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });
  it('separates completion from Assessment and never invents missing retention results', async () => {
    mocks.get.mockResolvedValue({ status: 'insufficient_evidence', excludedCount: 0, proposal: null,
      comparison: { status: 'collecting', before: { sessions: 3, completionRate: 1, longSessionRate: 1,
        assessment: { application: { testedSessions: 3, passRate: 0 } } },
      after: { sessions: 1, completionRate: 1, longSessionRate: null, assessment: {} } } });
    render(<RhythmProposalCard />);
    expect(await screen.findByText('Tiến độ và bằng chứng Assessment trước/sau')).toBeInTheDocument();
    expect(screen.getAllByText('Hoàn thành ca: 100%')).toHaveLength(2);
    expect(screen.getByText('Vận dụng: 0% · 3 phiên được kiểm tra')).toBeInTheDocument();
    expect(screen.getAllByText('Nhớ sau một thời gian: Chưa kiểm tra')).toHaveLength(2);
    expect(mocks.dispatch).not.toHaveBeenCalled();
  });
  it('deduplicates recovered completion records and does not change estimate or plan', () => {
    const session = { id: 'SS-1', taskId: '1:a', date: '2026-10-10', minutes: 20, source: 'timer' as const };
    const state = { ...initialState, tasks: [{ id: '1:a', courseId: '1', title: 'task', objective: '', deadline: '2026-10-11', estimateMin: 60, loggedMin: 0, status: 'todo' as const, priority: 'high' as const }] };
    const once = reducer(state, { type: 'RECORD_DURABLE_SESSION', session });
    const twice = reducer(once, { type: 'RECORD_DURABLE_SESSION', session });
    expect(twice.tasks[0].loggedMin).toBe(20); expect(twice.tasks[0].estimateMin).toBe(60);
    expect(twice.plan).toBe(state.plan); expect(twice.sessions).toHaveLength(1);
  });
});
