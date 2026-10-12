import { useEffect, useState } from 'react';
import { prepareDoSession } from '../services/api';
import type { DoSessionPreparation, LMSCourseData } from '../types';

// No completed-result cache: revisiting a session must revalidate live LMS rights.
const pending = new Map<string, { controller: AbortController; promise: Promise<DoSessionPreparation>; users: number }>();

export function materialRevision(data?: LMSCourseData): string {
  if (!data) return 'unknown';
  // Sync may replace object identities or progress counters without changing sources.
  return JSON.stringify({
    modules: data.modules.map(module => ({ id: module.id, name: module.name, published: module.published,
      items: module.items })).sort((a, b) => a.id - b.id),
    files: data.resources.map(file => ({ id: file.id, title: file.title, kind: file.kind,
      url: file.source_url, version: file.latest_version, access: file.access_scope })).sort((a, b) => a.id - b.id),
  });
}

export function useDoPreparation(userId: string | undefined, courseId: string | undefined,
  blockId: string | undefined, revision: string, enabled: boolean) {
  const [snapshot, setSnapshot] = useState<{ owner: string; data: DoSessionPreparation } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const owner = JSON.stringify([userId, courseId, blockId]);
  useEffect(() => {
    if (!enabled || !userId || !courseId || !blockId) { setLoading(false); return; }
    let active = true;
    const key = JSON.stringify([userId, courseId, blockId, revision, attempt]);
    let entry = pending.get(key);
    if (!entry || entry.controller.signal.aborted) {
      const controller = new AbortController();
      entry = { controller, users: 0, promise: prepareDoSession({ courseId, blockId }, controller.signal) };
      pending.set(key, entry);
    }
    const request = entry;
    request.users++;
    setLoading(true); setError('');
    void request.promise.then(data => {
      if (active) setSnapshot({ owner, data });
    }).catch(reason => {
      if (active && !request.controller.signal.aborted) {
        // A failed permissions refresh must not keep displaying revoked sources.
        setSnapshot(null);
        setError(reason instanceof Error ? reason.message : 'Chưa tải được học liệu.');
      }
    }).finally(() => {
      if (pending.get(key) === request) pending.delete(key);
      if (active) setLoading(false);
    });
    return () => {
      active = false;
      request.users--;
      // StrictMode's immediate remount reuses the in-flight request.
      queueMicrotask(() => { if (!request.users) request.controller.abort(); });
    };
  }, [userId, courseId, blockId, revision, enabled, attempt, owner]);
  return { preparation: snapshot?.owner === owner ? snapshot.data : null, loading, error,
    retry: () => setAttempt(value => value + 1) };
}
