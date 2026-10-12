import { useEffect, useState } from 'react';
import { fetchTeacherManagement, fetchTeacherScheduleHistory, teacherScheduleAction } from '../../services/api';
import type { ManagedCourse, SchedulePreview, TeacherLesson } from '../../types/teacherManagement';
import { Button } from '../ui/Button';
import { Input } from '../ui/Field';
import { Modal } from '../ui/Modal';
import { localDateTime } from './TeacherAuthoringForms';

export function SchedulePreviewDetails({ preview, courseName }: { preview: SchedulePreview; courseName: (id: number) => string }) {
  const counts = preview.counts;
  const removing = preview.mode === 'remove';
  return <div className="space-y-3"><p className="font-semibold">{removing ? `Xóa ${counts.removed_lessons ?? 0} buổi khỏi lịch` : `${counts.courses ?? 0} môn mới · ${counts.lessons ?? 0} buổi mới · ${counts.tasks ?? 0} nhiệm vụ · ${counts.weights ?? 0} bộ trọng số · ${counts.materials ?? 0} học liệu · hủy ${counts.cancelled_lessons ?? 0} buổi tương lai`}</p>
    {preview.applied && <p role="status" className="text-success-ink">{preview.restored ? 'Đã khôi phục các buổi học.' : removing ? 'Đã xóa khỏi lịch. Có thể khôi phục trong Lịch sử / khôi phục.' : 'Đã áp dụng — không tạo lại khi gửi cùng file.'}</p>}
    {!!counts.historical_lessons && <p className="text-sm text-muted">{counts.historical_lessons} buổi đã kết thúc được nhập vào lịch sử, chưa có thông tin tham dự.</p>}
    {!!preview.errors.length && <div role="alert" className="rounded-xl bg-warning-light p-3"><p className="font-semibold">Chưa thể xác nhận: cần sửa {preview.errors.length} lỗi.</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{preview.errors.map((error, index) => <li key={index}>{error.source}: {error.message}</li>)}</ul></div>}
    {!!preview.items.length && <details open><summary className="cursor-pointer font-semibold">Các mục sẽ thêm / cập nhật</summary><ul className="max-h-48 space-y-3 overflow-auto pt-2 text-sm">{preview.items.map((item, index) => <li key={index}>{item.course_code || courseName(item.course_id)} · {item.title} <span className="text-muted">({item.sheet}, dòng {item.row})</span>
      {item.details?.starts_at && <p className="text-muted">{localDateTime(item.details.starts_at).replace('T', ' ')} → {item.details.ends_at ? localDateTime(item.details.ends_at).replace('T', ' ') : ''} (GMT+7) · {item.details.repeat_count ?? 1} buổi, lặp tuần</p>}
      {item.details?.due_at && <p className="text-muted">Hạn {localDateTime(item.details.due_at).replace('T', ' ')} (GMT+7) · {item.details.points_possible} điểm · {item.details.published ? 'Xuất bản' : 'Nháp'}</p>}
      {item.details?.chapter && <p className="text-muted">{item.details.chapter}</p>}
      {item.details?.groups && <p className="text-muted">{item.details.groups.map((group) => `${group.name}: ${group.weight}%`).join(' · ')}</p>}
    </li>)}</ul></details>}
    {!!preview.cancellations.length && <details open><summary className="cursor-pointer font-semibold">{removing ? 'Buổi sẽ xóa khỏi lịch — giữ dữ liệu tham dự' : 'Buổi sẽ hủy — không xóa lịch sử'}</summary><ul className="max-h-48 space-y-1 overflow-auto pt-2 text-sm">{preview.cancellations.map((item) => <li key={item.id}>{courseName(item.course_id)} · {item.title} · {localDateTime(item.starts_at).replace('T', ' ')}</li>)}</ul></details>}
  </div>;
}

