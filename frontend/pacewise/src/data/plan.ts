import type { AvailabilityDay, UnavailableSlot } from '../types';

export const defaultAvailability: AvailabilityDay[] = [
  { weekday: 0, enabled: false, start: '18:00', end: '20:00' },
  { weekday: 1, enabled: false, start: '18:00', end: '20:00' },
  { weekday: 2, enabled: false, start: '18:00', end: '20:00' },
  { weekday: 3, enabled: false, start: '18:00', end: '20:00' },
  { weekday: 4, enabled: false, start: '18:00', end: '20:00' },
  { weekday: 5, enabled: false, start: '09:00', end: '11:00' },
  { weekday: 6, enabled: false, start: '09:00', end: '11:00' },
];

export const defaultUnavailable: UnavailableSlot[] = [];
