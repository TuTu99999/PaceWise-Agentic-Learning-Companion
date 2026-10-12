import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DurableStudySession } from '../types';
import { markContinuousStudySession, resetStudySessionContinuityForTests } from '../utils/studySessionContinuity';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  dispatch: vi.fn(),
  state: {} as Record<string, unknown>,
}));

vi.mock('../services/api', () => ({
  ApiError: class extends Error { code = ''; },
  getStudyTimer: mocks.get,
  updateStudyTimer: mocks.update,
}));
vi.mock('../store/AppStore', () => ({ useAppStore: () => ({ state: mocks.state, dispatch: mocks.dispatch }) }));

import { useActiveStudySessionHeartbeat } from './useActiveStudySessionHeartbeat';

const row: DurableStudySession = {
  id: 'SS-1', taskId: '1:a', courseId: '1', blockId: 'b1', version: 3,
  status: 'running', observed_seconds: 60, checkpoint_at: '2026-10-10T08:00:00Z', date: '2026-10-10',
  planned_minutes: 60, heartbeatSeconds: 20, interruption_reason: 'none', length_feeling: 'not_reported', unobserved_gap: false,
};

beforeEach(() => {
  resetStudySessionContinuityForTests();
  vi.clearAllMocks();
  mocks.state = {
    workspaceReady: true,
    activeSession: { id: row.id, blockId: row.blockId, taskId: row.taskId, version: row.version, accumulatedMs: 60_000, runningSince: 1 },
  };
  mocks.get.mockResolvedValue({ session: row });
  mocks.update.mockImplementation(async (_id, command) => ({
    ...row,
    version: command.expectedVersion + 1,
    status: command.action === 'recover' ? 'paused' : 'running',
    unobserved_gap: command.action === 'recover',
  }));
});

describe('active study session heartbeat', () => {
  it('keeps the timer observed while the learner visits another PaceWise route', async () => {
    markContinuousStudySession(row.id, row.version);
    renderHook(() => useActiveStudySessionHeartbeat(false));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(row.id, expect.objectContaining({
      action: 'checkpoint', expectedVersion: row.version,
    })));
  });

  it('pauses a workspace-restored timer after a hard reload', async () => {
    renderHook(() => useActiveStudySessionHeartbeat(false));
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(row.id, expect.objectContaining({
      action: 'recover', expectedVersion: row.version,
    })));
    expect(mocks.dispatch).toHaveBeenCalledWith(expect.objectContaining({
      type: 'SET_DURABLE_SESSION', session: expect.objectContaining({ runningSince: null }),
    }));
  });

  it('leaves lifecycle ownership to the session page on the Do route', async () => {
    markContinuousStudySession(row.id, row.version);
    renderHook(() => useActiveStudySessionHeartbeat(true));
    await Promise.resolve();
    expect(mocks.update).not.toHaveBeenCalled();
    expect(mocks.get).not.toHaveBeenCalled();
  });
});
