import { useEffect, useState } from 'react';
import type { ActiveSession } from '../types';

/** Elapsed milliseconds of the active study session, ticking every second while running. */
export function useTimer(session: ActiveSession | null) {
  const compute = () => (session ? session.accumulatedMs + (session.runningSince ? Date.now() - session.runningSince : 0) : 0);
  const [elapsed, setElapsed] = useState(compute);
  useEffect(() => {
    setElapsed(compute());
    if (!session?.runningSince) return;
    const id = window.setInterval(() => setElapsed(compute()), 1000);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.runningSince, session?.accumulatedMs, session?.taskId]);
  return elapsed;
}
