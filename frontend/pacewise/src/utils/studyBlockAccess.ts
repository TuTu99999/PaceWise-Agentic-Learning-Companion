import type { TimeBlock } from '../types';

export type StudyBlockAccess =
  | { state: 'available'; startsAt: number; endsAt: number }
  | { state: 'ended'; startsAt: number; endsAt: number };

const inVietnam = (date: string, clock: string) => new Date(`${date}T${clock}:00+07:00`).getTime();

/** Demo flow: confirmed blocks can be opened early, but completed time windows stay historical. */
export function studyBlockAccess(block: Pick<TimeBlock, 'date' | 'start' | 'end'>, now = Date.now()): StudyBlockAccess {
  const startsAt = inVietnam(block.date, block.start);
  const endsAt = inVietnam(block.date, block.end);

  if (now >= endsAt) return { state: 'ended', startsAt, endsAt };
  return { state: 'available', startsAt, endsAt };
}
