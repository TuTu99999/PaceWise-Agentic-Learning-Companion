import { describe, expect, it } from 'vitest';
import { initialState, reducer } from '../store/AppStore';
import { normalizeStudyPreferences } from './studyPreferences';

describe('Study preferences persistence', () => {
  it('migrates old reminder preferences with new defaults', () => {
    const legacy = { preferences: { enabled: true, browserEnabled: false, dailyCap: 2, studyBlockLeadMinutes: 10, digestHour: 20 }, deliveredAt: {}, readIds: [] };
    const result = reducer(initialState, { type: 'HYDRATE_WORKSPACE', state: { reminders: legacy } });
    expect(result.reminders.preferences.dailyCap).toBe(2);
    expect(result.reminders.preferences.reflectEnabled).toBe(true);
    expect(result.studyPreferences).toEqual({ activityRhythms: [], sessionMinutes: 90, breakMinutes: 10, checkpointMinutes: 0, adaptiveSuggestionsEnabled: true });
  });
  it('does not mutate the confirmed plan when editing rhythm', () => {
    const plan = { id: 'plan-1', weekStart: '2026-10-12', version: 1, savedAt: '2026-10-15T00:00:00Z',
      blocks: [{ id: 'b1', taskId: 't1', date: '2026-10-15', start: '15:00', end: '16:00' }] };
    const next = reducer({ ...initialState, plan }, { type: 'UPDATE_STUDY_PREFERENCES', patch: { sessionMinutes: 25, breakMinutes: 5 } });
    expect(next.plan).toBe(plan);
    expect(next.calendarDraft).toMatchObject({ blocks: plan.blocks, needsAnalysis: true });
    expect(next.studyPreferences).toEqual({ activityRhythms: [], sessionMinutes: 25, breakMinutes: 5, checkpointMinutes: 0, adaptiveSuggestionsEnabled: true });
    expect(normalizeStudyPreferences({ sessionMinutes: Infinity, breakMinutes: -10 })).toEqual({ activityRhythms: [], sessionMinutes: 90, breakMinutes: 5, checkpointMinutes: 0, adaptiveSuggestionsEnabled: true });
  });
  it('upserts one course/activity without changing defaults, other rhythms or plan', () => {
    const coding = { courseId: 1, activityType: 'coding' as const, sessionMinutes: 75, breakMinutes: 10 };
    const other = { courseId: 2, activityType: 'concept' as const, sessionMinutes: 60, breakMinutes: 5 };
    let next = reducer(initialState, { type: 'UPSERT_ACTIVITY_RHYTHM', rhythm: coding });
    next = reducer(next, { type: 'UPSERT_ACTIVITY_RHYTHM', rhythm: other });
    next = reducer(next, { type: 'UPSERT_ACTIVITY_RHYTHM', rhythm: { ...coding, sessionMinutes: 45 } });
    expect(next.studyPreferences.sessionMinutes).toBe(90);
    expect(next.studyPreferences.activityRhythms).toEqual([other, { ...coding, sessionMinutes: 45 }]);
    expect(next.plan).toBe(initialState.plan);
    const restored = reducer(initialState, { type: 'HYDRATE_WORKSPACE', state: { studyPreferences: next.studyPreferences } });
    expect(restored.studyPreferences).toEqual(next.studyPreferences);
    expect(reducer(next, { type: 'REMOVE_ACTIVITY_RHYTHM', courseId: 1, activityType: 'coding' }).studyPreferences.activityRhythms).toEqual([other]);
  });
});
