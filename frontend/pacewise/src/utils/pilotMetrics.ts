import type { AvailabilityDay, EstimateProfile, PilotMetrics, Plan, StudySession, Task, UnavailableSlot } from '../types';
import { detectDrift } from './progress';
import { TASK_SELECTION_HORIZON_DAYS, daysUntil } from './time';

export function updateEstimateProfiles(
  profiles: Record<string, EstimateProfile>,
  previousTasks: Task[],
  currentTasks: Task[],
): Record<string, EstimateProfile> {
  const previous = new Map(previousTasks.map((task) => [task.id, task]));
  const next = { ...profiles };
  currentTasks.forEach((task) => {
    const old = previous.get(task.id);
    if (!old || old.status === 'done' || task.status !== 'done' || old.loggedMin <= 0 || old.estimateMin <= 0) return;
    const ratio = Math.min(3, Math.max(0.5, old.loggedMin / old.estimateMin));
    const profile = next[task.courseId];
    const multiplier = profile ? profile.multiplier * 0.7 + ratio * 0.3 : ratio;
    next[task.courseId] = { courseId: task.courseId, sampleCount: (profile?.sampleCount ?? 0) + 1, multiplier: Math.round(multiplier * 100) / 100, updatedAt: new Date().toISOString() };
  });
  return next;
}

export function adaptiveEstimate(task: Task, profiles: Record<string, EstimateProfile>) {
  if (!task.estimateIsAssumption) return task.estimateMin;
  return Math.max(30, Math.round(task.estimateMin * (profiles[task.courseId]?.multiplier ?? 1) / 15) * 15);
}

export function calculatePilotMetrics(
  tasks: Task[],
  plan: Plan | null,
  sessions: StudySession[],
  recoveryCount: number,
  availability: AvailabilityDay[] = [],
  unavailable: UnavailableSlot[] = [],
): PilotMetrics {
  const plannedIds = new Set(plan?.blocks.map((block) => block.taskId) ?? []);
  const horizonTasks = tasks.filter((task) => {
    const distance = daysUntil(task.deadline);
    return distance >= 0 && distance < TASK_SELECTION_HORIZON_DAYS;
  });
  const open = horizonTasks.filter((task) => task.status !== 'done');
  const graded = tasks.filter((task) => task.submission?.score !== null && task.submission?.score !== undefined);
  const submitted = tasks.filter((task) => {
    const state = task.submission?.state.toLowerCase();
    return Boolean(task.submission?.submittedAt || task.submission?.attempts || state === 'submitted' || state === 'graded');
  });
  const onTime = submitted.filter((task) => !task.submission?.late);
  const sessionMinutes = new Map<string, number>();
  sessions.forEach((session) => sessionMinutes.set(session.taskId, (sessionMinutes.get(session.taskId) ?? 0) + session.minutes));
  const errors = tasks.flatMap((task) => {
    const actual = sessionMinutes.get(task.id);
    return actual && task.estimateMin > 0 ? [Math.abs(actual - task.estimateMin) / task.estimateMin] : [];
  });
  return {
    measuredAt: new Date().toISOString(),
    openDeadlineCount: open.length,
    plannedDeadlineCount: open.filter((task) => plannedIds.has(task.id)).length,
    atRiskDeadlineCount: detectDrift(plan, horizonTasks, availability, unavailable).length,
    onTimeSubmissionCount: onTime.length,
    gradedSubmissionCount: graded.length,
    submittedAssignmentCount: submitted.length,
    planCoverageRate: open.length ? open.filter((task) => plannedIds.has(task.id)).length / open.length : 1,
    onTimeSubmissionRate: submitted.length ? onTime.length / submitted.length : null,
    estimateMaePercent: errors.length ? errors.reduce((sum, value) => sum + value, 0) / errors.length : null,
    recoveryCount,
  };
}
