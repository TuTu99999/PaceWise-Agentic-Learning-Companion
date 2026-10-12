import type { TeachingEvent } from '../types';

export const localDateTimeValue = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
};

export const isoFromLocalDateTime = (value: string) => value ? new Date(value).toISOString() : '';

export const durationMinutes = (event: Pick<TeachingEvent, 'startAt' | 'endAt'>) =>
  Math.max(0, Math.round((new Date(event.endAt).getTime() - new Date(event.startAt).getTime()) / 60_000));

export function teachingEventError(event: Pick<TeachingEvent, 'title' | 'startAt' | 'endAt' | 'type' | 'meetingUrl'>) {
  if (!event.title.trim()) return 'Tên buổi học là bắt buộc.';
  const start = new Date(event.startAt).getTime();
  const end = new Date(event.endAt).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return 'Ngày giờ chưa hợp lệ.';
  if (end <= start) return 'Thời gian kết thúc phải sau thời gian bắt đầu.';
  if (event.type === 'online' && !event.meetingUrl.trim()) return 'Buổi học online cần có đường dẫn tham gia.';
  return null;
}

export const emptyTeachingEvent = (id: string): TeachingEvent => {
  const start = new Date();
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);
  const end = new Date(start.getTime() + 90 * 60_000);
  return {
    id,
    title: '',
    type: 'offline',
    startAt: start.toISOString(),
    endAt: end.toISOString(),
    location: '',
    meetingUrl: '',
    moduleId: '',
    knowledgeComponentIds: [],
    preparation: '',
    recurrence: 'none',
    recurrenceCount: 12,
    status: 'scheduled',
    source: 'pacewise',
  };
};
