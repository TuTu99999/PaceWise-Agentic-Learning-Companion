import type { PartialPlanPreview, PlanDraft, Task } from '../../types';
import { formatDay, formatDuration } from '../../utils/time';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';

export function PartialPlanDialog({ open, draft, preview, tasks, saving, onClose, onConfirm, onAdjust }: {
  open: boolean; draft: PlanDraft | null; preview?: PartialPlanPreview; tasks: Task[]; saving: boolean;
  onClose: () => void; onConfirm: () => void; onAdjust: () => void;
}) {
  const blocks = draft?.blocks.filter(b => preview?.blockIds.includes(b.id)) ?? [];
  return <Modal open={open} onClose={() => !saving && onClose()} title="Xác nhận phần lịch hợp lệ" footer={<>
    <Button variant="secondary" disabled={saving} onClick={onAdjust}>Điều chỉnh để xếp đủ</Button>
    <Button icon="check" loading={saving} disabled={!preview?.canConfirm} onClick={onConfirm}>Xác nhận {formatDuration(preview?.scheduledWorkMin ?? 0)} đã xếp</Button>
  </>}>
    <div className="space-y-3 text-sm">
      <p role="alert" className="rounded-xl bg-warning-light p-3 text-warning-ink">Chỉ xác nhận {blocks.length} ca hợp lệ dưới đây. Kế hoạch vẫn chưa bảo đảm hoàn thành toàn bộ công việc đúng hạn. Không đổi deadline, không giảm estimate.</p>
      <ul className="max-h-52 space-y-2 overflow-y-auto">{blocks.map(b => <li key={b.id} className="rounded-lg border border-line p-2">
        <p className="font-semibold">{b.milestoneTitle ?? tasks.find(t => t.id === b.taskId)?.title ?? 'Ca tự học'}</p>
        <p>{formatDay(b.date)} · {b.start}–{b.end}</p>
      </li>)}</ul>
      <p className="font-semibold">Phần việc chưa xếp đủ vẫn được giữ:</p>
      <ul className="space-y-1">{preview?.shortfalls.map(s => <li key={s.taskId}>{tasks.find(t => t.id === s.taskId)?.title ?? 'Nhiệm vụ'}: còn thiếu {formatDuration(s.missingMin)} trước deadline.</li>)}</ul>
      {!!preview?.excludedBlocks.length && <p>{preview.excludedBlocks.length} ca không hợp lệ không được áp dụng; phần công việc của chúng vẫn tính vào thời gian còn thiếu.</p>}
      <p className="text-muted">Backend sẽ kiểm tra lại deadline, xung đột và dependency trước khi xác nhận. Chỉ sau khi xác nhận, các ca mới được mở Do.</p>
    </div>
  </Modal>;
}
