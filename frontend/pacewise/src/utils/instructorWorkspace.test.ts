import { describe, expect, it } from 'vitest';
import type { TeachingEvent } from '../types';
import { durationMinutes, emptyTeachingEvent, teachingEventError } from './instructorWorkspace';

const event = (patch: Partial<TeachingEvent> = {}): TeachingEvent => ({
  id: 'event-1',
  title: 'Quan hệ tương đương',
  type: 'offline',
  startAt: '2026-10-08T01:00:00.000Z',
  endAt: '2026-10-08T02:30:00.000Z',
  location: 'A203',
  meetingUrl: '',
  moduleId: 'module-3',
  knowledgeComponentIds: ['kc-equivalence'],
  preparation: '',
  recurrence: 'none',
  status: 'scheduled',
  source: 'pacewise',
  ...patch,
});

describe('instructor workspace schedule utilities', () => {
  it('calculates exact duration and accepts a valid offline event', () => {
    expect(durationMinutes(event())).toBe(90);
    expect(teachingEventError(event())).toBeNull();
  });

  it('rejects invalid ranges and online classes without a URL', () => {
    expect(teachingEventError(event({ endAt: '2026-10-08T00:30:00.000Z' }))).toMatch(/kết thúc/i);
    expect(teachingEventError(event({ type: 'online', location: '' }))).toMatch(/đường dẫn/i);
  });

  it('creates an editable PaceWise-owned event with a positive duration', () => {
    const created = emptyTeachingEvent('new-id');
    expect(created.source).toBe('pacewise');
    expect(created.status).toBe('scheduled');
    expect(durationMinutes(created)).toBe(90);
  });
});
