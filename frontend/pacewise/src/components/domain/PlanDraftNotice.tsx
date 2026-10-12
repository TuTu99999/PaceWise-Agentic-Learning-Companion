import type { PlanDraft, Task } from '../../types';
import { canConfirmPlan, partialPlanPreview } from '../../utils/planConfirmation';
import { hasExpiredDraftWork } from '../../utils/planningScope';
import { PlanTaskAnalysis } from './PlanTaskAnalysis';

export function draftIssues(draft: PlanDraft, tasks: Task[]): string[] {
  const name = (id: unknown) => tasks.find((task) => task.id === id)?.title ?? 'Nhiệm vụ';
  const deadline = (id: string) => {
    const task = tasks.find((item) => item.id === id);
    if (task?.dueAt) {
      const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(task.dueAt) ? task.dueAt : `${task.dueAt}+07:00`;
      const date = new Date(normalized);
      if (Number.isFinite(date.getTime())) return date.toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit', year: 'numeric' });
    }
    return task?.deadline ?? 'deadline đã khai báo';
  };
  const result = draft.feasibility.shortfalls.map((item) => `${name(item.taskId)} còn thiếu ${item.missingMin} phút trước hạn ${deadline(item.taskId)}. Thêm thời gian rảnh trước hạn hoặc giảm phạm vi công việc có xác nhận, rồi phân tích lại.`);
  const errors = draft.qualityEvaluation?.blockingErrors ?? draft.qualityEvaluation?.violations ?? [];
  for (const issue of errors) {
    const block = draft.blocks.find((item) => item.id === issue.blockId);
    const milestone = draft.milestones?.find((item) => item.milestoneId === issue.milestoneId);
    const taskId = block?.taskId ?? milestone?.taskId;
    const label = name(taskId);
    switch (issue.code) {
      case 'DEADLINE_CAPACITY_SHORTFALL': if (!result.length) result.push('Chưa đủ thời gian trước deadline. Kiểm tra lịch rảnh và phạm vi nhiệm vụ, rồi phân tích lại.'); break;
      case 'AFTER_DEADLINE': result.push(`${label}: ca ${block?.start}–${block?.end} ngày ${block?.date} nằm sau hạn ${deadline(taskId ?? '')}. Dời ca về trước hạn rồi phân tích lại.`); break;
      case 'UNKNOWN_DEPENDENCY': case 'DEPENDENCY_ORDER': case 'DEPENDENCY_UNSCHEDULED': case 'DEPENDENCY_INCOMPLETE': case 'DEPENDENCY_CYCLE': result.push(`${label}: bước “${milestone?.title ?? 'milestone'}” thiếu hoặc sai thứ tự bước tiên quyết. Phân tích lại để bước tiên quyết được xếp đủ trước bước phụ thuộc.`); break;
      case 'UNAVAILABLE_OVERLAP': result.push(`${label}: ca ${block?.start}–${block?.end} trùng lịch LMS hoặc lịch cá nhân. Dời ca rồi phân tích lại.`); break;
      case 'OUTSIDE_AVAILABILITY': result.push(`${label}: ca ${block?.start}–${block?.end} nằm ngoài khung giờ học đã chọn. Chỉnh thời gian rảnh hoặc dời ca rồi phân tích lại.`); break;
      case 'BLOCK_OVERLAP': result.push(`Các ca tự học ngày ${issue.date ?? ''} bị trùng nhau. Dời ca hoặc phân tích lại.`); break;
      case 'PAST_BLOCK': result.push(`${label}: ca đã nằm trong quá khứ. Phân tích lại phần việc còn lại từ hiện tại.`); break;
      default: result.push(`${label}: dữ liệu ca học không hợp lệ (${String(issue.code ?? 'unknown')}). Kiểm tra rồi phân tích lại.`);
    }
  }
  return [...new Set(result)];
}

