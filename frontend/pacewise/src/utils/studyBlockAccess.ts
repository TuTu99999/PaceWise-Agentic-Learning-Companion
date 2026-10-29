import type { TimeBlock } from '../types';

export type StudyBlockAccess =
  | { state: 'available'; startsAt: number; endsAt: number }
  | { state: 'waiting_prerequisite'; startsAt: number; endsAt: number; availableAt: number }
  | { state: 'ended'; startsAt: number; endsAt: number };

const inVietnam = (date: string, clock: string) => new Date(`${date}T${clock}:00+07:00`).getTime();

/** Demo flow: confirmed blocks can be opened early, but completed time windows stay historical. */
export function studyBlockAccess(block: Pick<TimeBlock, 'date' | 'start' | 'end' | 'earliestStartAt'>, now = Date.now()): StudyBlockAccess {
  const startsAt = inVietnam(block.date, block.start);
  const endsAt = inVietnam(block.date, block.end);
  const availableAt = block.earliestStartAt ? new Date(block.earliestStartAt).getTime() : Number.NaN;

  if (now >= endsAt) return { state: 'ended', startsAt, endsAt };
  if (Number.isFinite(availableAt) && now < availableAt) {
    return { state: 'waiting_prerequisite', startsAt, endsAt, availableAt };
  }
  return { state: 'available', startsAt, endsAt };
}
