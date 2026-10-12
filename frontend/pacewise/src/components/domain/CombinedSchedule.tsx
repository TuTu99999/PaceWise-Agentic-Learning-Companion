import { useEffect, useMemo, useState } from 'react';
import type { PlanTimelineItem, PlanTimelineSource } from '../../utils/planTimeline';
import { cx } from '../../utils/cx';
import { DEMO_TODAY, formatDay, formatDeadline, formatDuration, formatRange, isPast } from '../../utils/time';
import { Badge } from '../ui/Badge';
import { Button, ButtonLink } from '../ui/Button';
import { Icon } from '../ui/Icon';

type TimelineFilter = 'all' | PlanTimelineSource;

const FILTERS: Array<{ value: TimelineFilter; label: string }> = [
  { value: 'all', label: 'Tất cả' },
  { value: 'lms', label: 'Lịch môn học' },
  { value: 'pacewise', label: 'Tự học' },
  { value: 'busy', label: 'Lịch bận' },
];

interface CombinedScheduleProps {
  items: PlanTimelineItem[];
  dates?: string[];
  nextItemId?: string;
}

export function CombinedSchedule({ items, dates, nextItemId }: CombinedScheduleProps) {
  const [filter, setFilter] = useState<TimelineFilter>('all');
  const allDates = useMemo(() => dates ?? Array.from(new Set(items.map((item) => item.date))), [dates, items]);
  const initialDate = allDates.includes(DEMO_TODAY)
    ? DEMO_TODAY
    : allDates.find((date) => items.some((item) => item.date === date)) ?? allDates[0];
  const [expandedDates, setExpandedDates] = useState<Set<string>>(() => new Set(initialDate ? [initialDate] : []));

  useEffect(() => {
    if (initialDate) setExpandedDates(new Set([initialDate]));
  }, [initialDate]);

  const counts = useMemo(() => ({
    all: items.length,
    lms: items.filter((item) => item.source === 'lms').length,
    pacewise: items.filter((item) => item.source === 'pacewise').length,
    busy: items.filter((item) => item.source === 'busy').length,
  }), [items]);
  const visible = filter === 'all' ? items : items.filter((item) => item.source === filter);

  const toggleDate = (date: string) => {
    setExpandedDates((current) => {
      const next = new Set(current);
      if (next.has(date)) next.delete(date);
      else next.add(date);
      return next;
    });
  };

  return (
    <div>
      <details className="mb-4 rounded-xl border border-line bg-canvas px-3 py-2">
        <summary className="cursor-pointer font-medium text-primary-ink">Lọc nội dung · {counts[filter]} mục</summary>
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Lọc lịch tuần">
          {FILTERS.map((option) => (
            <Button
              key={option.value}
              size="sm"
              variant={filter === option.value ? 'primary' : 'secondary'}
              aria-pressed={filter === option.value}
              onClick={() => setFilter(option.value)}
            >
              {option.label} ({counts[option.value]})
            </Button>
          ))}
        </div>
      </details>

      {!allDates.length ? (
        <p className="text-muted">Tuần này chưa có lịch.</p>
      ) : (
        <div className="divide-y divide-line">
          {allDates.map((date) => {
            const dayItems = visible.filter((item) => item.date === date);
            const studyMinutes = dayItems
              .filter((item) => item.source === 'pacewise')
              .reduce((total, item) => total + item.durationMin, 0);
            const expanded = expandedDates.has(date);
            const deadlineCount = dayItems.filter((item) => item.kind === 'assignment').length;
            const summary = dayItems.length
              ? dayItems.length + ' mục'
                + (studyMinutes > 0 ? ' · ' + formatDuration(studyMinutes) + ' tự học' : '')
                + (deadlineCount > 0 ? ' · ' + deadlineCount + ' hạn nộp' : '')
              : 'Chưa có lịch';
            return (
              <section key={date} aria-labelledby={'plan-day-' + date} className="py-2 first:pt-0 last:pb-0">
                <button
                  id={'plan-day-' + date}
                  type="button"
                  className="flex min-h-12 w-full items-center gap-3 rounded-xl px-2 text-left hover:bg-slate-50"
                  aria-expanded={expanded}
                  aria-controls={'plan-day-content-' + date}
                  onClick={() => toggleDate(date)}
                >
                  <span className="min-w-0 flex-1">
                    <span className="font-semibold">{formatDay(date, { relative: true })}</span>
                    <span className="caption ml-2">{summary}</span>
                  </span>
                  <Icon name="chevronDown" size={18} className={cx('shrink-0 transition-transform', expanded && 'rotate-180')} />
                </button>
                {expanded && (
                  <div id={'plan-day-content-' + date} className="pb-3 pt-1">
                    {dayItems.length ? (
                      <ul className="space-y-2">
                        {dayItems.map((item) => <TimelineRow key={item.id} item={item} isNext={item.id === nextItemId} />)}
                      </ul>
                    ) : (
                      <p className="px-2 py-3 text-sm text-muted">Bạn chưa có buổi học hoặc mốc LMS trong ngày này.</p>
                    )}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TimelineRow({ item, isNext }: { item: PlanTimelineItem; isNext: boolean }) {
  const past = isPast(item.date, item.end ?? item.start);
  const isLms = item.source === 'lms';
  const isBusy = item.source === 'busy';
  const sourceLabel = item.kind === 'assignment' ? 'Hạn nộp' : isLms ? 'Lịch môn học' : isBusy ? 'Lịch bận' : 'Tự học';

  return (
    <li
      className={cx(
        'flex items-start gap-3 rounded-xl border px-3 py-3 sm:px-4',
        isLms ? 'border-[#C9D8FB] bg-primary-light' : isBusy ? 'border-[#F3D9A5] bg-warning-light' : 'border-[#C7EBD8] bg-success-light',
        past && 'opacity-70',
      )}
    >
      <div className="w-[88px] shrink-0 sm:w-[108px]">
        <p className="font-semibold tabular-nums">{item.end ? formatRange(item.start, item.end) : item.start}</p>
        <p className="caption">{item.durationMin > 0 ? formatDuration(item.durationMin) : 'Mốc thời gian'}</p>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="font-semibold">{item.title}</p>
          {item.courseCode && <Badge tone="neutral">{item.courseCode}</Badge>}
          <Badge tone={isLms ? 'primary' : isBusy ? 'warning' : 'success'}>{sourceLabel}</Badge>
          {isNext && <Badge tone="success">Sắp tới</Badge>}
          {past && <Badge>Đã qua</Badge>}
        </div>
        <p className="caption mt-1">
          {isLms ? (
            <span className="inline-flex items-center gap-1"><Icon name="lock" size={13} />{item.kindLabel} · Chỉ đọc từ LMS</span>
          ) : isBusy ? (
            <span className="inline-flex items-center gap-1"><Icon name="clock" size={13} />PaceWise không xếp việc vào khoảng này</span>
          ) : item.deadline ? (
            <>Hạn chót {formatDeadline(item.deadline)}</>
          ) : 'Buổi tự học do PaceWise lập'}
        </p>
        {isNext && item.taskId && (
          <ButtonLink className="mt-2" to={'/study/' + encodeURIComponent(item.taskId) + '/session'} size="sm" icon="play">
            Bắt đầu học
          </ButtonLink>
        )}
      </div>
    </li>
  );
}
