import { useParams } from 'react-router-dom';
import { CourseTag, deadlineLabel, deadlineTone } from '../../components/domain/TaskCard';
import { Badge } from '../../components/ui/Badge';
import { ButtonLink } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Icon } from '../../components/ui/Icon';
import { PageHeader } from '../../components/ui/PageHeader';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { EmptyState } from '../../components/ui/States';
import { useDerived } from '../../hooks/useDerived';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAppStore } from '../../store/AppStore';
import { remainingOf, sortBlocks } from '../../utils/progress';
import { formatDay, formatDeadline, formatDuration, formatRange, isPast } from '../../utils/time';

export function TaskDetailPage() {
  const { taskId = '' } = useParams<{ taskId: string }>();
  const { state } = useAppStore();
  const { taskById, courseOf } = useDerived();
  const task = taskById.get(taskId);
  useDocumentTitle(task?.title ?? 'Nhiệm vụ');

  if (!task) {
    return (
      <div className="page">
        <EmptyState icon="file" title="Không tìm thấy nhiệm vụ" description="Nhiệm vụ có thể đã bị xóa khỏi dữ liệu Canvas." action={<ButtonLink to="/progress">Về trang Tiến độ</ButtonLink>} />
      </div>
    );
  }
  const course = courseOf(task.id);
  const upcoming = sortBlocks(state.plan?.blocks.filter((b) => b.taskId === task.id && !isPast(b.date, b.end)) ?? []);
  const sessions = state.sessions.filter((s) => s.taskId === task.id);
  const running = state.activeSession?.taskId === task.id;

  return (
    <div className="page max-w-4xl">
      <PageHeader
        back={{ to: '/dashboard', label: 'Tổng quan' }}
        eyebrow={
          <span className="flex flex-wrap gap-2">
            <CourseTag course={course} />
            <Badge tone={deadlineTone(task)}>{deadlineLabel(task)}</Badge>
          </span>
        }
        title={task.title}
        actions={
          task.status !== 'done' && (
            <ButtonLink to={running ? `/study/${task.id}/session` : '/plan'} icon={running ? 'play' : 'calendar'} size="lg">
              {running ? 'Tiếp tục phiên học' : 'Mở lịch học'}
            </ButtonLink>
          )
        }
      />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <Card aria-labelledby="info">
          <CardHeader id="info" title="Thông tin" />
          <dl className="space-y-3">
            <div className="flex gap-3">
              <Icon name="book" size={20} className="mt-0.5 text-muted" />
              <div>
                <dt className="caption">Môn</dt>
                <dd className="font-medium">
                  {course?.code} · {course?.name}
                </dd>
              </div>
            </div>
            {task.assignmentGroup && (
              <div className="flex gap-3">
                <Icon name="chart" size={20} className="mt-0.5 text-muted" />
                <div>
                  <dt className="caption">Nhóm điểm</dt>
                  <dd className="font-medium">
                    {task.assignmentGroup.name} · trọng số {task.assignmentGroup.weight}%
                  </dd>
                </div>
              </div>
            )}
            {(task.unlockAt || task.lockAt) && (
              <div className="flex gap-3">
                <Icon name="lock" size={20} className="mt-0.5 text-muted" />
                <div>
                  <dt className="caption">Khoảng thời gian làm bài</dt>
                  <dd className="font-medium">
                    {task.unlockAt ? new Date(task.unlockAt).toLocaleString('vi-VN') : 'Mở ngay'}
                    {' – '}
                    {task.lockAt ? new Date(task.lockAt).toLocaleString('vi-VN') : 'Không khóa'}
                  </dd>
                  {task.overrideTarget && <p className="caption">Deadline riêng theo {task.overrideTarget}</p>}
                </div>
              </div>
            )}
            <div className="flex gap-3">
              <Icon name="flag" size={20} className="mt-0.5 text-muted" />
              <div>
                <dt className="caption">Deadline</dt>
                <dd className="font-medium">{formatDeadline(task.deadline)} (GMT+7)</dd>
              </div>
            </div>
            <div className="flex gap-3">
              <Icon name="clock" size={20} className="mt-0.5 text-muted" />
              <div>
                <dt className="caption">Thời lượng ước tính</dt>
                <dd className="font-medium">
                  {formatDuration(task.estimateMin)}
                  {task.estimateIsAssumption && <span className="caption"> · ước lượng của PaceWise</span>}
                </dd>
              </div>
            </div>
          </dl>
        </Card>
        <Card aria-labelledby="submission">
          <CardHeader id="submission" title="Bài nộp trên LMS" />
          <dl className="grid grid-cols-2 gap-3">
            <div className="rounded-xl bg-canvas p-3">
              <dt className="caption">Trạng thái</dt>
              <dd className="font-semibold">{task.submission?.state ?? 'unsubmitted'}</dd>
            </div>
            <div className="rounded-xl bg-canvas p-3">
              <dt className="caption">Số lần nộp</dt>
              <dd className="font-semibold tabular-nums">{task.submission?.attempts ?? 0}</dd>
            </div>
            <div className="rounded-xl bg-canvas p-3">
              <dt className="caption">Điểm</dt>
              <dd className="font-semibold tabular-nums">
                {task.submission?.score ?? 'Chưa chấm'}{task.submission?.score != null ? ` / ${task.pointsPossible ?? 0}` : ''}
              </dd>
            </div>
            <div className="rounded-xl bg-canvas p-3">
              <dt className="caption">Nộp trễ</dt>
              <dd className="font-semibold">{task.submission?.late ? 'Có' : 'Không'}</dd>
            </div>
          </dl>
          {task.submission?.feedback && <p className="mt-3 text-sm text-muted">Phản hồi: {task.submission.feedback}</p>}
        </Card>
        <Card aria-labelledby="rubric">
          <CardHeader
            id="rubric"
            title="Rubric đánh giá"
            subtitle={task.rubric ? `${task.rubric.points_possible} điểm` : undefined}
          />
          {task.rubric ? (
            <ul className="space-y-2">
              {task.rubric.criteria.map((criterion) => (
                <li key={criterion.id} className="flex justify-between gap-3 rounded-xl bg-canvas px-3 py-2.5">
                  <span>{criterion.description}</span>
                  <strong className="shrink-0 tabular-nums">{criterion.points} điểm</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">Bài tập này chưa gắn rubric.</p>
          )}
        </Card>
        <Card aria-labelledby="obj">
          <CardHeader id="obj" title="Mục tiêu" />
          <p className="flex gap-3">
            <Icon name="target" size={20} className="mt-0.5 shrink-0 text-primary-ink" />
            {task.objective}
          </p>
          <div className="mt-5">
            <div className="mb-2 flex justify-between text-sm">
              <span className="text-muted">Đã học</span>
              <span className="font-semibold tabular-nums">
                {formatDuration(task.loggedMin)} / {formatDuration(task.estimateMin)}
              </span>
            </div>
            <ProgressBar value={task.loggedMin} max={task.estimateMin} label={`Tiến độ ${task.title}`} />
            <p className="caption mt-2">{task.status === 'done' ? 'Đã hoàn thành' : `Còn khoảng ${formatDuration(remainingOf(task))}`}</p>
          </div>
        </Card>
        <Card aria-labelledby="up">
          <CardHeader id="up" title="Buổi học sắp tới" />
          {upcoming.length ? (
            <ul className="space-y-2">
              {upcoming.map((b) => (
                <li key={b.id} className="flex justify-between gap-3 rounded-xl bg-canvas px-3 py-2.5">
                  <span>{formatDay(b.date, { relative: true })}</span>
                  <span className="font-semibold tabular-nums">{formatRange(b.start, b.end)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">Không có buổi nào trong kế hoạch.</p>
          )}
        </Card>
        <Card aria-labelledby="hist">
          <CardHeader id="hist" title="Phiên học đã ghi" />
          {sessions.length ? (
            <ul className="space-y-2">
              {sessions.map((s) => (
                <li key={s.id} className="flex justify-between gap-3 rounded-xl bg-canvas px-3 py-2.5">
                  <span>
                    {formatDay(s.date)} · {s.source === 'timer' ? 'Hẹn giờ' : 'Nhập tay'}
                  </span>
                  <span className="font-semibold tabular-nums">{formatDuration(s.minutes)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">Chưa có phiên học nào.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
