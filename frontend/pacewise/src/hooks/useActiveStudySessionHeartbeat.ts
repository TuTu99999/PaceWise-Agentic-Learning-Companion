import { useEffect } from 'react';
import { ApiError, getStudyTimer, updateStudyTimer } from '../services/api';
import { useAppStore } from '../store/AppStore';
import type { DurableStudySession } from '../types';
import {
  clearContinuousStudySession,
  continuousStudySessionVersion,
  isContinuousStudySession,
  markContinuousStudySession,
} from '../utils/studySessionContinuity';

const HEARTBEAT_MS = 20_000;

function mirror(session: DurableStudySession) {
  return {
    id: session.id,
    blockId: session.blockId,
    taskId: session.taskId,
    version: session.version,
    accumulatedMs: session.observed_seconds * 1000,
    runningSince: session.status === 'running' ? Date.now() : null,
  };
}

/** Keeps a server timer alive while the student visits another PaceWise route. */
export function useActiveStudySessionHeartbeat(onSessionRoute: boolean) {
  const { state, dispatch } = useAppStore();
  const active = state.activeSession;

  useEffect(() => {
    if (!state.workspaceReady || !active?.id || !active.blockId || active.runningSince === null) return;
    let mounted = true;
    let latestVersion = continuousStudySessionVersion(active.id) ?? active.version;

    const apply = (session: DurableStudySession) => {
      if (!mounted) return;
      latestVersion = session.version;
      if (session.status === 'running') markContinuousStudySession(session.id, session.version);
      else clearContinuousStudySession(session.id);
      dispatch({ type: 'SET_DURABLE_SESSION', session: mirror(session) });
    };

    const recoverAfterReload = async () => {
      try {
        const current = await getStudyTimer(active.blockId!);
        if (!mounted) return;
        const session = current.session;
        if (!session) {
          dispatch({ type: 'SET_DURABLE_SESSION', session: null });
          return;
        }
        if (session.status === 'running') {
          const paused = await updateStudyTimer(session.id, {
            action: 'recover',
            expectedVersion: session.version,
            eventKey: crypto.randomUUID(),
          });
          apply(paused);
        } else apply(session);
      } catch {
        // The server remains authoritative. The session page exposes retry UI.
      }
    };

    // The session page owns its timer lifecycle. In particular, it handles a
    // hard reload itself, so the layout must not race it with a second recover.
    if (onSessionRoute) return () => { mounted = false; };
    if (!isContinuousStudySession(active.id)) {
      // Workspace state survived a full reload, but in-memory continuity did
      // not. Pause without counting the unobserved wall-clock interval.
      void recoverAfterReload();
      return () => { mounted = false; };
    }
    const checkpoint = async () => {
      if (!latestVersion) {
        const current = await getStudyTimer(active.blockId!);
        if (current.session) apply(current.session);
        return;
      }
      try {
        const session = await updateStudyTimer(active.id!, {
          action: 'checkpoint',
          expectedVersion: latestVersion,
          eventKey: crypto.randomUUID(),
        });
        if (session.status === 'running') {
          latestVersion = session.version;
          markContinuousStudySession(session.id, session.version);
        } else apply(session);
      } catch (failure) {
        if (failure instanceof ApiError && failure.code === 'CONFLICT') {
          const current = await getStudyTimer(active.blockId!);
          if (current.session?.status === 'running') {
            latestVersion = current.session.version;
            markContinuousStudySession(current.session.id, current.session.version);
          } else if (current.session) apply(current.session);
        }
      }
    };

    void checkpoint();
    const timer = window.setInterval(() => void checkpoint(), HEARTBEAT_MS);
    const leave = () => {
      if (!latestVersion) return;
      void updateStudyTimer(active.id!, {
        action: 'recover',
        expectedVersion: latestVersion,
        eventKey: crypto.randomUUID(),
      }).catch(() => {});
    };
    window.addEventListener('pagehide', leave);
    return () => {
      mounted = false;
      window.clearInterval(timer);
      window.removeEventListener('pagehide', leave);
    };
  }, [active?.blockId, active?.id, active?.runningSince, dispatch, onSessionRoute, state.workspaceReady]);
}
