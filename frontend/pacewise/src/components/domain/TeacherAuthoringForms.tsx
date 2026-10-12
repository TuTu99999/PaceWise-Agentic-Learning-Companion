import { useState, type FormEvent } from 'react';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { Input, Textarea } from '../ui/Field';
import type { TeacherLesson, TeacherManagementData, TeacherTask, GradedQuestion } from '../../types/teacherManagement';
export { PdfUpload } from './PdfUpload';

export const taskKinds = { assignment: 'Bài tập', quiz: 'Quiz tính điểm', midterm: 'Giữa kỳ', final_exam: 'Cuối kỳ' };
const inputClass = 'min-h-11 w-full rounded-xl border border-line bg-white px-3 text-sm';
export const localDateTime = (value: string) => {
  const parts = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
  return parts.replace(' ', 'T');
};
const instant = (value: string) => new Date(`${value}:00+07:00`).toISOString();
type Mutate = (target: string, payload: object, method?: 'POST' | 'PUT') => Promise<void>;

export function ResourcePicker({ data, ids, onChange }: { data: TeacherManagementData; ids: number[]; onChange: (ids: number[]) => void }) {
  return <fieldset className="rounded-xl border border-line p-3"><legend className="px-1 text-sm font-semibold">Tài liệu môn học đính kèm</legend>
    <div className="max-h-40 space-y-2 overflow-auto">{data.resources.length ? data.resources.map((file) => <label key={file.id} className="flex items-start gap-2 text-sm">
      <input type="checkbox" checked={ids.includes(file.id)} onChange={(event) => onChange(event.target.checked ? [...ids, file.id] : ids.filter((id) => id !== file.id))} />{file.title}
    </label>) : <p className="text-sm text-muted">Chưa có PDF. Dùng nút “Thêm PDF” trước khi tạo.</p>}</div>
  </fieldset>;
}

