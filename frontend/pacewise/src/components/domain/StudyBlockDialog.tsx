import { useEffect, useMemo, useState } from 'react';
import type { TimeBlock } from '../../types';
import { durationMin, formatDay } from '../../utils/time';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';

const CLOCK_PATTERN = /^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$/;

export function StudyBlockDialog({
  block,
  title,
  saved,
  startIssue,
  draftReady,
  saving,
  minDate,
  maxDate,
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
  onClose: () => void;
  onSave: (block: TimeBlock) => boolean;
  onStart: () => void;
  onApplyAndStart: () => void;
  applyLabel?: string;
}) {
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
  const error = useMemo(() => {
    if (!date) return 'Chọn ngày cho ca tự học.';
    if (!validClocks) return 'Nhập giờ theo định dạng HH:mm, ví dụ 19:07.';
    if (start === '24:00') return 'Giờ bắt đầu phải nằm trong khoảng 00:00–23:59.';
    if (minutes < 15) return 'Ca tự học phải dài ít nhất 15 phút.';
    return '';
  }, [date, minutes, start, validClocks]);

  const saveExactTime = () => {
    if (!block || error) return;
    if (onSave({ ...block, date, start, end })) onClose();
  };

  return (
    <Modal
      open={Boolean(block)}
      onClose={onClose}
      title="Chi tiết ca tự học"
      description="Nhập chính xác đến từng phút hoặc kéo ca trực tiếp trên lịch."
      footer={(
        <>
          <Button variant="secondary" disabled={saving} onClick={onClose}>Đóng</Button>
          {dirty ? (
            <Button icon="check" disabled={Boolean(error)} onClick={saveExactTime}>Lưu giờ chính xác</Button>
          ) : saved ? (
            <Button icon="play" onClick={onStart}>Bắt đầu Do</Button>
          ) : draftReady ? (
            <Button icon="play" loading={saving} onClick={onApplyAndStart}>{applyLabel ?? 'Áp dụng & bắt đầu Do'}</Button>
          ) : <Button icon="play" disabled title={startIssue ?? 'Ca chưa được xác nhận'}>Bắt đầu Do</Button>}
        </>
      )}
    >
      {block && (
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-canvas p-4">
            <p className="font-semibold">{title}</p>
            <p className="mt-1 text-sm text-muted">{formatDay(block.date)} · {block.start}–{block.end}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-sm font-semibold">Ngày
              <input type="date" min={minDate} max={maxDate} value={date} onChange={(event) => setDate(event.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-white px-3 font-normal" />
            </label>
            <label className="text-sm font-semibold">Bắt đầu
              <input inputMode="numeric" maxLength={5} placeholder="HH:mm" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-white px-3 font-normal tabular-nums" />
            </label>
            <label className="text-sm font-semibold">Kết thúc
              <input inputMode="numeric" maxLength={5} placeholder="HH:mm" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1 block h-11 w-full rounded-xl border border-line bg-white px-3 font-normal tabular-nums" />
            </label>
          </div>
          <div className={`rounded-xl px-4 py-3 text-sm ${error ? 'bg-danger-light text-danger-ink' : 'bg-primary-light text-primary-ink'}`}>
            {error || `Thời lượng chính xác: ${minutes} phút.`}
          </div>
          {dirty && <p className="text-xs text-muted">Sau khi đổi giờ, Plan Agent cần phân tích lại để kiểm tra deadline, capacity và xung đột.</p>}
          {!dirty && !saved && !draftReady && <p role="status" className="rounded-xl bg-warning-light px-4 py-3 text-sm text-warning-ink">{startIssue ?? 'Ca này chưa được xác nhận. Đóng cửa sổ và bấm AI phân tích lại trước khi áp dụng hoặc bắt đầu Do.'}</p>}
        </div>
      )}
    </Modal>
  );
}
