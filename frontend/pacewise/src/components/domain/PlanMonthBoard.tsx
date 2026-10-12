import type { PlanTimelineItem } from '../../utils/planTimeline';
import { formatDay } from '../../utils/time';
import { useCalendarToday } from '../../hooks/useCalendarToday';

interface PlanMonthBoardProps {
  dates: string[];
  month: string;
  items: PlanTimelineItem[];
  onSelectDate: (date: string) => void;
}

const sourceDot: Record<PlanTimelineItem['source'], string> = {
  lms: 'bg-slate-500',
  pacewise: 'bg-primary',
  busy: 'bg-warning',
};

export function PlanMonthBoard({ dates, month, items, onSelectDate }: PlanMonthBoardProps) {
  const today = useCalendarToday();
  return (
    <section className="auto-hide-scrollbar h-full overflow-y-auto rounded-2xl border border-line bg-white shadow-card" aria-label="Tổng quan tháng">
      <div className="sticky top-0 z-10 grid grid-cols-7 border-b border-line bg-white">
        {['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map((day) => (
          <div key={day} className="border-r border-line px-2 py-2 text-center text-xs font-bold last:border-r-0">{day}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {dates.map((date) => {
          const dayItems = items.filter((item) => item.date === date);
          const inMonth = date.startsWith(month);
          return (
            <button
              key={date}
              type="button"
              onClick={() => onSelectDate(date)}
              className={`min-h-[76px] min-w-0 border-b border-r border-line p-1 text-left align-top hover:bg-primary-light/40 sm:min-h-[108px] sm:p-2 ${date === today ? 'calendar-today-header' : inMonth ? 'bg-white' : 'bg-slate-50 text-slate-400'}`}
              aria-current={date === today ? 'date' : undefined}
              aria-label={`${formatDay(date)} · ${dayItems.length} mục`}
            >
              <span className="text-xs font-bold">{Number(date.slice(8, 10))}</span>
              <span className="mt-1.5 block text-[10px] font-semibold text-primary-ink sm:hidden">{dayItems.length ? `${dayItems.length} mục` : ''}</span>
              <span className="mt-1.5 hidden space-y-1 sm:block">
                {dayItems.slice(0, 3).map((item) => (
                  <span key={item.id} className="flex min-w-0 items-center gap-1 rounded bg-canvas px-1.5 py-1 text-[10px] text-ink">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${sourceDot[item.source]}`} aria-hidden="true" />
                    <span className="truncate">{item.start} {item.title}</span>
                  </span>
                ))}
                {dayItems.length > 3 && <span className="block px-1 text-[10px] font-semibold text-primary-ink">+{dayItems.length - 3} mục</span>}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
