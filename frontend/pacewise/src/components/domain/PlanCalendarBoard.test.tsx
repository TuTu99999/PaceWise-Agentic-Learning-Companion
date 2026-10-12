import { act, createEvent, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Course, Task } from '../../types';
import type { PlanTimelineItem } from '../../utils/planTimeline';
import { PlanCalendarBoard, positionCalendarItems, splitCalendarLayers } from './PlanCalendarBoard';

const course: Course = { id: '1', code: 'CS101', name: 'Python', tone: 'primary' };
const task: Task = {
  id: 'task-1', title: 'Mini project', courseId: '1', deadline: '2026-10-10', estimateMin: 120,
  loggedMin: 0, status: 'todo', priority: 'high', objective: 'Hoàn thành bài',
};
const item: PlanTimelineItem = {
  id: 'pacewise:block-1', entityId: 'block-1', taskId: 'task-1', source: 'pacewise', title: 'Mini project',
  date: '2026-10-05', start: '19:00', end: '20:00', durationMin: 60, courseCode: 'CS101',
  kind: 'study_block', kindLabel: 'Study block', readOnly: false,
};
const deadline: PlanTimelineItem = {
  id: 'lms:deadline:task-1', source: 'lms', title: 'Deadline · Mini project', date: '2026-10-05',
  start: '19:30', durationMin: 0, courseCode: 'CS101', kind: 'assignment', kindLabel: 'Deadline', readOnly: true,
};

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function measuredCalendar(width: number) {
  let resize!: () => void;
  let currentWidth = width;
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({
    width: currentWidth, height: 1000, top: 0, left: 0, right: currentWidth, bottom: 1000, x: 0, y: 0, toJSON: () => ({}),
  }));
  const disconnect = vi.fn();
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resize = callback; }
    observe() {}
    disconnect = disconnect;
  });
  return { resize: (next: number) => act(() => { currentWidth = next; resize(); }), disconnect };
}

