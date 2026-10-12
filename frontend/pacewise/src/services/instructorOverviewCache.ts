import type { InstructorData } from './api';

const CACHE_PREFIX = 'pacewise:instructor-overview:v4'; // Invalidate first-login KPI and pre-evidence projections.
const CACHE_MAX_AGE_MS = 60 * 60 * 1000;

interface CachedInstructorOverview {
  savedAt: number;
  data: InstructorData;
}

const cacheKey = (userId: string, courseId: string) =>
  `${CACHE_PREFIX}:${userId}:${courseId}`;

function isInstructorData(value: unknown): value is InstructorData {
  if (!value || typeof value !== 'object') return false;
  const data = value as Partial<InstructorData>;
  return Array.isArray(data.classGroups)
    && !!data.groupStats
    && Array.isArray(data.reviewQueue)
    && Array.isArray(data.assessments)
    && Array.isArray(data.audit)
    && Array.isArray(data.guidance)
    && !!data.teacherWorkspace
    && Array.isArray(data.teacherWorkspace.schedule)
    && Array.isArray(data.teacherWorkspace.feedback)
    && Array.isArray(data.teacherWorkspace.courseStructure?.modules)
    && Array.isArray(data.teacherWorkspace.courseStructure?.knowledgeComponents);
}

function readCacheEntry(
  userId: string | undefined,
  courseId: string | undefined,
  now = Date.now(),
): CachedInstructorOverview | null {
  if (!userId || !courseId) return null;
  try {
    const raw = window.sessionStorage.getItem(cacheKey(userId, courseId));
    if (!raw) return null;
    const cached = JSON.parse(raw) as Partial<CachedInstructorOverview>;
    if (
      typeof cached.savedAt !== 'number'
      || now - cached.savedAt > CACHE_MAX_AGE_MS
      || !isInstructorData(cached.data)
    ) {
      window.sessionStorage.removeItem(cacheKey(userId, courseId));
      return null;
    }
    return cached as CachedInstructorOverview;
  } catch {
    return null;
  }
}

export function readInstructorOverviewCache(
  userId: string | undefined,
  courseId: string | undefined,
): InstructorData | null {
  return readCacheEntry(userId, courseId)?.data ?? null;
}

export function isInstructorOverviewCacheFresh(
  userId: string | undefined,
  courseId: string | undefined,
  maxAgeMs = 30_000,
): boolean {
  const now = Date.now();
  const cached = readCacheEntry(userId, courseId, now);
  return !!cached && now - cached.savedAt <= maxAgeMs;
}

export function writeInstructorOverviewCache(
  userId: string | undefined,
  courseId: string | undefined,
  data: InstructorData,
): void {
  if (!userId || !courseId) return;
  try {
    const cached: CachedInstructorOverview = { savedAt: Date.now(), data };
    window.sessionStorage.setItem(cacheKey(userId, courseId), JSON.stringify(cached));
  } catch {
    // A disabled/full browser storage must not break the instructor dashboard.
  }
}

export function removeInstructorOverviewCache(userId: string, courseId: string): void {
  try { window.sessionStorage.removeItem(cacheKey(userId, courseId)); }
  catch { /* Revoked access must clear in-memory UI even if storage is unavailable. */ }
}
