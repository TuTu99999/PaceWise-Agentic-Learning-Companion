import { act, renderHook, waitFor } from '@testing-library/react';
import { StrictMode, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { materialRevision, useDoPreparation } from './useDoPreparation';
import { prepareDoSession } from '../services/api';
import type { DoSessionPreparation, LMSCourseData } from '../types';

vi.mock('../services/api', () => ({ prepareDoSession: vi.fn() }));
const prepared: DoSessionPreparation = { action: 'prepare', status: 'ready', block_id: 'b1', task_id: '1:7',
  title: 'Task', objective: 'Read requirements', planned_minutes: 30, opening_prompt: 'Ask', recommended_resources: [] };
const props = { user: 'u1', course: '1', block: 'b1', revision: 'v1', enabled: true };
const hook = (value: typeof props) => useDoPreparation(value.user, value.course, value.block, value.revision, value.enabled);
beforeEach(() => vi.resetAllMocks());

describe('Do preparation request lifecycle', () => {
  it('loads once in StrictMode and does not reload for equal sync content', async () => {
    vi.mocked(prepareDoSession).mockResolvedValue(prepared);
    const wrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>;
    const { result, rerender } = renderHook(hook, { initialProps: props, wrapper });
    await waitFor(() => expect(result.current.preparation).toEqual(prepared));
    rerender({ ...props });
    expect(prepareDoSession).toHaveBeenCalledTimes(1);
  });

  it('coalesces concurrent consumers and aborts only after the last consumer leaves', async () => {
    vi.mocked(prepareDoSession).mockReturnValue(new Promise(() => {}));
    const a = renderHook(hook, { initialProps: props });
    const b = renderHook(hook, { initialProps: props });
    expect(prepareDoSession).toHaveBeenCalledTimes(1);
    const signal = vi.mocked(prepareDoSession).mock.calls[0][1]!;
    a.unmount(); await act(async () => {});
    expect(signal.aborted).toBe(false);
    b.unmount(); await act(async () => {});
    expect(signal.aborted).toBe(true);
  });

  it('keeps the previous resources visible during version refresh', async () => {
    vi.mocked(prepareDoSession).mockResolvedValueOnce(prepared).mockReturnValueOnce(new Promise(() => {}));
    const { result, rerender } = renderHook(hook, { initialProps: props });
    await waitFor(() => expect(result.current.preparation).toEqual(prepared));
    rerender({ ...props, revision: 'v2' });
    expect(result.current.loading).toBe(true);
    expect(result.current.preparation).toEqual(prepared);
  });

  it('aborts stale requests on block change and never displays their late result', async () => {
    let finish!: (data: DoSessionPreparation) => void;
    vi.mocked(prepareDoSession).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }))
      .mockResolvedValueOnce({ ...prepared, block_id: 'b2' });
    const { result, rerender } = renderHook(hook, { initialProps: props });
    const signal = vi.mocked(prepareDoSession).mock.calls[0][1]!;
    rerender({ ...props, block: 'b2' });
    expect(result.current.preparation).toBeNull();
    await waitFor(() => expect(result.current.preparation?.block_id).toBe('b2'));
    await act(async () => finish(prepared));
    expect(signal.aborted).toBe(true);
    expect(result.current.preparation?.block_id).toBe('b2');
  });

  it('clears sources after permissions refresh fails and provides explicit retry', async () => {
    vi.mocked(prepareDoSession).mockResolvedValueOnce(prepared).mockRejectedValueOnce(new Error('Permission revoked'))
      .mockResolvedValueOnce({ ...prepared, recommended_resources: [] });
    const { result, rerender } = renderHook(hook, { initialProps: props });
    await waitFor(() => expect(result.current.preparation).toEqual(prepared));
    rerender({ ...props, revision: 'revoked' });
    await waitFor(() => expect(result.current.error).toBe('Permission revoked'));
    expect(result.current.preparation).toBeNull();
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.preparation).toEqual(prepared));
    expect(result.current.error).toBe('');
  });

  it('does not load unconfirmed or not-ready sessions', () => {
    renderHook(hook, { initialProps: { ...props, enabled: false } });
    expect(prepareDoSession).not.toHaveBeenCalled();
  });

  it('ignores module completion progress but detects file, ACL and mapping revisions', () => {
    const data = { modules: [{ id: 1, name: 'Chapter 3', published: true, requirements: [{ status: 'pending' }],
      items: [{ id: 1, title: 'Slide', type: 'file', content_id: 2 }] }], resources: [{ id: 2, title: 'Slide', kind: 'slides',
      source_url: '/slide.pdf', latest_version: { version: 1 }, access_scope: [] }] } as unknown as LMSCourseData;
    const first = materialRevision(data);
    const next = JSON.parse(JSON.stringify(data));
    next.modules[0].requirements[0].status = 'complete';
    expect(materialRevision(next)).toBe(first);
    next.resources[0].latest_version.version = 2;
    expect(materialRevision(next)).not.toBe(first);
    next.resources[0].latest_version.version = 1;
    next.resources[0].access_scope = [{ type: 'student', id: 2 }];
    expect(materialRevision(next)).not.toBe(first);
    next.resources[0].access_scope = [];
    next.modules[0].items = [];
    expect(materialRevision(next)).not.toBe(first);
  });
});
