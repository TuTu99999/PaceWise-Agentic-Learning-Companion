import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchManagedCourses, fetchTeacherRoster, getCurrentSession, manageCourse, syncCanvas } from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import type { ManagedCourse } from '../../types/teacherManagement';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Field';
import { Modal } from '../../components/ui/Modal';
import { PageHeader } from '../../components/ui/PageHeader';
import { TeacherLessonManager } from '../../components/domain/TeacherLessonManager';
import { TeacherMaterialsPanel } from '../../components/domain/TeacherMaterialsPanel';
import { TeacherScheduleTools } from '../../components/domain/TeacherScheduleTools';
import { CourseMembersPanel } from '../../components/domain/CourseMembersPanel';
import { parseInvitationEmails } from '../../services/courseInvitations';
import { InstructorTasksPage } from './InstructorTasksPage';

export function InstructorCoursesPage() {
  useDocumentTitle('Môn học');
  const { state, dispatch } = useAppStore(); const [params] = useSearchParams();
  const [courses, setCourses] = useState<ManagedCourse[]>([]); const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState('active'); const [tab, setTab] = useState(params.get('tab') === 'tasks' ? 'tasks' : 'lessons');
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [editing, setEditing] = useState<ManagedCourse | 'new' | null>(null);
  const [action, setAction] = useState<{ course: ManagedCourse; kind: 'archive' | 'restore' } | null>(null);
  const alive = useRef(true);
  const load = async () => {
    const data = await fetchManagedCourses();
    if (!alive.current) return;
    const inCurrentFilter = (item: ManagedCourse) => filter === 'all' || (filter === 'archived' ? item.archived : !item.archived);
    setCourses(data);
    setSelected((id) => data.some((item) => item.id === id && inCurrentFilter(item))
      ? id
      : data.find(inCurrentFilter)?.id ?? null);
  };
  useEffect(() => {
    alive.current = true;
    void load().catch((reason) => { if (alive.current) setError(reason instanceof Error ? reason.message : 'Không tải được môn.'); })
      .finally(() => { if (alive.current) setLoading(false); });
    return () => { alive.current = false; };
  }, [state.user?.id]);
  const changed = async () => {
    // Preserve workspace; refresh membership without logging in or applying student plans.
    dispatch({ type: 'LMS_EVENT_RECEIVED' });
    try {
      await load(); const synced = await syncCanvas(); const user = await getCurrentSession();
      if (!alive.current) return;
      if (user) dispatch({ type: 'REFRESH_SESSION', user });
      dispatch({ type: 'SYNC_CANVAS', courses: synced.courses, tasks: synced.tasks, courseData: synced.courseData,
        assessments: synced.assessments, guidance: synced.guidance });
    } catch {
      // A successful write must not be presented as a failed create and submitted again.
      if (alive.current) setError('Thay đổi đã được lưu, nhưng chưa tải lại đủ dữ liệu. Bấm Làm mới dữ liệu; không cần lưu lại.');
    }
  };
  const perform = async (work: () => Promise<void>) => {
    setBusy(true); setError(''); try { await work(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không thực hiện được.'); }
    finally { if (alive.current) setBusy(false); }
  };
  const visible = courses.filter((item) => filter === 'all' || (filter === 'archived' ? item.archived : !item.archived));
  const course = courses.find((item) => item.id === selected);
  return <div className="page max-w-6xl"><PageHeader title="Môn học" description="Quản lý môn, buổi học, nhiệm vụ và học liệu ngay trong PaceWise."
    actions={<div className="flex flex-wrap gap-2"><Button disabled={busy} onClick={() => { setError(''); setEditing('new'); }}>Thêm môn</Button>
      <TeacherScheduleTools courses={courses} selectedCourseId={course && !course.archived ? course.id : undefined} onChanged={changed} /></div>} />
    {loading && <p role="status">Đang tải môn học…</p>}{error && <div className="mb-4 space-y-2"><p role="alert" className="text-danger-ink">{error}</p><Button variant="secondary" loading={busy} onClick={() => void perform(changed)}>Làm mới dữ liệu</Button></div>}
    <div className="grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)]"><aside className="min-w-0 space-y-3"><select aria-label="Trạng thái môn học" className="min-h-11 w-full rounded-xl border border-line bg-white px-3" value={filter} onChange={(event) => { const value = event.target.value; setFilter(value); const first = courses.find((c) => value === 'all' || c.archived === (value === 'archived')); setSelected(first?.id ?? null); }}>
      <option value="active">Đang dùng</option><option value="archived">Đã xóa</option><option value="all">Tất cả môn</option></select>
      <nav aria-label="Danh sách môn" className="flex gap-2 overflow-x-auto lg:block lg:space-y-2">{visible.map((item) => <button key={item.id} type="button" aria-current={selected === item.id ? 'true' : undefined} className={`min-w-40 rounded-xl border px-4 py-3 text-left lg:w-full ${selected === item.id ? 'border-primary bg-primary-light text-primary-ink' : 'border-line bg-white'}`}
        onClick={() => setSelected(item.id)}><span className="block font-bold">{item.code}</span><span className="mt-1 block break-words text-sm">{item.name}</span>{item.archived && <span className="text-xs text-danger-ink">Đã xóa</span>}</button>)}</nav>
      {!loading && !visible.length && <p className="text-sm text-muted">Không có môn trong bộ lọc này.</p>}</aside>
      {course && <Card className="min-w-0 p-4 sm:p-5"><div className="mb-4 flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h2 className="break-words text-xl font-bold">{course.code} · {course.name}</h2><p className="text-sm text-muted">{course.term}</p></div>
        <div className="flex flex-wrap gap-2"><Button size="sm" variant="secondary" disabled={busy} onClick={() => setEditing(course)}>Sửa tên / mã</Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => { setError(''); setAction({ course, kind: course.archived ? 'restore' : 'archive' }); }}>{course.archived ? 'Khôi phục môn' : 'Xóa môn'}</Button></div></div>
        {course.archived ? <p className="rounded-xl bg-danger-light p-4 text-sm text-danger-ink">Môn đã xóa. Buổi học, nhiệm vụ, học liệu và dữ liệu liên quan đang được ẩn khỏi PaceWise. Khôi phục môn để dùng lại toàn bộ dữ liệu.</p> : <>
          <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Nội dung môn">{[['lessons', 'Buổi học'], ['tasks', 'Nhiệm vụ & trọng số'], ['materials', 'Học liệu'], ['members', 'Sinh viên']].map(([key, label]) => <Button key={key} role="tab" aria-selected={tab === key} variant={tab === key ? 'primary' : 'secondary'} onClick={() => setTab(key)}>{label}</Button>)}</div>
          <div key={`${course.id}:${tab}`} role="tabpanel">{tab === 'lessons' ? <TeacherLessonManager preferredCourseId={String(course.id)} inline /> : tab === 'tasks' ? <InstructorTasksPage courseId={String(course.id)} embedded /> : tab === 'members' ? <CourseMembersPanel courseId={String(course.id)} /> : <TeacherMaterialsPanel courseId={String(course.id)} />}</div>
        </>}
      </Card>}
    </div>
    {editing && <CourseForm key={editing === 'new' ? 'new' : editing.id} course={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} onSaved={async (value) => { await changed(); setSelected(value.id); setFilter('active'); if (editing === 'new') setTab('members'); setEditing(null); }} />}
    <Modal open={!!action} onClose={() => !busy && setAction(null)} title={action?.kind === 'restore' ? 'Khôi phục môn học' : 'Xóa môn học'}
      description={action?.kind === 'restore'
        ? 'Khôi phục toàn bộ buổi học, nhiệm vụ, học liệu và dữ liệu liên quan của môn trong PaceWise.'
        : 'Môn cùng buổi học, nhiệm vụ, học liệu và dữ liệu liên quan sẽ biến mất khỏi các luồng đang dùng. Dữ liệu được giữ kín để có thể khôi phục sau này.'}>
      <p className="mb-3 font-semibold">{action?.course.code} · {action?.course.name}</p>{error && <p role="alert" className="mb-3 text-danger-ink">{error}</p>}
      <Button loading={busy} onClick={() => void perform(async () => { if (!action) return; await manageCourse(`/${action.course.id}/lifecycle/${action.kind}`, { expected_version: action.course.version }); await changed(); setAction(null); })}>Xác nhận {action?.kind === 'restore' ? 'khôi phục' : 'xóa môn'}</Button>
    </Modal>
  </div>;
}

function CourseForm({ course, onClose, onSaved }: { course?: ManagedCourse; onClose: () => void; onSaved: (course: ManagedCourse) => Promise<void> }) {
  const [code, setCode] = useState(course?.code ?? ''); const [name, setName] = useState(course?.name ?? ''); const [term, setTerm] = useState(course?.term ?? 'Demo');
  const [roster, setRoster] = useState<{ id: number; name: string }[]>([]); const [ids, setIds] = useState<number[]>([]);
  const [inviteEmails, setInviteEmails] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { if (course) return; let stopped = false; fetchTeacherRoster().then((items) => { if (!stopped) setRoster(items); }).catch(() => { if (!stopped) setError('Chưa tải được danh sách sinh viên. Có thể tạo môn trống, hoặc đóng và thử lại.'); }); return () => { stopped = true; }; }, [course]);
  return <Modal open title={course ? 'Sửa môn học' : 'Thêm môn học'} onClose={() => !busy && onClose()}><form className="space-y-4" onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError('');
    try { const saved = await manageCourse(course ? `/${course.id}/info` : '', { code, name, term, student_ids: ids, ...(!course ? { invite_emails: parseInvitationEmails(inviteEmails) } : {}), ...(course ? { expected_version: course.version } : {}) }, course ? 'PUT' : 'POST'); await onSaved(saved); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Không lưu được môn.'); } finally { setBusy(false); }
  }}><Input label="Mã môn" required maxLength={64} value={code} onChange={(event) => setCode(event.target.value)} />
    <Input label="Tên môn" required maxLength={255} value={name} onChange={(event) => setName(event.target.value)} />
    <Input label="Học kỳ" required maxLength={128} value={term} onChange={(event) => setTerm(event.target.value)} />
    {!course && <fieldset className="space-y-2 rounded-xl border border-line p-3"><legend className="px-1 text-sm font-semibold">Sinh viên tham gia (tùy chọn)</legend>
      <p className="text-sm text-muted">Chỉ các sinh viên thuộc lớp bạn đang quản lý. Không chọn ai thì môn mới là môn trống.</p>
      <Button type="button" variant="ghost" onClick={() => setIds(roster.map((item) => item.id))}>Chọn cả danh sách</Button><div className="max-h-48 overflow-auto">{roster.map((item) => <label key={item.id} className="flex min-h-9 items-center gap-2 text-sm"><input type="checkbox" checked={ids.includes(item.id)} onChange={(event) => setIds(event.target.checked ? [...ids, item.id] : ids.filter((id) => id !== item.id))} />{item.name}</label>)}</div>
      <label className="block text-sm font-semibold" htmlFor="new-course-invites">Mời sinh viên mới bằng email</label>
      <textarea id="new-course-invites" className="min-h-20 w-full rounded-xl border border-line bg-white p-3 text-sm" maxLength={13000} value={inviteEmails} onChange={event => setInviteEmails(event.target.value)} placeholder="Nhiều email cách nhau bằng dấu phẩy hoặc xuống dòng" />
      <p className="text-sm text-muted">Không cần thuộc lớp cũ. Sau khi lưu môn, vào Sinh viên để sao chép link mời; chưa gửi email tự động.</p></fieldset>}
    {error && <p role="alert" className="text-danger-ink">{error}</p>}<Button type="submit" loading={busy}>Lưu môn học</Button>
  </form></Modal>;
}
