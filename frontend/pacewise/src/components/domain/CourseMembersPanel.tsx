import { useEffect, useRef, useState } from 'react';
import { addKnownCourseStudents, fetchCourseMembers, fetchTeacherRoster, inviteCourseStudents, removeCourseStudent, revokeCourseInvitation, type CourseMembers } from '../../services/api';
import { parseInvitationEmails } from '../../services/courseInvitations';
import { Button } from '../ui/Button';
import { Input } from '../ui/Field';
import { Modal } from '../ui/Modal';

const labels = { pending: 'Đang chờ', accepted: 'Đã tham gia', expired: 'Hết hạn', revoked: 'Đã hủy' };

export function CourseMembersPanel({ courseId }: { courseId: string }) {
  const [data, setData] = useState<CourseMembers | null>(null);
  const [emails, setEmails] = useState(''); const [search, setSearch] = useState('');
  const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false); const [removing, setRemoving] = useState<{ id: number; name: string } | null>(null);
  const alive = useRef(true); const pending = useRef(false);
  const [choices, setChoices] = useState<{ id: number; name: string }[] | null>(null); const [selected, setSelected] = useState<number[]>([]);
  const load = async () => { const next = await fetchCourseMembers(courseId); if (alive.current) setData(next); };
  useEffect(() => {
    alive.current = true;
    void load().catch(() => { if (alive.current) setError('Chưa tải được thành viên. Bấm Làm mới để thử lại.'); });
    return () => { alive.current = false; };
  }, [courseId]);
  const perform = async (work: () => Promise<void>) => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : 'Không thực hiện được.'); }
    finally { pending.current = false; if (alive.current) setBusy(false); }
  };
  const students = (data?.students ?? []).filter(student => student.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <section className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-xl font-bold">Sinh viên của môn</h3>
      <p className="text-sm text-muted">Thêm sinh viên đã đăng ký bằng Google hoặc đã có trong lớp bạn quản lý.</p></div>
      <div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={busy} onClick={() => void perform(async () => {
        const roster = await fetchTeacherRoster(); setChoices(roster.filter(student => !data?.students.some(member => member.id === student.id))); setSelected([]);
      })}>Thêm tài khoản Google</Button><Button variant="secondary" loading={busy} onClick={() => void perform(load)}>Làm mới</Button></div></div>
    {error && <p role="alert" className="text-danger-ink">{error}</p>}{notice && <p role="status" className="rounded-xl bg-primary-light p-3 text-sm">{notice}</p>}
    {!data && !error && <p role="status">Đang tải thành viên…</p>}
    <form className="space-y-3 rounded-xl border border-line p-4" onSubmit={event => {
      event.preventDefault();
      const addresses = parseInvitationEmails(emails);
      if (!addresses.length || addresses.length > 50 || addresses.some(email => !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email))) { setError('Nhập từ 1 đến 50 email hợp lệ.'); return; }
      void perform(async () => {
        await inviteCourseStudents(courseId, addresses); setEmails('');
        setNotice('Đã gửi lời mời trong PaceWise. Sinh viên đăng nhập bằng đúng tài khoản Google sẽ thấy lời mời; sau khi xác nhận, lịch môn được đồng bộ tự động.');
        await load();
      });
    }}><label className="block text-sm font-semibold" htmlFor="course-invite-emails">Mời bằng email</label>
      <textarea id="course-invite-emails" className="min-h-24 w-full rounded-xl border border-line bg-white p-3 text-sm" value={emails} maxLength={13000} onChange={event => setEmails(event.target.value)} placeholder="Email cách nhau bằng dấu phẩy hoặc xuống dòng" />
      <p className="text-sm text-muted">Lời mời có hạn 7 ngày và chỉ hiện cho đúng email Google đã xác minh. Không cần sao chép token hoặc link.</p>
      <Button type="submit" loading={busy}>Gửi lời mời</Button></form>
    <Input label={`Tìm sinh viên (${data?.students.length ?? 0})`} value={search} onChange={event => setSearch(event.target.value)} />
    <ul className="space-y-2">{students.map(student => <li key={student.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-3">
      <span className="break-words font-medium">{student.name}</span><Button size="sm" variant="ghost" disabled={busy} onClick={() => setRemoving(student)}>Gỡ khỏi môn</Button></li>)}</ul>
    {data && !students.length && <p className="text-sm text-muted">{search ? 'Không có sinh viên khớp tìm kiếm.' : 'Chưa có sinh viên tham gia môn.'}</p>}
    <h4 className="font-semibold">Lời mời</h4><ul className="space-y-2">{data?.invitations.map(invite => <li key={invite.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line p-3">
      <div className="min-w-0"><p className="break-all text-sm font-medium">{invite.email}</p><p className="text-xs text-muted">{labels[invite.status]} · Hạn {new Date(invite.expiresAt).toLocaleString('vi-VN')}</p></div>
      {invite.status === 'pending' && <Button size="sm" variant="ghost" disabled={busy} onClick={() => void perform(async () => { await revokeCourseInvitation(courseId, invite.id); await load(); })}>Hủy lời mời</Button>}</li>)}</ul>
    {data && !data.invitations.length && <p className="text-sm text-muted">Chưa có lời mời.</p>}
    <Modal open={!!removing} title="Gỡ sinh viên khỏi môn" onClose={() => !busy && setRemoving(null)}>
      <p className="mb-4">Gỡ {removing?.name} khỏi môn này? Quyền học liệu và nhiệm vụ sẽ ngừng; tài khoản, lịch sử học và các môn khác vẫn giữ nguyên.</p>
      <Button loading={busy} onClick={() => void perform(async () => {
        if (!removing) return; await removeCourseStudent(courseId, removing.id); setRemoving(null); await load();
        setNotice('Đã gỡ khỏi môn. Quyền truy cập được kiểm tra lại ngay ở backend.');
      })}>Xác nhận gỡ khỏi môn</Button>
    </Modal>
    <Modal open={choices !== null} title="Chọn sinh viên tham gia" onClose={() => !busy && setChoices(null)}>
      <p className="mb-3 text-sm text-muted">Gồm tất cả sinh viên đã xác minh Google và sinh viên đã có trong các lớp bạn quản lý.</p>
      <div className="max-h-64 overflow-y-auto">{choices?.map(student => <label key={student.id} className="flex min-h-11 items-center gap-2"><input type="checkbox" checked={selected.includes(student.id)} onChange={event => setSelected(event.target.checked ? [...selected, student.id] : selected.filter(id => id !== student.id))} />{student.name}</label>)}</div>
      {!choices?.length && <p className="mb-3 text-sm text-muted">Không còn sinh viên phù hợp để thêm vào môn.</p>}
      <Button loading={busy} disabled={!selected.length} onClick={() => void perform(async () => {
        await addKnownCourseStudents(courseId, selected); setChoices(null); await load(); setNotice('Đã thêm những sinh viên được chọn vào môn.');
      })}>Xác nhận thêm sinh viên</Button>
    </Modal>
  </section>;
}
