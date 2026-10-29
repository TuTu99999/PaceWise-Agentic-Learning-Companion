import { useEffect, useMemo, useState } from 'react';
import { useLocale } from '../../i18n/LocaleContext';
import type { TimeBlock } from '../../types';
import { durationMin, formatDay, formatDuration } from '../../utils/time';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { StudyWorkList } from './StudyWorkList';

const CLOCK_PATTERN = /^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$/;

const localizedDuration = (value: number, locale: 'vi' | 'en') => {
  if (locale !== 'en') return formatDuration(value);
  const hours = Math.floor(value / 60);
  const remainder = value % 60;
  if (!hours) return `${remainder} ${remainder === 1 ? 'minute' : 'minutes'}`;
  if (!remainder) return `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  return `${hours} ${hours === 1 ? 'hour' : 'hours'} ${remainder} ${remainder === 1 ? 'minute' : 'minutes'}`;
};

export function StudyBlockDialog({
  block,
  title,
  saved,
  startIssue,
  draftReady,
  saving,
  minDate,
  maxDate,
  remainingWorkMin,
  onClose,
  onSave,
  onStart,
  onApplyAndStart,
  applyLabel,
}: {
  block: TimeBlock | null;
  title: string;
  saved: boolean;
  startIssue?: string;
  draftReady: boolean;
  saving: boolean;
  minDate: string;
  maxDate: string;
  remainingWorkMin?: number;
  onClose: () => void;
  onSave: (block: TimeBlock) => boolean;
  onStart: () => void;
  onApplyAndStart: () => void;
  applyLabel?: string;
}) {
  const { locale, t } = useLocale();
  const [date, setDate] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');

  useEffect(() => {
    if (!block) return;
    setDate(block.date);
    setStart(block.start);
    setEnd(block.end);
  }, [block]);

  const validClocks = CLOCK_PATTERN.test(start) && CLOCK_PATTERN.test(end);
  const minutes = validClocks ? durationMin(start, end) : 0;
  const dirty = Boolean(block && (date !== block.date || start !== block.start || end !== block.end));
  const maxDurationMin = remainingWorkMin === undefined
    ? undefined
    : remainingWorkMin + Math.max(0, block?.checkpointMinutes ?? 0);
  const error = useMemo(() => {
    if (!date) return t('Chọn ngày cho ca tự học.', 'Choose a date for this study session.');
    if (!validClocks) return t('Nhập giờ theo định dạng HH:mm, ví dụ 19:07.', 'Enter the time in HH:mm format, for example 19:07.');
    if (start === '24:00') return t('Giờ bắt đầu phải nằm trong khoảng 00:00–23:59.', 'The start time must be between 00:00 and 23:59.');
    if (minutes < 15) return t('Ca tự học phải dài ít nhất 15 phút.', 'A study session must be at least 15 minutes long.');
    return '';
  }, [date, minutes, start, t, validClocks]);
  const exceedsRemainingWork = maxDurationMin !== undefined && minutes > maxDurationMin;

  const saveExactTime = () => {
    if (!block || error) return;
    if (onSave({ ...block, date, start, end })) onClose();
  };

  return (
    <Modal
      open={Boolean(block)}
      onClose={onClose}
      title={t('Chi tiết ca tự học', 'Study session details')}
      description={t('Nhập chính xác đến từng phút hoặc kéo ca trực tiếp trên lịch.', 'Enter exact times to the minute or drag the session directly on the calendar.')}
      footer={(
        <>
          <Button variant="secondary" disabled={saving} onClick={onClose}>{t('Đóng', 'Close')}</Button>
          {dirty ? (
            <Button icon="check" disabled={Boolean(error)} onClick={saveExactTime}>{t('Lưu giờ chính xác', 'Save exact time')}</Button>
          ) : saved ? (
            <Button icon="play" onClick={onStart}>{t('Bắt đầu Do', 'Start study session')}</Button>
          ) : draftReady ? (
            <Button icon="play" loading={saving} onClick={onApplyAndStart}>{applyLabel ? t(applyLabel) : t('Áp dụng & bắt đầu Do', 'Apply and start studying')}</Button>
          ) : <Button icon="play" disabled title={startIssue ? t(startIssue) : t('Ca chưa được xác nhận', 'This session has not been confirmed')}>{t('Bắt đầu Do', 'Start study session')}</Button>}
        </>
      )}
    >
      {block && (
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-canvas p-4">
            <StudyWorkList title={title} />
            <p className="mt-3 text-sm text-muted">{t(formatDay(date || block.date))} · {start || block.start}–{end || block.end}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm font-semibold">{t('Ngày', 'Day')}
              <input type="date" lang={locale === 'en' ? 'en-GB' : 'vi-VN'} min={minDate} max={maxDate} value={date} onChange={(event) => setDate(event.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-white px-3 font-normal" />
            </label>
            <label className="text-sm font-semibold">{t('Bắt đầu', 'Start')}
              <input inputMode="numeric" maxLength={5} placeholder="HH:mm" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-white px-3 font-normal tabular-nums" />
            </label>
            <label className="text-sm font-semibold">{t('Kết thúc', 'End')}
              <input inputMode="numeric" maxLength={5} placeholder="HH:mm" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-white px-3 font-normal tabular-nums" />
            </label>
          </div>
          <div className={`rounded-xl px-4 py-3 text-sm ${error ? 'bg-danger-light text-danger-ink' : 'bg-primary-light text-primary-ink'}`}>
            {error || (locale === 'en' ? `Exact duration: ${localizedDuration(minutes, locale)}.` : `Thời lượng chính xác: ${minutes} phút.`)}
          </div>
          {remainingWorkMin !== undefined && !error && (exceedsRemainingWork ? (
            <p role="status" className="rounded-xl bg-warning-light px-4 py-3 text-sm text-warning-ink">
              {locale === 'en'
                ? `This session is longer than the remaining ${localizedDuration(remainingWorkMin, locale)} of unscheduled work. You can still save it; AI planning will recalculate the extra time.`
                : `Ca này dài hơn ${localizedDuration(remainingWorkMin, locale)} công việc chưa được xếp. Bạn vẫn có thể lưu; Plan Agent sẽ tính lại phần thời gian thêm.`}
            </p>
          ) : (
            <p className="text-xs text-muted">
              {locale === 'en'
                ? `This task has ${localizedDuration(remainingWorkMin, locale)} of unscheduled work remaining.`
                : `Nhiệm vụ còn ${localizedDuration(remainingWorkMin, locale)} chưa được xếp.`}
            </p>
          ))}
          {dirty && <p className="text-xs text-muted">{t(
            'Giờ mới của ca hiện tại được lưu ngay; Plan Agent sẽ tính lại phần lịch còn lại.',
            'The new time is saved for this session immediately; AI planning will recalculate the remaining schedule.',
          )}</p>}
          {!dirty && !saved && !draftReady && <p role="status" className="rounded-xl bg-warning-light px-4 py-3 text-sm text-warning-ink">{
            startIssue ? t(startIssue) : t(
              'Ca này chưa được xác nhận. Đóng cửa sổ và bấm AI phân tích lại trước khi áp dụng hoặc bắt đầu Do.',
              'This session has not been confirmed. Close this dialog and run AI planning again before applying or starting it.',
            )
          }</p>}
        </div>
      )}
    </Modal>
  );
}
