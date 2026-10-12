import { describe, expect, it } from 'vitest';
import { normalizeClockInput } from './clockInput';

describe('clock input', () => {
  it.each([
    ['23:10', '23:10'],
    ['23h3', '23:03'],
    ['7.05', '07:05'],
    ['00:00', '00:00'],
  ])('normalizes %s to %s', (input, expected) => {
    expect(normalizeClockInput(input)).toBe(expected);
  });

  it.each(['25:00', '23:60', '11', 'abc', ''])('rejects invalid clock %s', (input) => {
    expect(normalizeClockInput(input)).toBeNull();
  });
});
