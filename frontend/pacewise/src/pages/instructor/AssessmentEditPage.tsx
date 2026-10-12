import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Badge } from '../../components/ui/Badge';
import { Button, IconButton } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Input, Select, Textarea } from '../../components/ui/Field';
import { Icon } from '../../components/ui/Icon';
import { PageHeader } from '../../components/ui/PageHeader';
import { EmptyState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAppStore } from '../../store/AppStore';
import { previewQuestionDesign, saveInstructorAction } from '../../services/api';
import type { AssessmentItem, AssessmentStatus, Tone } from '../../types';

const statusMeta: Record<AssessmentStatus, { label: string; tone: Tone }> = {
  draft: { label: 'Bản nháp', tone: 'neutral' },
  review: { label: 'Chờ duyệt', tone: 'warning' },
  approved: { label: 'Đã duyệt', tone: 'success' },
  rejected: { label: 'Bị trả lại', tone: 'danger' },
};

const levels = [
  { value: 'recognition', label: 'Nhớ / nhận biết (Bloom 1)' },
  { value: 'conceptual', label: 'Hiểu và giải thích (Bloom 2)' },
  { value: 'application', label: 'Áp dụng (Bloom 3)' },
  { value: 'transfer', label: 'Phân tích / chuyển giao (Bloom 4+)' },
];
const answerTypes = [
  { value: 'open', label: 'Câu mở — rubric + HITL' },
  { value: 'multiple_choice', label: 'Trắc nghiệm lựa chọn' },
  { value: 'boolean', label: 'Đúng / sai' },
  { value: 'numeric', label: 'Giá trị số' },
  { value: 'exact_text', label: 'Chuỗi chính xác' },
];

interface Errors {
  question?: string;
  rubric?: string;
  note?: string;
}

