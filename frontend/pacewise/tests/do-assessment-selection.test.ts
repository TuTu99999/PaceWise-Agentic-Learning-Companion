import { describe, expect, it } from 'vitest';
import { assessmentMatchScore } from '../src/pages/student/StudySessionPage';

describe('Do assessment selection', () => {
  it('matches approved checkpoints to the active task topic despite Vietnamese accents', () => {
    const score = assessmentMatchScore(
      'Ôn quan hệ phản xạ và quan hệ tương đương',
      'Quan hệ hai ngôi',
      'Vì sao một quan hệ phản xạ phải chứa mọi cặp (x, x)?',
    );
    expect(score).toBeGreaterThan(0);
  });

  it('does not show an unrelated approved assessment in the current study session', () => {
    const score = assessmentMatchScore(
      'Luyện vòng lặp for trong Python',
      'Quan hệ hai ngôi',
      'Chứng minh một quan hệ là bắc cầu.',
    );
    expect(score).toBe(0);
  });
});
