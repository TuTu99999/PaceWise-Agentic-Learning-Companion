import { useState } from 'react';
import { useTeacherManagement } from '../../hooks/useTeacherManagement';
import { Button } from '../ui/Button';
import { Input, Textarea } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { PdfUpload } from './TeacherAuthoringForms';
import { LmsMaterialStatus } from './LmsMaterialStatus';
import type { TeacherLesson, TeacherManagementData } from '../../types/teacherManagement';

export function lessonChapterOptions(lessons: TeacherLesson[]) {
  const normalized = lessons
    .filter((lesson) => !lesson.cancelled && !lesson.removed)
    .map((lesson) => lesson.title
      .replace(/^\s*\[[^\]]+\]\s*/, '')
      .replace(/^\s*(?:Ca học\s+(?:online|trực tiếp)|Học\s+(?:online|tại lớp))\s*(?::|·)\s*/i, '')
      .replace(/\s*·\s*\d+\s*phút\s*$/i, '')
      .trim())
    .filter(Boolean);
  return [...new Set(normalized)].sort((left, right) => left.localeCompare(right, 'vi'));
}

export function materialChapterOptions(data?: TeacherManagementData) {
  if (!data) return [];
  const values = [
    ...lessonChapterOptions(data.lessons),
    ...data.tasks.map((item) => item.chapter ?? ''),
    ...data.resources.map((item) => item.chapter ?? ''),
    ...(data.materials ?? []).map((item) => item.chapter),
  ].map((item) => item.trim()).filter((item) => item && item !== 'Bài tập theo chương');
  return [...new Set(values)].sort((left, right) => left.localeCompare(right, 'vi'));
}

export function TeacherMaterialsPanel({ courseId }: { courseId: string }) {
  const { data, loading, error, mutate, removeResource, refreshAfterMutation } = useTeacherManagement(courseId);
  const [open, setOpen] = useState(false); const [title, setTitle] = useState('');
  const [chapter, setChapter] = useState(''); const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false); const [actionError, setActionError] = useState('');
  const [deleting, setDeleting] = useState<{ id: number; title: string } | null>(null);
  return <div className="space-y-4"><p className="text-sm text-muted">Gắn tài liệu và nhiệm vụ vào cùng chương để Do chỉ lấy đúng phạm vi. Xử lý/index diễn ra sau khi lưu, không đồng nghĩa AI đã dùng tài liệu.</p>
    <PdfUpload courseId={courseId} chapters={materialChapterOptions(data)} onUploaded={refreshAfterMutation} />
    <LmsMaterialStatus courseId={courseId} />
    <Button variant="secondary" onClick={() => setOpen(true)}>Thêm hướng dẫn dạng văn bản</Button>
    {loading && !data && <p role="status">Đang tải học liệu…</p>}{error && <p role="alert">{error}</p>}
    <div className="space-y-3">{data?.resources.map((item) => <article key={`file-${item.id}`} className="flex items-start justify-between gap-3 rounded-xl border border-line p-3"><div className="min-w-0"><h3 className="break-words font-semibold">{item.title}</h3><p className="text-sm text-muted">Tài liệu · {item.chapter || 'Chưa gắn chương — Do không tự chọn sang chương khác'}</p></div><Button type="button" variant="danger" size="sm" onClick={() => { setActionError(''); setDeleting(item); }}>Xóa</Button></article>)}
      {data?.materials?.map((item) => <article key={`page-${item.id}`} className="rounded-xl border border-line p-3"><h3 className="font-semibold">{item.title}</h3><p className="text-sm text-muted">Văn bản · {item.chapter}</p><details className="mt-2 text-sm"><summary>Xem nội dung</summary><p className="whitespace-pre-wrap pt-2">{item.content}</p></details></article>)}
      {data && !data.resources.length && !data.materials?.length && <p className="text-sm text-muted">Chưa có học liệu. Thêm PDF, Word hoặc hướng dẫn để thử Do có trích nguồn.</p>}</div>
    <Modal open={open} title="Thêm hướng dẫn" onClose={() => !busy && setOpen(false)}><form className="space-y-4" onSubmit={async (event) => {
      event.preventDefault(); setBusy(true); setActionError('');
      try { await mutate('materials', { title, chapter, content }); setOpen(false); setTitle(''); setContent(''); }
      catch (reason) { setActionError(reason instanceof Error ? reason.message : 'Không lưu được học liệu.'); }
      finally { setBusy(false); }
    }}><Input label="Tên tài liệu" required maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} />
      <Input label="Chương / module" required maxLength={255} value={chapter} onChange={(event) => setChapter(event.target.value)} />
      <Textarea label="Nội dung học liệu" required maxLength={20000} value={content} onChange={(event) => setContent(event.target.value)} />
      {actionError && <p role="alert" className="text-danger-ink">{actionError}</p>}<Button type="submit" loading={busy}>Lưu hướng dẫn</Button></form></Modal>
    <Modal open={Boolean(deleting)} title="Xóa tài liệu?" description="Tài liệu sẽ bị gỡ khỏi chương, nhiệm vụ và buổi học đang liên kết." onClose={() => !busy && setDeleting(null)} footer={<><Button type="button" variant="secondary" onClick={() => setDeleting(null)} disabled={busy}>Giữ lại</Button><Button type="button" variant="danger" loading={busy} onClick={async () => {
      if (!deleting) return;
      setBusy(true); setActionError('');
      try { await removeResource(deleting.id); setDeleting(null); }
      catch (reason) { setActionError(reason instanceof Error ? reason.message : 'Không xóa được tài liệu.'); }
      finally { setBusy(false); }
    }}>Xóa tài liệu</Button></>}>
      <p className="break-words text-sm"><strong>{deleting?.title}</strong></p>
      <p className="mt-2 text-sm text-muted">Các phiên Do đã hoàn thành vẫn được giữ làm lịch sử, nhưng tài liệu này sẽ không còn được Plan, Do hoặc chatbot sử dụng.</p>
      {actionError && <p role="alert" className="mt-3 text-danger-ink">{actionError}</p>}
    </Modal>
  </div>;
}
