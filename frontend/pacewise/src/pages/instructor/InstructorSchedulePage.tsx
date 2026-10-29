import { useMemo, useState } from 'react';
import { PlanCalendarBoard } from '../../components/domain/PlanCalendarBoard';
import { PlanMonthBoard } from '../../components/domain/PlanMonthBoard';
import { Button, ButtonLink, IconButton } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useAppStore } from '../../store/AppStore';
import { buildTeachingCalendar } from '../../utils/teachingCalendar';
import { Icon } from '../../components/ui/Icon';
import { addDays, calendarWeekStart, currentAppDateTime, diffDays, formatDay, formatDM } from '../../utils/time';
import { useLocale } from '../../i18n/LocaleContext';

type CalendarView = 'week' | 'month' | 'next7';
const monthStartOf = (date: string) => `${date.slice(0, 7)}-01`;
const addMonths = (date: string, offset: number) => {
  const [year, month] = date.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1 + offset, 1)).toISOString().slice(0, 10);
};

export function InstructorSchedulePage() {
  useDocumentTitle('Lịch dạy');
  const { state } = useAppStore();
  const { locale } = useLocale();
  const [view, setView] = useState<CalendarView>('week');
  const [anchor, setAnchor] = useState(() => currentAppDateTime().date);
  const [courseId, setCourseId] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const monthStart = monthStartOf(anchor);
  const from = view === 'month' ? calendarWeekStart(monthStart) : view === 'week' ? calendarWeekStart(anchor) : anchor;
  const to = view === 'month' ? addDays(calendarWeekStart(addDays(addMonths(monthStart, 1), -1)), 6) : addDays(from, 6);
  const dates = useMemo(() => Array.from({ length: diffDays(from, to) + 1 }, (_, index) => addDays(from, index)), [from, to]);
  const items = useMemo(() => buildTeachingCalendar({ courses: state.courses, courseData: state.courseData, courseId, from, to }), [state.courses, state.courseData, courseId, from, to]);
  const selected = items.find((item) => item.id === selectedId);
  const selectedCourse = selected ? state.courses.find((course) => course.id === selected.courseId) : undefined;
  const shift = (direction: -1 | 1) => {
    setSelectedId(null);
    setAnchor((current) => view === 'month' ? addMonths(current, direction) : addDays(current, direction * 7));
  };

  return (
    <div className="calendar-page flex min-h-0 flex-col overflow-hidden bg-canvas" tabIndex={0} aria-label="Cuộn lịch">
      <header className="calendar-toolbar shrink-0 border-b border-line bg-white px-3 py-2 sm:px-5">
        <div className="calendar-toolbar-title min-w-0">
          <h1 className="text-lg font-bold">Lịch dạy</h1>
          <p className="text-[11px] text-muted">{view === 'month' ? `${monthStart.slice(5, 7)}/${monthStart.slice(0, 4)}` : `${formatDM(from)}–${formatDM(to)}`} · GMT+7</p>
        </div>
        <div className="calendar-toolbar-views inline-flex rounded-lg border border-line bg-white p-0.5" role="group" aria-label="Kiểu hiển thị lịch">
          {([['week', 'Tuần'], ['month', 'Tháng'], ['next7', '7 ngày tới']] as const).map(([value, label]) => (
            <button key={value} type="button" aria-pressed={view === value} onClick={() => { setView(value); setSelectedId(null); }} className={`min-h-8 rounded-md px-3 text-xs font-semibold ${view === value ? 'bg-primary-light text-primary-ink' : 'text-muted hover:bg-slate-50'}`}>{label}</button>
          ))}
        </div>
        <div className="calendar-toolbar-dates flex min-w-0 items-center gap-1">
        <IconButton icon="chevronLeft" label="Khoảng trước" className="shrink-0" onClick={() => shift(-1)} />
        <input type="date" value={anchor} onChange={(event) => { setAnchor(event.target.value || currentAppDateTime().date); setSelectedId(null); }} className="h-9 max-w-full rounded-lg border border-line bg-white px-2 text-xs font-semibold" aria-label="Chọn ngày" />
        <Button size="sm" variant="ghost" title="Hôm nay" onClick={() => { setAnchor(currentAppDateTime().date); setSelectedId(null); }}><span className="sr-only sm:not-sr-only">Hôm nay</span><Icon name="clock" size={18} className="sm:hidden" /></Button>
        <IconButton icon="chevronRight" label="Khoảng sau" className="shrink-0" onClick={() => shift(1)} />
        </div>
        <div className="calendar-toolbar-actions flex min-w-0 flex-wrap items-center gap-2">
        <label className="calendar-course-filter flex min-w-0 max-w-full flex-1 items-center gap-2 text-xs font-semibold">
          <span className="shrink-0">Môn học</span>
          <select aria-label="Lọc lịch theo môn học" value={courseId} onChange={(event) => { setCourseId(event.target.value); setSelectedId(null); }} className="h-9 min-w-0 w-full max-w-[320px] rounded-lg border border-line bg-white px-2 text-xs font-semibold">
            <option value="all">Tất cả môn</option>
            {state.courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.name}</option>)}
          </select>
        </label>
        <ButtonLink to="/instructor/courses" size="sm" variant="secondary">Môn học / nhập Excel</ButtonLink>
        </div>
      </header>
      <div className="calendar-status shrink-0 border-b border-line bg-white px-4 py-2 text-xs text-muted sm:px-5" aria-live="polite">
        {locale === 'en'
          ? `Read only · ${new Set(items.map((item) => item.details.id)).size} events · Calendar editing and dragging are disabled`
          : `Chỉ xem · ${new Set(items.map((item) => item.details.id)).size} sự kiện · Không chỉnh sửa hoặc kéo thả lịch`}
        {state.settings.staleData && <p role="alert" className="mt-1 text-warning-ink">Đồng bộ chưa thành công. Lịch đang hiển thị dữ liệu đã tải gần nhất.</p>}
        {!state.workspaceReady && <p role="status" className="mt-1">Đang tải lịch dạy…</p>}
        {state.workspaceReady && !items.length && <p className="mt-1">Chưa có lịch cho môn học và khoảng thời gian đang chọn.</p>}
      </div>
      <div className="calendar-board-frame min-h-0 flex-1 overflow-hidden p-3 sm:p-4">
        {view === 'month' ? (
          <PlanMonthBoard dates={dates} month={monthStart.slice(0, 7)} items={items} onSelectDate={(date) => { setAnchor(date); setView('week'); }} />
        ) : (
          <PlanCalendarBoard readOnly startHour={7} dates={dates} selectedDate={anchor} items={items} onOpenItem={(item) => setSelectedId(item.id)} />
        )}
      </div>
      <Modal open={!!selected} onClose={() => setSelectedId(null)} title="Chi tiết lịch dạy" description="Chỉ xem thông tin. Không thay đổi lịch trong PaceWise.">
        {selected && <dl className="space-y-3 text-sm">
          <div><dt className="caption">Buổi học</dt><dd className="font-semibold">{selected.title}</dd></div>
          <div><dt className="caption">Môn học</dt><dd>{selectedCourse ? `${selectedCourse.code} · ${selectedCourse.name}` : selected.courseCode}</dd></div>
          <div><dt className="caption">Thời gian hiển thị · GMT+7</dt><dd>{formatDay(selected.date)} · {selected.start}{selected.end ? `–${selected.end}` : ''}</dd></div>
          <div><dt className="caption">Loại</dt><dd>{selected.kindLabel}</dd></div>
          <div><dt className="caption">Nguồn</dt><dd>{selected.details.source === 'pacewise_instructor' ? 'Lịch giảng viên đã tạo trong PaceWise' : 'LMS'}</dd></div>
          {selected.details.location && <div><dt className="caption">Địa điểm</dt><dd>{selected.details.location}</dd></div>}
          {selected.details.meeting_url && <div><dt className="caption">Thông tin online</dt><dd className="break-all">{selected.details.meeting_url}</dd></div>}
          {selected.details.preparation && <div><dt className="caption">Chuẩn bị</dt><dd className="whitespace-pre-wrap">{selected.details.preparation}</dd></div>}
        </dl>}
      </Modal>
    </div>
  );
}
