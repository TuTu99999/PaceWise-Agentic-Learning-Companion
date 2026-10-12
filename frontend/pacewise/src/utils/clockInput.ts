const CLOCK_TEXT = /^(\d{1,2})(?::|h|\.)(\d{1,2})$/i;

/** Parse a locale-independent 24-hour clock typed by the learner. */
export function normalizeClockInput(value: string): string | null {
  const match = CLOCK_TEXT.exec(value.trim().replace(/\s+/g, ''));
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour > 23 || minute > 59) return null;
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}
