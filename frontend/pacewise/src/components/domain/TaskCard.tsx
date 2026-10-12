import { Link } from 'react-router-dom';
import type { Course, Task } from '../../types';
import { cx } from '../../utils/cx';
import { remainingOf } from '../../utils/progress';
import { daysUntil, formatDeadline, formatDuration } from '../../utils/time';
import { Badge } from '../ui/Badge';
import { Icon } from '../ui/Icon';
import { ProgressBar } from '../ui/ProgressBar';

export function deadlineTone(task: Task) {
  if (task.status === 'done') return 'success' as const;
  const d = daysUntil(task.deadline);
  if (d <= 1) return 'danger' as const;
  if (d <= 3) return 'warning' as const;
  return 'neutral' as const;
}

export function deadlineLabel(task: Task) {
  if (task.status === 'done') return 'Đã xong';
  const d = daysUntil(task.deadline);
  if (d < 0) return 'Quá hạn';
  if (d === 0) return 'Hạn hôm nay';
  return `Còn ${d} ngày`;
}

export function CourseTag({ course }: { course?: Course }) {
  if (!course) return null;
  return (
    <Badge tone={course.tone} className="!min-h-[22px] !px-2 !text-xs">
      {course.name}
    </Badge>
  );
}

export function TaskCard({ task, course, compact, atRisk }: { task: Task; course?: Course; compact?: boolean; atRisk?: boolean }) {
  const done = task.status === 'done';
  return (
    <Link
      to={`/study/${task.id}`}
      className={cx(
        'group flex items-center gap-3 rounded-2xl border border-line bg-white p-4 transition-colors hover:border-[#C9D8FB] hover:bg-[#FBFCFF]',
        compact && 'p-3.5',
      )}
    >
      <span className={cx('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl', done ? 'bg-success-light text-success-ink' : 'bg-primary-light text-primary-ink')}>
        <Icon name={done ? 'check' : 'file'} size={20} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p className={cx('font-semibold', done && 'text-muted line-through decoration-slate-300')}>{task.title}</p>
          <CourseTag course={course} />
        </div>
        <p className="caption mt-0.5">
          Hạn {formatDeadline(task.deadline)}
          {!done && ` · còn khoảng ${formatDuration(remainingOf(task))}`}
          {task.assignmentGroup && ` · ${task.assignmentGroup.name} (${task.assignmentGroup.weight}%)`}
        </p>
        {!compact && !done && <ProgressBar className="mt-2.5" size="sm" value={task.loggedMin} max={task.estimateMin} label={`Tiến độ ${task.title}`} />}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        {task.overrideTarget && <Badge tone="accent">Hạn riêng</Badge>}
        {atRisk ? <Badge tone="warning" icon="alert">Nguy cơ</Badge> : <Badge tone={deadlineTone(task)}>{deadlineLabel(task)}</Badge>}
      </div>
    </Link>
  );
}
