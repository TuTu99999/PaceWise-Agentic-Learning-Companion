import { createContext, createElement, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, fetchInstructorData, type InstructorData, type LmsFileIndexStatus } from '../services/api';
import {
  isInstructorOverviewCacheFresh,
  readInstructorOverviewCache,
  removeInstructorOverviewCache,
  writeInstructorOverviewCache,
} from '../services/instructorOverviewCache';
import { useAppStore } from '../store/AppStore';
import type { TeacherManagementData, TeacherProfileData } from '../types/teacherManagement';

const inFlight = new Map<string, Promise<InstructorData>>();

const hasActiveCourse = (courseId: string | undefined): courseId is string => Boolean(courseId && courseId !== '0');

function requestInstructorData(key: string) {
  const current = inFlight.get(key);
  if (current) return current;
  const request = fetchInstructorData().finally(() => inFlight.delete(key));
  inFlight.set(key, request);
  return request;
}

/** One controller per authenticated instructor layout, not per routed page. */
function useInstructorDataController() {
  const { state, dispatch } = useAppStore();
  const hasData = state.classGroups?.length > 0;
  const [loading, setLoading] = useState(hasActiveCourse(state.user?.courseId) && !hasData);
  const [error, setError] = useState<ApiError | null>(null);
  const observed = useRef<{ scope: string; revision: number } | null>(null);
  const scope = `${state.user?.id}:${state.user?.courseId}`;
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const generation = useRef(0);
  // Private to this mounted authenticated layout; discarded on logout.
  const materialCache = useRef(new Map<string, { savedAt: number; files: LmsFileIndexStatus[] }>());
  const authoringCache = useRef(new Map<string, { savedAt: number; revision: number; data: TeacherManagementData }>());
  const profileCache = useRef<{ savedAt: number; data: TeacherProfileData } | null>(null);

  const recordError = (reason: unknown, userId: string, courseId: string) => {
    const failure = reason instanceof ApiError ? reason : new ApiError('UNKNOWN', 'Không thể tải dữ liệu giảng viên.');
    if (failure.code === 'FORBIDDEN' || failure.code === 'UNAUTHENTICATED') {
      materialCache.current.clear();
      authoringCache.current.clear();
      profileCache.current = null;
      loadedScope.current = null;
      removeInstructorOverviewCache(userId, courseId);
      dispatch({ type: 'SET_INSTRUCTOR_DATA', classGroups: [], groupStats: {}, reviewQueue: [], assessments: [],
        audit: [], guidance: [], lmsSummary: null, teacherWorkspace: { schedule: [], feedback: [],
          courseStructure: { modules: [], knowledgeComponents: [] }, settings: {
            minimumGroupSize: 5, allowIndividualReview: false, requireStudentConsent: true, autoPublishApprovedResources: false,
          } } });
    }
    setError(failure);
  };

  const [refreshing, setRefreshing] = useState(false);
  const loadedScope = useRef<string | null>(hasData ? scope : null);

  const refresh = async () => {
    const userId = state.user?.id;
    const courseId = state.user?.courseId;
    if (!userId || !hasActiveCourse(courseId)) {
      setLoading(false);
      setRefreshing(false);
      setError(null);
      return;
    }
    const startedGeneration = generation.current;
    setLoading(loadedScope.current !== scope);
    setRefreshing(true);
    setError(null);
    try {
      const data = await requestInstructorData(`${scope}:${state.lmsRevision}`);
      if (currentScope.current !== scope || generation.current !== startedGeneration) return;
      writeInstructorOverviewCache(userId, courseId, data);
      dispatch({ type: 'SET_INSTRUCTOR_DATA', ...data });
      loadedScope.current = scope;
    } catch (reason) {
      if (currentScope.current === scope && generation.current === startedGeneration) {
        recordError(reason, userId, courseId);
      }
    } finally {
      if (currentScope.current === scope && generation.current === startedGeneration) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    let active = true;
    generation.current += 1;
    const userId = state.user?.id;
    const courseId = state.user?.courseId;
    if (!userId || !hasActiveCourse(courseId)) {
      materialCache.current.clear();
      authoringCache.current.clear();
      loadedScope.current = null;
      setLoading(false);
      setRefreshing(false);
      setError(null);
      dispatch({ type: 'SET_INSTRUCTOR_DATA', classGroups: [], groupStats: {}, reviewQueue: [], assessments: [],
        audit: [], guidance: [], lmsSummary: null, teacherWorkspace: { schedule: [], feedback: [],
          courseStructure: { modules: [], knowledgeComponents: [] }, settings: {
            minimumGroupSize: 5, allowIndividualReview: false, requireStudentConsent: true, autoPublishApprovedResources: false,
          } } });
      return () => { active = false; generation.current += 1; };
    }

    const cached = readInstructorOverviewCache(userId, courseId);
    const cacheIsFresh = isInstructorOverviewCacheFresh(userId, courseId);
    const revisionChanged = observed.current?.scope === scope && observed.current.revision !== state.lmsRevision;
    observed.current = { scope, revision: state.lmsRevision };
    setError(null);
    setRefreshing(false);
    if (cached) {
      if (loadedScope.current !== scope) dispatch({ type: 'SET_INSTRUCTOR_DATA', ...cached });
      setLoading(false);
      loadedScope.current = scope;
      if (cacheIsFresh && !revisionChanged) return () => { active = false; generation.current += 1; };
    } else {
      setLoading(loadedScope.current !== scope);
    }

    const key = `${userId}:${courseId}:${state.lmsRevision}`;
    setRefreshing(true);
    void requestInstructorData(key)
      .then((data) => {
        if (!active) return;
        writeInstructorOverviewCache(userId, courseId, data);
        dispatch({ type: 'SET_INSTRUCTOR_DATA', ...data });
        loadedScope.current = scope;
        setError(null);
      })
      .catch((reason) => {
        if (!active) return;
        recordError(reason, userId, courseId);
      })
      .finally(() => { if (active) { setLoading(false); setRefreshing(false); } });

    return () => { active = false; generation.current += 1; };
  }, [dispatch, state.lmsRevision, state.user?.courseId, state.user?.id]);

  useEffect(() => {
    if (!state.user?.id || !hasActiveCourse(state.user.courseId)) return;
    const revalidate = () => {
      if (!document.hidden && !isInstructorOverviewCacheFresh(state.user?.id, state.user?.courseId)) void refresh();
    };
    const timer = window.setInterval(revalidate, 60_000);
    document.addEventListener('visibilitychange', revalidate);
    window.addEventListener('online', revalidate);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', revalidate);
      window.removeEventListener('online', revalidate);
    };
  }, [state.user?.id, state.user?.courseId, state.lmsRevision]);

  return { loading, refreshing, error, refresh, materialCache: materialCache.current, authoringCache: authoringCache.current, profileCache };
}

const InstructorDataContext = createContext<ReturnType<typeof useInstructorDataController> | null>(null);

export function InstructorDataProvider({ children }: { children: ReactNode }) {
  const value = useInstructorDataController();
  return createElement(InstructorDataContext.Provider, { value }, children);
}

/** Consumers never start a second request or replay an older cache snapshot. */
export function useInstructorData() {
  const value = useContext(InstructorDataContext);
  if (!value) throw new Error('useInstructorData requires InstructorDataProvider');
  return value;
}

export function useInstructorMaterialCache() {
  return useContext(InstructorDataContext)?.materialCache;
}
