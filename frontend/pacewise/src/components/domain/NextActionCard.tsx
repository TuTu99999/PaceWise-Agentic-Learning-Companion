import type { Course } from '../../types';
import type { NextAction } from '../../utils/progress';
import { durationMin, formatDay, formatDuration, formatRange } from '../../utils/time';
import { ButtonLink } from '../ui/Button';
import { Card } from '../ui/Card';
import { Icon } from '../ui/Icon';
import { CourseTag } from './TaskCard';

export function NextActionCard({ next, course, sessionRunning }: { next: NextAction; course?: Course; sessionRunning?: boolean }) {
  const { task, block, reason } = next;
  return (
    <Card tone="primary" className="relative overflow-hidden" aria-labelledby="next-title">
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-primary-light" aria-hidden="true" />
      <div className="relative">
        <p className="text-sm font-semibold uppercase tracking-wide text-primary-ink">Việc tiếp theo</p>
        <h2 id="next-title" className="mt-2 text-[22px] font-bold leading-snug sm:text-2xl">
          {task.title} <span className="text-muted">— {course?.name}</span>
        </h2>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[15px]">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 font-medium ring-1 ring-line">
            <Icon name="calendar" size={16} className="text-primary-ink" />
            {formatDay(block.date, { relative: true })} · {formatRange(block.start, block.end)}
          </span>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1 font-medium ring-1 ring-line">
            <Icon name="clock" size={16} className="text-primary-ink" />
            {formatDuration(durationMin(block.start, block.end))}
          </span>
          <CourseTag course={course} />
        </div>
        <div className="mt-4 flex gap-3 rounded-xl bg-canvas px-4 py-3">
          <Icon name="lightbulb" size={20} className="mt-0.5 shrink-0 text-primary-ink" />
          <p>
            <span className="font-semibold">Vì sao bây giờ? </span>
            {reason}
          </p>
        </div>
        <div className="mt-5 flex flex-col gap-3 sm:flex-row">
          <ButtonLink to={`/study/${task.id}/session`} icon="play" size="lg">
            {sessionRunning ? 'Tiếp tục phiên học' : 'Bắt đầu học'}
          </ButtonLink>
          <ButtonLink to="/plan" variant="secondary" size="lg">
            Xem kế hoạch
          </ButtonLink>
        </div>
      </div>
    </Card>
  );
}
