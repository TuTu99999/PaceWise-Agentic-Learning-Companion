import { useEffect, useRef, useState } from 'react';
import { uploadTeacherDocument, type CourseDocumentRole } from '../../services/api';
import { coursePdfMaxMb } from '../../services/courseSource';
import { Button } from '../ui/Button';
import { Input, Select } from '../ui/Field';
import { useLocale } from '../../i18n/LocaleContext';

interface UploadRow {
  id: string; file: File; chapter: string; contentRole: CourseDocumentRole;
  status: 'waiting' | 'uploading' | 'saved' | 'failed'; error?: string;
}

const AUTO_DETECT_CHAPTER = 'Bài tập theo chương';
const CUSTOM_CHAPTER = '__custom_chapter__';

export function PdfUpload({ courseId, chapters, onUploaded }: { courseId: string; chapters: string[]; onUploaded: () => Promise<void> }) {
  const { locale, t } = useLocale();
  const [chapter, setChapter] = useState('');
  const [chapterChoice, setChapterChoice] = useState('');
  const [contentRole, setContentRole] = useState<CourseDocumentRole>('learning_material');
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => {
    generation.current++; setRows([]); setBusy(false); setChapter(''); setChapterChoice(''); setContentRole('learning_material'); setMessage(''); setError('');
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

  const roleOptions = [
    { value: 'learning_material', label: t('Slide / học liệu', 'Slides / materials') },
    { value: 'student_assignment_brief', label: t('Đề bài cho sinh viên', 'Student assignment brief') },
    { value: 'student_rubric', label: t('Rubric công khai', 'Public rubric') },
    { value: 'mixed_assignment_package', label: t('Word có đề + rubric + đáp án', 'Word file with brief, rubric, and answers') },
    { value: 'teacher_solution', label: t('Đáp án chỉ giảng viên', 'Instructor-only answers') },
  ];
  const isExerciseRole = (role: CourseDocumentRole) => role !== 'learning_material';
  const chapterOptions = (role: CourseDocumentRole, includePlaceholder = false) => [
    ...(includePlaceholder ? [{ value: '', label: t('Chọn cách gắn chương', 'Choose how to assign a chapter') }] : []),
    ...(isExerciseRole(role) ? [{ value: AUTO_DETECT_CHAPTER, label: t('Tự nhận diện nhiều chương trong Word', 'Detect multiple chapters from Word') }] : []),
    ...chapters.filter((item) => item !== AUTO_DETECT_CHAPTER).map((item) => ({ value: item, label: item })),
    { value: CUSTOM_CHAPTER, label: t('Nhập tên chương khác…', 'Enter another chapter…') },
  ];
  const chapterHint = isExerciseRole(contentRole)
    ? t('Nếu Word có nhiều phần, chọn tự nhận diện để PaceWise khớp từng heading Buổi/Chương với nhiệm vụ. File một chương thì chọn hoặc nhập đúng tên chương.', 'For a Word file with multiple sections, use auto-detection so PaceWise can match each Session/Chapter heading to its task. For a single chapter, choose or enter its exact name.')
    : t('Chọn chương bài giảng từ danh sách hoặc nhập tên chương mới. Ví dụ: “Chương 4: Ngôn ngữ SQL”.', 'Choose the lecture chapter or enter a new chapter name. Example: “Chapter 4: SQL”.');

  return <div className="space-y-3">
    <Select label={t('Loại nội dung', 'Content type')} required disabled={busy} value={contentRole} onChange={(event) => {
      const next = event.target.value as CourseDocumentRole;
      const nextChapter = next === 'learning_material' && chapter === AUTO_DETECT_CHAPTER ? '' : chapter;
      setContentRole(next);
      if (next === 'learning_material' && chapter === AUTO_DETECT_CHAPTER) {
        setChapter('');
        setChapterChoice('');
      }
      setRows((current) => current.map((row) => ({ ...row, contentRole: next, chapter: nextChapter })));
    }}
      options={[
        ...roleOptions,
      ]} />
    <Select label={t('Chương / module của tài liệu', 'Document chapter / module')} required disabled={busy}
      value={chapterChoice} options={chapterOptions(contentRole, true)} hint={chapterHint}
      onChange={(event) => {
        const next = event.target.value;
        const nextChapter = next === CUSTOM_CHAPTER ? '' : next;
        setChapterChoice(next);
        setChapter(nextChapter);
        setRows((current) => current.map((row) => ({ ...row, chapter: nextChapter })));
      }} />
    {chapterChoice === CUSTOM_CHAPTER && <Input
      label={t('Tên chương / module mới', 'New chapter / module name')}
      required disabled={busy} autoFocus maxLength={255} value={chapter}
      placeholder={t('Ví dụ: Chương 4: Ngôn ngữ SQL', 'Example: Chapter 4: SQL')}
      onChange={(event) => {
        setChapter(event.target.value);
        setRows((current) => current.map((row) => ({ ...row, chapter: event.target.value })));
      }}
    />}
    <label className={`inline-flex min-h-11 items-center rounded-xl border border-line bg-white px-4 text-sm font-semibold ${chapter && !busy ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}>
      {locale === 'en' ? `Add PDF or Word (≤ ${coursePdfMaxMb} MB/file)` : `Thêm PDF hoặc Word (≤ ${coursePdfMaxMb} MB/file)`}
      <input aria-label={t('Tải tài liệu môn học', 'Upload course materials')} type="file" multiple accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx" disabled={busy || !chapter} className="sr-only" onChange={(event) => {
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
    <p className="text-sm text-muted">{t('Với Word chứa cả đáp án, chọn đúng loại hỗn hợp. PaceWise lưu bản gốc cho giảng viên và chỉ đưa bản đã loại đáp án cho Plan, Do và chatbot.', 'For a Word file that includes answers, choose the mixed package type. PaceWise keeps the original for instructors and gives Plan, Do, and the chatbot only the answer-free version.')}</p>
    <ul className="space-y-3" aria-label={t('Hàng chờ tải tài liệu', 'Material upload queue')}>{rows.filter((row) => row.status !== 'saved').map((row) =>
      <li key={row.id} className="space-y-2 rounded-xl border border-line p-3">
        <p className="break-words font-medium">{row.file.name}</p>
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
