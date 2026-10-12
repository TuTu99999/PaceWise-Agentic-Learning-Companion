import { useEffect, useState } from 'react';
import { useAppStore } from '../../store/AppStore';
import { useTeacherManagement } from '../../hooks/useTeacherManagement';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { LessonForm, localDateTime } from './TeacherAuthoringForms';
import type { TeacherLesson } from '../../types/teacherManagement';
import type { SchedulePreview } from '../../types/teacherManagement';
import { teacherScheduleAction } from '../../services/api';
import { SchedulePreviewDetails } from './TeacherScheduleTools';

export function visibleTeacherLessons(lessons: TeacherLesson[], filter: string, now = Date.now()) {
  return lessons.filter((item) => !item.removed && (filter === 'cancelled' ? item.cancelled : !item.cancelled &&
    (filter === 'past' ? Date.parse(item.ends_at) <= now : Date.parse(item.ends_at) > now)))
    .sort((a, b) => (Date.parse(a.starts_at) - Date.parse(b.starts_at)) * (filter === 'past' ? -1 : 1));
}

export function TeacherLessonManager({ preferredCourseId, inline = false }: { preferredCourseId?: string; inline?: boolean }) {
  const { state } = useAppStore(); const [open, setOpen] = useState(inline);
  const [filter, setFilter] = useState('upcoming');
  const [courseId, setCourseId] = useState(preferredCourseId ?? state.user?.courseId);
  const [editing, setEditing] = useState<TeacherLesson | 'new' | null>(null); const [cancel, setCancel] = useState<TeacherLesson | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [series, setSeries] = useState<SchedulePreview | null>(null);
  const [editingSeries, setEditingSeries] = useState(false);
  const management = useTeacherManagement(courseId); const { data, reload, mutate, refreshAfterMutation } = management;
  useEffect(() => { if (!open || inline) setCourseId(preferredCourseId ?? state.user?.courseId); }, [preferredCourseId, state.user?.courseId, open, inline]);
  useEffect(() => { setEditing(null); setEditingSeries(false); setCancel(null); setSeries(null); setFilter('upcoming'); }, [courseId]);
  const lessons = visibleTeacherLessons(data?.lessons ?? [], filter);
  const content = <div className="space-y-4">{!inline && <label className="text-sm font-semibold">Môn học<select aria-label="Môn tạo buổi học" value={courseId ?? ''} onChange={(event) => setCourseId(event.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-line bg-white px-3">
        {state.courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}</select></label>}
        <div className="flex flex-wrap gap-2"><Button disabled={!data} onClick={() => { setEditingSeries(false); setEditing('new'); }}>Thêm buổi học / lặp tuần</Button><Button variant="secondary" onClick={() => void reload()}>Làm mới</Button>
          <select aria-label="Lọc buổi học" className="min-h-11 rounded-xl border border-line bg-white px-3" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="upcoming">Đang diễn ra / sắp tới</option><option value="past">Đã diễn ra</option><option value="cancelled">Đã hủy</option></select></div>
        {management.loading && !data && <p role="status">Đang tải buổi học…</p>}{management.error && <p role="alert" className="text-danger-ink">{management.error}</p>}
        {error && !cancel && <p role="alert" className="text-danger-ink">{error}</p>}
        <div className={`${inline ? '' : 'max-h-80 overflow-auto'} space-y-3`}>{lessons.map((lesson) => {
          const past = Date.parse(lesson.starts_at) <= Date.now();
          const ongoing = past && Date.parse(lesson.ends_at) > Date.now();
          return <article key={lesson.id} className="rounded-xl border border-line p-3"><p className="font-semibold">{lesson.title}</p>
            <p className="text-sm text-muted">{localDateTime(lesson.starts_at).replace('T', ' ')} · {lesson.mode === 'online' ? 'Online' : 'Offline'}{lesson.cancelled ? ' · Đã hủy' : ongoing ? ' · Đang diễn ra' : past ? ' · Đã diễn ra' : ''}</p>
            {!past && !lesson.cancelled && <div className="mt-2 flex flex-wrap gap-2"><Button size="sm" variant="secondary" onClick={() => { setEditingSeries(false); setEditing(lesson); }}>Sửa buổi</Button><Button size="sm" variant="ghost" onClick={() => { setCancel(lesson); setError(''); }}>Hủy buổi</Button>
              {lesson.series_key && <Button size="sm" variant="secondary" onClick={() => { setEditingSeries(true); setEditing(lesson); }}>Sửa các buổi còn lại của chuỗi</Button>}
              {lesson.series_key && <Button size="sm" variant="ghost" loading={busy} onClick={async () => {
                setBusy(true); setError('');
                try { setSeries(await teacherScheduleAction('preview', { mode: 'cleanup', course_ids: [Number(courseId)], series_lesson_id: lesson.id, rows: [] })); }
                catch (reason) { setError(reason instanceof Error ? reason.message : 'Không tải được chuỗi.'); } finally { setBusy(false); }
              }}>Hủy các buổi còn lại của chuỗi</Button>}</div>}
            <Button className="mt-2" size="sm" variant="ghost" disabled={busy} aria-label={`Xóa buổi ${lesson.title}`} onClick={async () => {
              setBusy(true); setError('');
              try { setSeries(await teacherScheduleAction('preview', { mode: 'remove', period: 'all', course_ids: [Number(courseId)], lesson_ids: [lesson.id], rows: [] })); }
              catch (reason) { setError(reason instanceof Error ? reason.message : 'Không xem trước được thao tác xóa.'); }
              finally { setBusy(false); }
            }}>Xóa buổi</Button>
          </article>;
        })}{data && !lessons.length && <p className="text-sm text-muted">Không có buổi học trong bộ lọc này. Lịch sử nằm ở “Đã diễn ra”.</p>}</div>
      </div>;
  return <>
    {inline ? content : <><Button className="teacher-lesson-manager-trigger" size="sm" variant="secondary" onClick={() => setOpen(true)}>Quản lý buổi học</Button>
    <Modal open={open && !editing && !cancel && !series} onClose={() => setOpen(false)} title="Quản lý buổi học" description="Thêm/sửa/hủy buổi chưa diễn ra. Có thể xóa lịch cũ hoặc mới khỏi lịch; giữ dữ liệu tham dự và cho phép khôi phục.">{content}</Modal></>}
    {open && data && editing && <LessonForm key={`${editing === 'new' ? 'new' : editing.id}:${editingSeries}`} item={editing === 'new' ? undefined : editing} data={data} previewOnly={editingSeries} mutate={editingSeries && editing !== 'new' ? async (_target, payload) => {
      setSeries(await teacherScheduleAction('series-preview', { ...payload, course_ids: [Number(courseId)], series_lesson_id: editing.id }));
    } : mutate} onClose={() => setEditing(null)} />}
    <Modal open={!!cancel} onClose={() => !busy && setCancel(null)} title="Hủy buổi học" description="Hủy cho cả lớp. Buổi này không còn chiếm lịch rảnh của sinh viên; bản ghi lịch sử vẫn được giữ.">
      <p className="mb-3 font-semibold">{cancel?.title}</p>{error && <p role="alert" className="mb-3 text-danger-ink">{error}</p>}
      <Button loading={busy} onClick={async () => { if (!cancel) return; setBusy(true); try { await mutate(`lessons/${cancel.id}/cancel`, { expected_version: cancel.version }); setCancel(null); }
        catch (reason) { setError(reason instanceof Error ? reason.message : 'Không hủy được.'); } finally { setBusy(false); } }}>Xác nhận hủy buổi</Button>
    </Modal>
    <Modal open={!!series} onClose={() => !busy && setSeries(null)} title={series?.mode === 'remove' ? 'Xem trước xóa buổi học' : series?.mode === 'replace_series' ? 'Xem trước sửa chuỗi' : 'Hủy các buổi tương lai của chuỗi'} description={series?.mode === 'remove' ? 'Gỡ khỏi lịch cả lớp, không xóa dữ liệu tham dự hoặc lịch sử học. Khôi phục trong Nhập Excel / dọn lịch → Lịch sử / khôi phục.' : 'Chỉ các buổi chưa bắt đầu của đúng chuỗi này. Lịch sử và các chuỗi khác được giữ.'}>
      {series && <div className="space-y-4"><SchedulePreviewDetails preview={series} courseName={(id) => state.courses.find((item) => item.id === String(id))?.code ?? String(id)} />
        {!!(series.counts.cancelled_lessons || series.counts.removed_lessons) && !series.errors.length && !series.applied && <Button loading={busy} onClick={async () => {
          setBusy(true); setError('');
          try { await teacherScheduleAction('confirm', { ticket: series.ticket }); await refreshAfterMutation(); setSeries(null); }
          catch (reason) { setError(reason instanceof Error ? reason.message : 'Không áp dụng được thay đổi lịch.'); }
          finally { setBusy(false); }
        }}>Xác nhận {series.mode === 'remove' ? 'xóa' : series.mode === 'replace_series' ? 'sửa' : 'hủy'} {series.mode === 'remove' ? series.counts.removed_lessons : series.counts.cancelled_lessons} buổi</Button>}{error && <p role="alert" className="text-danger-ink">{error}</p>}</div>}
    </Modal>
  </>;
}
