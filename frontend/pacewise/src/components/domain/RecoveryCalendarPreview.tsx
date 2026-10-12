import type { PlanTimelineItem } from '../../utils/planTimeline';
import { addDays, formatDM, formatRange, weekDates, weekdayShort } from '../../utils/time';
import type { Weekday } from '../../types';
import { cx } from '../../utils/cx';
import { Badge } from '../ui/Badge';

type ProposedBlockStatus = 'added' | 'moved' | 'unchanged';

interface RecoveryCalendarPreviewProps {
  from: string;
  items: PlanTimelineItem[];
  proposedStatus: Map<string, ProposedBlockStatus>;
}

export function RecoveryCalendarPreview({ from, items, proposedStatus }: RecoveryCalendarPreviewProps) {
  const weeks = [from, addDays(from, 7)];
  return (
    <div className="space-y-6">
      {weeks.map((weekStart, weekIndex) => {
        const dates = weekDates(weekStart);
        const headingId = 'recovery-week-' + weekIndex;
        return (
          <section key={weekStart} aria-labelledby={headingId}>
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
              <h3 id={headingId} className="font-semibold">
                {weekIndex === 0 ? 'Tuần này · áp dụng khi xác nhận' : 'Tuần sau · dự kiến'}
              </h3>
              <span className="caption">{formatDM(weekStart)}–{formatDM(addDays(weekStart, 6))}</span>
            </div>
            <div className="overflow-x-auto pb-2">
              <div className="grid min-w-[980px] grid-cols-7 gap-2" role="grid" aria-label={weekIndex === 0 ? 'Lịch tuần này' : 'Lịch tuần sau'}>
                {dates.map((date, dayIndex) => {
                  const dayItems = items.filter((item) => item.date === date);
                  return (
                    <div key={date} className="min-h-[190px] rounded-xl border border-line bg-canvas p-2.5" role="gridcell">
                      <div className="mb-2 border-b border-line pb-2">
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                          {weekdayShort(dayIndex as Weekday)}
                        </p>
                        <p className="font-semibold tabular-nums">{formatDM(date)}</p>
                      </div>
                      <div className="space-y-2">
                        {dayItems.map((item) => (
                          <CalendarItem
                            key={item.id}
                            item={item}
                            status={item.source === 'pacewise' ? proposedStatus.get(item.id.replace('pacewise:', '')) : undefined}
                            provisional={weekIndex === 1 && item.source === 'pacewise'}
                          />
                        ))}
                        {!dayItems.length && <p className="pt-2 text-center text-xs text-muted">Trống</p>}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        );
      })}
    </div>
  );
}

function CalendarItem({ item, status, provisional }: { item: PlanTimelineItem; status?: ProposedBlockStatus; provisional?: boolean }) {
  const isLms = item.source === 'lms';
  const isBusy = item.source === 'busy';
  return (
    <div
      className={cx(
        'rounded-lg border px-2 py-2 text-xs',
        isLms
          ? 'border-[#C9D8FB] bg-primary-light'
          : isBusy
            ? 'border-[#F3D9A5] bg-warning-light'
            : status === 'added' || status === 'moved'
              ? 'border-[#A8DEC1] bg-success-light ring-1 ring-success/20'
              : 'border-line bg-white',
      )}
    >
      <p className="font-semibold tabular-nums">
        {item.end ? formatRange(item.start, item.end) : item.start}
      </p>
      <p className="mt-1 line-clamp-3 font-medium">{item.title}</p>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {item.courseCode && <Badge tone="neutral">{item.courseCode}</Badge>}
        {isLms && <Badge tone="primary">LMS</Badge>}
        {isBusy && <Badge tone="warning">Bận</Badge>}
        {status === 'added' && <Badge tone="success">Đề xuất thêm</Badge>}
        {status === 'moved' && <Badge tone="success">Đề xuất dời</Badge>}
        {provisional && <Badge tone="accent">Dự kiến tuần sau</Badge>}
      </div>
    </div>
  );
}
