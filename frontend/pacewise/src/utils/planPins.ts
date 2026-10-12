import type { TimeBlock } from '../types';
import { DEMO_NOW, DEMO_TODAY, toMin } from './time';

/** Keep learner intent and elapsed history without freezing an older AI draft. */
export function pinnedBlocksForReanalysis(
  blocks: TimeBlock[],
  today = DEMO_TODAY,
  now = DEMO_NOW,
): TimeBlock[] {
  const nowMinute = toMin(now);
  return blocks.filter((block) => (
    block.placementSource === 'student'
    || block.status === 'history'
    || block.date < today
    || (block.date === today && toMin(block.start) <= nowMinute)
  ));
}
