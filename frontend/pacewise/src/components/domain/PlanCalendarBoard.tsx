import { useEffect, useId, useMemo, useRef, useState, type DragEvent, type PointerEvent as ReactPointerEvent } from 'react';
import type { Course, PersonalSlotCategory, RoutineProfile, Task } from '../../types';
import type { PlanTimelineItem } from '../../utils/planTimeline';
import { formatDay, weekdayOf, weekdayShort } from '../../utils/time';
import { Icon } from '../ui/Icon';
import { useCalendarToday } from '../../hooks/useCalendarToday';
import { useElementWidth } from '../../hooks/useElementWidth';
import { calendarDayCount, visibleCalendarDates } from '../../utils/responsiveCalendar';
import { Modal } from '../ui/Modal';
import { calendarFocusMinute } from '../../utils/calendarFocus';
import { CALENDAR_HOUR_HEIGHT as HOUR_HEIGHT, calendarMinuteTop, calendarDurationHeight, calendarDropMinute } from '../../utils/calendarGeometry';

const START_HOUR = 0;
const END_HOUR = 24;
const MIN_EVENT_HEIGHT = 18;
const SELECTED_MIN_EVENT_HEIGHT = 30;
const MIN_VISUAL_DURATION = Math.ceil(((MIN_EVENT_HEIGHT + 3) / HOUR_HEIGHT) * 60);
const EDIT_SNAP_MINUTES = 1;
const MIN_EDITABLE_DURATION = 15;

type DragPayload =
  | { kind: 'block'; id: string; grabOffsetMin?: number }
  | { kind: 'existing-busy'; id: string; grabOffsetMin?: number }
  | { kind: 'busy'; category: PersonalSlotCategory; label: string };

const PACEWISE_DRAG_TYPE = 'application/x-pacewise';
const NEW_PERSONAL_DRAG_TYPE = 'application/x-pacewise-new-personal';

interface EditableCalendarProps {
  readOnly?: false;
  dates: string[];
  selectedDate?: string;
  focusUsefulTime?: boolean;
  toolsPanel?: 'personal' | null;
  onToolsPanelChange?: (panel: 'personal' | null) => void;
  courses: Course[];
  tasks: Task[];
  items: PlanTimelineItem[];
  draftMode: boolean;
  onMoveBlock: (id: string, date: string, start: string) => void;
  onResizeBlock: (id: string, edge: 'start' | 'end', clock: string) => void;
  onResizeBusy: (id: string, edge: 'start' | 'end', clock: string) => void;
  onMoveBusy: (id: string, date: string, start: string) => void;
  onAddBusy: (date: string, start: string, category: PersonalSlotCategory, label: string) => void;
  onOpenPersonal: (category: PersonalSlotCategory, label: string) => void;
  onOpenRoutine: () => void;
  routineProfile: RoutineProfile | null;
  onOpenBlock: (id: string) => void;
  onOpenItem: (item: PlanTimelineItem) => void;
  onRemoveBlock: (id: string) => void;
  onRemoveBusy: (id: string) => void;
}

type PlanCalendarBoardProps = EditableCalendarProps | {
  readOnly: true;
  dates: string[];
  selectedDate?: string;
  items: PlanTimelineItem[];
  /** Hide empty early hours in teaching views; actual earlier events remain visible. */
  startHour?: number;
  onOpenItem?: (item: PlanTimelineItem) => void;
};

const minuteOf = (clock: string) => {
  const [hours, minutes] = clock.split(':').map(Number);
  return hours * 60 + minutes;
};

const clockOf = (minutes: number, allowGridEnd = false) => {
  const maximum = END_HOUR * 60 - (allowGridEnd ? 0 : 1);
  const bounded = Math.max(START_HOUR * 60, Math.min(maximum, minutes));
  return `${String(Math.floor(bounded / 60)).padStart(2, '0')}:${String(bounded % 60).padStart(2, '0')}`;
};

const payloadOf = (event: DragEvent): DragPayload | null => {
  try {
    const raw = event.dataTransfer.getData(PACEWISE_DRAG_TYPE)
      || event.dataTransfer.getData(NEW_PERSONAL_DRAG_TYPE)
      || event.dataTransfer.getData('text/plain');
    return raw ? JSON.parse(raw) as DragPayload : null;
  } catch {
    return null;
  }
};

