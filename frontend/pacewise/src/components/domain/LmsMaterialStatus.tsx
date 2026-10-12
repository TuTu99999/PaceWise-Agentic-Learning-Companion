import { useEffect, useRef, useState } from 'react';
import { ApiError, fetchLmsFileIndexStatus, retryLmsFileIndex, type LmsFileIndexStatus } from '../../services/api';
import { standaloneCourses } from '../../services/courseSource';
import { Card } from '../ui/Card';
import { useInstructorMaterialCache } from '../../hooks/useInstructorData';
import { useAppStore } from '../../store/AppStore';
import { Button } from '../ui/Button';

const labels: Record<string, string> = {
  queued: 'Chờ xử lý', extracting: 'Đang xử lý · trích xuất', pending: 'Đang xử lý · chờ tạo nguồn AI',
  indexing: 'Đang xử lý · tạo nguồn AI', retry: 'Đang thử lại', extraction_retry: 'Đang thử lại',
  indexed: 'Đã có · sẵn sàng', failed: 'Thiếu · lỗi xử lý', delete_pending: 'Thiếu · đã thu hồi', unavailable: 'Thiếu · không dùng được',
};

const statusTone = (status: string) => status === 'indexed'
  ? { text: 'text-success-ink', dot: 'bg-success' }
  : ['failed', 'delete_pending', 'unavailable'].includes(status)
    ? { text: 'text-danger-ink', dot: 'bg-danger' }
    : { text: 'text-warning-ink', dot: 'bg-warning' };

export function LmsMaterialStatus({ courseId }: { courseId?: string }) {
  const { state } = useAppStore();
  const cache = useInstructorMaterialCache();
  const scope = `${state.user?.id}:${courseId}`;
  const cached = cache?.get(scope);
  const [snapshot, setSnapshot] = useState({ scope, files: cached?.files ?? [] });
  const files: LmsFileIndexStatus[] = snapshot.scope === scope ? snapshot.files : cached?.files ?? [];
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(!cached);
  const [reload, setReload] = useState(0);
  const [retrying, setRetrying] = useState<number | null>(null);
  const [retryError, setRetryError] = useState('');
  const lastRevision = useRef({ scope, revision: state.lmsRevision });
  useEffect(() => {
    let cancelled = false;
    let timer: number;
    const controller = new AbortController();
    const changed = lastRevision.current.scope === scope && lastRevision.current.revision !== state.lmsRevision;
    lastRevision.current = { scope, revision: state.lmsRevision };
    const saved = cache?.get(scope);
    setSnapshot({ scope, files: saved?.files ?? [] });
    setError(false);
    setLoading(!saved);
    if (!courseId) { setLoading(false); return; }
    const schedule = (current: LmsFileIndexStatus[]) => {
      const active = current.some((file) => ['queued', 'extracting', 'pending', 'indexing', 'retry', 'extraction_retry'].includes(file.status));
      timer = window.setTimeout(() => { if (!document.hidden) void refresh(); else schedule(current); }, active ? 3000 : 15000);
    };
    const refresh = () => fetchLmsFileIndexStatus(courseId, controller.signal).then((result) => {
      if (!cancelled) {
        cache?.set(scope, { savedAt: Date.now(), files: result.files });
        setSnapshot({ scope, files: result.files }); setError(false); setLoading(false);
        schedule(result.files);
      }
    }).catch(() => { if (!cancelled) { setError(true); setLoading(false); schedule(saved?.files ?? []); } });
    if (!saved || changed || reload || Date.now() - saved.savedAt >= 15_000) void refresh();
    else schedule(saved.files);
    return () => { cancelled = true; controller.abort(); window.clearTimeout(timer); };
  }, [courseId, scope, cache, state.lmsRevision, reload]);
  return <Card className="mb-5 px-4 py-3">
    <h2 className="font-semibold">{standaloneCourses ? 'Trạng thái học liệu PaceWise' : 'Học liệu đồng bộ từ LMS'}</h2>
    <p className="mt-1 text-sm text-muted">{standaloneCourses ? 'Kiểm tra nhanh tài liệu nào Do và chatbot đã dùng được. Xanh là sẵn sàng; đỏ là thiếu hoặc lỗi.' : 'Upload, cập nhật và phân quyền trên LMS. PaceWise chỉ xử lý nguồn cho Do và chatbot.'}</p>
    {loading ? <p role="status" className="mt-2 text-sm text-muted">Đang tải trạng thái…</p>
      : files.length === 0 ? <p className="mt-2 text-sm text-muted">Chưa có học liệu trong môn này.</p>
          : <ul className="mt-3 max-h-48 space-y-2 overflow-y-auto text-sm">
            {files.map((file) => { const tone = statusTone(file.status); return <li key={file.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line px-3 py-2">
              <span className="min-w-0 flex-1 break-words">{file.title}</span>
              <span className={`inline-flex items-center gap-2 font-semibold ${tone.text}`} title={file.error || undefined}>
                <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${tone.dot}`} aria-hidden="true" />
                {labels[file.status] ?? file.status}{file.status === 'indexed' ? ` · ${file.chunk_count} đoạn` : ''}
              </span>
              {file.status === 'indexed' && file.view_url && <a className="font-semibold text-primary-ink underline" href={file.view_url} target="_blank" rel="noreferrer" aria-label={`Xem tài liệu ${file.title}`}>Xem</a>}
              {file.status === 'failed' && <div className="w-full space-y-1">
                <p className="text-sm text-danger-ink">{file.error || 'Chưa xử lý được file.'}</p>
                {file.version && <Button variant="secondary" loading={retrying === file.id} disabled={retrying !== null} onClick={async () => {
                  if (!courseId || !file.version) return;
                  setRetrying(file.id); setRetryError('');
                  try { await retryLmsFileIndex(courseId, file.id, file.version); if (lastRevision.current.scope === scope) setReload((value) => value + 1); }
                  catch (reason) { if (lastRevision.current.scope === scope) setRetryError(reason instanceof ApiError && reason.retryAfterSeconds
                    ? `Thử lại sau ${reason.retryAfterSeconds} giây.` : reason instanceof Error ? reason.message : 'Chưa thử lại được.'); }
                  finally { setRetrying(null); }
                }}>Thử xử lý lại</Button>}
              </div>}
            </li>; })}
          </ul>}
    {error && <p role="alert" className="mt-2 text-sm text-danger-ink">Chưa tải được trạng thái học liệu. Dữ liệu đã lưu vẫn được giữ.</p>}
    {retryError && <p role="alert" className="mt-2 text-sm text-danger-ink">{retryError}</p>}
  </Card>;
}
