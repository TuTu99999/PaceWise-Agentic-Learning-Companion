import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Badge } from '../../components/ui/Badge';
import { Button, IconButton } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Input, Select, Textarea } from '../../components/ui/Field';
import { PageHeader } from '../../components/ui/PageHeader';
import { EmptyState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useTeacherManagement } from '../../hooks/useTeacherManagement';
import { useAppStore } from '../../store/AppStore';
import { saveInstructorAction } from '../../services/api';
import type { AssessmentItem, AssessmentStatus, Tone } from '../../types';
import { useLocale } from '../../i18n/LocaleContext';

const statusMeta: Record<AssessmentStatus, { label: string; tone: Tone }> = {
  draft: { label: 'Bản nháp', tone: 'neutral' },
  review: { label: 'Chờ duyệt', tone: 'warning' },
  approved: { label: 'Đã duyệt', tone: 'success' },
  rejected: { label: 'Bị trả lại', tone: 'danger' },
};

// Stage/level are retained only as a backwards-compatible storage detail.
// Teachers author an open question and its expected ideas; the Assessment Agent
// decides what the student's answer demonstrates from that approved rubric.
const INTERNAL_ASSESSMENT_STAGE = 'explain' as const;

interface Errors {
  source?: string;
  questions?: Record<string, { question?: string; rubric?: string }>;
  note?: string;
}

interface QuestionDraft {
  id: string;
  question: string;
  rubric: string[];
  original?: AssessmentItem;
}

