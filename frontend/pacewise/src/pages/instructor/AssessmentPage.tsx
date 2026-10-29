import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Badge } from '../../components/ui/Badge';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { StatTile } from '../../components/domain/StatTile';
import { Textarea } from '../../components/ui/Field';
import { Modal } from '../../components/ui/Modal';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useInstructorData } from '../../hooks/useInstructorData';
import { useAppStore } from '../../store/AppStore';
import { deleteAssessmentDesign, saveInstructorAction } from '../../services/api';
import type { AssessmentItem, AssessmentStatus, Tone } from '../../types';
import { useLocale } from '../../i18n/LocaleContext';

const meta: Record<AssessmentStatus, { label: string; tone: Tone }> = {
  draft: { label: 'Bản nháp', tone: 'neutral' },
  review: { label: 'Chờ duyệt', tone: 'warning' },
  approved: { label: 'Đã duyệt', tone: 'success' },
  rejected: { label: 'Bị trả lại', tone: 'danger' },
};

export function AssessmentPage() {
  const { t } = useLocale();
  useDocumentTitle(t('Thiết kế kiểm chứng'));
  const { state, dispatch } = useAppStore();
  const navigate = useNavigate();
  const toast = useToast();
  const [returning, setReturning] = useState<AssessmentItem | null>(null);
  const [deleting, setDeleting] = useState<AssessmentItem | null>(null);
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState('');
  const { loading, error: loadError } = useInstructorData();
  const statusCounts = state.assessments.reduce<Record<AssessmentStatus, number>>(
    (counts, item) => ({ ...counts, [item.status]: counts[item.status] + 1 }),
    { draft: 0, review: 0, approved: 0, rejected: 0 },
  );

  const updateStatus = async (item: AssessmentItem, status: AssessmentStatus, actionNote?: string) => {
    setBusyId(item.id);
    setActionError('');
    try {
      const saved = await saveInstructorAction('assessment', item.id, {
        question: item.question,
        assessmentSetId: item.assessmentSetId ?? item.id,
        rubric: item.rubric,
        level: 'conceptual',
        source: item.source,
        sourceResourceId: item.sourceResourceId,
        sourceChapter: item.sourceChapter,
        moduleId: item.moduleId,
        answerType: 'open',
        knowledgeComponentIds: item.knowledgeComponentIds,
        kcProvisional: item.kcProvisional,
        assessmentStage: 'explain',
        hints: item.hints,
        questionDesign: { mode: 'fixed', relation_property: 'transitive', stages: ['explain'], reference_text: '' },
        status,
        ...(actionNote ? { note: actionNote } : {}),
      });
      dispatch({
        type: 'UPDATE_ASSESSMENT',
        item: {
          ...item,
          assessmentSetId: item.assessmentSetId ?? item.id,
          answerType: 'open',
          level: 'conceptual',
          assessmentStage: 'explain',
          questionDesign: { mode: 'fixed', relation_property: 'transitive', stages: ['explain'], reference_text: '' },
          version: Number(saved.payload.version ?? item.version ?? 1),
        },
        status,
        note: actionNote,
        historyText: status === 'approved' ? 'Duyệt và xuất bản' : status === 'rejected' ? 'Trả lại kèm ghi chú' : 'Gửi duyệt',
      });
      return true;
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Chưa lưu được thay đổi.');
      return false;
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="page max-w-4xl">
      <PageHeader
        title={t('Thiết kế kiểm chứng')}
        actions={<Button icon="plus" onClick={() => {
          const firstComponent = state.teacherWorkspace.courseStructure.knowledgeComponents.find((component) => component.status === 'approved');
          const id = `assessment-${globalThis.crypto?.randomUUID?.() ?? Date.now()}`;
          dispatch({
            type: 'ADD_ASSESSMENT_DRAFT',
            item: {
              id,
              assessmentSetId: id,
              courseId: state.user?.courseId,
              topic: firstComponent?.name ?? t('Câu kiểm tra mới'),
              question: '',
              rubric: ['', ''],
              status: 'draft',
              level: 'conceptual',
              source: '',
              answerType: 'open',
              assessmentStage: 'explain',
              knowledgeComponentIds: firstComponent ? [firstComponent.id] : [],
              questionDesign: { mode: 'fixed', relation_property: 'transitive', stages: ['explain'], reference_text: '' },
              hints: ['', '', '', '', ''],
              kcProvisional: !firstComponent,
              version: 0,
            },
          });
          navigate(`/instructor/assessment/${id}`);
        }}>{t('Tạo bộ câu hỏi')}</Button>}
      />
      {loadError && state.assessments.length === 0 && <ErrorState title={t('Không thể tải ngân hàng câu hỏi')} description={loadError.message} requestId={loadError.requestId} />}
      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-busy={loading}>
        <StatTile icon="file" label={t('Bản nháp')} value={statusCounts.draft} />
        <StatTile icon="clock" label={t('Chờ giảng viên')} value={statusCounts.review} />
        <StatTile icon="checkCircle" label={t('Đã xuất bản')} value={statusCounts.approved} />
        <StatTile icon="refresh" label={t('Cần chỉnh sửa')} value={statusCounts.rejected} />
      </div>
      {actionError && <p role="alert" className="mb-4 text-sm font-medium text-danger-ink">{actionError}</p>}
      <div className="space-y-4">
        {state.assessments.map((a) => (
          <Card as="article" key={a.id} aria-labelledby={`as-${a.id}`}>
            <div className="flex justify-end">
              <Badge tone={meta[a.status].tone}>
                {t(meta[a.status].label)}
              </Badge>
            </div>
            <h2 id={`as-${a.id}`} className="mt-1 text-lg font-semibold">
              {a.question}
            </h2>
            {a.assignmentTitle && <p className="mt-2 text-sm font-medium">{t('Bài tập')}: {a.assignmentTitle}</p>}
            {(a.weekStart || a.weekEnd) && (
              <p className="caption mt-1">Tuần áp dụng: {a.weekStart ?? '—'} đến {a.weekEnd ?? '—'}</p>
            )}
            {a.source && <p className="caption mt-1">{t('Nguồn')}: {a.source}</p>}
            <p className="caption mt-2">{t(a.aiGenerated ? 'AI đề xuất từ học liệu đã chọn' : 'Giảng viên tạo')}</p>
            <p className="mt-3 text-sm font-semibold text-muted">{t('Các ý câu trả lời cần thể hiện')}</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-[15px]">
              {a.rubric.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            {a.note && <p className="mt-3 rounded-xl bg-danger-light px-3 py-2 text-sm text-danger-ink">Ghi chú khi trả lại: {a.note}</p>}
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              {a.status === 'draft' && (
                <Button size="sm" variant="secondary" loading={busyId === a.id} onClick={() => void updateStatus(a, 'review')}>
                  {t('Gửi duyệt')}
                </Button>
              )}
              {(a.status === 'review' || a.status === 'rejected') && (
                <>
                  <Button
                    size="sm"
                    icon="check"
                    loading={busyId === a.id}
                    onClick={() => void updateStatus(a, 'approved').then((saved) => {
                      if (saved) toast({ tone: 'success', title: 'Đã duyệt và xuất bản cho pilot' });
                    })}
                  >
                    {t('Duyệt và xuất bản')}
                  </Button>
                  {a.status === 'review' && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        setReturning(a);
                        setNote('');
                        setErr('');
                      }}
                    >
                      {t('Trả lại kèm ghi chú')}
                    </Button>
                  )}
                </>
              )}
              {(
                <ButtonLink to={`/instructor/assessment/${a.id}`} size="sm" variant="ghost" icon="edit" className="sm:ml-auto">
                  {t('Sửa')}
                </ButtonLink>
              )}
              <Button size="sm" variant="danger" icon="trash" onClick={() => {
                setDeleting(a);
                setActionError('');
              }}>
                {t('Xóa')}
              </Button>
            </div>
          </Card>
        ))}
      </div>
      {!loading && state.assessments.length === 0 && (
        <Card className="text-center">
          <h2 className="text-lg font-semibold">{t('Chưa có câu kiểm tra được duyệt')}</h2>
        </Card>
      )}

      <Modal
        open={!!returning}
        onClose={() => setReturning(null)}
        title={t('Trả lại câu hỏi')}
        description={returning?.question}
        footer={
          <>
            <Button variant="secondary" onClick={() => setReturning(null)}>
              {t('Hủy')}
            </Button>
            <Button
              onClick={() => {
                if (!note.trim()) {
                  setErr('Ghi chú là bắt buộc khi trả lại.');
                  return;
                }
                void updateStatus(returning!, 'rejected', note.trim()).then((saved) => {
                  if (!saved) return;
                  toast({ tone: 'info', title: 'Đã trả lại kèm ghi chú' });
                  setReturning(null);
                });
              }}
              loading={busyId === returning?.id}
            >
              {t('Trả lại')}
            </Button>
          </>
        }
      >
        <Textarea label={t('Ghi chú cho người soạn')} value={note} onChange={(e) => setNote(e.target.value)} error={err} rows={4} />
      </Modal>

      <Modal
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={t('Xóa câu kiểm tra?')}
        description={deleting?.question || deleting?.topic}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeleting(null)}>{t('Hủy')}</Button>
            <Button
              variant="danger"
              icon="trash"
              loading={busyId === deleting?.id}
              onClick={() => {
                if (!deleting) return;
                setBusyId(deleting.id);
                setActionError('');
                void deleteAssessmentDesign(deleting.id)
                  .then(() => {
                    dispatch({ type: 'DELETE_ASSESSMENT', id: deleting.id });
                    toast({
                      tone: 'success',
                      title: 'Đã xóa khỏi ngân hàng câu hỏi',
                      description: 'Câu này không còn được dùng cho Self-check; lịch sử và audit cũ vẫn được giữ.',
                    });
                    setDeleting(null);
                  })
                  .catch((error) => setActionError(error instanceof Error ? error.message : 'Chưa xóa được câu kiểm tra.'))
                  .finally(() => setBusyId(null));
              }}
            >
              {t('Xóa câu kiểm tra')}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          {t('Câu này sẽ biến mất khỏi Thiết kế kiểm chứng và không được dùng cho Self-check mới. Bằng chứng học tập và lịch sử phê duyệt đã có sẽ không bị xóa.')}
        </p>
      </Modal>
    </div>
  );
}
