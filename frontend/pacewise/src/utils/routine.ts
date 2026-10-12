import type { AvailabilityDay, RoutineProfile, UnavailableSlot, Weekday } from '../types';

const WEEKDAYS: Weekday[] = [0, 1, 2, 3, 4, 5, 6];

const slot = (weekday: Weekday, suffix: string, start: string, end: string): UnavailableSlot => ({
  id: `routine-sleep-${weekday}-${suffix}`,
  label: 'Giờ ngủ',
  weekday,
  start,
  end,
  source: 'routine',
  category: 'sleep',
  readOnly: true,
});

/** Build recurring sleep constraints without assuming everyone follows a daytime routine. */
export function routineSleepSlots(profile: RoutineProfile | null): UnavailableSlot[] {
  if (!profile || profile.sleepTime === profile.wakeTime) return [];
  return WEEKDAYS.flatMap((weekday) => {
    if (profile.sleepTime < profile.wakeTime) {
      return [slot(weekday, 'overnight', profile.sleepTime, profile.wakeTime)];
    }
    return [
      ...(profile.sleepTime < '24:00' ? [slot(weekday, 'late', profile.sleepTime, '24:00')] : []),
      ...(profile.wakeTime > '00:00' ? [slot(weekday, 'early', '00:00', profile.wakeTime)] : []),
    ];
  });
}

/** Routine mode exposes the whole day; sleep and personal events carve out unavailable time. */
export function routineAvailability(profile: RoutineProfile | null, fallback: AvailabilityDay[]): AvailabilityDay[] {
  if (!profile) return fallback;
  return WEEKDAYS.map((weekday) => ({ weekday, enabled: true, start: '00:00', end: '24:00' }));
}
