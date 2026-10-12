import { describe, expect, it } from 'vitest';
import { routineAvailability, routineSleepSlots } from './routine';

describe('routine constraints', () => {
  it('supports a learner who sleeps after midnight', () => {
    const slots = routineSleepSlots({ wakeTime: '10:00', sleepTime: '02:00', preferred: ['late_night'] });
    expect(slots).toHaveLength(7);
    expect(slots[0]).toMatchObject({ start: '02:00', end: '10:00', category: 'sleep' });
  });

  it('treats 00:00 as midnight and blocks only midnight through wake-up', () => {
    const slots = routineSleepSlots({ wakeTime: '07:00', sleepTime: '00:00', preferred: ['morning'] });
    expect(slots).toHaveLength(7);
    expect(slots[0]).toMatchObject({ start: '00:00', end: '07:00', category: 'sleep' });
  });

  it('splits a conventional sleep window around midnight', () => {
    const slots = routineSleepSlots({ wakeTime: '07:00', sleepTime: '23:00', preferred: ['morning'] });
    expect(slots).toHaveLength(14);
    expect(slots.slice(0, 2).map((item) => [item.start, item.end])).toEqual([['23:00', '24:00'], ['00:00', '07:00']]);
  });

  it('opens a full-day availability envelope when routine mode is enabled', () => {
    const result = routineAvailability({ wakeTime: '07:00', sleepTime: '23:00', preferred: ['evening'] }, []);
    expect(result).toHaveLength(7);
    expect(result[0]).toMatchObject({ enabled: true, start: '00:00', end: '24:00' });
  });
});
