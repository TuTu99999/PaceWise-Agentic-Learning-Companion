import { describe, expect, it } from 'vitest';
import { studyBlockAccess } from './studyBlockAccess';

const block = { date: '2026-10-04', start: '19:00', end: '20:00' };
const at = (clock: string) => new Date(`2026-10-04T${clock}:00+07:00`).getTime();

describe('studyBlockAccess', () => {
  it('allows a confirmed block to open before its planned start for demos', () => {
    expect(studyBlockAccess(block, at('08:00')).state).toBe('available');
    expect(studyBlockAccess(block, at('18:54')).state).toBe('available');
  });

  it('keeps access during the block and closes it when the block ends', () => {
    expect(studyBlockAccess(block, at('19:30')).state).toBe('available');
    expect(studyBlockAccess(block, at('20:00')).state).toBe('ended');
  });
});