describe('PlanCalendarBoard', () => {
  it('uses two readable days on mobile, selects Sunday, and restores the full week on resize', () => {
    const measured = measuredCalendar(390);
    const dates = ['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11'];
    const { unmount } = render(<PlanCalendarBoard readOnly dates={dates} selectedDate={dates[0]} items={[item]} />);
    expect(screen.getAllByLabelText(/^Lịch ngày /)).toHaveLength(2);
    expect(screen.getByLabelText('Lịch ngày 2026-10-05')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Xem ngày Chủ Nhật 11/10' }));
    expect(screen.getByLabelText('Lịch ngày 2026-10-11')).toBeInTheDocument();
    expect(screen.queryByLabelText('Lịch ngày 2026-10-05')).not.toBeInTheDocument();
    measured.resize(900);
    expect(screen.getAllByLabelText(/^Lịch ngày /)).toHaveLength(7);
    expect(screen.queryByRole('group', { name: 'Chọn ngày trong tuần' })).not.toBeInTheDocument();
    measured.resize(320);
    expect(screen.getAllByLabelText(/^Lịch ngày /)).toHaveLength(1);
    expect(screen.getByLabelText('Lịch ngày 2026-10-11')).toBeInTheDocument();
    unmount(); expect(measured.disconnect).toHaveBeenCalled();
  });

  it('resets the day window when the parent changes week or selects an exact date', () => {
    measuredCalendar(320);
    const dates = ['2026-10-05', '2026-10-06', '2026-10-07'];
    const { rerender } = render(<PlanCalendarBoard readOnly dates={dates} selectedDate={dates[0]} items={[]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Xem ngày Thứ Tư 07/10' }));
    rerender(<PlanCalendarBoard readOnly dates={dates} selectedDate={dates[1]} items={[]} />);
    expect(screen.getByLabelText('Lịch ngày 2026-10-06')).toBeInTheDocument();
    rerender(<PlanCalendarBoard readOnly dates={['2026-10-12', '2026-10-13']} items={[]} />);
    expect(screen.getByLabelText('Lịch ngày 2026-10-12')).toBeInTheDocument();
  });

  it('opens personal tools in a dialog and hands off to the exact-time form', () => {
    measuredCalendar(390); const onOpenPersonal = vi.fn();
    render(<PlanCalendarBoard dates={[item.date]} courses={[course]} tasks={[task]} items={[item]} draftMode
      onMoveBlock={vi.fn()} onMoveBusy={vi.fn()} onResizeBlock={vi.fn()} onResizeBusy={vi.fn()}
      onAddBusy={vi.fn()} onOpenPersonal={onOpenPersonal} onOpenRoutine={vi.fn()} onOpenBlock={vi.fn()}
      onOpenItem={vi.fn()} routineProfile={null} onRemoveBlock={vi.fn()} onRemoveBusy={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Lịch cá nhân' }));
    const dialog = screen.getByRole('dialog', { name: 'Thêm lịch cá nhân' });
    fireEvent.change(within(dialog).getByLabelText('Loại hoạt động'), { target: { value: 'self_study' } });
    fireEvent.click(within(dialog).getByRole('button', { name: /Giờ tự học/ }));
    expect(onOpenPersonal).toHaveBeenCalledWith('self_study', 'Giờ tự học');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it.each([
    ['meal', 'Ăn uống'],
    ['self_study', 'Giờ tự học'],
    ['sleep', 'Ngủ'],
    ['other', 'Bận khác'],
  ] as const)('drops %s into Sunday even when dragover data is browser-protected', (category, label) => {
    const onAddBusy = vi.fn();
    const dates = ['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11'];
    render(<PlanCalendarBoard dates={dates} selectedDate="2026-10-11" courses={[course]} tasks={[task]} items={[]} draftMode
      onMoveBlock={vi.fn()} onMoveBusy={vi.fn()} onResizeBlock={vi.fn()} onResizeBusy={vi.fn()}
      onAddBusy={onAddBusy} onOpenPersonal={vi.fn()} onOpenRoutine={vi.fn()} onOpenBlock={vi.fn()}
      onOpenItem={vi.fn()} routineProfile={null} onRemoveBlock={vi.fn()} onRemoveBusy={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Loại hoạt động'), { target: { value: category } });
    const source = screen.getByRole('button', { name: new RegExp(label) });
    const data = new Map<string, string>();
    let protectedMode = false;
    const dataTransfer = {
      effectAllowed: 'none', dropEffect: 'none', types: [] as string[],
      setData: vi.fn((type: string, value: string) => { data.set(type, value); if (!dataTransfer.types.includes(type)) dataTransfer.types.push(type); }),
      getData: vi.fn((type: string) => protectedMode ? '' : data.get(type) ?? ''),
    };
    fireEvent.dragStart(source, { dataTransfer });
    const sunday = screen.getByLabelText('Lịch ngày 2026-10-11');
    protectedMode = true;
    fireEvent.dragOver(sunday, { dataTransfer });
    expect(dataTransfer.dropEffect).toBe('copy');
    protectedMode = false;
    const drop = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperties(drop, {
      clientY: { value: 18 * 80 },
      dataTransfer: { value: dataTransfer },
    });
    fireEvent(sunday, drop);
    expect(onAddBusy).toHaveBeenCalledWith('2026-10-11', '18:00', category, label);
  });
  it('hides empty overnight hours in the teaching view without shifting event times or duration', () => {
    render(<PlanCalendarBoard readOnly startHour={7} dates={['2026-10-05']} items={[item]} />);
    expect(screen.queryByText('00:00')).not.toBeInTheDocument();
    expect(screen.queryByText('06:00')).not.toBeInTheDocument();
    expect(screen.getByText('07:00')).toBeInTheDocument();
    const event = screen.getByTitle('19:00–20:00 · Mini project');
    expect(event.style.top).toBe('960px');
    expect(event.style.height).toBe('80px');
  });

  it('preserves real earlier events if the teaching timetable contains one', () => {
    const early = { ...item, start: '06:30', end: '07:30' };
    render(<PlanCalendarBoard readOnly startHour={7} dates={['2026-10-05']} items={[early]} />);
    expect(screen.queryByText('00:00')).not.toBeInTheDocument();
    expect(screen.getByText('06:00')).toBeInTheDocument();
    expect(screen.getByTitle('06:30–07:30 · Mini project').style.top).toBe('40px');
  });

  it('positions late-night teaching events at the exact minute without clamping to 23:00', () => {
    const late = { ...item, source: 'lms' as const, readOnly: true, title: 'Late class', start: '23:45', end: '24:00', durationMin: 15 };
    render(<PlanCalendarBoard readOnly dates={['2026-10-05']} items={[late]} />);
    const event = screen.getByTitle('23:45–24:00 · Late class');
    expect(event.style.top).toBe('1900px');
    expect(event.style.height).toBe('20px');
    expect(event).toHaveClass('py-0');
    expect(event).toHaveTextContent('23:45');
  });

  it('enforces read-only mode even when supplied editable student or personal items', () => {
    const onOpenItem = vi.fn();
    const personal = { ...item, id: 'busy:meal', source: 'busy' as const, title: 'Dinner', kind: 'personal_busy' };
    render(<PlanCalendarBoard readOnly dates={['2026-10-05']} items={[item, personal]} onOpenItem={onOpenItem} />);
    expect(screen.queryByLabelText('Chọn nhiệm vụ')).not.toBeInTheDocument();
    expect(screen.queryByText('Lịch cá nhân')).not.toBeInTheDocument();
    const study = screen.getByTitle('19:00–20:00 · Mini project');
    expect(study).toHaveAttribute('draggable', 'false');
    fireEvent.click(study);
    expect(onOpenItem).toHaveBeenCalledWith(item);
    fireEvent.keyDown(study, { key: 'Enter' });
    expect(onOpenItem).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: /Xóa|Thay đổi|Giờ sinh hoạt/ })).not.toBeInTheDocument();
    const dataTransfer = { setData: vi.fn(), getData: vi.fn(() => JSON.stringify({ kind: 'busy', category: 'meal', label: 'Dinner' })) };
    fireEvent.dragStart(study, { dataTransfer });
    fireEvent.drop(screen.getByLabelText('Lịch ngày 2026-10-05'), { dataTransfer });
    expect(dataTransfer.setData).not.toHaveBeenCalled();
    expect(dataTransfer.getData).not.toHaveBeenCalled();
  });

  it('presents read-only LMS task selection and the positioned study block', () => {
    Object.defineProperty(window, 'PointerEvent', { configurable: true, writable: true, value: MouseEvent });
    const onResizeBlock = vi.fn();
    const onOpenBlock = vi.fn();
    render(
      <PlanCalendarBoard
        dates={['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11']}
        courses={[course]}
        tasks={[task]}
        items={[item, deadline]}
        draftMode
        onMoveBlock={vi.fn()}
        onMoveBusy={vi.fn()}
        onResizeBlock={onResizeBlock}
        onResizeBusy={vi.fn()}
        onAddBusy={vi.fn()}
        onOpenPersonal={vi.fn()}
        onOpenRoutine={vi.fn()}
        onOpenBlock={onOpenBlock}
        onOpenItem={vi.fn()}
        routineProfile={null}
        onRemoveBlock={vi.fn()}
        onRemoveBusy={vi.fn()}
      />,
    );

    expect(screen.getAllByText(/Mini project/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByLabelText('Chọn nhiệm vụ')).toBeTruthy();
    expect(screen.queryByLabelText('Ưu tiên cá nhân cho Mini project')).not.toBeInTheDocument();
    expect(screen.getByText(/Plan đề xuất thứ tự theo deadline/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Lịch cá nhân' })).toBeTruthy();
    expect(screen.getAllByText('Ăn uống')).toHaveLength(2);
    expect(screen.getByRole('button', { name: /Giờ sinh hoạt/ })).toBeTruthy();
    expect(screen.getByTitle(/19:30 · CS101 · Deadline/)).toBeTruthy();
    const studyBlock = screen.getByTitle(/Nhấp đúp để mở chi tiết/);
    fireEvent.click(studyBlock);
    expect(onOpenBlock).not.toHaveBeenCalled();
    fireEvent.doubleClick(studyBlock);
    expect(onOpenBlock).toHaveBeenCalledWith('block-1');
    expect(screen.getByRole('button', { name: 'Xóa Mini project' })).toBeTruthy();
    const resizeHandle = screen.getByRole('button', { name: 'Thay đổi thời lượng Mini project' });
    const touchResizeStart = createEvent.pointerDown(resizeHandle, { clientY: 100 });
    // jsdom's MouseEvent fallback does not populate PointerEvent.pointerType.
    Object.defineProperty(touchResizeStart, 'pointerType', { value: 'touch' });
    fireEvent(resizeHandle, touchResizeStart);
    fireEvent.pointerMove(window, { clientY: 129, pointerType: 'touch' });
    fireEvent.pointerUp(window, { clientY: 129, pointerType: 'touch' });
    expect(onResizeBlock).not.toHaveBeenCalled();
    fireEvent.pointerDown(resizeHandle, { clientY: 100 });
    fireEvent.pointerMove(window, { clientY: 140 });
    fireEvent.pointerUp(window, { clientY: 140 });
    expect(onResizeBlock).toHaveBeenCalledWith('block-1', 'end', '20:30');

    const startHandle = screen.getByRole('button', { name: 'Thay đổi giờ bắt đầu Mini project' });
    fireEvent.pointerDown(startHandle, { clientY: 100 });
    fireEvent.pointerMove(window, { clientY: 60 });
    fireEvent.pointerUp(window, { clientY: 60 });
    expect(onResizeBlock).toHaveBeenCalledWith('block-1', 'start', '18:30');
  });

  it('places overlapping items in separate horizontal lanes', () => {
    const overlapping = { ...item, id: 'pacewise:block-2', entityId: 'block-2', start: '19:30', end: '20:30' };
    const positioned = positionCalendarItems([item, overlapping]);

    expect(positioned.map((entry) => entry.laneCount)).toEqual([2, 2]);
    expect(new Set(positioned.map((entry) => entry.lane)).size).toBe(2);
  });
  it('renders one compact cell per hour and minute-accurate event dimensions', () => {
    const precise = { ...item, start: '19:07', end: '20:13', durationMin: 66 };
    const short = { ...item, id: 'short', entityId: 'short', title: 'Short lesson', start: '21:03', end: '21:10', durationMin: 7 };
    const { container } = render(<PlanCalendarBoard readOnly dates={['2026-10-05']} items={[precise, short]} />);
    expect(container.querySelectorAll('[data-calendar-hour]')).toHaveLength(24);
    expect(container.querySelector('[data-calendar-hour="19"]')).toHaveStyle({ height: '80px', top: '1520px' });
    expect(container.querySelector('[data-calendar-hour] .border-dashed')).toBeNull();
    const event = screen.getByTitle('19:07–20:13 · Mini project');
    expect(parseFloat(event.style.top)).toBeCloseTo(1529.333333);
    expect(event).toHaveStyle({ height: '88px' });
    const shortEvent = screen.getByTitle('21:03–21:10 · Short lesson');
    expect(parseFloat(shortEvent.style.top)).toBeCloseTo(1684);
    expect(parseFloat(shortEvent.style.height)).toBeCloseTo(9.333333);
  });

  it('keeps preferred self-study windows behind study blocks', () => {
    const preferredWindow: PlanTimelineItem = {
      id: 'busy:self-study', entityId: 'self-study', source: 'busy', title: 'Giờ tự học',
      date: '2026-10-05', start: '19:00', end: '22:00', durationMin: 180,
      kind: 'personal_self_study', kindLabel: 'Khung tự học ưu tiên', readOnly: false,
    };
    const layers = splitCalendarLayers([preferredWindow, item]);

    expect(layers.background.map((entry) => entry.id)).toEqual(['busy:self-study']);
    expect(layers.foreground.map((entry) => entry.id)).toEqual(['pacewise:block-1']);
    expect(positionCalendarItems(layers.foreground)[0]).toMatchObject({ lane: 0, laneCount: 1 });
  });

  it('selects and deletes a preferred self-study window without running AI first', () => {
    const preferredWindow: PlanTimelineItem = {
      id: 'busy:self-study', entityId: 'self-study', source: 'busy', title: 'Giờ tự học',
      date: '2026-10-05', start: '19:00', end: '22:00', durationMin: 180,
      kind: 'personal_self_study', kindLabel: 'Khung tự học ưu tiên', readOnly: false,
    };
    const onRemoveBusy = vi.fn();
    render(
      <PlanCalendarBoard
        dates={['2026-10-05']}
        courses={[course]}
        tasks={[task]}
        items={[preferredWindow]}
        draftMode
        onMoveBlock={vi.fn()}
        onMoveBusy={vi.fn()}
        onResizeBlock={vi.fn()}
        onResizeBusy={vi.fn()}
        onAddBusy={vi.fn()}
        onOpenPersonal={vi.fn()}
        onOpenRoutine={vi.fn()}
        onOpenBlock={vi.fn()}
        onOpenItem={vi.fn()}
        routineProfile={null}
        onRemoveBlock={vi.fn()}
        onRemoveBusy={onRemoveBusy}
      />,
    );

    fireEvent.click(screen.getByTitle(/19:00–22:00 · Giờ tự học/));
    const remove = screen.getByRole('button', { name: 'Xóa Giờ tự học' });
    expect(remove).toBeVisible();
    fireEvent.click(remove);
    expect(onRemoveBusy).toHaveBeenCalledWith('self-study');
  });

  it('allows an editable personal activity to start dragging without a prior click', () => {
    const personalActivity: PlanTimelineItem = {
      id: 'busy:meal:2026-10-05', entityId: 'meal', source: 'busy', title: 'Dinner',
      date: '2026-10-05', start: '18:00', end: '19:00', durationMin: 60,
      kind: 'personal_busy', kindLabel: 'Personal activity', readOnly: false,
    };
    let dragData = '';
    const onMoveBusy = vi.fn();
    const dataTransfer = {
      effectAllowed: 'none',
      dropEffect: 'none',
      setData: vi.fn((_type: string, value: string) => { dragData = value; }),
      getData: vi.fn(() => dragData),
    };
    render(
      <PlanCalendarBoard
        dates={['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11']}
        courses={[course]}
        tasks={[task]}
        items={[personalActivity]}
        draftMode
        onMoveBlock={vi.fn()}
        onMoveBusy={onMoveBusy}
        onResizeBlock={vi.fn()}
        onResizeBusy={vi.fn()}
        onAddBusy={vi.fn()}
        onOpenPersonal={vi.fn()}
        onOpenRoutine={vi.fn()}
        onOpenBlock={vi.fn()}
        onOpenItem={vi.fn()}
        routineProfile={null}
        onRemoveBlock={vi.fn()}
        onRemoveBusy={vi.fn()}
      />,
    );

    const activity = screen.getByTitle(/18:00.*Dinner/);
    expect(activity.getAttribute('draggable')).toBe('true');
    Object.defineProperty(activity, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ top: 100, bottom: 180, left: 0, right: 100, width: 100, height: 80, x: 0, y: 100, toJSON: () => ({}) }),
    });
    const dragStart = new Event('dragstart', { bubbles: true, cancelable: true });
    Object.defineProperties(dragStart, {
      clientY: { value: 140 },
      dataTransfer: { value: dataTransfer },
    });
    fireEvent(activity, dragStart);
    expect(dataTransfer.setData).toHaveBeenCalledWith(
      'application/x-pacewise',
      JSON.stringify({ kind: 'existing-busy', id: 'meal', grabOffsetMin: 30 }),
    );
    expect(activity.className).toContain('ring-2');
    const targetDay = screen.getByLabelText('Lịch ngày 2026-10-06');
    const drop = new Event('drop', { bubbles: true, cancelable: true });
    Object.defineProperties(drop, {
      clientY: { value: 19 * 80 },
      dataTransfer: { value: dataTransfer },
    });
    fireEvent(targetDay, drop);
    expect(onMoveBusy).toHaveBeenCalledWith('meal', '2026-10-06', '18:30');
  });

  it('does not create extra lanes for adjacent short blocks', () => {
    const first = { ...item, id: 'pacewise:short-1', start: '20:55', end: '21:25' };
    const second = { ...item, id: 'pacewise:short-2', start: '21:30', end: '22:00' };
    const positioned = positionCalendarItems([first, second]);

    expect(positioned.map((entry) => entry.laneCount)).toEqual([1, 1]);
    expect(positioned.map((entry) => entry.lane)).toEqual([0, 0]);
  });

  it('keeps a legacy zero-duration block readable and expands it when selected', () => {
    const collapsed = { ...item, start: '19:00', end: '19:00', durationMin: 0 };
    render(
      <PlanCalendarBoard
        dates={['2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-10', '2026-10-11']}
        courses={[course]}
        tasks={[task]}
        items={[collapsed]}
        draftMode
        onMoveBlock={vi.fn()}
        onMoveBusy={vi.fn()}
        onResizeBlock={vi.fn()}
        onResizeBusy={vi.fn()}
        onAddBusy={vi.fn()}
        onOpenPersonal={vi.fn()}
        onOpenRoutine={vi.fn()}
        onOpenBlock={vi.fn()}
        onOpenItem={vi.fn()}
        routineProfile={null}
        onRemoveBlock={vi.fn()}
        onRemoveBusy={vi.fn()}
      />,
    );

    const collapsedBlock = screen.getByTitle(/19:00.*Mini project/);
    expect(collapsedBlock.style.height).toBe('18px');
    fireEvent.click(collapsedBlock);
    expect(collapsedBlock.style.height).toBe('30px');
  });
});
