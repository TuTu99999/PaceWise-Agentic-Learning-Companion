import { useMemo } from 'react';
import { useAppStore } from '../store/AppStore';
import { detectDrift, nextAction, weekStats } from '../utils/progress';
import type { Course, Plan, StudySession, Task } from '../types';
import { lmsUnavailableSlots, mergeUnavailable } from '../utils/lmsPlanning';

export function buildCourseScope(
  activeCourseId: string | undefined,
  tasks: Task[],
  sessions: StudySession[],
  plan: Plan | null,
) {
  const activeTasks = activeCourseId
    ? tasks.filter((task) => task.courseId === activeCourseId)
    : tasks;
  const activeTaskIds = new Set(activeTasks.map((task) => task.id));
  return {
    activeTasks,
    activeSessions: sessions.filter((session) => activeTaskIds.has(session.taskId)),
    activePlan: plan
      ? { ...plan, blocks: plan.blocks.filter((block) => activeTaskIds.has(block.taskId)) }
      : null,
  };
}

/** Derived, read-only view of the store used by many pages. */
export function useDerived() {
  const { state } = useAppStore();
  return useMemo(() => {
    const taskById = new Map<string, Task>(state.tasks.map((t) => [t.id, t]));
    const courseById = new Map<string, Course>(state.courses.map((c) => [c.id, c]));
    const unavailable = mergeUnavailable(state.unavailable, lmsUnavailableSlots(state.courseData));
    const drifts = detectDrift(state.plan, state.tasks, state.availability, unavailable).filter((d) => !state.dismissedDrifts.includes(d.taskId));
    const activeCourseId = state.user?.courseId;
    const { activeTasks, activeSessions, activePlan } = buildCourseScope(
      activeCourseId,
      state.tasks,
      state.sessions,
      state.plan,
    );
    const activeDrifts = detectDrift(activePlan, activeTasks, state.availability, unavailable)
      .filter((drift) => !state.dismissedDrifts.includes(drift.taskId));
    const scopeCourseId = state.courseScope === 'all' ? undefined : state.courseScope;
    const scoped = buildCourseScope(scopeCourseId, state.tasks, state.sessions, state.plan);
    const scopedDrifts = detectDrift(scoped.activePlan, scoped.activeTasks, state.availability, unavailable)
      .filter((drift) => !state.dismissedDrifts.includes(drift.taskId));
    return {
      taskById,
      courseById,
      unavailable,
      courseOf: (taskId: string) => courseById.get(taskById.get(taskId)?.courseId ?? ''),
      drifts,
      next: nextAction(state.plan, state.tasks, drifts),
      stats: weekStats(state.tasks, state.sessions, state.plan, state.plan?.weekStart),
      activeCourse: activeCourseId ? courseById.get(activeCourseId) : undefined,
      activeTasks,
      activeSessions,
      activePlan,
      activeDrifts,
      activeNext: nextAction(activePlan, activeTasks, activeDrifts),
      activeStats: weekStats(activeTasks, activeSessions, activePlan, activePlan?.weekStart),
      scopeCourse: scopeCourseId ? courseById.get(scopeCourseId) : undefined,
      scopeLabel: scopeCourseId ? courseById.get(scopeCourseId)?.code ?? 'môn đã chọn' : 'tất cả môn',
      scopedTasks: scoped.activeTasks,
      scopedSessions: scoped.activeSessions,
      scopedPlan: scoped.activePlan,
      scopedDrifts,
      scopedNext: nextAction(scoped.activePlan, scoped.activeTasks, scopedDrifts),
      scopedStats: weekStats(scoped.activeTasks, scoped.activeSessions, scoped.activePlan, scoped.activePlan?.weekStart),
    };
  }, [state.tasks, state.courses, state.courseData, state.plan, state.sessions, state.availability, state.unavailable, state.dismissedDrifts, state.user?.courseId, state.courseScope]);
}