export function TaskForm({ item, data, mutate, onClose }: { item?: TeacherTask; data: TeacherManagementData; mutate: Mutate; onClose: () => void }) {
  const [title, setTitle] = useState(item?.title ?? ''); const [description, setDescription] = useState(item?.description ?? '');
  const [chapter, setChapter] = useState(item?.chapter ?? '');
  const [kind, setKind] = useState<TeacherTask['kind']>(item?.kind ?? 'assignment');
  const [due, setDue] = useState(item ? localDateTime(item.due_at) : '');
  const [points, setPoints] = useState(item?.points_possible ?? 10); const [published, setPublished] = useState(item?.published ?? false);
  const [group, setGroup] = useState(String(item?.group_id ?? '')); const [ids, setIds] = useState(item?.resource_ids ?? []);
  const [questions, setQuestions] = useState<GradedQuestion[]>(item?.questions ?? []);
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const submitted = item?.has_submissions;
  const save = async (event: FormEvent) => {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      if (kind === 'quiz' && published && !questions.length) throw new Error('Quiz xuất bản phải có ít nhất một câu hỏi.');
      if (kind === 'quiz' && questions.length && Math.abs(questions.reduce((sum, question) => sum + question.points, 0) - points) > 0.005) throw new Error('Tổng điểm câu hỏi phải bằng điểm tối đa của quiz.');
      await mutate(item ? `tasks/${item.id}` : 'tasks', { title, description, chapter, kind, due_at: instant(due), points_possible: points,
        published, group_id: group ? Number(group) : null, resource_ids: ids, questions: kind === 'quiz' ? questions : [],
        ...(item ? { expected_version: item.version } : {}) }, item ? 'PUT' : 'POST');
      onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không lưu được nhiệm vụ.'); }
    finally { setBusy(false); }
  };
  return <Modal open onClose={() => !busy && onClose()} title={item ? 'Sửa nhiệm vụ học tập' : 'Thêm nhiệm vụ học tập'} description="Sinh viên chỉ thấy nhiệm vụ đã xuất bản. Thời gian GMT+7.">
    <form onSubmit={save} className="space-y-4">
      <Input label="Tên nhiệm vụ" required maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} />
      <Input label="Chương / module của nhiệm vụ" maxLength={255} value={chapter} onChange={(event) => setChapter(event.target.value)} />
      <Textarea label="Yêu cầu / mô tả" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={20000} />
      <div className="grid gap-3 sm:grid-cols-2"><label className="space-y-1 text-sm font-semibold">Loại nhiệm vụ<select aria-label="Loại nhiệm vụ" className={inputClass} value={kind} disabled={submitted || item?.kind === 'quiz'} onChange={(event) => setKind(event.target.value as TeacherTask['kind'])}>
        {Object.entries(taskKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <Input label="Deadline (GMT+7)" type="datetime-local" required value={due} onChange={(event) => setDue(event.target.value)} />
        <Input label="Điểm tối đa của bài" type="number" min={0} max={10000} step="0.01" required disabled={submitted} value={points} onChange={(event) => setPoints(Number(event.target.value))} />
        <label className="space-y-1 text-sm font-semibold">Nhóm đánh giá<select aria-label="Nhóm đánh giá" className={inputClass} value={group} onChange={(event) => setGroup(event.target.value)}><option value="">Chưa phân nhóm</option>
          {data.weights.groups.map((row) => <option key={row.id} value={row.id}>{row.name} — {row.weight}% điểm môn</option>)}</select></label>
      </div>
      {submitted && <p className="text-sm text-warning-ink">Đã có bài nộp: khóa loại, thang điểm và câu hỏi để giữ lịch sử chấm.</p>}
      {kind === 'quiz' && <fieldset className="space-y-3 rounded-xl border border-line p-3"><legend className="text-sm font-semibold">Câu hỏi quiz tính điểm — không phải Assessment trong Do</legend>
        {questions.map((question, index) => <div key={index} className="space-y-2 border-b border-line pb-3">
          <Input label={`Câu ${index + 1}`} required disabled={submitted} value={question.prompt} onChange={(event) => setQuestions(questions.map((q, i) => i === index ? { ...q, prompt: event.target.value } : q))} />
          {question.options.map((option, oi) => <Input key={oi} label={`Câu ${index + 1} — lựa chọn ${oi + 1}`} required disabled={submitted} value={option} onChange={(event) => setQuestions(questions.map((q, i) => i === index ? { ...q, options: q.options.map((o, j) => j === oi ? event.target.value : o), correct_answer: q.correct_answer === option ? event.target.value : q.correct_answer } : q))} />)}
          <label className="text-sm">Đáp án đúng<select aria-label={`Đáp án câu ${index + 1}`} className={inputClass} disabled={submitted} value={question.correct_answer} onChange={(event) => setQuestions(questions.map((q, i) => i === index ? { ...q, correct_answer: event.target.value } : q))}><option value="">Chọn đáp án</option>{question.options.map((option, oi) => <option key={oi} value={option}>{option || `Lựa chọn ${oi + 1}`}</option>)}</select></label>
          <Input label={`Điểm câu ${index + 1}`} type="number" required min={0.01} step="0.01" disabled={submitted} value={question.points} onChange={(event) => setQuestions(questions.map((q, i) => i === index ? { ...q, points: Number(event.target.value) } : q))} />
          <Button type="button" variant="ghost" disabled={submitted} onClick={() => setQuestions(questions.filter((_, i) => i !== index))}>Bỏ câu {index + 1}</Button>
        </div>)}
        <Button type="button" variant="secondary" disabled={submitted} onClick={() => setQuestions([...questions, { prompt: '', options: ['', '', '', ''], correct_answer: '', points: 1 }])}>Thêm câu hỏi</Button>
        <p className="text-sm text-muted">Tổng điểm câu hỏi: {questions.reduce((sum, q) => sum + q.points, 0)} / {points}.</p>
      </fieldset>}
      <ResourcePicker data={data} ids={ids} onChange={setIds} />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={published} onChange={(event) => setPublished(event.target.checked)} />Xuất bản cho sinh viên</label>
      {error && <p role="alert" className="text-sm text-danger-ink">{error}</p>}
      <div className="flex justify-end gap-2"><Button type="button" variant="secondary" disabled={busy} onClick={onClose}>Đóng</Button><Button type="submit" loading={busy}>Lưu nhiệm vụ</Button></div>
    </form>
  </Modal>;
}

export function addAttendanceWeight(groups: TeacherManagementData['weights']['groups'], attendanceWeight = 10) {
  const total = groups.reduce((sum, row) => sum + row.weight, 0);
  if (!groups.length || total <= 0) return [...groups, { name: 'Chuyên cần', weight: attendanceWeight }];
  const available = 100 - attendanceWeight;
  const scaled = groups.map((row) => ({ ...row, weight: Math.round((row.weight / total) * available * 100) / 100 }));
  const remainder = Math.round((available - scaled.reduce((sum, row) => sum + row.weight, 0)) * 100) / 100;
  if (remainder) {
    const largest = scaled.reduce((best, row, index) => row.weight > scaled[best].weight ? index : best, 0);
    scaled[largest] = { ...scaled[largest], weight: Math.round((scaled[largest].weight + remainder) * 100) / 100 };
  }
  return [...scaled, { name: 'Chuyên cần', weight: attendanceWeight }];
}

export function WeightsForm({ data, mutate, onClose }: { data: TeacherManagementData; mutate: Mutate; onClose: () => void }) {
  const [groups, setGroups] = useState(data.weights.groups); const [version] = useState(data.weights.version);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const total = groups.reduce((sum, row) => sum + row.weight, 0);
  return <Modal open onClose={() => !busy && onClose()} title="Cấu hình trọng số điểm môn" description="Trọng số theo nhóm; khác với điểm tối đa của từng bài. Tổng phải là 100%.">
    <form className="space-y-4" onSubmit={async (event) => { event.preventDefault(); setBusy(true); setError(''); try {
      await mutate('weights', { groups, expected_version: version }, 'PUT'); onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không lưu được.'); } finally { setBusy(false); } }}>
      {groups.map((row, index) => <div key={index} className="flex items-end gap-2"><Input label={`Nhóm ${index + 1}`} required maxLength={255} value={row.name} onChange={(event) => setGroups(groups.map((g, i) => i === index ? { ...g, name: event.target.value } : g))} />
        <Input label={`Trọng số nhóm ${index + 1} (%)`} type="number" required min={0} max={100} step="0.01" value={row.weight} onChange={(event) => setGroups(groups.map((g, i) => i === index ? { ...g, weight: Number(event.target.value) } : g))} />
        <Button type="button" variant="ghost" onClick={() => setGroups(groups.filter((_, i) => i !== index))}>Bỏ</Button></div>)}
      <div className="flex flex-wrap gap-2"><Button type="button" variant="secondary" onClick={() => setGroups([...groups, { name: '', weight: 0 }])}>Thêm nhóm</Button>
        {!groups.some((row) => /chuy[eê]n c[aầ]n|attendance/i.test(row.name)) && groups.length > 0 && <Button type="button" variant="secondary" onClick={() => setGroups(addAttendanceWeight(groups))}>Thêm Chuyên cần 10%</Button>}
      </div>
      <p className="text-sm font-semibold">Tổng trọng số: {total.toFixed(2)}%</p><p className="text-sm text-muted">Không xóa nhóm đang có bài tập. Thay đổi trọng số có thể làm đổi ưu tiên Plan, không tự ghi điểm cho sinh viên.</p>
      {groups.some((row) => /chuy[eê]n c[aầ]n|attendance/i.test(row.name)) && <p className="text-sm text-muted">Chuyên cần là nhóm điểm riêng; PaceWise không tự suy điểm chỉ từ thời gian online. Hãy gắn mục điểm chuyên cần vào nhóm này khi ghi nhận kết quả cuối kỳ.</p>}
      {error && <p role="alert" className="text-danger-ink">{error}</p>}<Button type="submit" loading={busy} disabled={Math.abs(total - 100) > .005 || !groups.length}>Lưu trọng số</Button>
    </form>
  </Modal>;
}

export function LessonForm({ item, data, mutate, onClose, previewOnly = false }: { item?: TeacherLesson; data: TeacherManagementData; mutate: Mutate; onClose: () => void; previewOnly?: boolean }) {
  const [title, setTitle] = useState(item?.title ?? ''); const [description, setDescription] = useState(item?.description ?? '');
  const [start, setStart] = useState(item ? localDateTime(item.starts_at) : ''); const [end, setEnd] = useState(item ? localDateTime(item.ends_at) : '');
  const [mode, setMode] = useState<TeacherLesson['mode']>(item?.mode ?? 'offline'); const [location, setLocation] = useState(item?.location ?? '');
  const [url, setUrl] = useState(item?.meeting_url ?? ''); const [repeatWeekly, setRepeatWeekly] = useState(false);
  const [repeat, setRepeat] = useState(2); const [ids, setIds] = useState(item?.resource_ids ?? []);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const duration = start && end ? (Date.parse(`${end}:00+07:00`) - Date.parse(`${start}:00+07:00`)) / 60000 : null;
  return <Modal open onClose={() => !busy && onClose()} title={previewOnly ? 'Sửa các buổi tương lai của chuỗi' : item ? 'Sửa buổi học' : 'Thêm buổi học'} description={previewOnly ? 'Đổi tên, hình thức và giờ cho các buổi còn lại. Ngày/giờ dịch cùng độ lệch so với buổi đang chọn; số buổi không đổi. Chỉ lưu sau khi xem và xác nhận.' : 'GMT+7. Buổi học được cập nhật cho sinh viên; không tự thay kế hoạch tự học.'}>
    <form className="space-y-4" onSubmit={async (event) => { event.preventDefault(); setBusy(true); setError(''); try {
      if (!duration || duration <= 0 || duration > 720) throw new Error('Thời lượng phải lớn hơn 0 và tối đa 12 giờ.');
      await mutate(item ? `lessons/${item.id}` : 'lessons', { title, description, starts_at: instant(start), ends_at: instant(end), mode,
        location, meeting_url: mode === 'online' ? url : '', repeat_count: repeatWeekly ? repeat : 1, resource_ids: ids,
        ...(item ? { expected_version: item.version } : {}) }, item ? 'PUT' : 'POST'); onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Không lưu được buổi học.'); } finally { setBusy(false); } }}>
      <Input label="Tên buổi học" required maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} />
      <div className="grid gap-3 sm:grid-cols-2"><Input label="Bắt đầu (GMT+7)" type="datetime-local" required value={start} onChange={(event) => setStart(event.target.value)} />
        <Input label="Kết thúc (GMT+7)" type="datetime-local" required value={end} onChange={(event) => setEnd(event.target.value)} /></div>
      {duration !== null && <p className="text-sm">Thời lượng: {duration} phút.</p>}
      <label className="text-sm font-semibold">Hình thức<select aria-label="Hình thức" className={inputClass} value={mode} onChange={(event) => setMode(event.target.value as TeacherLesson['mode'])}><option value="offline">Offline</option><option value="online">Online</option></select></label>
      {mode === 'offline' ? <Input label="Phòng / địa điểm" maxLength={255} value={location} onChange={(event) => setLocation(event.target.value)} /> : <Input label="Link buổi học (HTTPS)" type="url" pattern="https://.*" required maxLength={500} value={url} onChange={(event) => setUrl(event.target.value)} />}
      <Textarea label="Nội dung / chuẩn bị" maxLength={5000} value={description} onChange={(event) => setDescription(event.target.value)} />
      {!item && <fieldset className="space-y-3 rounded-xl border border-line p-3"><legend className="px-1 text-sm font-semibold">Lặp lịch (tùy chọn)</legend>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={repeatWeekly} onChange={(event) => setRepeatWeekly(event.target.checked)} />Lặp lại buổi này mỗi tuần</label>
        {repeatWeekly && <Input label="Tổng số buổi trong chuỗi (2–16)" type="number" min={2} max={16} required value={repeat} onChange={(event) => setRepeat(Number(event.target.value))} />}
        <p className="text-sm text-muted">Ví dụ 8 buổi sẽ tạo buổi hiện tại và 7 tuần tiếp theo. Buổi học một lần không cần bật.</p>
      </fieldset>}
      <ResourcePicker data={data} ids={ids} onChange={setIds} />{error && <p role="alert" className="text-danger-ink">{error}</p>}
      <div className="flex justify-end gap-2"><Button type="button" variant="secondary" disabled={busy} onClick={onClose}>Đóng</Button><Button type="submit" loading={busy}>{previewOnly ? 'Xem trước thay đổi chuỗi' : 'Lưu buổi học'}</Button></div>
    </form>
  </Modal>;
}
