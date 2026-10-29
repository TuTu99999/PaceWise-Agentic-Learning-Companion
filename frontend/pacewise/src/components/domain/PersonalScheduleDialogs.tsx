import { useEffect, useState } from 'react';
import { useLocale } from '../../i18n/LocaleContext';
import type { PersonalSlotCategory, PreferredTime, RoutineProfile } from '../../types';
import { normalizeClockInput } from '../../utils/clockInput';
import type { PlanTimelineItem } from '../../utils/planTimeline';
import { Button, IconButton } from '../ui/Button';
import { Input } from '../ui/Field';
import { Modal } from '../ui/Modal';

const CATEGORY_LABELS: Record<PersonalSlotCategory, string> = {
  meal: 'Ăn uống',
  self_study: 'Giờ tự học ưu tiên',
  sleep: 'Ngủ',
  other: 'Bận khác',
};

export function PersonalSlotDialog({
  open,
  category,
  initialLabel,
  initialDate,
  initialStart = '18:00',
  initialEnd = '19:00',
  mode = 'add',
  minDate,
  maxDate,
  onClose,
  onSubmit,
}: {
  open: boolean;
  category: PersonalSlotCategory;
  initialLabel: string;
  initialDate: string;
  initialStart?: string;
  initialEnd?: string;
  mode?: 'add' | 'edit';
  minDate: string;
  maxDate: string;
  onClose: () => void;
  onSubmit: (value: { date: string; start: string; end: string; label: string; category: PersonalSlotCategory }) => void;
}) {
  const { locale } = useLocale();
  const [date, setDate] = useState(initialDate);
  const [start, setStart] = useState(initialStart);
  const [end, setEnd] = useState(initialEnd);
  const [label, setLabel] = useState(initialLabel);

  useEffect(() => {
    if (!open) return;
    setDate(initialDate);
    setStart(initialStart);
    setEnd(initialEnd);
    setLabel(initialLabel);
  }, [initialDate, initialEnd, initialLabel, initialStart, open]);

  if (!open) return null;
  const [startHour, startMinute] = start.split(':').map(Number);
  const [endHour, endMinute] = end.split(':').map(Number);
  const minutes = endHour * 60 + endMinute - startHour * 60 - startMinute;
  const valid = Boolean(date && label.trim() && minutes >= 15);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="dialog" aria-modal="true" aria-labelledby="personal-slot-title">
      <form
        className="w-full max-w-md rounded-2xl border border-line bg-white p-5 shadow-xl"
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) onSubmit({ date, start, end, label: label.trim(), category });
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="personal-slot-title" className="text-lg font-bold">{mode === 'edit' ? 'Chỉnh sửa' : 'Thêm'} {CATEGORY_LABELS[category].toLowerCase()}</h2>
            <p className="mt-1 text-sm text-muted">
              {category === 'self_study'
                ? 'Plan Agent sẽ ưu tiên đặt ca tự học vào khoảng này.'
                : 'Plan Agent sẽ không xếp ca tự học trùng khoảng này.'}
            </p>
          </div>
          <IconButton icon="x" label="Đóng" onClick={onClose} />
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="sm:col-span-2 text-sm font-semibold">Ngày
            <input type="date" lang={locale === 'en' ? 'en-GB' : 'vi-VN'} min={minDate} max={maxDate} value={date} onChange={(event) => setDate(event.target.value)} className="mt-1 block h-10 w-full rounded-lg border border-line px-3 font-normal" required />
          </label>
          <label className="text-sm font-semibold">Bắt đầu
            <input type="time" step="300" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1 block h-10 w-full rounded-lg border border-line px-3 font-normal" required />
          </label>
          <label className="text-sm font-semibold">Kết thúc
            <input type="time" step="300" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1 block h-10 w-full rounded-lg border border-line px-3 font-normal" required />
          </label>
          <label className="sm:col-span-2 text-sm font-semibold">Tên hiển thị
            <input value={label} onChange={(event) => setLabel(event.target.value)} maxLength={80} className="mt-1 block h-10 w-full rounded-lg border border-line px-3 font-normal" placeholder={category === 'other' ? 'Ví dụ: Làm thêm, đi khám…' : CATEGORY_LABELS[category]} required />
          </label>
        </div>
        {minutes < 15 && <p className="mt-3 text-sm font-semibold text-danger-ink">Hoạt động phải dài ít nhất 15 phút.</p>}
        {valid && <p className="mt-3 rounded-xl bg-primary-light px-3 py-2 text-sm font-semibold text-primary-ink">Thời lượng: {minutes} phút.</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
          <Button type="submit" icon="check" disabled={!valid}>{mode === 'edit' ? 'Xác nhận thay đổi' : 'Thêm vào lịch'}</Button>
        </div>
      </form>
    </div>
  );
}

export function LmsCalendarNoticeDialog({ item, onClose }: { item: PlanTimelineItem | null; onClose: () => void }) {
  return (
    <Modal
      open={Boolean(item)}
      onClose={onClose}
      title="Không thể chỉnh lịch Canvas LMS"
      description="Ngày và giờ của hoạt động này do giảng viên hoặc LMS quản lý."
      footer={<Button variant="secondary" onClick={onClose}>Đã hiểu</Button>}
    >
      {item && (
        <div className="space-y-4">
          <div className="rounded-xl border border-line bg-canvas p-4">
            <p className="font-semibold">{item.courseCode ? `${item.courseCode} · ` : ''}{item.title}</p>
            <p className="mt-1 text-sm text-muted">Lịch này được đồng bộ trực tiếp từ Canvas LMS.</p>
          </div>
          <div className="rounded-xl bg-warning-light px-4 py-3 text-sm text-warning-ink">
            PaceWise không tự điền biểu mẫu và không cho đổi ngày hoặc thời gian tại đây, vì thay đổi cục bộ sẽ lệch với lịch chính thức mà giảng viên đã công bố. Nếu lịch LMS sai, hãy cập nhật từ Canvas hoặc liên hệ giảng viên.
          </div>
        </div>
      )}
    </Modal>
  );
}

