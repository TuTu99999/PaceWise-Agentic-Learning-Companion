/** Re-plan is a Plan hand-off, not a separate learner recovery workflow. */
export function replanHref(trigger: 'lms' | 'progress' | 'deadline' | 'reflection' | 'preferences',
  context: { impactId?: string; taskId?: string; courseId?: string; scope?: 'activity' | 'weekly' } = {}): string {
  const params = new URLSearchParams({ reanalyze: trigger });
  for (const [key, value] of Object.entries(context)) if (value) params.set(key, value);
  return `/plan?${params}`;
}
