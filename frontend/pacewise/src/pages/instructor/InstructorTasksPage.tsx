import { useEffect, useState } from 'react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { TaskForm, WeightsForm, taskKinds, localDateTime } from '../../components/domain/TeacherAuthoringForms';
import { useTeacherManagement } from '../../hooks/useTeacherManagement';
import { useAppStore } from '../../store/AppStore';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import type { TeacherTask } from '../../types/teacherManagement';

export function InstructorTasksPage({ courseId: selectedCourseId, embedded = false }: { courseId?: string; embedded?: boolean } = {}) {
  useDocumentTitle('Nhiệm vụ học tập');
  const { state } = useAppStore(); const courseId = selectedCourseId ?? state.user?.courseId;
  const { data, loading, error, reload, mutate } = useTeacherManagement(courseId);
  const [editing, setEditing] = useState<TeacherTask | 'new' | null>(null); const [weights, setWeights] = useState(false);
  const [archive, setArchive] = useState<TeacherTask | null>(null); const [busy, setBusy] = useState(false); const [actionError, setActionError] = useState('');
  const [filter, setFilter] = useState('active'); const [query, setQuery] = useState('');
  useEffect(() => { setEditing(null); setWeights(false); setArchive(null); setActionError(''); }, [courseId]);
  const tasks = data?.tasks.filter((item) => (filter === 'all' || (filter === 'archived' ? item.archived : !item.archived)) &&
    `${item.title} ${taskKinds[item.kind]}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())) ?? [];
  return <div className={embedded ? 'space-y-4' : 'page max-w-5xl'}><PageHeader title="Nhiệm vụ & trọng số" description="Bài tập, quiz tính điểm và kỳ thi. Kiểm chứng mức hiểu trong Do là luồng riêng."
    actions={<div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => void reload()}>Làm mới</Button>
      <Button variant="secondary" disabled={!data} onClick={() => setWeights(true)}>Cấu hình trọng số</Button><Button disabled={!data} onClick={() => setEditing('new')}>Thêm nhiệm vụ</Button></div>} />
    {loading && !data && <p role="status">Đang tải nhiệm vụ…</p>}{error && <p role="alert" className="mb-3 text-danger-ink">{error}</p>}
    <div className="mb-4 flex flex-wrap gap-3"><input aria-label="Tìm nhiệm vụ" placeholder="Tìm nhiệm vụ…" className="min-h-11 flex-1 rounded-xl border border-line bg-white px-3" value={query} onChange={(event) => setQuery(event.target.value)} />
      <select aria-label="Trạng thái nhiệm vụ" className="min-h-11 rounded-xl border border-line bg-white px-3" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="active">Đang dùng / nháp</option><option value="archived">Đã ẩn</option><option value="all">Tất cả</option></select></div>
    {data && !tasks.length && <Card className="p-5 text-muted">Chưa có nhiệm vụ phù hợp. Thêm nhiệm vụ hoặc đổi bộ lọc.</Card>}
    <div className="space-y-3">{tasks.map((item) => <Card key={item.id} className="p-4"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0 flex-1">
      <h2 className="break-words font-semibold">{item.title}</h2><p className="mt-1 text-sm text-muted">{taskKinds[item.kind]} · {item.archived ? 'Đã ẩn' : item.published ? 'Đã xuất bản' : 'Bản nháp'}</p>
      <p className="mt-1 text-sm">Hạn: {localDateTime(item.due_at).replace('T', ' ')} (GMT+7) · {item.points_possible} điểm tối đa</p>
      <p className="text-sm text-muted">Nhóm: {data?.weights.groups.find((group) => group.id === item.group_id)?.name ?? 'Chưa phân nhóm'} · {item.resource_ids.length} tài liệu{item.has_submissions ? ' · Đã có bài nộp' : ''}</p></div>
      {!item.archived && <div className="flex gap-2"><Button variant="secondary" onClick={() => setEditing(item)}>Sửa</Button><Button variant="ghost" onClick={() => { setArchive(item); setActionError(''); }}>Ẩn nhiệm vụ</Button></div>}
    </div></Card>)}</div>
    {data && editing && courseId && <TaskForm key={editing === 'new' ? 'new' : editing.id} courseId={courseId} data={data} item={editing === 'new' ? undefined : editing} mutate={mutate} onClose={() => setEditing(null)} />}
    {data && weights && <WeightsForm data={data} mutate={mutate} onClose={() => setWeights(false)} />}
    <Modal open={!!archive} onClose={() => !busy && setArchive(null)} title="Ẩn nhiệm vụ khỏi sinh viên" description="Giữ nguyên bài nộp, điểm và audit. Plan cần rà lại các block tương lai liên quan; không xóa evidence đã học.">
      <p className="mb-4 font-semibold">{archive?.title}</p>{actionError && <p role="alert" className="mb-3 text-danger-ink">{actionError}</p>}
      <Button loading={busy} onClick={async () => { if (!archive) return; setBusy(true); try { await mutate(`tasks/${archive.id}/archive`, { expected_version: archive.version }); setArchive(null); }
        catch (reason) { setActionError(reason instanceof Error ? reason.message : 'Không ẩn được.'); } finally { setBusy(false); } }}>Xác nhận ẩn</Button>
    </Modal>
  </div>;
}
