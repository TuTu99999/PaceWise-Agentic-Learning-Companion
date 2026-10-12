import type { ActivityRhythm, ReminderPreferences, StudyActivity, StudyPreferences } from '../types';

export const activityLabels: Record<StudyActivity, string> = {
  concept: 'Học khái niệm', practice: 'Luyện tập vận dụng', coding: 'Thực hành lập trình', review: 'Ôn tập / kiểm tra lại',
};

export const defaultStudyPreferences: StudyPreferences = { sessionMinutes: 90, breakMinutes: 10 };
export const defaultReminderPreferences: ReminderPreferences = {
  enabled: true, browserEnabled: false, pushEnabled: false, dailyCap: 3,
  studyBlockLeadMinutes: 15, digestHour: 20,
  deadlineEnabled: true, studyEnabled: true, reflectEnabled: true,
  quietHoursEnabled: false, quietStart: '22:00', quietEnd: '07:00',
};

const bounded = (value: number, min: number, max: number, fallback: number) =>
  Number.isFinite(value) ? Math.min(max, Math.max(min, Math.round(value))) : fallback;

export function normalizeStudyPreferences(value?: Partial<StudyPreferences>): StudyPreferences {
  const scopes = new Map<string, ActivityRhythm>();
  for (const item of value?.activityRhythms ?? []) {
    if (!Number.isSafeInteger(item.courseId) || item.courseId <= 0 || !Object.prototype.hasOwnProperty.call(activityLabels, item.activityType)) continue;
    scopes.set(`${item.courseId}:${item.activityType}`, { ...item,
      sessionMinutes: bounded(item.sessionMinutes, 20, 120, 90), breakMinutes: bounded(item.breakMinutes, 5, 30, 10) });
  }
  return {
    activityRhythms: [...scopes.values()].slice(0, 40),
    sessionMinutes: bounded(value?.sessionMinutes ?? 90, 20, 120, 90),
    breakMinutes: bounded(value?.breakMinutes ?? 10, 5, 30, 10),
    checkpointMinutes: bounded(value?.checkpointMinutes ?? 0, 0, 15, 0),
    adaptiveSuggestionsEnabled: value?.adaptiveSuggestionsEnabled ?? true,
  };
}

export function activityRhythm(preferences: StudyPreferences, courseId: number, activityType: StudyActivity) {
  return preferences.activityRhythms?.find((item) => item.courseId === courseId && item.activityType === activityType)
    ?? { courseId, activityType, sessionMinutes: preferences.sessionMinutes, breakMinutes: preferences.breakMinutes };
}
