import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, getStudyTimer, startStudyTimer, updateStudyTimer, type StudyTimerCommand } from '../services/api';
import { useAppStore } from '../store/AppStore';
import type { DurableStudySession } from '../types';
import {
  clearContinuousStudySession,
  isContinuousStudySession,
  markContinuousStudySession,
} from '../utils/studySessionContinuity';

/** A frozen checkpoint after reload/offline; inactivity/hidden PDF never means failed learning. */
export function useDurableStudyTimer(courseId: string | undefined, blockId: string | undefined, ready: boolean, note = '') {
  const { state, dispatch } = useAppStore();
  const [session, setSession] = useState<DurableStudySession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [elapsed, setElapsed] = useState(0);
  const row = useRef<DurableStudySession | null>(null);
  const receivedAt = useRef(Date.now());
  const mounted = useRef(false);
  const inFlight = useRef(false);
  const pending = useRef<{ id: string; body: StudyTimerCommand } | null>(null);
  const mirrored = useRef('');
  const generation = useRef(0);
  const noteRef = useRef(note);
  const activeMirrorRef = useRef(state?.activeSession ?? null);
  noteRef.current = note;
  activeMirrorRef.current = state?.activeSession ?? null;
  const apply = useCallback((next: DurableStudySession | null, active?: DurableStudySession | null) => {
    row.current = next; receivedAt.current = Date.now();
    if (!mounted.current) return;
    setSession(next); setElapsed((next?.observed_seconds ?? 0) * 1000); setError('');
    const tracked = next && ['running', 'paused'].includes(next.status) ? next : active;
    if (next?.status === 'running') markContinuousStudySession(next.id, next.version);
    else if (next) clearContinuousStudySession(next.id);
    const mirrorKey = `${tracked?.id ?? ''}:${tracked?.status ?? ''}`;
    if (mirrorKey !== mirrored.current) dispatch({ type: 'SET_DURABLE_SESSION', session: tracked
      ? { id: tracked.id, blockId: tracked.blockId, taskId: tracked.taskId, accumulatedMs: tracked.observed_seconds * 1000,
          runningSince: tracked.status === 'running' ? Date.now() : null, version: tracked.version } : null });
    mirrored.current = mirrorKey;
    if (next?.status === 'completed' && next.evaluation) {
      dispatch({ type: 'RECORD_DURABLE_SESSION', session: {
        id: next.id, taskId: next.taskId, blockId: next.blockId, date: next.date,
        minutes: next.evaluation.actual_minutes, source: 'timer', plannedMin: next.planned_minutes,
        completedAt: next.checkpoint_at, completionPercent: next.evaluation.completion_percent,
        remainingMinutes: next.evaluation.remaining_minutes, workResult: next.evaluation.work_result ?? undefined,
        understandingSelfReport: next.evaluation.understanding_self_report,
        outcome: next.evaluation.status, blocker: next.evaluation.blocker, blockerNote: next.evaluation.blocker_note,
        needsRecovery: next.evaluation.needs_recovery, interruptionReason: next.evaluation.interruption_reason ?? next.interruption_reason,
        lengthFeeling: next.length_feeling, unobservedGap: next.unobserved_gap,
        timeSource: next.evaluation.time_source ?? 'timer',
      } });
    }
  }, [dispatch]);

  const act = useCallback(async (action: StudyTimerCommand['action'], detail: Partial<StudyTimerCommand> = {}) => {
    const epoch = generation.current;
    if (inFlight.current) throw new Error('Đang lưu checkpoint; hãy thử lại sau giây lát.');
    const current = row.current;
    if (!current) throw new Error('Chưa có phiên học.');
    // An unacknowledged command is retried verbatim, never with a new key.
    if (pending.current && pending.current.body.action !== action) throw new Error('Hãy thử lưu lại checkpoint trước khi thao tác tiếp.');
    const request = pending.current ?? { id: current.id, body: { ...(action === 'recover' ? {} : { note: noteRef.current }), ...detail, action,
      eventKey: crypto.randomUUID(), expectedVersion: current.version } as StudyTimerCommand };
    pending.current = request; inFlight.current = true;
    if (mounted.current) setBusy(true);
    try {
      const next = await updateStudyTimer(request.id, request.body);
      if (generation.current !== epoch) return next;
      pending.current = null; apply(next); return next;
    } catch (failure) {
      if (generation.current !== epoch) throw failure;
      if (failure instanceof ApiError && failure.code === 'CONFLICT' && blockId) {
        pending.current = null;
        const latest = await getStudyTimer(blockId);
        if (generation.current !== epoch) throw failure;
        apply(latest.session, latest.activeSession);
        const restored = latest.session;
        if (restored) {
          const alreadyApplied = request.body.action === 'checkpoint'
            || (['pause', 'recover'].includes(request.body.action) && restored.status === 'paused')
            || (request.body.action === 'resume' && restored.status === 'running')
            || (request.body.action === 'cancel' && restored.status === 'cancelled')
            || (request.body.action === 'complete' && restored.status === 'completed')
            || ['completed', 'cancelled'].includes(restored.status);
          if (alreadyApplied) return restored;
          const retried = { id: restored.id, body: { ...request.body, expectedVersion: restored.version,
            eventKey: crypto.randomUUID() } as StudyTimerCommand };
          pending.current = retried;
          try {
            const resolved = await updateStudyTimer(retried.id, retried.body);
            if (generation.current !== epoch) return resolved;
            pending.current = null; apply(resolved); return resolved;
          } catch (retryFailure) {
            if (retryFailure instanceof ApiError && retryFailure.code === 'CONFLICT') {
              pending.current = null;
              const reconciled = await getStudyTimer(blockId);
              if (generation.current !== epoch) throw retryFailure;
              apply(reconciled.session, reconciled.activeSession);
              if (reconciled.session) return reconciled.session;
            }
            if (mounted.current) {
              setError(retryFailure instanceof Error ? retryFailure.message : 'Chưa lưu được checkpoint.');
              setElapsed((row.current?.observed_seconds ?? 0) * 1000);
            }
            throw retryFailure;
          }
        }
      }
      if (mounted.current) { setError(failure instanceof Error ? failure.message : 'Chưa lưu được checkpoint.'); setElapsed((row.current?.observed_seconds ?? 0) * 1000); }
      throw failure;
    } finally { if (generation.current === epoch) { inFlight.current = false; if (mounted.current) setBusy(false); } }
  }, [apply, blockId]);

  useEffect(() => {
    generation.current += 1;
    mounted.current = true;
    row.current = null; pending.current = null; inFlight.current = false; mirrored.current = '';
    const mirroredSession = activeMirrorRef.current?.blockId === blockId ? activeMirrorRef.current : null;
    const mirroredElapsed = mirroredSession
      ? mirroredSession.accumulatedMs + (mirroredSession.runningSince === null
        ? 0
        : Math.min(45_000, Math.max(0, Date.now() - mirroredSession.runningSince)))
      : 0;
    setSession(null); setElapsed(mirroredElapsed); setError('');
    if (!ready || !blockId) return () => { mounted.current = false; };
    let active = true;
    setBusy(true);
    void getStudyTimer(blockId).then(async ({ session: restored, activeSession }) => {
      if (!active) return;
      // Never count wall-clock absence on reload, even if pagehide could not send.
      if (restored?.status === 'running' && !isContinuousStudySession(restored.id)) restored = await updateStudyTimer(restored.id,
        { action: 'recover', expectedVersion: restored.version, eventKey: crypto.randomUUID() });
      if (active) apply(restored, activeSession);
    }).catch((failure: unknown) => { if (active) setError(failure instanceof Error ? failure.message : 'Chưa tải được phiên học.'); })
      .finally(() => { if (active) setBusy(false); });
    return () => { active = false; mounted.current = false; };
  }, [ready, blockId, apply, act]);

  useEffect(() => {
    if (session?.status !== 'running') return;
    const tick = window.setInterval(() => setElapsed(error ? (row.current?.observed_seconds ?? 0) * 1000
      : (row.current?.observed_seconds ?? 0) * 1000 + Math.min(45_000, Math.max(0, Date.now() - receivedAt.current))), 1000);
    const heartbeat = window.setInterval(() => {
      if (!inFlight.current && !pending.current && navigator.onLine) void act('checkpoint').catch(() => {});
    }, 20_000);
    const checkpointBeforeBackground = () => {
      if (document.visibilityState === 'hidden' && !inFlight.current && !pending.current && navigator.onLine) {
        void act('checkpoint').catch(() => {});
      }
    };
    const leave = () => { if (!inFlight.current) void act('recover').catch(() => {}); };
    document.addEventListener('visibilitychange', checkpointBeforeBackground);
    window.addEventListener('pagehide', leave);
    return () => {
      window.clearInterval(tick);
      window.clearInterval(heartbeat);
      document.removeEventListener('visibilitychange', checkpointBeforeBackground);
      window.removeEventListener('pagehide', leave);
    };
  }, [session?.status, act, error]);

  const start = async () => {
    if (!courseId || !blockId || inFlight.current) return;
    inFlight.current = true; setBusy(true);
    const epoch = generation.current;
    try { const next = await startStudyTimer(courseId, blockId); if (generation.current === epoch) apply(next); }
    catch (failure) { if (generation.current === epoch && mounted.current) setError(failure instanceof Error ? failure.message : 'Chưa bắt đầu được phiên.'); }
    finally { if (generation.current === epoch) { inFlight.current = false; if (mounted.current) setBusy(false); } }
  };
  const retry = () => {
    const epoch = generation.current;
    return pending.current ? act(pending.current.body.action)
    : blockId ? getStudyTimer(blockId).then(async ({ session: next, activeSession }) => {
      if (generation.current !== epoch) return;
      if (next?.status === 'running' && !isContinuousStudySession(next.id)) next = await updateStudyTimer(next.id, { action: 'recover', expectedVersion: next.version, eventKey: crypto.randomUUID() });
      if (generation.current === epoch) apply(next, activeSession);
    }) : Promise.resolve();
  };
  return { session, elapsed, busy, error, start, act, retry };
}