export function PlanDraftNotice({ draft, tasks, now = Date.now() }: { draft: PlanDraft; tasks: Task[]; now?: number }) {
  if (hasExpiredDraftWork(draft, tasks, now)) return <div role="alert" className="rounded-lg bg-warning-light p-2 text-xs text-warning-ink">
    <p className="font-semibold">Bản nháp cũ còn chứa nhiệm vụ đã quá hạn.</p>
    <p className="mt-1">Bấm AI phân tích lại để tính kế hoạch từ hiện tại. Nhiệm vụ quá hạn không được cộng vào thiếu giờ của lịch tương lai; không thể thêm giờ trước một deadline đã qua. Lịch sử học vẫn giữ nguyên, chưa coi nhiệm vụ là hoàn thành.</p>
  </div>;
  const issues = draftIssues(draft, tasks);
  const adjustments = draft.durationAdjustments ?? [];
  const repairAdjustments = draft.replanAdjustments ?? [];
  const highestRisk = [...(draft.feasibility.deadlineRisks ?? [])]
    .sort((left, right) => left.slackP80Min - right.slackP80Min)[0];
  const uncertain = draft.planningTargets?.filter((item) => item.estimateStatus === 'insufficient_evidence').length ?? 0;
  const partial = partialPlanPreview(draft);
  return <div className="space-y-2 text-xs">
    <PlanTaskAnalysis draft={draft} tasks={tasks} />
    {repairAdjustments.length > 0 && <div role="status" className="rounded-lg bg-primary-light p-2 text-primary-ink">
      <p className="font-semibold">Bản lịch mới đã dùng tiến độ Do và Reflect</p>
      {repairAdjustments.map((item) => <p className="mt-1" key={item.taskId}>
        {tasks.find((task) => task.id === item.taskId)?.title ?? 'Nhiệm vụ'} còn cần thêm {item.addedMin} phút so với lần tính lại không có evidence, do phần việc trong phiên trước chưa hoàn thành.
      </p>)}
      <p className="mt-1">Đây vẫn là bản đề xuất; lịch đang dùng chưa thay đổi cho đến khi bạn xác nhận.</p>
    </div>}
    {highestRisk && highestRisk.risk !== 'safe' && <p className="rounded-lg bg-warning-light p-2 text-warning-ink">
      Trước hạn {highestRisk.deadline}: slack P50 {highestRisk.slackP50Min} phút, slack P80 {highestRisk.slackP80Min} phút. P80 là vùng dự phòng, không tự tăng workload.
    </p>}
    {!!draft.expiredTasks?.length && <details className="rounded-lg border border-line p-2 text-muted">
      <summary className="cursor-pointer">{draft.expiredTasks.length} nhiệm vụ đã quá hạn — không tính vào capacity tương lai</summary>
      <p className="mt-1">Chưa coi là hoàn thành. Giữ dữ liệu để nhìn lại; muốn học bù cần mục tiêu mới hoặc deadline mới từ LMS.</p>
      <ul className="mt-1 max-h-32 space-y-1 overflow-y-auto">{draft.expiredTasks.map(t => <li key={t.taskId}>{t.title}</li>)}</ul>
    </details>}
    {!canConfirmPlan(draft) && <div role="alert" className={`rounded-lg p-2 ${partial?.canConfirm ? 'bg-warning-light text-warning-ink' : 'bg-danger-light text-danger-ink'}`}>
      <p className="font-semibold">{partial?.canConfirm ? 'Có thể xác nhận phần lịch hợp lệ; toàn kế hoạch vẫn có rủi ro:' : 'Chưa thể áp dụng bản nháp — cần xử lý:'}</p>
      {partial?.canConfirm && <p className="mt-1">Đã xếp {partial.blockIds.length} ca hợp lệ. Xem và xác nhận trước khi mở Do; phần còn thiếu vẫn được giữ.</p>}
      <p className="mt-1">{issues[0] ?? 'Chưa đủ dữ liệu kiểm tra. Hãy phân tích lại lịch.'}</p>
      {issues.length > 1 && <details className="mt-1"><summary className="cursor-pointer">Xem thêm {issues.length - 1} lỗi cụ thể</summary><ul className="mt-1 max-h-40 list-disc space-y-1 overflow-y-auto pl-4">{issues.slice(1).map((issue) => <li key={issue}>{issue}</li>)}</ul></details>}
    </div>}
    {adjustments.length > 0 && <details className="rounded-lg border border-line p-2">
      <summary className="cursor-pointer font-semibold text-warning-ink">Có {adjustments.length} đề xuất thời lượng — Xem chi tiết</summary>
      <p className="mt-2 text-muted">Đây là tổng công việc dự kiến, không phải độ dài phiên tối ưu. Chỉ đổi lịch sau khi bạn xác nhận bản nháp hợp lệ.</p>
      <ul className="mt-2 max-h-48 space-y-2 overflow-y-auto">{adjustments.map((item) => <li key={item.taskId}>
        <p className="font-semibold">{tasks.find((task) => task.id === item.taskId)?.title ?? 'Nhiệm vụ'}: {item.baselineTargetMin} → {item.proposedTargetMin} phút trong phạm vi kế hoạch này.</p>
        <p>Số phút còn lại bạn nhập: {item.studentRemainingMin}. {item.sourceRefs?.length ? `Nguồn: ${item.sourceRefs.join(', ')} (${item.evidenceCount ?? 0} phiên hợp lệ).` : 'Nguồn: quy tắc trạng thái kiến thức/bước ôn đã xác nhận; chưa có lịch sử thời gian đủ để cá nhân hóa.'}</p>
        {!!item.reviewAddedMin && <p>Trong đó có {item.reviewAddedMin} phút hỗ trợ/ôn thêm; đây không phải hệ số thời gian suy ra từ việc bạn bận đột xuất.</p>}
        <p className="text-muted">Estimate là heuristic chưa hiệu chỉnh bằng pilot. Số phút gốc và lịch hiện tại chưa đổi.</p>
      </li>)}</ul>
    </details>}
    {uncertain > 0 && <p className="text-muted">{uncertain} nhiệm vụ chưa đủ bằng chứng cá nhân hóa thời lượng; giữ số phút nền đã nhập. Estimate còn bất định.</p>}
  </div>;
}
