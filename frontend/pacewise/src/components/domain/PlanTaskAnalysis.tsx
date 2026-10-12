import type { PlanDraft, Task } from '../../types';
import { formatDuration } from '../../utils/time';
import { Icon } from '../ui/Icon';

function sourceLabel(ref: string): string {
  if (ref.startsWith('rubric:')) return 'Rubric';
  if (ref.startsWith('module:')) return 'Chương / module';
  if (ref.startsWith('file:')) return 'Tài liệu bài tập';
  return 'Assignment';
}

function methodLabel(source: string | undefined): string {
  if (source === 'llm') return 'AI phân rã';
  if (source === 'rubric_evidence') return 'Theo rubric';
  if (source === 'template') return 'Theo loại bài';
  if (source === 'rule_based_fallback') return 'Bản an toàn';
  return 'Theo dữ liệu nhiệm vụ';
}

export function PlanTaskAnalysis({ draft, tasks }: { draft: PlanDraft; tasks: Task[] }) {
  const goals = draft.weeklyGoals ?? draft.input.weeklyGoals ?? [];
  const milestones = draft.milestones ?? [];
  if (!goals.length && !milestones.length) return null;

  const taskName = (taskId: string) => tasks.find((task) => task.id === taskId)?.title ?? taskId;
  const fallback = draft.decompositionAnalysis?.modelOutput?.fallbackApplied === true;
  const grouped = new Map<string, typeof milestones>();
  for (const milestone of milestones) {
    grouped.set(milestone.taskId, [...(grouped.get(milestone.taskId) ?? []), milestone]);
  }

  return <details open className="rounded-xl border border-primary/20 bg-primary-light/30 p-3" aria-label="Phân tích mục tiêu và nhiệm vụ">
    <summary className="cursor-pointer list-none">
      <span className="flex items-center gap-2 font-bold text-ink">
        <Icon name="sparkle" size={16} className="text-primary-ink" />
        Mục tiêu tuần & các bước thực hiện
      </span>
      <span className="mt-1 block text-muted">
        {goals.length} mục tiêu · {milestones.length} bước · nguồn từ assignment, module, rubric hoặc tài liệu bài tập được phép.
      </span>
    </summary>

    {fallback && <p role="status" className="mt-3 rounded-lg bg-warning-light p-2 text-warning-ink">
      Đầu ra AI chưa gắn đủ task ID nên PaceWise đã dùng bản phân rã an toàn theo assignment/rubric. Không có bước nào được gán sang bài khác.
    </p>}

    {!!goals.length && <div className="mt-3 space-y-2" aria-label="Mục tiêu tuần đã chọn">
      {goals.map((goal) => <article key={goal.id} className="rounded-lg border border-line bg-white p-2.5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <p className="font-semibold text-ink">{goal.title}</p>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-muted">
            {goal.analysisSource === 'model' ? 'AI đề xuất' : 'Theo deadline/assignment'}
          </span>
        </div>
        {!!goal.rationale && <p className="mt-1 text-muted">{goal.rationale}</p>}
        <p className="mt-1 text-[11px] text-muted">Bài liên quan: {goal.taskIds.map(taskName).join('; ')}</p>
        {!!goal.sourceRefs?.length && <p className="mt-1 text-[11px] text-primary-ink">
          Nguồn: {[...new Set(goal.sourceRefs.map(sourceLabel))].join(' · ')}
        </p>}
      </article>)}
    </div>}

    {!!milestones.length && <div className="mt-3 max-h-80 space-y-3 overflow-y-auto pr-1" aria-label="Các bước nhiệm vụ đã phân rã">
      {[...grouped.entries()].map(([taskId, steps]) => <section key={taskId} className="rounded-lg border border-line bg-white p-2.5">
        <h3 className="font-bold text-ink">{taskName(taskId)}</h3>
        <ol className="mt-2 space-y-2">
          {steps.map((step, index) => <li key={step.milestoneId} className="grid grid-cols-[22px_minmax(0,1fr)] gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary-light text-[10px] font-bold text-primary-ink">{index + 1}</span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-semibold text-ink">{step.title}</p>
                <span className="text-[10px] font-semibold text-primary-ink">{formatDuration(step.targetMin || step.estimatedMin)}</span>
                <span className="text-[10px] text-muted">{methodLabel(step.decompositionSource)}</span>
              </div>
              {!!step.deliverable && <p className="mt-0.5 text-muted">Đầu ra: {step.deliverable}</p>}
              {!!step.difficulty && <p className="mt-0.5 text-[11px] text-muted">Độ khó dự kiến: {step.difficulty}</p>}
              {!!step.sourceRefs?.length && <p className="mt-0.5 text-[11px] text-primary-ink">
                Nguồn: {[...new Set(step.sourceRefs.map(sourceLabel))].join(' · ')}
              </p>}
            </div>
          </li>)}
        </ol>
      </section>)}
    </div>}
  </details>;
}