const PERIODS: Array<{ value: PreferredTime; label: string; detail: string }> = [
  { value: 'late_night', label: 'Khuya', detail: '00:00–05:00' },
  { value: 'morning', label: 'Sáng', detail: '05:00–12:00' },
  { value: 'afternoon', label: 'Chiều', detail: '12:00–17:00' },
  { value: 'evening', label: 'Tối', detail: '17:00–24:00' },
];

export function RoutineDialog({ open, value, onClose, onSave }: {
  open: boolean;
  value: RoutineProfile | null;
  onClose: () => void;
  onSave: (profile: RoutineProfile) => void;
}) {
  const [wakeTime, setWakeTime] = useState(value?.wakeTime ?? '07:00');
  const [sleepTime, setSleepTime] = useState(value?.sleepTime ?? '23:00');
  const [preferred, setPreferred] = useState<PreferredTime[]>(value?.preferred ?? ['morning', 'evening']);

  useEffect(() => {
    if (!open) return;
    setWakeTime(value?.wakeTime ?? '07:00');
    setSleepTime(value?.sleepTime ?? '23:00');
    setPreferred(value?.preferred ?? ['morning', 'evening']);
  }, [open, value]);

  if (!open) return null;
  const normalizedWakeTime = normalizeClockInput(wakeTime);
  const normalizedSleepTime = normalizeClockInput(sleepTime);
  const validTimes = Boolean(normalizedWakeTime && normalizedSleepTime);
  const distinctTimes = validTimes && normalizedWakeTime !== normalizedSleepTime;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="dialog" aria-modal="true" aria-labelledby="routine-title">
      <form
        className="w-full max-w-lg rounded-2xl border border-line bg-white p-5 shadow-xl"
        onSubmit={(event) => {
          event.preventDefault();
          if (preferred.length && normalizedWakeTime && normalizedSleepTime && distinctTimes) {
            onSave({ wakeTime: normalizedWakeTime, sleepTime: normalizedSleepTime, preferred });
          }
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="routine-title" className="text-lg font-bold">Giờ sinh hoạt</h2>
            <p className="mt-1 text-sm text-muted">PaceWise chỉ học theo nhịp của bạn sau khi bạn xác nhận, kể cả khi bạn thường học khuya.</p>
          </div>
          <IconButton icon="x" label="Đóng" onClick={onClose} />
        </div>
        <div className="mt-5 grid grid-cols-2 gap-4">
          <Input
            label="Thường thức dậy"
            type="text"
            inputMode="text"
            autoComplete="off"
            placeholder="07:00"
            maxLength={5}
            value={wakeTime}
            onChange={(event) => setWakeTime(event.target.value)}
            onBlur={() => normalizedWakeTime && setWakeTime(normalizedWakeTime)}
            error={wakeTime && !normalizedWakeTime ? 'Nhập giờ 24h hợp lệ, ví dụ 07:05.' : undefined}
          />
          <Input
            label="Thường đi ngủ"
            type="text"
            inputMode="text"
            autoComplete="off"
            placeholder="23:10"
            maxLength={5}
            hint="Nhập chính xác từng phút: 23:10 hoặc 23h10. 00:00 là 12 giờ đêm."
            value={sleepTime}
            onChange={(event) => setSleepTime(event.target.value)}
            onBlur={() => normalizedSleepTime && setSleepTime(normalizedSleepTime)}
            error={sleepTime && !normalizedSleepTime ? 'Nhập giờ 24h hợp lệ, ví dụ 23:10.' : undefined}
          />
        </div>
        {validTimes && !distinctTimes && <p className="mt-3 text-sm font-semibold text-danger-ink">Giờ đi ngủ và thức dậy phải khác nhau.</p>}
        <fieldset className="mt-5">
          <legend className="text-sm font-bold">Khung giờ thích tự học</legend>
          <p className="mt-1 text-xs text-muted">Có thể chọn nhiều khung. “Khuya” chỉ được ưu tiên khi bạn chủ động chọn.</p>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {PERIODS.map((period) => {
              const checked = preferred.includes(period.value);
              return (
                <label key={period.value} className={`cursor-pointer rounded-xl border p-3 ${checked ? 'border-primary bg-primary-light' : 'border-line bg-white'}`}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => setPreferred((current) => checked ? current.filter((item) => item !== period.value) : [...current, period.value])}
                    className="sr-only"
                  />
                  <span className="block text-sm font-bold">{period.label}</span>
                  <span className="block text-[11px] text-muted">{period.detail}</span>
                </label>
              );
            })}
          </div>
        </fieldset>
        {preferred.length === 0 && <p className="mt-3 text-sm font-semibold text-danger-ink">Chọn ít nhất một khung giờ ưa thích.</p>}
        <div className="mt-5 rounded-xl bg-slate-50 p-3 text-xs text-muted">
          Giờ ngủ là ràng buộc cứng. Khung ưa thích chỉ thay đổi thứ tự xếp lịch, không cho phép vượt deadline hoặc chèn vào lịch LMS.
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>Hủy</Button>
          <Button type="submit" icon="check" disabled={!preferred.length || !distinctTimes}>Lưu giờ sinh hoạt</Button>
        </div>
      </form>
    </div>
  );
}