const setPayload = (event: DragEvent, payload: DragPayload) => {
  const serialized = JSON.stringify(payload);
  // Browsers protect getData() during dragover. A dedicated MIME marker keeps
  // copy-vs-move discoverable through dataTransfer.types before drop.
  event.dataTransfer.effectAllowed = payload.kind === 'busy' ? 'copyMove' : 'move';
  event.dataTransfer.setData(PACEWISE_DRAG_TYPE, serialized);
  event.dataTransfer.setData('text/plain', serialized);
  if (payload.kind === 'busy') event.dataTransfer.setData(NEW_PERSONAL_DRAG_TYPE, serialized);
};

const sourceStyle: Record<PlanTimelineItem['source'], string> = {
  lms: 'border-l-[#596579] bg-[#EEF1F5] text-[#253044]',
  pacewise: 'border-l-[#526FE8] bg-[#E8EDFF] text-[#203A99]',
  busy: 'border-l-[#E8A426] bg-[#FFF5DE] text-[#70480A]',
};

const isPointMarker = (item: PlanTimelineItem) => !item.end && item.durationMin <= 0;

interface PositionedItem {
  item: PlanTimelineItem;
  lane: number;
  laneCount: number;
}

const visualRange = (item: PlanTimelineItem) => {
  const start = Math.max(START_HOUR * 60, Math.min(END_HOUR * 60 - 1, minuteOf(item.start)));
  const actualEnd = item.end ? minuteOf(item.end) : start + Math.max(item.durationMin, 30);
  return { start, end: actualEnd > start ? actualEnd : start + MIN_VISUAL_DURATION };
};

/** Assign overlapping events to horizontal lanes instead of painting them on top of each other. */
export function positionCalendarItems(items: PlanTimelineItem[]): PositionedItem[] {
  const sorted = [...items].sort((left, right) => {
    const leftRange = visualRange(left);
    const rightRange = visualRange(right);
    return leftRange.start - rightRange.start || rightRange.end - leftRange.end || left.id.localeCompare(right.id);
  });
  const result: PositionedItem[] = [];
  let cluster: Array<{ item: PlanTimelineItem; start: number; end: number; lane: number }> = [];
  let clusterEnd = -1;

  const flush = () => {
    if (!cluster.length) return;
    const laneCount = Math.max(...cluster.map((entry) => entry.lane)) + 1;
    cluster.forEach((entry) => result.push({ item: entry.item, lane: entry.lane, laneCount }));
    cluster = [];
    clusterEnd = -1;
  };

  sorted.forEach((item) => {
    const range = visualRange(item);
    if (cluster.length && range.start >= clusterEnd) flush();
    const occupied = new Set(cluster.filter((entry) => entry.end > range.start).map((entry) => entry.lane));
    let lane = 0;
    while (occupied.has(lane)) lane += 1;
    cluster.push({ item, ...range, lane });
    clusterEnd = Math.max(clusterEnd, range.end);
  });
  flush();
  return result;
}

/** Preferred study windows are calendar guides, not competing foreground events. */
export function splitCalendarLayers(items: PlanTimelineItem[]) {
  return {
    background: items.filter((item) => item.kind === 'personal_self_study'),
    foreground: items.filter((item) => item.kind !== 'personal_self_study'),
  };
}

const PERSONAL_CATEGORIES: Array<{ value: PersonalSlotCategory; label: string; help: string }> = [
  { value: 'meal', label: 'Ăn uống', help: 'Khoảng không xếp việc học' },
  { value: 'self_study', label: 'Giờ tự học', help: 'Khung Agent ưu tiên xếp học' },
  { value: 'sleep', label: 'Ngủ', help: 'Khoảng nghỉ được bảo vệ' },
  { value: 'other', label: 'Bận khác', help: 'Bạn tự đặt tên hoạt động' },
];