export function AssessmentEditPage() {
  const { itemId } = useParams();
  const { state, dispatch } = useAppStore();
  const navigate = useNavigate();
  const toast = useToast();
  const item = state.assessments.find((a) => a.id === itemId);
  useDocumentTitle('Sửa câu hỏi');

  const [question, setQuestion] = useState(item?.question ?? '');
  const [level, setLevel] = useState(
    levels.some((entry) => entry.value === item?.level) ? item?.level ?? 'conceptual' : 'conceptual',
  );
  const [source, setSource] = useState(item?.source ?? '');
  const [answerType, setAnswerType] = useState(item?.answerType ?? 'open');
  const [assessmentStage, setAssessmentStage] = useState(item?.assessmentStage ?? (
    item?.level === 'recognition' ? 'recall' : item?.level === 'application' ? 'application' : item?.level === 'transfer' ? 'transfer' : 'explain'
  ));
  const [hints, setHints] = useState<string[]>(Array.from({ length: 5 }, (_, index) => item?.hints?.[index] ?? ''));
  const components = state.teacherWorkspace.courseStructure.knowledgeComponents.filter((component) => component.status === 'approved');
  const [knowledgeComponentIds, setKnowledgeComponentIds] = useState<string[]>(item?.knowledgeComponentIds ?? []);
  const [rubric, setRubric] = useState<string[]>(item?.rubric ?? ['']);
  const [designMode, setDesignMode] = useState<NonNullable<AssessmentItem['questionDesign']>['mode']>(item?.questionDesign?.mode ?? 'fixed');
  const [relationProperty, setRelationProperty] = useState<NonNullable<AssessmentItem['questionDesign']>['relation_property']>(item?.questionDesign?.relation_property ?? 'transitive');
  const [referenceText, setReferenceText] = useState(item?.questionDesign?.reference_text ?? '');
  const [examples, setExamples] = useState<Awaited<ReturnType<typeof previewQuestionDesign>>['examples']>([]);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewSpec, setPreviewSpec] = useState('');
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  if (!item) {
    return (
      <div className="page max-w-3xl">
        <EmptyState
          icon="clipboard"
          title="Không tìm thấy câu hỏi"
          description="Câu hỏi này có thể đã bị xoá hoặc đường dẫn chưa đúng."
          action={
            <Link to="/instructor/assessment" className="font-semibold text-primary-ink underline">
              Về Thiết kế kiểm chứng
            </Link>
          }
        />
      </div>
    );
  }

  const cleanRubric = rubric.map((r) => r.trim()).filter(Boolean);
  const questionDesign: NonNullable<AssessmentItem['questionDesign']> = { mode: designMode, relation_property: relationProperty,
    stages: designMode === 'relation_template' ? ['recall', 'explain', 'why', 'application', 'transfer'] : [assessmentStage], reference_text: referenceText.trim() };
  const payload = {
    id: item.id,
    question: question.trim(),
    rubric: cleanRubric,
    level,
    source,
    answerType,
    assessmentStage,
    hints,
    knowledgeComponentIds,
    kcProvisional: knowledgeComponentIds.length === 0,
    questionDesign,
  };

  const validate = (needNote = false) => {
    const next: Errors = {};
    if (question.trim().length < 10) next.question = 'Câu hỏi cần ít nhất 10 ký tự.';
    if (cleanRubric.length < 2) next.rubric = 'Rubric cần ít nhất 2 tiêu chí.';
    if (needNote && !note.trim()) next.note = 'Nhập ghi chú để người soạn biết cần sửa gì.';
    setErrors(next);
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
      const saved = await saveInstructorAction('assessment', payload.id, { ...payload, ...extra, ...(status ? { status } : {}) });
      dispatch({
        type: 'UPDATE_ASSESSMENT',
        item: { ...payload, version: Number(saved.payload.version ?? item.version ?? 1) },
        status,
        note: typeof extra.note === 'string' ? extra.note : undefined,
        historyText,
      });
      return true;
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Chưa lưu được thay đổi.');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const approve = async () => {
    if (!validate()) return;
    if (!await persist('approved', 'Duyệt và xuất bản')) return;
    toast({ tone: 'success', title: 'Đã duyệt và xuất bản' });
    navigate('/instructor/assessment');
  };
  const saveDraft = async () => {
    if (!validate()) return;
    if (!await persist(item.status, 'Lưu thay đổi')) return;
    toast({ tone: 'info', title: 'Đã lưu nháp' });
    navigate('/instructor/assessment');
  };
  const sendBack = async () => {
    if (!validate(true)) return;
    if (!await persist('rejected', 'Trả lại kèm ghi chú', { note: note.trim() })) return;
    toast({ tone: 'info', title: 'Đã trả lại kèm ghi chú' });
    navigate('/instructor/assessment');
  };

  const meta = statusMeta[item.status];

  return (
    <div className="page max-w-6xl">
      <PageHeader
        back={{ to: '/instructor/assessment', label: 'Thiết kế kiểm chứng' }}
        eyebrow={
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={meta.tone}>{meta.label}</Badge>
            <span className="caption">{item.topic} · v{item.version ?? 0}</span>
          </div>
        }
        title="Sửa câu hỏi & rubric"
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
        <Card aria-labelledby="edit-title">
          <CardHeader id="edit-title" title="Nội dung" />
          <div className="space-y-5">
            <Textarea
              label="Câu hỏi"
              hint="Câu hỏi mở — sinh viên trả lời bằng lời của mình."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              error={errors.question}
              rows={3}
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Select label="Mức độ bằng chứng" value={level} onChange={(e) => setLevel(e.target.value)} options={levels} />
              <Input label="Nguồn tài liệu đã xác nhận" value={source} onChange={(e) => setSource(e.target.value)} />
            </div>
            <Select label="Kiểu chấm" value={answerType} onChange={(event) => setAnswerType(event.target.value as typeof answerType)} options={answerTypes} />
            <fieldset className="space-y-3 rounded-xl border border-line p-4">
              <legend className="px-1 text-sm font-semibold">Khung tạo câu hỏi thích ứng</legend>
              <Select label="Cách tạo câu hỏi" value={designMode} onChange={(event) => setDesignMode(event.target.value as typeof designMode)} options={[
                { value: 'fixed', label: 'Câu mẫu cố định — fallback' },
                { value: 'relation_template', label: 'Quan hệ hai ngôi — sinh biến thể có checker' },
                { value: 'llm_followup', label: 'LLM hỏi tiếp nối — chỉ formative, không nâng mức hiểu' },
              ]} />
              {designMode === 'relation_template' && <>
                <Select label="Tính chất cần kiểm chứng" value={relationProperty} onChange={(event) => setRelationProperty(event.target.value as typeof relationProperty)} options={[
                  { value: 'reflexive', label: 'Phản xạ' }, { value: 'symmetric', label: 'Đối xứng' },
                  { value: 'antisymmetric', label: 'Phản đối xứng' }, { value: 'transitive', label: 'Bắc cầu' },
                  { value: 'equivalence', label: 'Quan hệ tương đương' }, { value: 'partial_order', label: 'Quan hệ thứ tự bộ phận' },
                ]} />
                <p className="caption">Duyệt khung cho Recall → Explain → Why → Apply → Transfer. Rubric bên dưới phải phù hợp các mức này. Code kiểm tra dữ kiện/đáp án; phần lập luận mở vẫn cần đánh giá theo rubric.</p>
                <Button type="button" size="sm" variant="secondary" loading={previewBusy} disabled={cleanRubric.length < 2 || !source.trim()} onClick={() => {
                  setPreviewBusy(true); setSaveError('');
                  setPreviewSpec(JSON.stringify([questionDesign, cleanRubric, source]));
                  void previewQuestionDesign(questionDesign, cleanRubric, source).then((result) => setExamples(result.examples))
                    .catch((failure: unknown) => setSaveError(failure instanceof Error ? failure.message : 'Chưa tạo được minh họa.'))
                    .finally(() => setPreviewBusy(false));
                }}>Xem biến thể và đáp án checker</Button>
                {!!examples.length && previewSpec === JSON.stringify([questionDesign, cleanRubric, source]) && <div className="space-y-3">{examples.map((example) => <div key={example.stage} className="rounded-lg bg-canvas p-3 text-sm">
                  <p className="font-semibold">{example.stage}: {example.question}</p>
                  <p className="caption mt-1">Checker: {example.expected_facts.holds ? 'Đạt tính chất' : 'Không đạt tính chất'} · Cặp cần bổ sung: {JSON.stringify(example.expected_facts.minimal_additions)}</p>
                </div>)}</div>}
              </>}
              {designMode === 'llm_followup' && <Textarea label="Nội dung tham chiếu được giảng viên xác nhận" value={referenceText} onChange={(event) => setReferenceText(event.target.value)} rows={4}
                hint="40–5000 ký tự, đúng nguồn ở trên. Tối đa hai lần sinh trong checkpoint; câu chưa được xác thực không dùng làm bằng chứng hiểu bài." />}
              <p className="caption">Duyệt cách kiểm chứng, không duyệt thủ công từng biến thể cho từng sinh viên. Câu mẫu bị gỡ khỏi LMS hoặc phiên bản khung thay đổi thì checkpoint phải cập nhật.</p>
            </fieldset>
            <Select
              label="Knowledge component được kiểm tra"
              hint="Chỉ KC đã được giảng viên duyệt mới được phép cập nhật Knowledge State."
              value={knowledgeComponentIds[0] ?? ''}
              onChange={(event) => setKnowledgeComponentIds(event.target.value ? [event.target.value] : [])}
              options={[
                { value: '', label: 'Chưa gắn KC — chỉ lưu bằng chứng, không cập nhật mastery' },
                ...components.map((component) => ({ value: component.id, label: component.name })),
              ]}
            />

            <Select label="Checkpoint thích ứng" value={assessmentStage}
              onChange={(event) => setAssessmentStage(event.target.value as typeof assessmentStage)}
              options={[{ value: 'recall', label: 'Nhận biết' }, { value: 'explain', label: 'Giải thích' },
                { value: 'why', label: 'Vì sao / như thế nào' }, { value: 'application', label: 'Vận dụng' },
                { value: 'transfer', label: 'Bài biến thể / phản ví dụ' }]} />
            <fieldset>
              <legend className="mb-2 text-sm font-semibold">Gợi ý được duyệt H1–H5</legend>
              <p className="mb-2 text-xs text-muted">Từ gợi mở đến hướng dẫn đầy đủ. Để trống sẽ dùng hướng dẫn quy trình chung, không tự sinh đáp án.</p>
              {hints.map((hint, index) => <Input key={index} label={`H${index + 1}`} value={hint}
                onChange={(event) => setHints(hints.map((value, position) => position === index ? event.target.value : value))} />)}
            </fieldset>
            <fieldset>
              <legend className="mb-2 text-sm font-semibold">Tiêu chí rubric</legend>
              <p className="mb-2 text-xs text-muted">Mỗi tiêu chí dùng mức chẩn đoán 0–4: không có bằng chứng → hiểu một phần → đang hình thành → đáp ứng → đầy đủ. Không cộng thành điểm tổng hay ghi gradebook.</p>
              <div className="space-y-2">
                {rubric.map((r, i) => (
                  <div key={i} className="flex items-end gap-2">
                    <span className="caption w-5 pb-3 text-center" aria-hidden="true">
                      {i + 1}
                    </span>
                    <Input
                      className="flex-1"
                      label={`Tiêu chí ${i + 1}`}
                      hideLabel
                      value={r}
                      onChange={(e) => setRubric(rubric.map((x, j) => (j === i ? e.target.value : x)))}
                    />
                    <IconButton icon="trash" label={`Xoá tiêu chí ${i + 1}`} onClick={() => setRubric(rubric.filter((_, j) => j !== i))} disabled={rubric.length <= 1} />
                  </div>
                ))}
              </div>
              {errors.rubric && (
                <p role="alert" className="mt-2 text-[13px] font-semibold text-danger-ink">
                  {errors.rubric}
                </p>
              )}
              <Button type="button" variant="secondary" size="sm" icon="plus" className="mt-3" onClick={() => setRubric([...rubric, ''])} disabled={rubric.length >= 6}>
                Thêm tiêu chí
              </Button>
            </fieldset>

            <Textarea
              label="Ghi chú khi trả lại"
              hint="Chỉ bắt buộc khi bạn trả lại câu hỏi."
              placeholder="Ví dụ: thêm một tiêu chí về giả thuyết đối"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              error={errors.note}
              rows={2}
            />
          </div>

          <div className="mt-6 flex flex-col gap-3 border-t border-line pt-5 sm:flex-row">
            {saveError && <p role="alert" className="w-full text-sm font-medium text-danger-ink">{saveError}</p>}
            <Button icon="check" onClick={() => void approve()} loading={saving}>
              Duyệt và xuất bản
            </Button>
            <Button variant="secondary" onClick={() => void saveDraft()} loading={saving}>
              Lưu nháp
            </Button>
            <Button variant="ghost" className="sm:ml-auto" onClick={() => void sendBack()} loading={saving}>
              Trả lại kèm ghi chú
            </Button>
          </div>
        </Card>

        <aside className="space-y-4">
          <Card aria-labelledby="pv-title">
            <CardHeader id="pv-title" title="Sinh viên sẽ thấy" />
            <div className="space-y-2 rounded-xl border border-line bg-canvas p-4">
              <Badge tone="primary">Kiểm tra nhanh</Badge>
              <p className="text-[15px] font-semibold leading-snug">{question.trim() || 'Câu hỏi sẽ hiện ở đây'}</p>
              <div className="h-16 rounded-lg border border-dashed border-slate-300 bg-white" aria-hidden="true" />
            </div>
            <p className="caption mt-3">Rubric chỉ dùng để chấm, không hiện cho sinh viên.</p>
          </Card>

          {item.aiGenerated && (
            <Card tone="accent">
              <div className="flex gap-3">
                <Icon name="sparkle" className="shrink-0 text-accent-ink" />
                <div>
                  <p className="font-semibold">Do hệ thống gợi ý</p>
                  <p className="mt-1 text-sm">Câu hỏi được tạo từ {item.source ?? 'tài liệu môn học'}. Chỉ xuất bản sau khi bạn duyệt.</p>
                </div>
              </div>
            </Card>
          )}

          <Card aria-labelledby="hs-title">
            <CardHeader id="hs-title" title="Lịch sử" />
            {item.history?.length ? (
              <ol className="space-y-2 text-sm">
                {item.history.map((h, i) => (
                  <li key={i}>
                    <span className="text-muted">{h.at}</span> · {h.text}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="caption">Chưa có thay đổi.</p>
            )}
          </Card>
        </aside>
      </div>
    </div>
  );
}
