import type { TimeBlock } from '../types';
import { DEMO_NOW, DEMO_TODAY } from './time';

/** Keep learner intent and proven history without freezing an older AI draft. */
export function pinnedBlocksForReanalysis(
  blocks: TimeBlock[],
  today = DEMO_TODAY,
  now = DEMO_NOW,
): TimeBlock[] {
  void today;
  void now;
  return blocks.filter((block) => (
    block.placementSource === 'student'
    || block.status === 'history'
  ));
}
