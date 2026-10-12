import { useEffect, useState } from 'react';
import { APP_TIMEZONE } from '../utils/time';

/** Calendar highlighting follows real local time, independently of the demo plan clock. */
export function calendarToday(now = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: APP_TIMEZONE,
    year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const part = (name: string) => parts.find((entry) => entry.type === name)!.value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

export function useCalendarToday(): string {
  const [today, setToday] = useState(calendarToday);
  useEffect(() => {
    const refresh = () => setToday(calendarToday());
    const timer = window.setInterval(refresh, 60_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, []);
  return today;
}

/** Planning must use actual time, including deadlines earlier on the same day. */
export function useCalendarNow(): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const refresh = () => setNow(Date.now());
    const timer = window.setInterval(refresh, 60_000);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, []);
  return now;
}