const newQuestionId = () => `assessment-${globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;

const normalizedChapter = (value: string) => value.trim().toLocaleLowerCase('vi').replace(/\s+/g, ' ');
const chapterNumber = (value: string) => normalizedChapter(value).match(/(?:chương|chapter)\s*(\d+)/)?.[1];
const sameChapter = (left: string, right: string) => {
  if (normalizedChapter(left) === normalizedChapter(right)) return true;
  const leftNumber = chapterNumber(left);
  return Boolean(leftNumber && leftNumber === chapterNumber(right));
};

export const chapterKnowledgeComponentId = (courseId: string | undefined, chapter: string) => {
  const courseKey = String(courseId ?? 'course').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const chapterKey = normalizedChapter(chapter)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 100);
  return chapterKey ? `chapter:${courseKey || 'course'}:${chapterKey}` : undefined;
};

export function AssessmentEditPage() {
  const { locale, t } = useLocale();
  const { itemId } = useParams();
  const { state, dispatch } = useAppStore();
  const navigate = useNavigate();
  const toast = useToast();
  const item = state.assessments.find((a) => a.id === itemId);
  const courseId = item?.courseId ?? state.user?.courseId;
  const { data: courseMaterials, loading: materialsLoading, error: materialsError } = useTeacherManagement(courseId);
  useDocumentTitle(t('Sửa bộ câu hỏi'));

  const [sourceResourceId, setSourceResourceId] = useState<number | undefined>(item?.sourceResourceId);
  const [sourceChapter, setSourceChapter] = useState(item?.sourceChapter ?? '');
  const components = state.teacherWorkspace.courseStructure.knowledgeComponents.filter((component) => component.status === 'approved');
  const modules = state.teacherWorkspace.courseStructure.modules ?? [];
  const assessmentSetId = item?.assessmentSetId ?? item?.id ?? '';
  const [questions, setQuestions] = useState<QuestionDraft[]>(() => {
    if (!item) return [];
    const grouped = state.assessments.filter((assessment) => (
      (assessment.assessmentSetId ?? assessment.id) === assessmentSetId
    ));
    const drafts: QuestionDraft[] = (grouped.length ? grouped : [item]).map((assessment) => ({
      id: assessment.id,
      question: assessment.question,
      rubric: assessment.rubric.length ? assessment.rubric : ['', ''],
      original: assessment,
    }));
    if ((item.version ?? 0) === 0 && !item.question.trim()) {
      while (drafts.length < 3) drafts.push({ id: newQuestionId(), question: '', rubric: ['', ''] });
    }
    return drafts;
  });
  const [openQuestionId, setOpenQuestionId] = useState(() => questions[0]?.id ?? '');
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const sourceInitialized = useRef(false);

  const resources = useMemo(() => courseMaterials?.resources ?? [], [courseMaterials?.resources]);
  const chapterOptions = useMemo(() => [...new Set(resources.map((resource) => resource.chapter?.trim() ?? '').filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, 'vi')), [resources]);
  const selectedModule = modules.find((module) => sourceChapter && sameChapter(module.title, sourceChapter));
  const scopedComponents = selectedModule
    ? components.filter((component) => component.moduleId === selectedModule.id)
    : [];
  const mappedComponent = scopedComponents.find((component) => item?.knowledgeComponentIds?.includes(component.id))
    ?? scopedComponents[0];
  const chapterResources = sourceChapter
    ? resources.filter((resource) => resource.chapter && sameChapter(resource.chapter, sourceChapter))
    : [];
  const selectedResource = resources.find((resource) => resource.id === sourceResourceId);
  const knowledgeComponentId = mappedComponent?.id
    ?? (selectedResource ? chapterKnowledgeComponentId(courseId, sourceChapter) : undefined);
  const knowledgeComponentIds = knowledgeComponentId ? [knowledgeComponentId] : [];
  const source = selectedResource?.title ?? '';
  useEffect(() => {
    if (!resources.length || sourceInitialized.current) return;
    sourceInitialized.current = true;
    const linked = item?.sourceResourceId
      ? resources.find((resource) => resource.id === item.sourceResourceId)
      : resources.find((resource) => resource.title.trim() === item?.source?.trim());
    if (linked) {
      setSourceResourceId(linked.id);
      if (linked.chapter) setSourceChapter((current) => current || linked.chapter || '');
      return;
    }
    if (chapterOptions.length === 1) setSourceChapter((current) => current || chapterOptions[0]);
  }, [chapterOptions, item?.source, item?.sourceResourceId, resources]);

  if (!item) {
    return (
      <div className="page max-w-3xl">
        <EmptyState
          icon="clipboard"
          title={t('Không tìm thấy câu hỏi')}
          description={t('Câu hỏi này có thể đã bị xoá hoặc đường dẫn chưa đúng.')}
          action={
            <Link to="/instructor/assessment" className="font-semibold text-primary-ink underline">
              {t('Về Thiết kế kiểm chứng')}
            </Link>
          }
        />
      </div>
    );
  }

  const questionDesign: NonNullable<AssessmentItem['questionDesign']> = {
    mode: 'fixed', relation_property: 'transitive', stages: [INTERNAL_ASSESSMENT_STAGE], reference_text: '',
  };
  const questionPayload = (draft: QuestionDraft, index: number): AssessmentItem => ({
    id: draft.id,
    assessmentSetId,
    courseId: item.courseId,
    topic: sourceChapter ? `${sourceChapter} · Câu ${index + 1}` : item.topic,
    question: draft.question.trim(),
    rubric: draft.rubric.map((value) => value.trim()).filter(Boolean),
    status: draft.original?.status ?? item.status,
    level: 'conceptual',
    source,
    sourceResourceId,
    sourceChapter,
    moduleId: selectedModule?.id ?? mappedComponent?.moduleId,
    answerType: 'open',
    assessmentStage: INTERNAL_ASSESSMENT_STAGE,
    hints: draft.original?.hints ?? item.hints ?? [],
    knowledgeComponentIds,
    kcProvisional: knowledgeComponentIds.length === 0,
    questionDesign,
    aiGenerated: draft.original?.aiGenerated ?? false,
    assignmentTitle: item.assignmentTitle,
    weekStart: item.weekStart,
    weekEnd: item.weekEnd,
    version: draft.original?.version ?? 0,
  });

  const validate = (needNote = false) => {
    const next: Errors = {};
    if (!sourceChapter || !sourceResourceId || !source) next.source = t('Chọn một tài liệu đã tải lên cho chương này.');
    const questionErrors: NonNullable<Errors['questions']> = {};
    questions.forEach((draft) => {
      const entry: { question?: string; rubric?: string } = {};
      if (draft.question.trim().length < 10) entry.question = t('Câu hỏi cần ít nhất 10 ký tự.');
      if (draft.rubric.map((value) => value.trim()).filter(Boolean).length < 2) entry.rubric = t('Cần ít nhất 2 ý để AI đánh giá câu trả lời.');
      if (entry.question || entry.rubric) questionErrors[draft.id] = entry;
    });
    if (Object.keys(questionErrors).length) next.questions = questionErrors;
    if (needNote && !note.trim()) next.note = t('Nhập ghi chú để người soạn biết cần sửa gì.');
    setErrors(next);
    if (Object.keys(questionErrors).length) setOpenQuestionId(Object.keys(questionErrors)[0]);
    return Object.keys(next).length === 0;
  };

  const persist = async (
    status: AssessmentStatus | undefined,
    historyText: string,
    extra: Record<string, unknown> = {},
  ) => {
    setSaving(true);
    setSaveError('');
    try {
      for (const [index, draft] of questions.entries()) {
        const payload = questionPayload(draft, index);
        const saved = await saveInstructorAction('assessment', payload.id, { ...payload, ...extra, ...(status ? { status } : {}) });
        const savedItem = {
          ...payload,
          status: status ?? payload.status,
          version: Number(saved.payload.version ?? payload.version ?? 1),
        };
        if (!state.assessments.some((assessment) => assessment.id === payload.id)) {
          dispatch({ type: 'ADD_ASSESSMENT_DRAFT', item: savedItem });
        }
        dispatch({
          type: 'UPDATE_ASSESSMENT',
          item: savedItem,
          status,
          note: typeof extra.note === 'string' ? extra.note : undefined,
          historyText,
        });
      }
      return true;
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t('Chưa lưu được thay đổi.'));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const approve = async () => {
    if (!validate()) return;
    if (!await persist('approved', 'Duyệt và xuất bản')) return;
    toast({ tone: 'success', title: t('Đã duyệt và xuất bản') });
    navigate('/instructor/assessment');
  };
  const saveDraft = async () => {
    if (!validate()) return;
    if (!await persist(item.status, 'Lưu thay đổi')) return;
    toast({ tone: 'info', title: t('Đã lưu nháp') });
    navigate('/instructor/assessment');
  };
  const sendBack = async () => {
    if (!validate(true)) return;
    if (!await persist('rejected', 'Trả lại kèm ghi chú', { note: note.trim() })) return;
    toast({ tone: 'info', title: t('Đã trả lại kèm ghi chú') });
    navigate('/instructor/assessment');
  };

  const meta = statusMeta[item.status];

  return (
    <div className="page max-w-6xl">
      <PageHeader
        back={{ to: '/instructor/assessment', label: t('Thiết kế kiểm chứng') }}
        eyebrow={
          <Badge tone={meta.tone}>{t(meta.label)}</Badge>
        }
        title={t('Sửa bộ câu hỏi kiểm chứng')}
        description={t('Soạn tối đa 5 câu cho cùng một chương. Mỗi câu được lưu riêng để chatbot chọn và kiểm chứng khi cần.')}
      />

      <div>
        <Card aria-labelledby="edit-title">
          <CardHeader id="edit-title" title={t('Bộ câu hỏi tự luận')} />
          <div className="space-y-5">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Select
                label={t('Chương')}
                value={sourceChapter}
                onChange={(event) => {
                  const chapter = event.target.value;
                  setSourceChapter(chapter);
                  setSourceResourceId(undefined);
                }}
                options={[
                  { value: '', label: materialsLoading ? t('Đang tải chương…') : t('Chọn chương') },
                  ...chapterOptions.map((chapter) => ({ value: chapter, label: chapter })),
                ]}
                disabled={materialsLoading || chapterOptions.length === 0}
                error={errors.source && !sourceChapter ? errors.source : undefined}
              />
              <Select
                label={t('Tài liệu')}
                value={sourceResourceId ? String(sourceResourceId) : ''}
                onChange={(event) => setSourceResourceId(event.target.value ? Number(event.target.value) : undefined)}
                options={[
                  { value: '', label: sourceChapter ? t('Chọn tài liệu') : t('Chọn chương trước') },
                  ...chapterResources.map((resource) => ({ value: String(resource.id), label: resource.title })),
                ]}
                disabled={!sourceChapter || chapterResources.length === 0}
                error={errors.source && sourceChapter ? errors.source : undefined}
              />
            </div>
            {materialsError && <p role="alert" className="text-sm font-medium text-danger-ink">{materialsError}</p>}
            {!materialsLoading && !resources.length && (
              <p className="rounded-xl border border-warning/40 bg-warning-light p-3 text-sm text-warning-ink">
                {t('Chưa có tài liệu đã tải lên.')} <Link to="/instructor/courses" className="font-semibold underline">{t('Mở tab Môn học để thêm tài liệu')}</Link>.
              </p>
            )}
            {!materialsLoading && resources.length > 0 && chapterOptions.length === 0 && (
              <p className="rounded-xl border border-warning/40 bg-warning-light p-3 text-sm text-warning-ink">
                {t('Các tài liệu hiện chưa được gắn chương. Hãy gắn chương trong tab Môn học trước khi dùng làm nguồn kiểm chứng.')}
              </p>
            )}
            <div className="flex flex-wrap items-end justify-between gap-3 border-t border-line pt-5">
              <p className="text-sm font-semibold">{t('Câu hỏi')}</p>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-muted">{locale === 'en' ? `${questions.length}/5 questions` : `${questions.length}/5 câu`}</span>
            </div>

            <div className="space-y-3">
              {questions.map((draft, questionIndex) => {
                const expanded = openQuestionId === draft.id;
                const draftErrors = errors.questions?.[draft.id];
                const summary = draft.question.trim() || t('Chưa nhập câu hỏi');
                return (
                  <section key={draft.id} className={`overflow-hidden rounded-2xl border ${expanded ? 'border-primary/50 bg-white shadow-sm' : 'border-line bg-canvas/40'}`}>
                    <div className="flex items-center gap-2 p-3">
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        aria-expanded={expanded}
                        aria-controls={`question-panel-${draft.id}`}
                        onClick={() => setOpenQuestionId(expanded ? '' : draft.id)}
                      >
                        <span className="block text-sm font-bold text-primary-ink">{locale === 'en' ? `Question ${questionIndex + 1}` : `Câu ${questionIndex + 1}`}</span>
                        <span className="mt-0.5 block truncate text-sm text-muted">{summary}</span>
                      </button>
                      <span className="shrink-0 text-xs text-muted">{locale === 'en' ? `${draft.rubric.filter((value) => value.trim()).length} ideas` : `${draft.rubric.filter((value) => value.trim()).length} ý`}</span>
                      <IconButton
                        icon="trash"
                        label={locale === 'en' ? `Delete question ${questionIndex + 1}` : `Xoá câu ${questionIndex + 1}`}
                        disabled={questions.length <= 1}
                        onClick={() => {
                          const remaining = questions.filter((question) => question.id !== draft.id);
                          setQuestions(remaining);
                          if (expanded) setOpenQuestionId(remaining[0]?.id ?? '');
                        }}
                      />
                    </div>

                    {expanded && (
                      <div id={`question-panel-${draft.id}`} className="space-y-4 border-t border-line bg-white p-4">
                        <Textarea
                          label={locale === 'en' ? `Question ${questionIndex + 1}` : `Câu hỏi ${questionIndex + 1}`}
                          hint={t('Nên hỏi cách giải thích, lý do hoặc cách áp dụng; tránh câu chỉ cần trả lời Có/Không.')}
                          placeholder={t('Ví dụ: Hãy giải thích khái niệm này bằng lời của bạn và nêu vì sao nó được dùng trong tình huống trên.')}
                          value={draft.question}
                          onChange={(event) => setQuestions((current) => current.map((question) => (
                            question.id === draft.id ? { ...question, question: event.target.value } : question
                          )))}
                          error={draftErrors?.question}
                          rows={3}
                        />

                        <fieldset>
                          <legend className="mb-1 text-sm font-semibold">{t('Các ý đúng AI cần tìm')}</legend>
                          <p className="mb-3 text-xs text-muted">{t('Nhập 2–4 ý ngắn, cụ thể. AI đối chiếu từng ý với câu trả lời của sinh viên.')}</p>
                          <div className="space-y-2">
                            {draft.rubric.map((value, rubricIndex) => (
                              <div key={rubricIndex} className="flex items-end gap-2">
                                <span className="caption w-5 pb-3 text-center" aria-hidden="true">{rubricIndex + 1}</span>
                                <Input
                                  className="flex-1"
                                  label={locale === 'en' ? `Question ${questionIndex + 1}, required idea ${rubricIndex + 1}` : `Câu ${questionIndex + 1}, ý cần có ${rubricIndex + 1}`}
                                  hideLabel
                                  placeholder={[
                                    t('Ý chính hoặc khái niệm bắt buộc sinh viên phải nêu'),
                                    t('Lập luận, điều kiện hoặc cách áp dụng cần giải thích'),
                                    t('Ví dụ, kết quả hoặc giới hạn cần chỉ ra (nếu có)'),
                                    t('Điểm giúp phân biệt với cách hiểu sai phổ biến (nếu có)'),
                                  ][rubricIndex]}
                                  value={value}
                                  onChange={(event) => setQuestions((current) => current.map((question) => (
                                    question.id === draft.id
                                      ? { ...question, rubric: question.rubric.map((entry, index) => index === rubricIndex ? event.target.value : entry) }
                                      : question
                                  )))}
                                />
                                <IconButton
                                  icon="trash"
                                  label={locale === 'en' ? `Delete idea ${rubricIndex + 1} from question ${questionIndex + 1}` : `Xoá ý ${rubricIndex + 1} của câu ${questionIndex + 1}`}
                                  disabled={draft.rubric.length <= 2}
                                  onClick={() => setQuestions((current) => current.map((question) => (
                                    question.id === draft.id
                                      ? { ...question, rubric: question.rubric.filter((_, index) => index !== rubricIndex) }
                                      : question
                                  )))}
                                />
                              </div>
                            ))}
                          </div>
                          {draftErrors?.rubric && <p role="alert" className="mt-2 text-[13px] font-semibold text-danger-ink">{draftErrors.rubric}</p>}
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            icon="plus"
                            className="mt-3"
                            disabled={draft.rubric.length >= 4}
                            onClick={() => setQuestions((current) => current.map((question) => (
                              question.id === draft.id ? { ...question, rubric: [...question.rubric, ''] } : question
                            )))}
                          >
                            {t('Thêm ý cho câu này')}
                          </Button>
                        </fieldset>
                      </div>
                    )}
                  </section>
                );
              })}
            </div>

            <Button
              type="button"
              variant="secondary"
              icon="plus"
              disabled={questions.length >= 5}
              onClick={() => {
                const draft = { id: newQuestionId(), question: '', rubric: ['', ''] };
                setQuestions((current) => [...current, draft]);
                setOpenQuestionId(draft.id);
              }}
            >
              {t('Thêm câu hỏi')}
            </Button>

            {item.status === 'review' && (
              <Textarea
                label={t('Ghi chú khi trả lại')}
                hint={t('Chỉ bắt buộc khi bạn trả lại câu hỏi.')}
                placeholder={t('Ví dụ: thêm một tiêu chí về giả thuyết đối')}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                error={errors.note}
                rows={2}
              />
            )}
          </div>

          <div className="mt-6 flex flex-col gap-3 border-t border-line pt-5 sm:flex-row">
            {saveError && <p role="alert" className="w-full text-sm font-medium text-danger-ink">{saveError}</p>}
            <Button icon="check" onClick={() => void approve()} loading={saving}>
              {t(item.status === 'approved' ? 'Lưu và xuất bản' : 'Duyệt và xuất bản')}
            </Button>
            {item.status !== 'approved' && (
              <Button variant="secondary" onClick={() => void saveDraft()} loading={saving}>
                {t('Lưu nháp')}
              </Button>
            )}
            {item.status === 'review' && (
              <Button variant="ghost" className="sm:ml-auto" onClick={() => void sendBack()} loading={saving}>
                {t('Trả lại kèm ghi chú')}
              </Button>
            )}
          </div>

          {item.aiGenerated && (
            <p className="mt-4 rounded-xl bg-accent-light p-3 text-sm text-accent-ink">
              {t('Hệ thống đã gợi ý câu này từ học liệu môn học. Câu chỉ được dùng sau khi bạn duyệt.')}
            </p>
          )}
          {!!item.history?.length && (
            <details className="mt-4 rounded-xl border border-line p-4">
              <summary className="cursor-pointer font-semibold">{t('Xem lịch sử thay đổi')} ({item.history.length})</summary>
              <ol className="mt-3 space-y-2 text-sm">
                {item.history.map((history, index) => (
                  <li key={index}><span className="text-muted">{history.at}</span> · {history.text}</li>
                ))}
              </ol>
            </details>
          )}
        </Card>
      </div>
    </div>
  );
}
