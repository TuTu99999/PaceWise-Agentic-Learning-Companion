import { useEffect, useRef, useState } from 'react';
import { deleteTeacherResource, fetchTeacherManagement, syncCanvas, writeTeacherManagement, ApiError } from '../services/api';
import { useAppStore } from '../store/AppStore';
import { useInstructorData } from './useInstructorData';
import type { TeacherManagementData } from '../types/teacherManagement';

export function useTeacherManagement(courseId?: string) {
  const { state, dispatch } = useAppStore();
  const { authoringCache } = useInstructorData();
  const scope = `${state.user?.id}:${courseId}`;
  const current = useRef(scope); current.current = scope;
  const generation = useRef(0);
  const [snapshot, setSnapshot] = useState<{ scope: string; data?: TeacherManagementData }>(() => ({ scope, data: authoringCache.get(scope)?.data }));
  const [loading, setLoading] = useState(!snapshot.data);
  const [error, setError] = useState('');
  const data = snapshot.scope === scope ? snapshot.data : authoringCache.get(scope)?.data;

  const reload = async (force = true) => {
    if (!courseId) return;
    const startedGeneration = generation.current;
    const saved = authoringCache.get(scope);
    if (!force && saved && saved.revision === state.lmsRevision && Date.now() - saved.savedAt < 30000) {
      setSnapshot({ scope, data: saved.data }); setLoading(false); return;
    }
    setLoading(!saved); setError('');
    try {
      const fresh = await fetchTeacherManagement(courseId);
      if (current.current !== scope || generation.current !== startedGeneration) return;
      authoringCache.set(scope, { savedAt: Date.now(), revision: state.lmsRevision, data: fresh });
      setSnapshot({ scope, data: fresh });
    } catch (reason) {
      if (current.current === scope && generation.current === startedGeneration) {
        if (reason instanceof ApiError && ['FORBIDDEN', 'UNAUTHENTICATED'].includes(reason.code)) {
          authoringCache.delete(scope); setSnapshot({ scope });
        }
        setError(reason instanceof Error ? reason.message : 'Không tải được dữ liệu.');
      }
    } finally { if (current.current === scope && generation.current === startedGeneration) setLoading(false); }
  };
  useEffect(() => { current.current = scope; generation.current++; void reload(false); return () => { current.current = ''; generation.current++; }; }, [scope, state.lmsRevision]);

  const refreshAfterMutation = async () => {
    authoringCache.delete(scope);
    if (current.current !== scope) return;
    await reload();
    dispatch({ type: 'LMS_EVENT_RECEIVED' });
    void syncCanvas().then((result) => {
      if (current.current !== scope) return;
      dispatch({ type: 'SYNC_CANVAS', courses: result.courses, tasks: result.tasks, courseData: result.courseData,
        assessments: result.assessments, guidance: result.guidance });
    }).catch(() => dispatch({ type: 'UPDATE_SETTINGS', patch: { staleData: true } }));
  };
  const mutate = async (target: string, payload: object, method: 'POST' | 'PUT' = 'POST') => {
    if (!courseId) throw new Error('Chọn môn học trước.');
    await writeTeacherManagement(courseId, target, payload, method);
    await refreshAfterMutation();
  };
  const removeResource = async (resourceId: number) => {
    if (!courseId) throw new Error('Chọn môn học trước.');
    await deleteTeacherResource(courseId, resourceId);
    await refreshAfterMutation();
  };
  return { data, loading, error, reload, mutate, removeResource, refreshAfterMutation };
}
