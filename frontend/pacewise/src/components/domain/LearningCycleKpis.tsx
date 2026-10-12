import type { LearningCycleMetrics, PlanAttainmentMetric } from '../../types';
import { Card, CardHeader } from '../ui/Card';
import { StatTile } from './StatTile';

const pct = (rate: number) => `${Math.round(rate * 100)}%`;

function PlanMetric({ metric, label }: { metric?: PlanAttainmentMetric; label: string }) {
  const available = metric?.status === 'available' && metric.rate != null;
  return <StatTile icon="checkCircle" label={label}
    value={available ? pct(metric.rate!) : 'Chưa đủ dữ liệu'}
    hint={available ? `${metric.count}/${metric.total} mốc đến hạn được kiểm chứng đúng mốc; n = ${metric.n}` : 'Cần mục tiêu đã xác nhận trên server và đủ nhóm quan sát'} />;
}

export function LearningCycleKpis({ metrics }: { metrics?: LearningCycleMetrics }) {
  const quality = metrics?.learningEvidence;
  const available = quality?.status === 'available' && quality.rate != null;
  return <Card className="mt-5" aria-labelledby="learning-cycle-kpis">
    <CardHeader id="learning-cycle-kpis" title="Tiến độ kế hoạch và bằng chứng học tập"
      subtitle="Tách tiến độ khỏi điểm hiểu bài. Chỉ xét mốc đã đến hạn trong tuần; không lấy timer hoặc tự báo hoàn thành làm bằng chứng." />
    <div className="grid gap-3 sm:grid-cols-3">
      <PlanMetric metric={metrics?.originalPlan} label="Đạt kế hoạch ban đầu" />
      <PlanMetric metric={metrics?.currentPlan} label="Đạt kế hoạch hiện tại" />
      <StatTile icon="chart" label="Mục tiêu đủ evidence"
        value={available ? pct(quality.rate!) : 'Chưa đủ dữ liệu'}
        hint={available ? `${quality.satisfied}/${quality.total} mốc có Assessment đạt mức yêu cầu` : 'Không suy mức hiểu từ điểm LMS hoặc thời gian học'} />
    </div>
    <p className="mt-3 text-sm text-muted">Kế hoạch ban đầu được giữ nguyên khi re-plan. Bài nộp LMS chứng minh giao bài, không chứng minh hiểu bài; checkpoint chỉ chứng minh tiêu chí học đã kiểm tra, không chứng minh toàn bộ sản phẩm bài tập.</p>
    {metrics?.originalPlan.status === 'available' && <p className="mt-2 text-sm text-muted">
      {metrics.originalPlan.removedCount} mốc ban đầu không còn trong kế hoạch hiện tại; {metrics.originalPlan.unverifiedCount} mốc chưa có bằng chứng hoàn thành.
    </p>}
    {available && <div className="mt-2 space-y-1 text-sm text-muted">
      <p>{quality.missing} mốc thiếu evidence; {quality.belowRequirement} mốc chưa đạt yêu cầu; {quality.unmapped} mốc chưa có KC được xác nhận.</p>
      {quality.retention && <p>Retention đến hạn: {quality.retention.checked}/{quality.retention.due} đã kiểm tra; {quality.retention.passed} đạt. Chưa kiểm tra không được coi là đã nhớ.</p>}
    </div>}
    <p className="mt-2 text-sm text-muted">Chưa có lịch sử milestone trước PaceWise: không tạo so sánh tiến độ trước/sau giả. Số liệu tổng hợp không dùng để xếp hạng sinh viên.</p>
  </Card>;
}
