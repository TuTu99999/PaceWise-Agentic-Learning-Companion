import { useEffect, useRef, useState } from 'react';
import { uploadTeacherDocument, type CourseDocumentRole } from '../../services/api';
import { coursePdfMaxMb } from '../../services/courseSource';
import { Button } from '../ui/Button';
import { Select } from '../ui/Field';

interface UploadRow {
  id: string; file: File; chapter: string; contentRole: CourseDocumentRole;
  status: 'waiting' | 'uploading' | 'saved' | 'failed'; error?: string;
}

export function PdfUpload({ courseId, chapters, onUploaded }: { courseId: string; chapters: string[]; onUploaded: () => Promise<void> }) {
  const [chapter, setChapter] = useState('');
  const [contentRole, setContentRole] = useState<CourseDocumentRole>('learning_material');
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    generation.current++; setRows([]); setBusy(false); setChapter(''); setContentRole('learning_material'); setMessage(''); setError('');
    return () => { generation.current++; };
  }, [courseId]);

  const upload = async (selected: UploadRow[]) => {
    if (busy || !selected.length) return;
    if (selected.some((row) => !row.chapter.trim())) { setError('Gắn chương cho từng tài liệu trước khi tải.'); return; }
    const active = generation.current;
    const update = (id: string, patch: Partial<UploadRow>) => {
      if (generation.current === active) setRows((current) => current.map((row) => row.id === id ? { ...row, ...patch } : row));
    };
    setBusy(true); setError(''); setMessage('');
    let saved = 0;
    for (const row of selected) {
      if (generation.current !== active) break;
      update(row.id, { status: 'uploading', error: undefined });
      try {
        const result = await uploadTeacherDocument(courseId, row.file, row.chapter.trim(), row.contentRole);
        saved++; update(row.id, { status: 'saved' });
        if (generation.current === active) setMessage(result?.duplicate
          ? `${row.file.name}: đã có cùng nội dung trong chương này; không tạo bản trùng.`
          : `Đã lưu ${saved} tài liệu. Theo dõi xử lý từng file bên dưới.`);
      } catch (reason) {
        update(row.id, { status: 'failed', error: reason instanceof Error ? reason.message : 'Không tải được file.' });
      }
    }
    if (saved && generation.current === active) {
      try { await onUploaded(); }
      catch { if (generation.current === active) setError('Tài liệu đã lưu; chưa cập nhật được danh sách. Không cần tải lại file đã lưu.'); }
    }
    if (generation.current === active) setBusy(false);
  };

  return <div className="space-y-3">
    <Select label="Loại nội dung" required disabled={busy} value={contentRole} onChange={(event) => setContentRole(event.target.value as CourseDocumentRole)}
      options={[
        { value: 'learning_material', label: 'Slide / học liệu' },
        { value: 'student_assignment_brief', label: 'Đề bài cho sinh viên' },
        { value: 'student_rubric', label: 'Rubric công khai' },
        { value: 'mixed_assignment_package', label: 'Word có đề + rubric + đáp án' },
        { value: 'teacher_solution', label: 'Đáp án chỉ giảng viên' },
      ]} />
    <Select label="Chương / module của tài liệu" required disabled={busy || !chapters.length} value={chapter} onChange={(event) => setChapter(event.target.value)}
      hint={chapters.length ? 'Word nhiều chương có thể chọn “Bài tập theo chương”; hệ thống tiếp tục khớp theo heading bên trong.' : 'Chưa có chủ đề buổi học. Hãy thêm hoặc nhập lịch học trước khi tải tài liệu.'}
      options={[{ value: '', label: chapters.length ? 'Chọn chương / chủ đề' : 'Chưa có chủ đề từ lịch học' }, { value: 'Bài tập theo chương', label: 'Bài tập theo chương (Word nhiều chương)' }, ...chapters.map((item) => ({ value: item, label: item }))]} />
    <label className={`inline-flex min-h-11 items-center rounded-xl border border-line bg-white px-4 text-sm font-semibold ${chapter && !busy ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}>
      {`Thêm PDF hoặc Word (≤ ${coursePdfMaxMb} MB/file)`}
      <input aria-label="Tải tài liệu môn học" type="file" multiple accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx" disabled={busy || !chapter} className="sr-only" onChange={(event) => {
        const files = Array.from(event.target.files ?? []); event.target.value = '';
        if (!files.length) return;
        if (files.length + rows.filter((row) => row.status !== 'saved').length > 20) { setError('Mỗi hàng chờ tối đa 20 tài liệu.'); return; }
        if (files.some((file) => !file.size || file.size > coursePdfMaxMb * 1024 * 1024 || !/\.(pdf|docx)$/i.test(file.name))) {
          setError(`Chỉ nhận PDF hoặc DOCX có nội dung, tối đa ${coursePdfMaxMb} MB/file.`); return;
        }
        setError('');
        setRows((current) => [...current.filter((row) => row.status !== 'saved'), ...files.map((file): UploadRow => ({ id: crypto.randomUUID(), file, chapter, contentRole, status: 'waiting' }))]);
      }} />
    </label>
    <p className="text-sm text-muted">Với Word chứa cả đáp án, chọn đúng loại hỗn hợp. PaceWise lưu bản gốc cho giảng viên và chỉ đưa bản đã loại đáp án cho Plan, Do và chatbot.</p>
    <ul className="space-y-3" aria-label="Hàng chờ tải tài liệu">{rows.filter((row) => row.status !== 'saved').map((row) =>
      <li key={row.id} className="space-y-2 rounded-xl border border-line p-3">
        <p className="break-words font-medium">{row.file.name}</p>
        <Select label={`Chương của ${row.file.name}`} required value={row.chapter} disabled={busy}
          options={[{ value: '', label: 'Chọn chương / chủ đề' }, { value: 'Bài tập theo chương', label: 'Bài tập theo chương (Word nhiều chương)' }, ...chapters.map((item) => ({ value: item, label: item }))]}
          onChange={(event) => setRows((current) => current.map((item) => item.id === row.id ? { ...item, chapter: event.target.value } : item))} />
        <Select label={`Loại nội dung của ${row.file.name}`} required value={row.contentRole} disabled={busy}
          options={[
            { value: 'learning_material', label: 'Slide / học liệu' }, { value: 'student_assignment_brief', label: 'Đề bài cho sinh viên' },
            { value: 'student_rubric', label: 'Rubric công khai' }, { value: 'mixed_assignment_package', label: 'Word có đề + rubric + đáp án' },
            { value: 'teacher_solution', label: 'Đáp án chỉ giảng viên' },
          ]}
          onChange={(event) => setRows((current) => current.map((item) => item.id === row.id ? { ...item, contentRole: event.target.value as CourseDocumentRole } : item))} />
        <p role={row.status === 'failed' ? 'alert' : 'status'} className="text-sm text-muted">{row.status === 'uploading' ? 'Đang tải…' : row.status === 'failed' ? row.error : 'Chờ tải'}</p>
        <div className="flex gap-2">
          {row.status === 'failed' && <Button variant="secondary" disabled={busy} onClick={() => void upload([row])}>Thử tải lại</Button>}
          <Button variant="ghost" disabled={busy} onClick={() => setRows((current) => current.filter((item) => item.id !== row.id))}>Bỏ file</Button>
        </div>
      </li>)}</ul>
    {rows.some((row) => row.status === 'waiting') && <Button loading={busy} onClick={() => void upload(rows.filter((row) => row.status === 'waiting'))}>Tải {rows.filter((row) => row.status === 'waiting').length} tài liệu</Button>}
    {message && <p role="status" className="text-sm text-muted">{message}</p>}
    {error && <p role="alert" className="text-sm text-danger-ink">{error}</p>}
  </div>;
}