function PersonalSchedulePanel({ onAdd, onOpenRoutine, routineProfile }: {
  onAdd: (category: PersonalSlotCategory, label: string) => void;
  onOpenRoutine: () => void;
  routineProfile: RoutineProfile | null;
}) {
  const [category, setCategory] = useState<PersonalSlotCategory>('meal');
  const titleId = useId();
  const [customLabel, setCustomLabel] = useState('');
  const selected = PERSONAL_CATEGORIES.find((item) => item.value === category)!;
  const label = category === 'other' ? customLabel.trim() || 'Bận khác' : selected.label;
  return (
    <aside className="flex h-full min-h-0 w-full flex-col bg-white" aria-labelledby={titleId}>
      <div className="border-b border-line px-4 py-3">
        <h2 id={titleId} className="text-sm font-bold">Lịch cá nhân</h2>
        <p className="mt-1 text-xs text-muted">Kéo hoạt động vào lịch hoặc bấm để nhập giờ.</p>
      </div>
      <div className="auto-hide-scrollbar min-h-0 flex-1 overflow-y-auto p-3">
        <label className="text-xs font-bold text-muted">Loại hoạt động
          <select value={category} onChange={(event) => setCategory(event.target.value as PersonalSlotCategory)} className="mt-1 block h-10 w-full rounded-lg border border-line bg-white px-3 text-sm font-semibold text-ink">
            {PERSONAL_CATEGORIES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        {category === 'other' && (
          <label className="mt-3 block text-xs font-bold text-muted">Tên hoạt động
            <input value={customLabel} onChange={(event) => setCustomLabel(event.target.value)} maxLength={80} placeholder="Ví dụ: Làm thêm" className="mt-1 block h-10 w-full rounded-lg border border-line px-3 text-sm font-normal text-ink" />
          </label>
        )}
        <button
          type="button"
          draggable
          onDragStart={(event) => setPayload(event, { kind: 'busy', category, label })}
          onClick={() => onAdd(category, label)}
          className={`mt-3 flex w-full cursor-grab items-start gap-2 rounded-xl border border-dashed px-3 py-3 text-left active:cursor-grabbing ${category === 'self_study' ? 'border-[#7DA98A] bg-[#EEF8F1] text-[#245D34]' : 'border-[#E3B85F] bg-[#FFF9EA] text-[#70480A]'}`}
          title="Kéo vào lịch hoặc bấm để chọn ngày giờ"
        >
          <Icon name={category === 'self_study' ? 'book' : 'plus'} size={16} className="mt-0.5 shrink-0" />
          <span><span className="block text-xs font-bold">{label}</span><span className="mt-0.5 block text-[11px] opacity-75">{selected.help}</span></span>
        </button>
      </div>
      <div className="shrink-0 border-t border-line p-3">
        <button type="button" onClick={onOpenRoutine} className="flex w-full items-center gap-2 rounded-xl border border-line bg-white px-3 py-2.5 text-left hover:bg-slate-50">
          <Icon name="clock" size={16} className="text-primary-ink" />
          <span className="min-w-0"><span className="block text-xs font-bold">Giờ sinh hoạt</span><span className="block truncate text-[11px] text-muted">{routineProfile ? `${routineProfile.wakeTime} thức · ${routineProfile.sleepTime} ngủ` : 'Thiết lập nhịp học cá nhân'}</span></span>
        </button>
      </div>
    </aside>
  );
}

function CalendarEvent({
  readOnly = false,
  gridStartHour = START_HOUR,
  item,
  lane,
  laneCount,
  draftMode,
  onResizeBlock,
  onResizeBusy,
  onOpenBlock,
  onOpenItem,
  onRemoveBlock,
  onRemoveBusy,
  selected,
  interactionLocked,
  onSelect,
}: {
  item: PlanTimelineItem;
  lane: number;
  laneCount: number;
  readOnly?: boolean;
  gridStartHour?: number;
  draftMode?: boolean;
  onResizeBlock?: (id: string, edge: 'start' | 'end', clock: string) => void;
  onResizeBusy?: (id: string, edge: 'start' | 'end', clock: string) => void;
  onOpenBlock?: (id: string) => void;
  onOpenItem?: (item: PlanTimelineItem) => void;
  onRemoveBlock?: (id: string) => void;
  onRemoveBusy?: (id: string) => void;
  selected: boolean;
  interactionLocked: boolean;
  onSelect: (id: string) => void;
}) {
  const start = Math.max(START_HOUR * 60, Math.min(END_HOUR * 60 - 1, minuteOf(item.start)));
  const end = item.end ? minuteOf(item.end) : start + Math.max(item.durationMin, 30);
  const [resizeStart, setResizeStart] = useState<number | null>(null);
  const [resizeEnd, setResizeEnd] = useState<number | null>(null);
  const displayStart = resizeStart ?? start;
  const displayEnd = resizeEnd ?? end;
  const top = calendarMinuteTop(displayStart, gridStartHour);
  const minimumHeight = selected ? SELECTED_MIN_EVENT_HEIGHT : MIN_EVENT_HEIGHT;
  // Valid events retain their true duration, even when selected. Only corrupt
  // legacy zero-duration entries need a readable placeholder.
  const height = displayEnd > displayStart ? calendarDurationHeight(displayEnd - displayStart) : minimumHeight;
  const canMove = !readOnly && item.source === 'pacewise' && !item.readOnly && draftMode && item.entityId;
  const canMoveBusy = !readOnly && item.source === 'busy' && !item.readOnly && draftMode && item.entityId;
  const canDrag = Boolean(canMove || canMoveBusy);
  const canDeleteBusy = !readOnly && draftMode && item.source === 'busy' && !item.readOnly && item.entityId;
  const canResize = selected && Boolean(canMove || canDeleteBusy);
  const canOpen = !readOnly && item.source === 'pacewise' && item.scheduleStatus !== 'history' && Boolean(item.entityId && item.taskId);
  const preferredWindow = item.kind === 'personal_self_study';
  const widthPercent = 100 / laneCount;
  const leftPercent = lane * widthPercent;
  const compact = height < 38;

  const startResize = (edge: 'start' | 'end') => (event: ReactPointerEvent<HTMLButtonElement>) => {
    // A finger swipe belongs to native scrolling. Exact-time editing is available
    // in the event dialog; resize handles remain mouse/pen controls.
    if (event.pointerType === 'touch' || !canResize || !item.entityId) return;
    event.preventDefault();
    event.stopPropagation();
    const originY = Number.isFinite(event.clientY) ? event.clientY : 0;
    const originValue = edge === 'start' ? start : end;
    let latestValue = originValue;
    const move = (pointerEvent: PointerEvent) => {
      const pointerY = Number.isFinite(pointerEvent.clientY) ? pointerEvent.clientY : originY;
      const rawDelta = ((pointerY - originY) / HOUR_HEIGHT) * 60;
      const delta = Math.round(rawDelta / EDIT_SNAP_MINUTES) * EDIT_SNAP_MINUTES;
      latestValue = edge === 'start'
        ? Math.max(START_HOUR * 60, Math.min(end - MIN_EDITABLE_DURATION, originValue + delta))
        : Math.max(start + MIN_EDITABLE_DURATION, Math.min(END_HOUR * 60, originValue + delta));
      if (edge === 'start') setResizeStart(latestValue);
      else setResizeEnd(latestValue);
    };
    const finish = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', finish);
      window.removeEventListener('pointercancel', finish);
      setResizeStart(null);
      setResizeEnd(null);
      if (latestValue !== originValue) {
        const nextClock = clockOf(latestValue, edge === 'end');
        if (item.source === 'pacewise') onResizeBlock?.(item.entityId!, edge, nextClock);
        if (item.source === 'busy') onResizeBusy?.(item.entityId!, edge, nextClock);
      }
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', finish, { once: true });
    window.addEventListener('pointercancel', finish, { once: true });
  };

  return (
    <article
      data-calendar-source={preferredWindow ? 'preferred' : item.source}
      draggable={canDrag}
      onDragStart={(event) => {
        if (interactionLocked || !canDrag) {
          event.preventDefault();
          return;
        }
        // Select at drag start so press-drag works without a separate click.
        onSelect(item.id);
        const rect = event.currentTarget.getBoundingClientRect();
        const pointerY = Number.isFinite(event.clientY) ? event.clientY : rect.top;
        const rawGrabOffset = ((pointerY - rect.top) / HOUR_HEIGHT) * 60;
        const grabOffsetMin = Math.max(0, Math.min(item.durationMin, rawGrabOffset));
        if (canMove) setPayload(event, { kind: 'block', id: item.entityId!, grabOffsetMin });
        if (canMoveBusy) setPayload(event, { kind: 'existing-busy', id: item.entityId!, grabOffsetMin });
      }}
      onClick={(event) => {
        event.stopPropagation();
        if (interactionLocked) return;
        if (readOnly || item.source === 'lms') {
          onOpenItem?.(item);
          return;
        }
        if (!selected) onSelect(item.id);
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        if (interactionLocked || readOnly || item.source === 'lms') return;
        if (canOpen) onOpenBlock?.(item.entityId!);
        else if (canMoveBusy) onOpenItem?.(item);
      }}
      onKeyDown={(event) => {
        if (!interactionLocked && event.key === ' ') {
          event.preventDefault();
          if (!selected) onSelect(item.id);
        }
        if (!interactionLocked && event.key === 'Enter') {
          event.preventDefault();
          if (readOnly || item.source === 'lms') onOpenItem?.(item);
          else if (canOpen) onOpenBlock?.(item.entityId!);
          else if (canMoveBusy) onOpenItem?.(item);
        }
      }}
      role="button"
      tabIndex={!interactionLocked ? 0 : undefined}
      aria-pressed={canDrag ? selected : undefined}
      className={`group absolute overflow-hidden rounded-md border border-white/70 border-l-[3px] ${selected ? 'z-50 ring-2 ring-primary ring-offset-1' : ''} ${interactionLocked ? 'pointer-events-none saturate-50' : ''} ${preferredWindow ? `${selected ? 'bg-[#DDF2E3]/95' : 'bg-[#EAF7EE]/75'} border-dashed border-l-[#4E9462] text-[#245D34]` : `px-2 ${compact ? 'py-0' : 'py-1'} shadow-sm hover:z-50 focus:z-50 ${item.source === 'pacewise' ? 'z-20' : 'z-10'} ${sourceStyle[item.source]}`} ${item.scheduleStatus === 'tentative' ? 'border-dashed opacity-80' : ''} ${item.scheduleStatus === 'history' ? 'opacity-55 grayscale' : ''} ${canDrag ? 'cursor-grab active:cursor-grabbing' : ''}`}
      style={{ top, height, left: `calc(${leftPercent}% + 3px)`, width: `calc(${widthPercent}% - 5px)` }}
      title={`${item.start}${item.end ? `–${item.end}` : ''} · ${item.title}${item.outsidePreferred ? ' · Ngoài khung ưu tiên' : ''}${canOpen || canMoveBusy ? ' · Nhấp đúp để mở chi tiết' : ''}`}
    >
      {preferredWindow ? (
        <>
          {!readOnly && !selected && (
            <button
              type="button"
              aria-label={`Chọn ${item.title}`}
              title="Chọn khung này để kéo hoặc đổi thời lượng"
              onClick={(event) => {
                event.stopPropagation();
                if (!interactionLocked) onSelect(item.id);
              }}
              className="absolute left-0.5 top-0.5 z-30 flex h-4 w-4 items-center justify-center rounded bg-[#4E9462] text-white shadow-sm"
            >
              <Icon name="book" size={10} />
            </button>
          )}
          <p className="absolute inset-x-1 bottom-1 truncate pr-5 text-[9px] font-semibold opacity-70">Giờ tự học ưu tiên · chưa phải ca học</p>
        </>
      ) : <div className={`flex gap-1 ${compact ? 'items-center' : 'items-start'}`}>
        <div className="min-w-0 flex-1">
          {compact ? (
            <p className="truncate text-[10px] font-bold leading-3">
              {clockOf(displayStart)} · {item.courseCode ?? item.title}{item.scheduleStatus === 'tentative' ? ' · Dự kiến' : ''}
            </p>
          ) : (
            <>
              <p className="truncate text-[10px] font-semibold leading-4">{clockOf(displayStart)}{item.end ? `–${clockOf(displayEnd, true)}` : ''}</p>
              <p className={`${height < 48 ? 'truncate' : 'line-clamp-2'} text-[11px] font-bold leading-4`}>{item.courseCode ? `${item.courseCode} · ` : ''}{item.title}{item.scheduleStatus === 'tentative' ? ' · Dự kiến' : ''}</p>
              {item.outsidePreferred && height >= 58 && (
                <p className="mt-0.5 truncate text-[9px] font-semibold text-amber-700">Ngoài khung ưu tiên</p>
              )}
            </>
          )}
        </div>
        {selected && (canMove || canDeleteBusy) && (
          <button
            type="button"
            aria-label={`Xóa ${item.title}`}
            title="Xóa khỏi bản nháp"
            onClick={(event) => {
              event.stopPropagation();
              if (canMove) onRemoveBlock?.(item.entityId!);
              else if (canDeleteBusy) onRemoveBusy?.(item.entityId!);
            }}
            className="mt-0.5 rounded p-0.5 opacity-70 hover:bg-white hover:opacity-100"
          >
            <Icon name="x" size={12} />
          </button>
        )}
      </div>}
      {preferredWindow && selected && canDeleteBusy && (
        <button
          type="button"
          aria-label={`Xóa ${item.title}`}
          title="Xóa khung tự học ưu tiên"
          onClick={(event) => {
            event.stopPropagation();
            onRemoveBusy?.(item.entityId!);
          }}
          className="absolute bottom-1 right-1 z-40 flex h-6 w-6 items-center justify-center rounded-md border border-[#9BC5A6] bg-white text-[#245D34] shadow-sm hover:bg-[#F4FBF6]"
        >
          <Icon name="x" size={14} />
        </button>
      )}
      {canResize && (
        <>
          <button
            type="button"
            draggable={false}
            aria-label={`Thay đổi giờ bắt đầu ${item.title}`}
            title="Kéo lên hoặc xuống để đổi giờ bắt đầu"
            onPointerDown={startResize('start')}
            className={`calendar-resize-handle absolute inset-x-0 top-0 flex h-2.5 touch-none cursor-ns-resize items-center justify-center bg-white/15 opacity-0 transition-opacity hover:bg-white/50 focus:opacity-100 group-hover:opacity-100 ${resizeStart === null ? '' : 'opacity-100'}`}
          >
            <span className="h-0.5 w-5 rounded-full bg-current opacity-45" aria-hidden="true" />
          </button>
          <button
            type="button"
            draggable={false}
            aria-label={`Thay đổi thời lượng ${item.title}`}
            title="Kéo lên hoặc xuống để đổi giờ kết thúc"
            onPointerDown={startResize('end')}
            className={`calendar-resize-handle absolute inset-x-0 bottom-0 flex h-2.5 touch-none cursor-ns-resize items-center justify-center bg-white/15 opacity-0 transition-opacity hover:bg-white/50 focus:opacity-100 group-hover:opacity-100 ${resizeEnd === null ? '' : 'opacity-100'}`}
          >
            <span className="h-0.5 w-5 rounded-full bg-current opacity-45" aria-hidden="true" />
          </button>
        </>
      )}
    </article>
  );
}

export function PlanCalendarBoard(props: PlanCalendarBoardProps) {
  const today = useCalendarToday();
  const { ref: calendarRef, width } = useElementWidth<HTMLElement>();
  const [daySelection, setDaySelection] = useState<{ scope: string; date: string }>();
  const [localPanel, setLocalPanel] = useState<'personal' | null>(null);
  const panel = props.readOnly ? null : props.toolsPanel === undefined ? localPanel : props.toolsPanel;
  const setPanel = (value: 'personal' | null) => {
    if (!props.readOnly && props.onToolsPanelChange) props.onToolsPanelChange(value);
    else setLocalPanel(value);
  };
  const scope = `${props.dates.join(',')}:${props.selectedDate ?? ''}`;
  const selectedDate = daySelection?.scope === scope ? daySelection.date
    : props.dates.includes(props.selectedDate ?? '') ? props.selectedDate!
    : props.dates.includes(today) ? today : props.dates[0];
  const dayCount = calendarDayCount(width, props.dates.length);
  const visibleDates = useMemo(() => visibleCalendarDates(props.dates, selectedDate, dayCount), [props.dates, selectedDate, dayCount]);
  const compact = visibleDates.length < props.dates.length;
  const columns = `48px repeat(${visibleDates.length}, minmax(0, 1fr))`;
  const editable = props.readOnly ? undefined : props;
  const requestedStart = props.readOnly && Number.isFinite(props.startHour)
    ? Math.max(START_HOUR, Math.min(END_HOUR - 1, Math.floor(props.startHour!)))
    : START_HOUR;
  const gridStartHour = Math.min(requestedStart, ...props.items
    .filter((item) => props.dates.includes(item.date) && !isPointMarker(item))
    .map((item) => Math.floor(minuteOf(item.start) / 60)));
  const hours = Array.from({ length: END_HOUR - gridStartHour + 1 }, (_, index) => gridStartHour + index);
  const gridHeight = (END_HOUR - gridStartHour) * HOUR_HEIGHT;
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const focusKey = `${visibleDates.join(',')}:${scope}`;
  const lastFocusKey = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!editable?.focusUsefulTime || !scrollRef.current || lastFocusKey.current === focusKey) return;
    // Wait for asynchronous workspace/LMS data before choosing a useful hour.
    if (!props.items.length) return;
    lastFocusKey.current = focusKey;
    const now = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date());
    const minute = calendarFocusMinute(props.items, visibleDates, today, minuteOf(now));
    const node = scrollRef.current;
    const offset = Math.max(0, calendarMinuteTop(minute, gridStartHour));
    if (getComputedStyle(node).overflowY === 'visible') {
      const page = node.closest<HTMLElement>('.calendar-page');
      if (page) page.scrollTop = node.getBoundingClientRect().top - page.getBoundingClientRect().top + page.scrollTop + offset;
    } else node.scrollTop = offset;
  }, [editable?.focusUsefulTime, focusKey, gridStartHour, props.items, today, visibleDates]);
  useEffect(() => {
    if (selectedItemId && !props.items.some((item) => item.id === selectedItemId && visibleDates.includes(item.date))) {
      setSelectedItemId(null);
    }
  }, [selectedItemId, props.items, visibleDates]);

  const handleDrop = (event: DragEvent<HTMLDivElement>, date: string) => {
    if (!editable) return;
    event.preventDefault();
    const payload = payloadOf(event);
    if (!payload) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const grabOffsetMin = payload.kind === 'busy' ? 0 : payload.grabOffsetMin ?? 0;
    const minute = calendarDropMinute(event.clientY, rect.top, gridStartHour, grabOffsetMin);
    const start = clockOf(minute);
    if (payload.kind === 'block') editable.onMoveBlock(payload.id, date, start);
    if (payload.kind === 'existing-busy') editable.onMoveBusy(payload.id, date, start);
    if (payload.kind === 'busy') editable.onAddBusy(date, start, payload.category, payload.label);
    setSelectedItemId(null);
  };

  return (
    <div className="calendar-board flex h-full min-h-0 min-w-0 overflow-hidden rounded-2xl border border-line bg-white shadow-card">
      <section ref={calendarRef} className="calendar-timeline-section flex h-full min-h-0 min-w-0 flex-1 flex-col" aria-label={props.readOnly ? 'Lịch tuần chỉ xem' : 'Lịch tuần kéo thả'}>
        {editable && <div className="calendar-panel-actions flex shrink-0 gap-2 border-b border-line p-2">
          <button type="button" onClick={() => setPanel('personal')} className="flex min-h-11 min-w-0 flex-1 items-center justify-center gap-2 rounded-xl bg-primary-light text-sm font-semibold text-primary-ink"><Icon name="plus" size={16} />Lịch cá nhân</button>
        </div>}
        {compact && <div className="shrink-0 border-b border-line bg-white px-1 py-2">
          <div className="grid grid-cols-7 gap-0.5" role="group" aria-label="Chọn ngày trong tuần">
            {props.dates.map((date) => <button key={date} type="button" aria-label={`Xem ngày ${formatDay(date)}`} aria-pressed={visibleDates.includes(date)} aria-current={date === today ? 'date' : undefined}
              onClick={() => { setDaySelection({ scope, date }); setSelectedItemId(null); }}
              className={`min-h-11 min-w-0 rounded-xl px-0.5 text-center text-xs ${visibleDates.includes(date) ? 'bg-primary-light font-bold text-primary-ink' : 'text-muted'} ${date === today ? 'ring-1 ring-inset ring-primary' : ''}`}>
              <span className="block text-[10px]">{weekdayShort(weekdayOf(date))}</span>
              <span className="block text-sm font-bold">{Number(date.slice(8, 10))}</span>
            </button>)}
          </div>
        </div>}
        <div className="calendar-timeline-body min-h-0 min-w-0 flex-1">
          <div className="calendar-timeline-content flex h-full min-w-0 flex-col">
            <div className="calendar-timeline-header z-20 grid shrink-0 border-b border-line bg-white" style={{ gridTemplateColumns: columns }}>
              <div className="border-r border-line" />
              {visibleDates.map((date) => {
                const markers = props.items.filter((item) => item.date === date && isPointMarker(item));
                return (
                  <div key={date} aria-current={date === today ? 'date' : undefined} className={`min-w-0 border-r border-line px-2 py-2 text-center last:border-r-0 ${date === today ? 'calendar-today-header' : ''}`}>
                    <p className="text-xs font-bold capitalize text-ink">{formatDay(date, { short: true })}</p>
                    <p className="text-[11px] text-muted">{date.slice(8, 10)}/{date.slice(5, 7)}</p>
                    {date === today && <span className="calendar-today-badge">Hôm nay</span>}
                    {markers.length > 0 && (
                      <div
                        className="mt-1 flex min-w-0 items-center justify-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600"
                        title={markers.map((item) => `${item.start} · ${item.courseCode ? `${item.courseCode} · ` : ''}${item.title}`).join('\n')}
                      >
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" aria-hidden="true" />
                        <span className="truncate">{markers[0].start} · {markers[0].courseCode ?? markers[0].kindLabel}</span>
                        {markers.length > 1 && <span className="shrink-0">+{markers.length - 1}</span>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div ref={scrollRef} data-calendar-hour-height={HOUR_HEIGHT} className="calendar-timeline-scroll auto-hide-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain" tabIndex={0} aria-label="Cuộn theo giờ">
              <div className="grid" style={{ gridTemplateColumns: columns }}>
                <div className="relative border-r border-line bg-canvas" style={{ height: gridHeight }} aria-hidden="true">
                  {hours.slice(0, -1).map((hour) => (
                    <span key={hour} className={`absolute right-2 text-[10px] font-medium text-muted ${hour === gridStartHour ? '' : '-translate-y-1/2'}`} style={{ top: hour === gridStartHour ? 4 : (hour - gridStartHour) * HOUR_HEIGHT }}>
                      {String(hour).padStart(2, '0')}:00
                    </span>
                  ))}
                </div>

                {visibleDates.map((date) => (
                  <div
                    key={date}
                    aria-label={`Lịch ngày ${date}`}
                    className={`relative border-r border-line last:border-r-0 ${date === today ? 'calendar-today-column' : ''}`}
                    style={{ height: gridHeight }}
                    onDragOver={(event) => {
                      if (!editable) return;
                      event.preventDefault();
                      // getData() may be empty until drop; MIME types remain readable.
                      const isNewPersonal = Array.from(event.dataTransfer.types ?? []).includes(NEW_PERSONAL_DRAG_TYPE);
                      event.dataTransfer.dropEffect = isNewPersonal ? 'copy' : 'move';
                    }}
                    onDrop={(event) => handleDrop(event, date)}
                    onClick={() => setSelectedItemId(null)}
                  >
                    {hours.slice(0, -1).map((hour) => (
                      <div key={hour} data-calendar-hour={hour} aria-hidden="true" className="calendar-hour-cell pointer-events-none absolute inset-x-0 border-t border-line" style={{ top: calendarMinuteTop(hour * 60, gridStartHour), height: HOUR_HEIGHT }} />
                    ))}
                    {splitCalendarLayers(props.items.filter((item) => item.date === date && !isPointMarker(item))).background
                      .map((item) => (
                        <CalendarEvent
                          key={item.id}
                          item={item}
                          lane={0}
                          laneCount={1}
                          readOnly={props.readOnly}
                          gridStartHour={gridStartHour}
                          draftMode={editable?.draftMode}
                          onResizeBlock={editable?.onResizeBlock}
                          onResizeBusy={editable?.onResizeBusy}
                          onOpenBlock={editable?.onOpenBlock}
                          onOpenItem={props.onOpenItem}
                          onRemoveBlock={editable?.onRemoveBlock}
                          onRemoveBusy={editable?.onRemoveBusy}
                          selected={selectedItemId === item.id}
                          interactionLocked={false}
                          onSelect={setSelectedItemId}
                        />
                      ))}
                    {positionCalendarItems(splitCalendarLayers(props.items.filter((item) => item.date === date && !isPointMarker(item))).foreground).map(({ item, lane, laneCount }) => (
                      <CalendarEvent
                        key={item.id}
                        item={item}
                        lane={lane}
                        laneCount={laneCount}
                        readOnly={props.readOnly}
                        gridStartHour={gridStartHour}
                        draftMode={editable?.draftMode}
                        onResizeBlock={editable?.onResizeBlock}
                        onResizeBusy={editable?.onResizeBusy}
                        onOpenBlock={editable?.onOpenBlock}
                        onOpenItem={props.onOpenItem}
                        onRemoveBlock={editable?.onRemoveBlock}
                        onRemoveBusy={editable?.onRemoveBusy}
                        selected={selectedItemId === item.id}
                        interactionLocked={false}
                        onSelect={setSelectedItemId}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
      {editable && <div className="calendar-input-panel w-[220px] shrink-0 border-l border-line"><PersonalSchedulePanel onAdd={editable.onOpenPersonal} onOpenRoutine={editable.onOpenRoutine} routineProfile={editable.routineProfile} /></div>}
      {editable && <Modal open={panel !== null} onClose={() => setPanel(null)} title="Thêm lịch cá nhân">
        {panel === 'personal' && <PersonalSchedulePanel onAdd={(category, label) => { setPanel(null); editable.onOpenPersonal(category, label); }} onOpenRoutine={() => { setPanel(null); editable.onOpenRoutine(); }} routineProfile={editable.routineProfile} />}
      </Modal>}
    </div>
  );
}
