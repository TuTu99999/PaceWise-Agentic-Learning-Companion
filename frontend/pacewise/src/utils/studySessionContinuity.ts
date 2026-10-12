const continuousSessionIds = new Set<string>();
const continuousSessionVersions = new Map<string, number>();

/**
 * Marks a running timer as observed by this JavaScript document.
 *
 * The set intentionally lives only in memory: client-side route changes keep
 * it, while a reload creates a new document and therefore requires recovery.
 */
export function markContinuousStudySession(sessionId: string, version?: number) {
  continuousSessionIds.add(sessionId);
  if (version !== undefined) continuousSessionVersions.set(sessionId, version);
}

export function clearContinuousStudySession(sessionId: string) {
  continuousSessionIds.delete(sessionId);
  continuousSessionVersions.delete(sessionId);
}

export function isContinuousStudySession(sessionId: string) {
  return continuousSessionIds.has(sessionId);
}

export function continuousStudySessionVersion(sessionId: string) {
  return continuousSessionVersions.get(sessionId);
}

/** Ends document-level timer ownership, for example after a confirmed logout. */
export function clearStudySessionContinuity() {
  continuousSessionIds.clear();
  continuousSessionVersions.clear();
}

export function resetStudySessionContinuityForTests() {
  clearStudySessionContinuity();
}