export function TeacherScheduleTools({ courses, selectedCourseId, onChanged }: { courses: ManagedCourse[]; selectedCourseId?: number; onChanged: () => Promise<void> }) {
  const [open, setOpen] = useState(false); const [tab, setTab] = useState('import');
  const [mode, setMode] = useState<'append' | 'replace_future'>('append');
  const [file, setFile] = useState<File | null>(null); const [ids, setIds] = useState<number[]>([]);
  const [from, setFrom] = useState(''); const [until, setUntil] = useState('');
  const [period, setPeriod] = useState<'all' | 'past' | 'future'>('past');
  const [lessons, setLessons] = useState<TeacherLesson[]>([]);
  const [lessonsLoading, setLessonsLoading] = useState(false);
  const [lessonsError, setLessonsError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [preview, setPreview] = useState<SchedulePreview | null>(null); const [ack, setAck] = useState(false);
  const [history, setHistory] = useState<SchedulePreview[]>([]); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const active = courses.filter((course) => !course.archived);
  const name = (id: number) => courses.find((item) => item.id === id)?.code ?? `Môn ${id}`;
  const clearPreview = () => { setPreview(null); setAck(false); setError(''); };
  const closeDialog = () => {
    if (busy) return;
    setOpen(false);
    setFile(null);
    clearPreview();
  };
  const singleCourseId = ids.length === 1 ? ids[0] : undefined;
  useEffect(() => {
    setLessons([]); setLessonsError('');
    if (!open || tab !== 'cleanup' || !singleCourseId) { setLessonsLoading(false); return; }
    let cancelled = false;
    setLessonsLoading(true);
    fetchTeacherManagement(String(singleCourseId)).then((data) => { if (!cancelled) setLessons(data.calendar_events ?? data.lessons); })
      .catch((reason) => { if (!cancelled) setLessonsError(reason instanceof Error ? reason.message : 'Không tải được buổi học.'); })
      .finally(() => { if (!cancelled) setLessonsLoading(false); });
    return () => { cancelled = true; };
  }, [open, tab, singleCourseId, refresh]);
  const removalRequest = (lessonId?: number) => {
    const untilDate = until ? new Date(`${until}T00:00:00+07:00`) : null;
    if (untilDate) untilDate.setUTCDate(untilDate.getUTCDate() + 1);
    return { mode: 'remove', course_ids: ids, rows: [], period,
      ...(lessonId === undefined ? {} : { lesson_ids: [lessonId] }),
      ...(from ? { from_at: `${from}T00:00:00+07:00` } : {}),
      ...(untilDate ? { until_at: untilDate.toISOString() } : {}) };
  };
  const visibleLessons = lessons.filter((item) => !item.removed
    && (period !== 'past' || Date.parse(item.ends_at) <= Date.now())
    && (period !== 'future' || Date.parse(item.starts_at) > Date.now())
    && (!from || Date.parse(item.starts_at) >= Date.parse(`${from}T00:00:00+07:00`))
    && (!until || Date.parse(item.starts_at) < Date.parse(`${until}T00:00:00+07:00`) + 86400000));
  useEffect(() => {
    if (!open || tab !== 'history') return;
    let cancelled = false;
    fetchTeacherScheduleHistory().then((items) => { if (!cancelled) setHistory(items); })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : 'Không tải được lịch sử.'); });
    return () => { cancelled = true; };
  }, [open, tab]);
  const perform = async (action: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await action(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Thao tác thất bại.'); }
    finally { setBusy(false); }
  };
  const previewFooter = !preview ? undefined : preview.applied ? (
    <Button onClick={closeDialog}>Hoàn tất</Button>
  ) : preview.errors.length ? (
    <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm font-medium text-warning-ink">Sửa lỗi trong file rồi kiểm tra lại để tiếp tục.</p>
      <Button disabled>Chưa thể nhập dữ liệu</Button>
    </div>
  ) : preview.ticket ? (
    <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={ack} disabled={busy} onChange={(event) => setAck(event.target.checked)} />
        Tôi đã kiểm tra đúng môn, thời gian và các thay đổi ở trên.
      </label>
      <Button loading={busy} disabled={!ack} onClick={() => void perform(async () => {
        setPreview(await teacherScheduleAction('confirm', { ticket: preview.ticket }));
        await onChanged();
        setRefresh((value) => value + 1);
      })}>{tab === 'cleanup' ? 'Xác nhận xóa các buổi đã chọn' : 'Xác nhận nhập dữ liệu'}</Button>
    </div>
  ) : (
    <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-muted">File không có thay đổi mới để áp dụng.</p>
      <Button onClick={closeDialog}>Hoàn tất</Button>
    </div>
  );
  return <><Button variant="secondary" onClick={() => { setOpen(true); setIds(selectedCourseId ? [selectedCourseId] : active.map((c) => c.id)); clearPreview(); }}>Nhập Excel / dọn lịch</Button>
    <Modal open={open} onClose={closeDialog} title="Nhập và dọn lịch" description="Có thể khai báo môn mới trong sheet Courses. File không được áp dụng trước khi xem và xác nhận." footer={previewFooter}>
      <div className="space-y-4"><div className="flex flex-wrap gap-2" role="tablist" aria-label="Công cụ lịch">{[['import', 'Nhập Excel'], ['cleanup', 'Dọn lịch'], ['history', 'Lịch sử / khôi phục']].map(([key, label]) =>
        <Button key={key} role="tab" aria-selected={tab === key} variant={tab === key ? 'primary' : 'secondary'} disabled={busy} onClick={() => { setTab(key); clearPreview(); }}>{label}</Button>)}</div>
        {tab === 'import' && <div className="space-y-3"><a className="font-semibold text-primary-ink underline" href={`${import.meta.env.BASE_URL}templates/pacewise-schedule-template.xlsx`} download>Tải file Excel mẫu (.xlsx)</a>
          <p className="text-sm text-muted">Courses: mã, tên môn và học kỳ; môn chưa có chỉ được tạo sau khi xác nhận. Lessons: ngày đầu, giờ, số buổi lặp tuần (1–16). Buổi đã kết thúc được nhập vào lịch sử, chưa có thông tin tham dự. Tasks: bài tập/quiz/thi và deadline tương lai. Weights: tên nhóm, tổng 100% mỗi môn. Giờ GMT+7. Quiz nhập ở trạng thái nháp, thêm câu hỏi trước khi xuất bản.</p>
          <Input label="File lịch (.xlsx, tối đa 5 MB)" type="file" accept=".xlsx" disabled={busy} onChange={(event) => { clearPreview(); setFile(event.target.files?.[0] ?? null); }} />
          <label className="block text-sm font-semibold">Cách nhập<select aria-label="Cách nhập lịch" className="mt-1 min-h-11 w-full rounded-xl border border-line bg-white px-3" value={mode} disabled={busy} onChange={(event) => { setMode(event.target.value as typeof mode); clearPreview(); }}>
            <option value="append">Thêm vào lịch hiện tại</option><option value="replace_future">Thay buổi tương lai của môn có trong sheet Lessons</option></select></label>
          <p className="text-sm text-muted">Thay lịch không xóa bài tập hoặc học liệu cũ. Sheet Weights cập nhật cấu hình trọng số sau xác nhận; bỏ sheet này nếu không muốn thay đổi.</p>
          <Button loading={busy} disabled={!file} onClick={() => void perform(async () => {
            if (!file || file.size > 5 * 1024 * 1024 || !file.name.toLowerCase().endsWith('.xlsx')) throw new Error('Chỉ nhận .xlsx tối đa 5 MB.');
            const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
            for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
            setPreview(await teacherScheduleAction('import-preview', { mode, data_base64: btoa(binary) })); setAck(false);
          })}>Kiểm tra và xem trước file</Button></div>}
        {tab === 'cleanup' && <div className="space-y-3"><p className="text-sm">Xóa lịch buổi học, video, quiz và thi trong phạm vi đã chọn, kể cả lịch cũ. Gỡ sự kiện khỏi lịch cả lớp; không xóa nhiệm vụ, deadline bài tập, điểm, bài nộp, học liệu hoặc lịch cá nhân. Có thể khôi phục.</p>
          <Button variant="ghost" disabled={busy} onClick={() => { setIds(active.map((c) => c.id)); clearPreview(); }}>Chọn tất cả môn đang dùng</Button>
          <fieldset className="max-h-48 space-y-2 overflow-auto rounded-xl border border-line p-3"><legend className="px-1 text-sm font-semibold">Môn cần dọn</legend>{active.map((course) => <label key={course.id} className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={busy} checked={ids.includes(course.id)} onChange={(event) => { setIds(event.target.checked ? [...ids, course.id] : ids.filter((id) => id !== course.id)); clearPreview(); }} />{course.code} · {course.name}</label>)}</fieldset>
          <label className="block text-sm font-semibold">Phạm vi buổi học<select aria-label="Phạm vi buổi học" className="mt-1 min-h-11 w-full rounded-xl border border-line bg-white px-3" value={period} disabled={busy} onChange={(event) => { setPeriod(event.target.value as typeof period); clearPreview(); }}>
            <option value="past">Lịch cũ — đã diễn ra</option><option value="all">Tất cả lịch — cũ và mới</option><option value="future">Lịch chưa bắt đầu</option></select></label>
          <div className="grid gap-3 sm:grid-cols-2"><Input label="Từ ngày (để trống: không giới hạn)" type="date" disabled={busy} value={from} onChange={(event) => { setFrom(event.target.value); clearPreview(); }} />
            <Input label="Đến ngày (để trống: không giới hạn)" type="date" disabled={busy} value={until} onChange={(event) => { setUntil(event.target.value); clearPreview(); }} /></div>
          <Button loading={busy} disabled={!ids.length} onClick={() => void perform(async () => {
            setPreview(await teacherScheduleAction('preview', removalRequest())); setAck(false);
          })}>Xem trước xóa tất cả trong phạm vi</Button>
          {!singleCourseId && <p className="text-sm text-muted">Chọn một môn để xem danh sách và xóa từng buổi.</p>}
          {lessonsLoading && <p role="status">Đang tải buổi học…</p>}
          {lessonsError && <p role="alert" className="text-danger-ink">{lessonsError}</p>}
          {singleCourseId && !lessonsLoading && !lessonsError && <div className="max-h-64 space-y-2 overflow-y-auto">
            {!visibleLessons.length && <p className="text-sm text-muted">Không có buổi học trong phạm vi này.</p>}
            {visibleLessons.map((lesson) => <article key={lesson.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-line p-3">
              <div className="min-w-0 flex-1"><p className="break-words text-sm font-semibold">{lesson.title}</p><p className="text-sm text-muted">{localDateTime(lesson.starts_at).replace('T', ' ')}{lesson.cancelled ? ' · Đã hủy' : ''}</p></div>
              <Button size="sm" variant="ghost" disabled={busy} aria-label={`Xóa buổi ${lesson.title}`} onClick={() => void perform(async () => {
                setPreview(await teacherScheduleAction('preview', removalRequest(lesson.id))); setAck(false);
              })}>Xóa buổi</Button></article>)}
          </div>}</div>}
        {tab === 'history' && <div className="space-y-3"><p className="text-sm text-muted">Đây là nhật ký các thao tác đã áp dụng, không phải lịch đang hiển thị. Buổi đã xóa chỉ xuất hiện lại khi bạn xác nhận khôi phục.</p>
          {!history.length && <p className="text-sm text-muted">Chưa có lần nhập/dọn đã áp dụng.</p>}{history.map((item) => <article key={item.ticket} className="space-y-2 rounded-xl border border-line p-3">
          <p className="text-sm font-semibold">{item.mode === 'remove' ? 'Xóa lịch' : item.mode === 'cleanup' ? 'Dọn lịch' : item.mode === 'replace_series' ? 'Sửa chuỗi buổi học' : 'Nhập lịch'} · {(item.courses ?? []).map((id) => name(Number(id))).join(', ')}</p>
          <p className="text-sm">{item.counts.lessons ?? 0} buổi thêm · {item.counts.cancelled_lessons ?? 0} buổi hủy · {item.counts.removed_lessons ?? 0} buổi xóa</p>
          {!!(item.counts.cancelled_lessons || item.counts.removed_lessons) && <p className={`text-sm font-semibold ${item.restored ? 'text-warning-ink' : 'text-success-ink'}`}>
            {item.restored ? 'Đã khôi phục — các buổi đã được đưa lại vào lịch.' : item.mode === 'remove' ? 'Đã xóa khỏi lịch — chỉ giữ bản ghi để khôi phục.' : 'Đã hủy khỏi lịch — chỉ giữ bản ghi để khôi phục.'}</p>}
          {!!(item.counts.cancelled_lessons || item.counts.removed_lessons) && !item.restored && <Button variant="secondary" size="sm" loading={busy} onClick={() => void perform(async () => {
            if (!window.confirm('Khôi phục sẽ đưa các buổi đã xóa/hủy trở lại lịch của cả lớp. Bạn có chắc muốn khôi phục? Không gỡ các mục mới được nhập.')) return;
            await teacherScheduleAction('restore', { ticket: item.ticket }); await onChanged(); setHistory(await fetchTeacherScheduleHistory());
          })}>Khôi phục buổi học</Button>}</article>)}</div>}
        {preview && <div className="space-y-3 rounded-xl border border-line p-4"><SchedulePreviewDetails preview={preview} courseName={name} /></div>}{error && <p role="alert" className="text-danger-ink">{error}</p>}
      </div>
    </Modal></>;
}
