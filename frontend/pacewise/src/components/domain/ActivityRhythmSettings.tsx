import { useEffect, useState } from 'react';
import { useAppStore } from '../../store/AppStore';
import type { StudyActivity } from '../../types';
import { activityLabels, activityRhythm, normalizeStudyPreferences } from '../../utils/studyPreferences';
import { Button } from '../ui/Button';

/** Explicit student choice, scoped to one course/activity; never alters a plan. */
export function ActivityRhythmSettings() {
  const { state, dispatch } = useAppStore();
  const courses = (state.courses ?? []).filter((course) => Number.isSafeInteger(Number(course.id)) && Number(course.id) > 0);
  const [selectedCourse, setSelectedCourse] = useState('');
  const courseId = Number(courses.some((course) => course.id === selectedCourse) ? selectedCourse : courses[0]?.id);
  const [activity, setActivity] = useState<StudyActivity>('concept');
  const preferences = normalizeStudyPreferences(state.studyPreferences);
  const preference = activityRhythm(preferences, courseId, activity);
  const customized = preferences.activityRhythms?.some((item) => item.courseId === courseId && item.activityType === activity);
  const [session, setSession] = useState(preference.sessionMinutes);
  const [pause, setPause] = useState(preference.breakMinutes);
  const [saved, setSaved] = useState(false);
  useEffect(() => { setSession(preference.sessionMinutes); setPause(preference.breakMinutes); },
    [courseId, activity, preference.sessionMinutes, preference.breakMinutes]);
  useEffect(() => { setSaved(false); }, [courseId, activity]);
  if (!courses.length) return null;
  return <section aria-label="Nhịp riêng theo môn và hoạt động" className="mt-4 rounded-xl border border-line p-3">
    <p className="text-sm font-semibold">Nhịp riêng theo môn và hoạt động</p>
    <div className="mt-3 grid gap-3 sm:grid-cols-2">
      <label className="flex flex-col gap-1 text-sm">Môn áp dụng
        <select className="min-w-0 rounded-lg border border-line bg-white p-2" value={String(courseId)} onChange={(event) => setSelectedCourse(event.target.value)}>
          {courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">Loại hoạt động
        <select className="rounded-lg border border-line bg-white p-2" value={activity} onChange={(event) => setActivity(event.target.value as StudyActivity)}>
          {(Object.keys(activityLabels) as StudyActivity[]).map((kind) => <option key={kind} value={kind}>{activityLabels[kind]}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">Phiên riêng (phút)
        <input className="min-w-0 rounded-lg border border-line p-2" type="number" min="20" max="120" value={session} onChange={(event) => { setSession(Number(event.target.value)); setSaved(false); }} />
      </label>
      <label className="flex flex-col gap-1 text-sm">Nghỉ riêng (phút)
        <input className="min-w-0 rounded-lg border border-line p-2" type="number" min="5" max="30" value={pause} onChange={(event) => { setPause(Number(event.target.value)); setSaved(false); }} />
      </label>
    </div>
    <div className="mt-3 flex flex-wrap gap-2">
      <Button size="sm" disabled={!Number.isInteger(session) || session < 20 || session > 120 || !Number.isInteger(pause) || pause < 5 || pause > 30} onClick={() => {
        dispatch({ type: 'UPSERT_ACTIVITY_RHYTHM', rhythm: { courseId, activityType: activity, sessionMinutes: session, breakMinutes: pause } }); setSaved(true);
      }}>Lưu nhịp riêng</Button>
      {customized && <Button size="sm" variant="secondary" onClick={() => dispatch({ type: 'REMOVE_ACTIVITY_RHYTHM', courseId, activityType: activity })}>Dùng mặc định</Button>}
    </div>
    {saved && <p role="status" className="caption mt-2">Đã lưu nhịp riêng.</p>}
  </section>;
}
