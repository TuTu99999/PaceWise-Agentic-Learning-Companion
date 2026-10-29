import type { InstructorDashboard } from '../types';
import type { ManagedCourse } from '../types/teacherManagement';

const MAX_AGE_MS = 60 * 60 * 1000;
const FRESH_MS = 30_000;
const memory = new Map<string, Entry<unknown>>();

interface Entry<T> {
  savedAt: number;
  revision: number;
  data: T;
}

function read<T>(key: string): Entry<T> | null {
  const value = memory.get(key) as Entry<T> | undefined;
  if (!value) return null;
  if (Date.now() - value.savedAt > MAX_AGE_MS) {
    memory.delete(key);
    return null;
  }
  return value;
}

function write<T>(key: string, revision: number, data: T) {
  // Keep instructor/student-identifying dashboard data in memory only. It is
  // discarded on reload and never persisted in browser storage.
  memory.set(key, { savedAt: Date.now(), revision, data });
}

const dashboardKey = (userId: string, courseId: string) => `pacewise:instructor-dashboard:v1:${userId}:${courseId}`;
const coursesKey = (userId: string) => `pacewise:instructor-courses:v1:${userId}`;

export const readInstructorDashboardCache = (userId?: string, courseId?: string) =>
  userId && courseId ? read<InstructorDashboard>(dashboardKey(userId, courseId)) : null;

export const writeInstructorDashboardCache = (
  userId: string,
  courseId: string,
  revision: number,
  data: InstructorDashboard,
) => write(dashboardKey(userId, courseId), revision, data);

export const readManagedCoursesCache = (userId?: string) =>
  userId ? read<ManagedCourse[]>(coursesKey(userId)) : null;

export const writeManagedCoursesCache = (userId: string, revision: number, data: ManagedCourse[]) =>
  write(coursesKey(userId), revision, data);

export const isFresh = <T>(entry: Entry<T> | null, revision: number) =>
  !!entry && entry.revision === revision && Date.now() - entry.savedAt <= FRESH_MS;

export const clearInstructorPageCache = () => memory.clear();
