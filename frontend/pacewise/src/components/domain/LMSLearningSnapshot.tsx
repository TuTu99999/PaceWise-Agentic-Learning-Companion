import type { LMSCourseData } from '../../types';
import { Card, CardHeader } from '../ui/Card';
import { ProgressBar } from '../ui/ProgressBar';

function completedRequirements(data: LMSCourseData) {
  const requirements = data.modules.flatMap((module) => module.requirements);
  const completed = requirements.filter((item) => item.status === 'completed').length;
  return { completed, total: requirements.length };
}

export function LMSLearningSnapshot({ data }: { data?: LMSCourseData }) {
  if (!data) return null;
  const progress = completedRequirements(data);
  const pendingPlanner = data.plannerItems.filter((item) => !item.completed);

  return (
    <Card aria-labelledby="lms-learning-snapshot">
      <CardHeader
        id="lms-learning-snapshot"
        title="Tiến độ từ LMS"
        subtitle="Dữ liệu mới nhất từ module, planner và lịch hẹn của môn"
      />
      <div className="space-y-4">
        <div>
          <div className="mb-1.5 flex justify-between text-sm">
            <span className="font-medium">Yêu cầu module</span>
            <span className="tabular-nums text-muted">{progress.completed}/{progress.total}</span>
          </div>
          <ProgressBar
            value={progress.completed}
            max={Math.max(progress.total, 1)}
            label={`${progress.completed} trên ${progress.total} yêu cầu module đã hoàn thành`}
            tone="success"
          />
        </div>

        <dl className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-canvas p-3">
            <dt className="caption">Module</dt>
            <dd className="text-lg font-semibold tabular-nums">{data.modules.length}</dd>
          </div>
          <div className="rounded-xl bg-canvas p-3">
            <dt className="caption">Việc LMS</dt>
            <dd className="text-lg font-semibold tabular-nums">{pendingPlanner.length}</dd>
          </div>
          <div className="rounded-xl bg-canvas p-3">
            <dt className="caption">Lịch hẹn</dt>
            <dd className="text-lg font-semibold tabular-nums">{data.appointmentGroups.length}</dd>
          </div>
        </dl>

        {pendingPlanner.length > 0 && (
          <ul className="space-y-2 border-t border-line pt-3">
            {pendingPlanner.slice(0, 3).map((item) => (
              <li key={item.id} className="flex justify-between gap-3 text-sm">
                <span className="min-w-0 truncate font-medium">{item.title}</span>
                <time className="shrink-0 text-muted" dateTime={item.due_at ?? undefined}>
                  {item.due_at ? new Date(item.due_at).toLocaleDateString('vi-VN') : 'Chưa có hạn'}
                </time>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
