import type { PartialPlanPreview, PlanDraft, Task } from '../../types';
import { useLocale } from '../../i18n/LocaleContext';
import { formatDay, formatDuration } from '../../utils/time';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';

export function PartialPlanDialog({ open, draft, preview, tasks, saving, onClose, onConfirm, onAdjust }: {
  open: boolean; draft: PlanDraft | null; preview?: PartialPlanPreview; tasks: Task[]; saving: boolean;
  onClose: () => void; onConfirm: () => void; onAdjust: () => void;
}) {
  const { locale, t } = useLocale();
  const blocks = draft?.blocks.filter(b => preview?.blockIds.includes(b.id)) ?? [];
  const scheduledDuration = formatDuration(preview?.scheduledWorkMin ?? 0, locale);
  return <Modal open={open} size="lg" onClose={() => !saving && onClose()} title={t('Xác nhận phần lịch hợp lệ', 'Confirm valid scheduled sessions')} footer={<>
    <Button className="whitespace-normal text-center" variant="secondary" disabled={saving} onClick={onAdjust}>{t('Điều chỉnh để xếp đủ', 'Adjust to schedule all work')}</Button>
    <Button className="whitespace-normal text-center" icon="check" loading={saving} disabled={!preview?.canConfirm} onClick={onConfirm}>{t(`Xác nhận ${scheduledDuration} đã xếp`, `Confirm ${scheduledDuration} scheduled`)}</Button>
  </>}>
    <div className="space-y-3 text-sm">
      <p role="alert" className="rounded-xl bg-warning-light p-3 text-warning-ink">{t(
        `Chỉ xác nhận ${blocks.length} ca hợp lệ dưới đây. Kế hoạch vẫn chưa bảo đảm hoàn thành toàn bộ công việc đúng hạn. Không đổi deadline, không giảm estimate.`,
        `Only the ${blocks.length} valid sessions below will be confirmed. The plan still does not guarantee that all work will be completed by its deadlines. Deadlines and estimates will not change.`,
      )}</p>
      <ul className="space-y-2">{blocks.map(b => <li key={b.id} className="rounded-lg border border-line p-2">
        <p className="font-semibold">{b.milestoneTitle ?? tasks.find(task => task.id === b.taskId)?.title ?? t('Ca tự học', 'Study session')}</p>
        <p>{formatDay(b.date)} · {b.start}–{b.end}</p>
      </li>)}</ul>
      <p className="font-semibold">{t('Phần việc chưa xếp đủ vẫn được giữ:', 'Remaining unscheduled work:')}</p>
      <ul className="space-y-1">{preview?.shortfalls.map(s => {
        const taskTitle = tasks.find(task => task.id === s.taskId)?.title ?? t('Nhiệm vụ', 'Task');
        const missingDuration = formatDuration(s.missingMin, locale);
        return <li key={s.taskId}>{t(`${taskTitle}: còn thiếu ${missingDuration} trước deadline.`, `${taskTitle}: ${missingDuration} still needs to be scheduled before the deadline.`)}</li>;
      })}</ul>
      {!!preview?.excludedBlocks.length && <p>{t(
        `${preview.excludedBlocks.length} ca không hợp lệ không được áp dụng; phần công việc của chúng vẫn tính vào thời gian còn thiếu.`,
        `${preview.excludedBlocks.length} invalid sessions will not be applied; their work still counts toward the remaining time.`,
      )}</p>}
      <p className="text-muted">{t(
        'Backend sẽ kiểm tra lại deadline, xung đột và dependency trước khi xác nhận. Chỉ sau khi xác nhận, các ca mới được mở Do.',
        'The system will recheck deadlines, conflicts, and dependencies before confirmation. Study sessions become available in Do only after confirmation.',
      )}</p>
    </div>
  </Modal>;
}
