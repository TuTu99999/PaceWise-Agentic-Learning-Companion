import { useMemo, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';
import { DiffList, diffMeta } from '../../components/domain/DiffList';
import { RecoveryCalendarPreview } from '../../components/domain/RecoveryCalendarPreview';
import { RecoveryCapacitySummary } from '../../components/domain/RecoveryCapacitySummary';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Icon } from '../../components/ui/Icon';
import { PageHeader } from '../../components/ui/PageHeader';
import { useToast } from '../../components/ui/Toast';
import { useDerived } from '../../hooks/useDerived';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAppStore } from '../../store/AppStore';
import { confirmRecovery } from '../../services/api';
import type { DiffType } from '../../types';
import { diffBlocks } from '../../utils/recovery';
import { buildPlanTimeline } from '../../utils/planTimeline';
import { addDays, calendarWeekStart, DEMO_TODAY } from '../../utils/time';
import { useRecoveryOptions } from './RecoverPage';

export function RecoverDiffPage() {
  useDocumentTitle('Bản thay đổi');
  const { optionId } = useParams<{ optionId: string }>();
  const { state, dispatch } = useAppStore();
  const { taskById } = useDerived();
  const { options, drift, impactId } = useRecoveryOptions();
  const navigate = useNavigate();
  const toast = useToast();
  const [showUnchanged, setShowUnchanged] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const option = options.find((o) => o.id === optionId);

  const diff = useMemo(() => (option && state.plan ? diffBlocks(state.plan.blocks, option.newBlocks) : []), [option, state.plan]);
  const calendarStart = calendarWeekStart(DEMO_TODAY);
  const calendarEnd = addDays(calendarStart, 13);
  const proposedStatus = useMemo(() => {
    const previous = new Map((state.plan?.blocks ?? []).map((block) => [block.id, block]));
    return new Map<string, 'added' | 'moved' | 'unchanged'>((option?.newBlocks ?? []).map((block) => {
      const old = previous.get(block.id);
      if (!old) return [block.id, 'added'];
      const moved = old.date !== block.date || old.start !== block.start || old.end !== block.end;
      return [block.id, moved ? 'moved' : 'unchanged'];
    }));
  }, [option, state.plan]);
  const timeline = useMemo(() => buildPlanTimeline({
    blocks: option?.newBlocks ?? [],
    calendarItems: Object.values(state.courseData).flatMap((course) => course.calendarItems ?? []),
    tasks: state.tasks,
    courses: state.courses,
    unavailable: state.unavailable,
    from: calendarStart,
    to: calendarEnd,
  }), [option, state.courseData, state.tasks, state.courses, state.unavailable, calendarStart, calendarEnd]);
  if (!option || !state.plan) return <Navigate to="/recover" replace />;

  const counts = (['added', 'moved', 'removed', 'unchanged'] as DiffType[]).map((t) => [t, diff.filter((d) => d.type === t).length] as const);
  const changed = diff.filter((d) => d.type !== 'unchanged');
  const visible = showUnchanged ? diff : changed;

  const confirm = async () => {
    setConfirming(true);
    try {
      await confirmRecovery(option.id);
    } catch (error) {
      toast({ tone: 'danger', title: 'Chưa xác nhận được phương án', description: error instanceof Error ? error.message : 'Hãy thử lại.' });
      setConfirming(false);
      return;
    }
    if (option.id === 'C') {
      if (drift) dispatch({ type: 'DISMISS_DRIFT', taskId: drift.taskId });
      if (impactId) dispatch({ type: 'DISMISS_PLAN_IMPACT', impactId });
      toast({ tone: 'info', title: 'Đã giữ nguyên lịch', description: 'Không có buổi học nào thay đổi.' });
    } else {
      dispatch({ type: 'APPLY_RECOVERY', blocks: option.newBlocks, impactId: impactId ?? undefined });
      toast({
        tone: option.fullyRecovers ? 'success' : 'info',
        title: option.fullyRecovers ? 'Lịch mới đã được áp dụng' : 'Đã áp dụng phần lịch khả thi',
        description: option.fullyRecovers
          ? 'Bản trước thay đổi đã được giữ trong lịch sử.'
          : 'Phần còn thiếu vẫn được giữ dưới dạng rủi ro trong Tiến độ và Phục hồi.',
      });
    }
    navigate('/plan');
  };

  return (
    <div className="page max-w-7xl">
      <PageHeader back={{ to: '/recover', label: 'Các phương án' }} title={`Phương án ${option.id} · ${option.title}`} description={option.summary} />

      <div className="mb-5 flex items-start gap-3 rounded-2xl border-2 border-dashed border-[#9DB6F5] bg-primary-light px-4 py-4" role="status">
        <Icon name="edit" size={20} className="mt-0.5 shrink-0 text-primary-ink" />
        <div>
          <p className="font-bold uppercase tracking-wide text-primary-ink">Bản thay đổi — chưa lưu</p>
          <p className="text-[#23408F]">Kế hoạch hiện tại chỉ thay đổi khi bạn bấm “Xác nhận thay đổi”.</p>
        </div>
      </div>

      <Card className="mb-5" tone={option.fullyRecovers ? 'default' : 'warning'} aria-labelledby="capacity-summary">
        <CardHeader
          id="capacity-summary"
          title={option.fullyRecovers ? 'Capacity sau khi phục hồi' : 'Kế hoạch chưa khả thi hoàn toàn'}
          subtitle={option.fullyRecovers
            ? 'Phương án đã bố trí đủ khối lượng trong phạm vi lịch rảnh và deadline.'
            : 'PaceWise chỉ xếp phần khả thi; phần còn thiếu không bị tự động bỏ hoặc nhồi ngoài giờ rảnh.'}
        />
        <RecoveryCapacitySummary option={option} taskById={taskById} />
        {!option.fullyRecovers && (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button variant="secondary" icon="edit" onClick={() => navigate('/plan/new')}>
              Điều chỉnh quỹ thời gian và estimate
            </Button>
            <p className="caption">Chỉ liên hệ giảng viên nếu bạn cần đổi deadline hoặc phạm vi học vụ.</p>
          </div>
        )}
      </Card>

      <Card aria-labelledby="calendar-preview">
        <CardHeader
          id="calendar-preview"
          title="Lịch đề xuất trong 2 tuần"
          subtitle="Tuần hiện tại và tuần kế tiếp · gồm lịch LMS, lịch bận và ca tự học sau khi áp dụng"
        />
        <RecoveryCalendarPreview from={calendarStart} items={timeline} proposedStatus={proposedStatus} />
      </Card>

      <Card className="mt-5" aria-labelledby="diff">
        <CardHeader id="diff" title="Trước và sau" />
        <div className="mb-4 flex flex-wrap gap-2">
          {counts.map(([t, n]) => (
            <Badge key={t} tone={diffMeta[t].tone} icon={diffMeta[t].icon}>
              {n} {diffMeta[t].label.toLowerCase()}
            </Badge>
          ))}
        </div>
        {changed.length === 0 && <p className="mb-4 rounded-xl bg-canvas px-4 py-3">Không có buổi học nào thay đổi.</p>}
        <DiffList items={visible} taskById={taskById} />
        <button className="mt-4 min-h-[44px] font-semibold text-primary-ink hover:underline" onClick={() => setShowUnchanged((v) => !v)} aria-expanded={showUnchanged}>
          {showUnchanged ? 'Ẩn các buổi không đổi' : `Hiện ${counts[3][1]} buổi không đổi`}
        </button>
      </Card>

      <Card className="mt-5" tone="warning" aria-labelledby="impact">
        <CardHeader id="impact" title="Tác động và đánh đổi" />
        <p>{option.impact}</p>
        <p className="mt-2">
          <strong>Đánh đổi: </strong>
          {option.tradeoff}
        </p>
      </Card>

      <div className="sticky bottom-[76px] z-20 mt-6 flex flex-col-reverse gap-3 rounded-2xl border border-line bg-white/95 p-4 shadow-card backdrop-blur sm:flex-row sm:items-center lg:bottom-4">
        <Button variant="secondary" icon="arrowLeft" onClick={() => navigate('/recover')}>
          Quay lại
        </Button>
        <span className="flex-1" />
        <Button icon="check" onClick={confirm} loading={confirming}>
          {option.id === 'C' ? 'Xác nhận giữ nguyên' : option.fullyRecovers ? 'Xác nhận thay đổi' : 'Áp dụng phần đã xếp'}
        </Button>
      </div>
    </div>
  );
}
