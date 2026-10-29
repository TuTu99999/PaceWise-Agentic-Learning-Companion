import { useState } from 'react';
import { NextActionCard } from '../../components/domain/NextActionCard';
import { LMSLearningSnapshot } from '../../components/domain/LMSLearningSnapshot';
import { TaskCard } from '../../components/domain/TaskCard';
import { WarningCard } from '../../components/domain/WarningCard';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { EmptyState } from '../../components/ui/States';
import { useToast } from '../../components/ui/Toast';
import { useDerived } from '../../hooks/useDerived';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAppStore } from '../../store/AppStore';
import { syncCanvas } from '../../services/api';
import { replanHref } from '../../utils/replanNavigation';
import { diffDays } from '../../utils/time';
import { formatDay, formatHours, TIMEZONE_LABEL, DEMO_TODAY, DEMO_NOW } from '../../utils/time';

export function DashboardPage() {
  useDocumentTitle('Tổng quan');
  const { state, dispatch } = useAppStore();
  const toast = useToast();
  const {
    scopeCourse,
    scopeLabel,
    scopedDrifts: drifts,
    scopedNext: next,
    scopedPlan,
    scopedStats: stats,
    scopedTasks: visibleTasks,
    taskById,
    courseById,
    courseOf,
  } = useDerived();
  const firstName = state.user?.name.split(' ').slice(-1)[0] ?? 'bạn';
  const [syncing, setSyncing] = useState(false);
  const scopedCourseData = scopeCourse ? state.courseData[scopeCourse.id] : undefined;

  const handleSyncCanvas = async () => {
    setSyncing(true);
    try {
      const synced = await syncCanvas();
      dispatch({ type: 'SYNC_CANVAS', courses: synced.courses, tasks: synced.tasks, guidance: synced.guidance, assessments: synced.assessments, courseData: synced.courseData });
      toast({ tone: 'success', title: 'Đã đồng bộ dữ liệu môn học từ Canvas', description: 'Các bài tập và deadline đã được cập nhật vào hệ thống.' });
    } finally {
      setSyncing(false);
    }
  };

  const nearestTasks = visibleTasks
    .filter((t) => t.status !== 'done')
    .sort((a, b) => diffDays(b.deadline, a.deadline))
    .slice(0, 4);
  const topDrift = drifts[0];
  const planImpact = state.planImpacts[0];

  return (
    <div className="page">
      <header className="mb-6 sm:mb-8">
        <p className="caption">
          {formatDay(DEMO_TODAY)} · {DEMO_NOW} ({TIMEZONE_LABEL})
        </p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Chào {firstName}, hôm nay mình làm gì trước?</h1>
      </header>

      {planImpact && (
        <Card className="mb-5" tone={planImpact.kind === 'capacity_released' || planImpact.kind === 'deadline_later' ? 'accent' : 'warning'} aria-labelledby="lms-impact-title">
          <CardHeader id="lms-impact-title" title={planImpact.title} subtitle="Thay đổi mới từ LMS · kế hoạch chưa bị sửa tự động" />
          <p>{planImpact.message}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <ButtonLink to={replanHref('lms', {
              impactId: planImpact.id,
              taskId: planImpact.taskId,
              courseId: planImpact.courseId,
            })}>
              AI phân tích lại
            </ButtonLink>
            <Button variant="secondary" onClick={() => dispatch({ type: 'DISMISS_PLAN_IMPACT', impactId: planImpact.id })}>Bỏ qua đề xuất</Button>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:gap-6">
        <div className="min-w-0 space-y-5 lg:space-y-6">
          {next ? (
            <NextActionCard next={next} course={courseOf(next.task.id)} sessionRunning={state.activeSession?.taskId === next.task.id} />
          ) : visibleTasks.length === 0 ? (
            <EmptyState
              icon="book"
              title="Chưa có môn học và deadline"
              description="PaceWise cần danh sách bài tập từ Canvas LMS để giúp bạn sắp xếp thời gian học và theo dõi tiến độ."
              action={
                <Button
                  icon="refresh"
                  size="lg"
                  loading={syncing}
                  onClick={handleSyncCanvas}
                >
                  Đồng bộ dữ liệu từ Canvas
                </Button>
              }
            />
          ) : (
            <EmptyState
              title="Chưa có kế hoạch cho 7 ngày tới"
              description="Thêm mục tiêu, deadline và thời gian rảnh để PaceWise gợi ý việc nên làm tiếp theo."
              action={
                <ButtonLink to="/plan/new" icon="plus" size="lg">
                  Tạo kế hoạch
                </ButtonLink>
              }
            />
          )}

          {topDrift && taskById.get(topDrift.taskId) && <WarningCard drift={topDrift} task={taskById.get(topDrift.taskId)!} compact />}

          <Card aria-labelledby="week-title">
            <CardHeader
              id="week-title"
              title={`Deadline gần nhất · ${scopeLabel}`}
              subtitle="Các nhiệm vụ mở được sắp theo hạn nộp, không phụ thuộc môn đang mở trên LMS"
              action={visibleTasks.length > 0 ? <ButtonLink to="/progress" variant="ghost" size="sm">Xem tất cả</ButtonLink> : undefined}
            />
            {nearestTasks.length ? (
              <div className="space-y-2.5">
                {nearestTasks.map((t) => (
                  <TaskCard key={t.id} task={t} course={courseById.get(t.courseId)} compact atRisk={drifts.some((d) => d.taskId === t.id)} />
                ))}
              </div>
            ) : (
              <p className="py-2 text-muted">Chưa có deadline mở nào trong phạm vi đang xem.</p>
            )}
          </Card>
        </div>

        <div className="min-w-0 space-y-5 lg:space-y-6">
          <Card aria-labelledby="progress-title">
            <CardHeader id="progress-title" title="Tiến độ" />
            {visibleTasks.length === 0 ? (
              <div className="py-1">
                <p className="text-xl font-bold text-muted">Chưa có dữ liệu</p>
                <p className="caption mt-1">Tiến độ sẽ hiển thị sau khi đồng bộ môn học từ Canvas.</p>
              </div>
            ) : (
              <>
                <p className="text-3xl font-bold tabular-nums">
                  {stats.done} / {stats.total}
                  <span className="ml-2 text-base font-medium text-muted">nhiệm vụ hoàn thành</span>
                </p>
                <ProgressBar className="mt-3" value={stats.done} max={stats.total} label="Nhiệm vụ hoàn thành trong chu kỳ 7 ngày" tone="success" />
              </>
            )}
            <dl className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-canvas p-3">
                <dt className="caption">Đã học trong 7 ngày</dt>
                <dd className="text-lg font-semibold tabular-nums">{formatHours(stats.studiedMin)}</dd>
              </div>
              <div className="rounded-xl bg-canvas p-3">
                <dt className="caption">Kế hoạch 7 ngày</dt>
                <dd className="text-lg font-semibold tabular-nums">{formatHours(stats.plannedMin)}</dd>
              </div>
            </dl>
          </Card>

          <Card aria-labelledby="attention-title">
            <CardHeader id="attention-title" title="Cần chú ý" />
            {visibleTasks.length === 0 ? (
              <p className="text-muted">Tài khoản mới chưa có dữ liệu. Vui lòng bấm <strong>“Đồng bộ dữ liệu từ Canvas”</strong> để bắt đầu.</p>
            ) : !scopedPlan?.blocks.length ? (
              <div className="space-y-3">
                <p className="text-muted">Chưa có kế hoạch 7 ngày. Hãy tạo kế hoạch để PaceWise theo dõi tiến độ và hỗ trợ điều chỉnh khi cần.</p>
                <ButtonLink to="/plan/new" variant="soft" block icon="plus">
                  Tạo kế hoạch 7 ngày
                </ButtonLink>
              </div>
            ) : topDrift ? (
              <div className="space-y-3">
                <p>
                  <strong>{taskById.get(topDrift.taskId)?.title}</strong> đang thiếu <strong>{formatHours(topDrift.deficitMin)}</strong> để bảo vệ deadline.
                </p>
                <ButtonLink to={replanHref('progress', { taskId: topDrift.taskId, courseId: topDrift.courseId })} variant="soft" block iconRight="arrowRight">
                  Xem phương án
                </ButtonLink>
              </div>
            ) : (
              <p className="flex items-center gap-2 text-success-ink">Kế hoạch đang đúng hướng. Không có gì cần xử lý.</p>
            )}
          </Card>

          {scopedCourseData && <LMSLearningSnapshot data={scopedCourseData} />}

          {scopedPlan && scopedPlan.blocks.length > 0 && (
            <Card aria-labelledby="plan-title">
              <CardHeader id="plan-title" title="Kế hoạch đã lưu" subtitle={`Phiên bản ${scopedPlan.version} · ${scopedPlan.blocks.length} buổi học cho ${scopeLabel}`} />
              <ButtonLink to="/plan" variant="secondary" block>
                Mở kế hoạch 7 ngày
              </ButtonLink>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
