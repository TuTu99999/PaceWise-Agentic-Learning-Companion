import { describe, expect, it } from 'vitest';
import type { TimeBlock } from '../types';
import { pinnedBlocksForReanalysis } from './planPins';

const block = (id: string, date: string, placementSource?: TimeBlock['placementSource']): TimeBlock => ({
  id,
  taskId: 'task-1',
  date,
  start: '18:00',
  end: '19:00',
  placementSource,
});

describe('pinnedBlocksForReanalysis', () => {
  it('releases future AI blocks but keeps the learner choice', () => {
    const result = pinnedBlocksForReanalysis([
      block('old-ai-monday', '2026-10-05', 'agent'),
      block('student-choice', '2026-10-10', 'student'),
    ], '2026-10-05', '12:00');

    expect(result.map((item) => item.id)).toEqual(['student-choice']);
  });

  it('releases elapsed AI blocks when there is no completion evidence', () => {
    const result = pinnedBlocksForReanalysis([
      block('past-day', '2026-10-04', 'agent'),
      { ...block('past-today', '2026-10-05', 'agent'), start: '10:00', end: '11:00' },
      { ...block('future-today', '2026-10-05', 'agent'), start: '13:00', end: '14:00' },
    ], '2026-10-05', '12:00');

    expect(result).toEqual([]);
  });

  it('does not infer that a current block was started from wall-clock time', () => {
    const current = { ...block('current', '2026-10-05', 'agent'), start: '11:30', end: '12:30' };
    expect(pinnedBlocksForReanalysis([current], '2026-10-05', '12:00')).toEqual([]);
  });
});
