import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DurableStudySession } from '../types';
import { resetStudySessionContinuityForTests } from '../utils/studySessionContinuity';

const mocks = vi.hoisted(() => ({ get: vi.fn(), start: vi.fn(), update: vi.fn(), dispatch: vi.fn(),
  state: { activeSession: null } as { activeSession: null | { id: string; blockId: string; taskId: string; version: number; accumulatedMs: number; runningSince: number | null } } }));
vi.mock('../services/api', () => ({ ApiError: class extends Error {
    constructor(public code: string, message: string) { super(message); }
  }, getStudyTimer: mocks.get,
  startStudyTimer: mocks.start, updateStudyTimer: mocks.update }));
vi.mock('../store/AppStore', () => ({ useAppStore: () => ({ state: mocks.state, dispatch: mocks.dispatch }) }));
import { ApiError } from '../services/api';
import { useDurableStudyTimer } from './useDurableStudyTimer';

const row: DurableStudySession = { id: 'SS-1', taskId: '1:a', courseId: '1', blockId: 'b1', version: 1,
  status: 'running', observed_seconds: 60, checkpoint_at: '2026-10-10T08:00:00Z', date: '2026-10-10',
  planned_minutes: 60, heartbeatSeconds: 20, interruption_reason: 'none', length_feeling: 'not_reported', unobserved_gap: false };
beforeEach(() => {
  resetStudySessionContinuityForTests();
  vi.useFakeTimers(); vi.setSystemTime(new Date(row.checkpoint_at)); vi.clearAllMocks();
  mocks.state.activeSession = null;
  mocks.get.mockResolvedValue({ session: null }); mocks.start.mockResolvedValue({ ...row });
  mocks.update.mockImplementation(async (_id, command) => ({ ...row, version: command.expectedVersion + 1,
    status: command.action === 'pause' || command.action === 'recover' ? 'paused' : 'running',
    observed_seconds: command.action === 'recover' ? 60 : 80, unobserved_gap: command.action === 'recover' }));
});
afterEach(() => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  vi.useRealTimers();
});
describe('durable timer lifecycle', () => {
  it('recovers a running checkpoint as paused without counting time away', async () => {
    mocks.get.mockResolvedValue({ session: row });
    vi.setSystemTime(new Date('2026-10-11T08:00:00Z'));
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {});
    expect(mocks.update).toHaveBeenCalledWith('SS-1', expect.objectContaining({ action: 'recover', expectedVersion: 1 }));
    expect(result.current.session?.status).toBe('paused');
    expect(result.current.elapsed).toBe(60_000);
  });
  it('keeps heartbeats without mouse activity or document visibility heuristics', async () => {
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {});
    await act(async () => { await result.current.start(); });
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(20_000); });
    expect(mocks.update).toHaveBeenCalledWith('SS-1', expect.objectContaining({ action: 'checkpoint' }));
    expect(mocks.update.mock.calls.every(([, command]) => command.action !== 'pause')).toBe(true);
    const activeDispatches = mocks.dispatch.mock.calls.filter(([command]) => command.type === 'SET_DURABLE_SESSION');
    expect(activeDispatches).toHaveLength(2); // initial empty + start; no workspace write every heartbeat
  });
  it('checkpoints immediately before the browser tab is backgrounded', async () => {
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {});
    await act(async () => { await result.current.start(); });
    mocks.update.mockClear();
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' });
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); await Promise.resolve(); });
    expect(mocks.update).toHaveBeenCalledWith('SS-1', expect.objectContaining({ action: 'checkpoint' }));
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  });
  it('shows the mirrored elapsed time while restoring the authoritative server checkpoint', () => {
    vi.setSystemTime(new Date('2026-10-10T08:00:05Z'));
    mocks.state.activeSession = { id: row.id, blockId: row.blockId, taskId: row.taskId, version: row.version,
      accumulatedMs: 60_000, runningSince: new Date(row.checkpoint_at).getTime() };
    mocks.get.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    expect(result.current.elapsed).toBe(65_000);
  });
  it('silently reconciles an automatic checkpoint conflict instead of showing an error', async () => {
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {});
    await act(async () => { await result.current.start(); });
    mocks.update.mockRejectedValueOnce(new ApiError('CONFLICT', 'Session changed in another tab; reload its checkpoint'));
    mocks.get.mockResolvedValue({ session: { ...row, version: 2, observed_seconds: 65 } });
    await act(async () => { await result.current.act('checkpoint'); });
    expect(result.current.session?.version).toBe(2);
    expect(result.current.elapsed).toBe(65_000);
    expect(result.current.error).toBe('');
  });
  it('retries a user action once with the reconciled server version', async () => {
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {});
    await act(async () => { await result.current.start(); });
    mocks.update.mockRejectedValueOnce(new ApiError('CONFLICT', 'stale version'));
    mocks.get.mockResolvedValue({ session: { ...row, version: 2, observed_seconds: 65 } });
    await act(async () => { await result.current.act('pause'); });
    expect(mocks.update).toHaveBeenLastCalledWith('SS-1', expect.objectContaining({ action: 'pause', expectedVersion: 2 }));
    expect(result.current.session?.status).toBe('paused');
    expect(result.current.error).toBe('');
  });
  it('keeps a running session continuous across an internal route unmount', async () => {
    const first = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {});
    await act(async () => { await first.result.current.start(); });
    first.unmount();
    mocks.update.mockClear();
    mocks.get.mockResolvedValue({ session: row });

    const second = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {});

    expect(second.result.current.session?.status).toBe('running');
    expect(mocks.update).not.toHaveBeenCalledWith('SS-1', expect.objectContaining({ action: 'recover' }));
  });
  it('retries the exact unacknowledged command key/version after network failure', async () => {
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b1', true));
    await act(async () => {}); await act(async () => { await result.current.start(); });
    mocks.update.mockRejectedValueOnce(new Error('offline'));
    await act(async () => { await result.current.act('pause', { interruptionReason: 'unexpected' }).catch(() => {}); });
    const first = mocks.update.mock.calls[0];
    expect(result.current.error).toBe('offline');
    await act(async () => { await result.current.retry(); });
    expect(mocks.update.mock.calls[1]).toEqual(first);
    expect(result.current.error).toBe('');
  });
  it('ignores a delayed command response after changing study blocks', async () => {
    const { result, rerender } = renderHook(({ block }) => useDurableStudyTimer('1', block, true), { initialProps: { block: 'b1' } });
    await act(async () => {}); await act(async () => { await result.current.start(); });
    let resolve!: (value: DurableStudySession) => void;
    mocks.update.mockImplementationOnce(() => new Promise<DurableStudySession>((done) => { resolve = done; }));
    let command!: Promise<DurableStudySession>;
    await act(async () => { command = result.current.act('pause'); });
    rerender({ block: 'b2' });
    await act(async () => {});
    await act(async () => { resolve({ ...row, status: 'paused', version: 2 }); await command; });
    expect(result.current.session).toBeNull();
    expect(result.current.elapsed).toBe(0);
  });
  it('keeps a link to another active server session without counting it in this block', async () => {
    mocks.get.mockResolvedValue({ session: null, activeSession: { ...row, status: 'paused' } });
    const { result } = renderHook(() => useDurableStudyTimer('1', 'b2', true));
    await act(async () => {});
    expect(result.current.session).toBeNull();
    expect(result.current.elapsed).toBe(0);
    expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: 'SET_DURABLE_SESSION',
      session: expect.objectContaining({ blockId: 'b1' }) }));
  });
});
