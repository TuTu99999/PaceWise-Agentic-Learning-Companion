import { useState } from 'react';
import { LearningCycleKpis } from '../../components/domain/LearningCycleKpis';
import { StatTile } from '../../components/domain/StatTile';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Select } from '../../components/ui/Field';
import { Icon } from '../../components/ui/Icon';
import { PageHeader } from '../../components/ui/PageHeader';
import { ProgressBar } from '../../components/ui/ProgressBar';
import { ErrorState } from '../../components/ui/States';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useInstructorData } from '../../hooks/useInstructorData';
import { useCalendarToday } from '../../hooks/useCalendarToday';
import { useAppStore } from '../../store/AppStore';
import { APP_TIMEZONE } from '../../utils/time';

const pct = (x: number) => `${Math.round(x * 100)}%`;
const formatDateTime = (value: string) => Number.isNaN(Date.parse(value)) ? 'Chưa xác định' : new Intl.DateTimeFormat('vi-VN', {
  timeZone: APP_TIMEZONE,
  day: '2-digit',
  month: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
}).format(new Date(value));

function currentWeekLabel(today: string) {
  const monday = new Date(`${today}T00:00:00Z`);
  const day = monday.getUTCDay() || 7;
  monday.setUTCDate(monday.getUTCDate() - day + 1);
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  const short = (value: Date) => value.toLocaleDateString('vi-VN', { timeZone: 'UTC', day: '2-digit', month: '2-digit' });
  return `${short(monday)} – ${short(sunday)}`;
}

export function InstructorOverviewPage() {
  useDocumentTitle('Tổng quan lớp');
  const today = useCalendarToday();
  const { state } = useAppStore();
  const { loading, refreshing, error: loadError, refresh } = useInstructorData();
  const [groupId, setGroupId] = useState('all');
  const classGroups = state.classGroups;
  const groupStats = state.groupStats;
  const group = classGroups.find((g) => g.id === groupId) ?? classGroups[0] ?? { id: 'all', name: 'Cả lớp', n: 0 };
  const stats = groupStats[group.id];
  const reviewQueue = state.reviewQueue;
  const pending = reviewQueue.filter((r) => r.status === 'pending' || r.status === 'in_review').length;
  const activeCourse = state.courses.find((course) => course.id === state.user?.courseId);
  const minimumGroupSize = Math.max(5, state.teacherWorkspace.settings.minimumGroupSize || 5);
  const enough = group.n >= minimumGroupSize && !!stats;

  if (!state.user?.courseId || state.user.courseId === '0') {
    return (
      <div className="page">
        <PageHeader title="Tổng quan lớp" description="Quản lý hoạt động dạy và học ngay trong PaceWise." />
        <Card className="flex flex-col items-center px-6 py-12 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-light text-primary">
            <Icon name="book" size={28} />
          </span>
          <h2 className="mt-4 text-xl font-semibold">Tạo môn học đầu tiên</h2>
          <p className="mt-2 max-w-md text-muted">
            Sau khi tạo môn, bạn có thể thêm lịch học, nhiệm vụ, học liệu và mời sinh viên ngay trong PaceWise.
          </p>
          <ButtonLink className="mt-6" to="/instructor/courses" icon="plus">Quản lý môn học</ButtonLink>
        </Card>
      </div>
    );
  }

  if (loading && classGroups.length === 0) {
    return (
      <div className="page" aria-busy="true">
        <PageHeader
          title="Tổng quan lớp"
          description="Đang tải dữ liệu tổng hợp của môn học..."
        />
        <Card className="flex items-center gap-4 px-5 py-6">
          <span
            className="h-6 w-6 shrink-0 animate-spin rounded-full border-2 border-primary border-r-transparent"
            aria-hidden="true"
          />
          <div>
            <h2 className="font-semibold">Đang chuẩn bị số liệu lớp</h2>
            <p className="mt-1 text-sm text-muted">
              PaceWise đang tổng hợp và ẩn danh số liệu trước khi hiển thị.
            </p>
          </div>
        </Card>
      </div>
    );
  }
  if (loadError && classGroups.length === 0) {
    return <div className="page"><ErrorState title="Không thể tải tổng quan lớp" description={loadError.message} requestId={loadError.requestId} onRetry={() => void refresh()} /></div>;
  }

  return (
    <div className="page">
      <PageHeader
        title="Tổng quan lớp"
        description={`${activeCourse?.code ?? 'Môn đang chọn'} · ${activeCourse?.name ?? 'Dữ liệu lớp học'} — tuần ${currentWeekLabel(today)}`}
        actions={
          <div className="flex flex-wrap items-end gap-3">
          <Button variant="secondary" icon="refresh" disabled={loading || refreshing} onClick={() => void refresh()}>Làm mới</Button>
          {classGroups.length > 1 && <Select
            className="w-full sm:w-64"
            label="Nhóm sinh viên"
            value={groupId}
            onChange={(e) => setGroupId(e.target.value)}
            options={classGroups.map((g) => ({ value: g.id, label: `${g.name} (n = ${g.n})` }))}
          />}
          </div>
        }
      />

      {loadError && <div className="mb-5" role="status">
        <ErrorState title="Chưa làm mới được số liệu" description="Đang hiển thị bản đồng bộ gần nhất, có thể chưa phản ánh tiến độ hiện tại." onRetry={() => void refresh()} />
      </div>}

      <div className="mb-5 flex items-start gap-3 rounded-2xl border border-line bg-white px-4 py-3">
        <Icon name="eyeOff" size={20} className="mt-0.5 shrink-0 text-muted" />
        <p className="text-[15px]">
          <strong>Chỉ hiển thị dữ liệu tổng hợp của nhóm từ {minimumGroupSize} sinh viên.</strong> Không có tên, nội dung hỏi đáp hay tổng kết cá nhân. Không dùng để xếp hạng hay chấm điểm.
        </p>
      </div>


      {!enough ? (
        <Card className="flex flex-col items-center px-6 py-12 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-600">
            <Icon name="eyeOff" size={28} />
          </span>
          <h2 className="mt-4 text-xl font-semibold">Chưa đủ dữ liệu để hiển thị.</h2>
          <p className="mt-2 max-w-md text-muted">
            Nhóm “{group.name}” có {group.n} sinh viên. Số liệu chỉ hiển thị khi nhóm có ít nhất {minimumGroupSize} sinh viên để hạn chế nguy cơ nhận diện cá nhân.
          </p>
          <button className="mt-6 min-h-[44px] rounded-xl bg-primary-dark px-4 font-semibold text-white hover:bg-primary-deeper" onClick={() => setGroupId('all')}>
            Xem cả lớp
          </button>
        </Card>
      ) : (
        <>
          {!!stats.completionUnknownCount && <p className="mb-3 text-sm text-muted" role="status">
            {stats.completionUnknownCount} nhiệm vụ đã nộp thiếu dữ liệu thời điểm: không tính vào tỷ lệ đúng hạn.
          </p>}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatTile icon="checkCircle" label="Nộp đúng hạn" value={stats.onTimeTotal > 0 ? pct(stats.onTimeRate) : 'Chưa có dữ liệu'} hint={stats.onTimeTotal > 0 ? `${stats.onTimeCount}/${stats.onTimeTotal} nhiệm vụ đến hạn` : 'Chưa có nhiệm vụ đến hạn để tính tỷ lệ'} />
            <StatTile icon="alert" label="Cần chú ý deadline" value={stats.atRisk} hint="chưa nộp bài có hạn trong 72 giờ; không phải dự đoán chắc chắn trễ" />
            <StatTile
              icon="chart"
              label="Thay đổi nộp đúng hạn"
              value={stats.progressImprovement == null ? 'Chưa đủ mẫu' : `${stats.progressImprovement >= 0 ? '+' : ''}${Math.round(stats.progressImprovement * 100)} điểm %`}
              hint="so với tuần đầu trong cửa sổ"
            />
            <StatTile icon="users" label="Quy mô nhóm" value={group.n} hint="sinh viên" />
            <StatTile icon="inbox" label="Ca cần xem" value={pending} hint="trong Hàng chờ duyệt" />
          </div>

          <Card className="mt-5" aria-labelledby="adoption-comparison">
            <CardHeader id="adoption-comparison" title="Nộp đúng hạn trước / sau PaceWise"
              subtitle="Mốc lần xác nhận kế hoạch đầu tiên; hai cửa sổ 14 ngày hoàn chỉnh trước/sau, cùng nhóm sinh viên. Đây là quan sát, không chứng minh tác động nhân quả." />
            {stats.adoptionComparison?.status === 'available' ? (
              <div className="grid gap-3 sm:grid-cols-3">
                <StatTile icon="clock" label="Trước sử dụng" value={pct(stats.adoptionComparison.before!.rate)} hint={`${stats.adoptionComparison.before!.count}/${stats.adoptionComparison.before!.total} nhiệm vụ`} />
                <StatTile icon="checkCircle" label="Sau sử dụng" value={pct(stats.adoptionComparison.after!.rate)} hint={`${stats.adoptionComparison.after!.count}/${stats.adoptionComparison.after!.total} nhiệm vụ`} />
                <StatTile icon="chart" label="Chênh lệch" value={`${stats.adoptionComparison.deltaPercentagePoints! >= 0 ? '+' : ''}${stats.adoptionComparison.deltaPercentagePoints} điểm %`} />
              </div>
            ) : <p className="text-sm text-muted">Chưa đủ hai cửa sổ 14 ngày trước/sau xác nhận kế hoạch của cùng ít nhất {minimumGroupSize} sinh viên. Không dùng đăng nhập hay số liệu giả để tính mức cải thiện.</p>}
          </Card>

          <LearningCycleKpis metrics={stats.learningCycle} />

          <Card className="mt-5" aria-labelledby="assignment-risks">
            <CardHeader
              id="assignment-risks"
              title="Deadline sắp đến"
              subtitle="Số sinh viên chưa nộp bài có hạn trong 72 giờ tới; chưa kết luận thiếu thời gian học"
            />
            {(stats.assignmentRisks ?? []).length === 0 ? (
              <p className="text-[15px] text-muted">Chưa có bài chưa nộp với deadline trong 72 giờ tới.</p>
            ) : (
              <ul className="divide-y divide-line">
                {(stats.assignmentRisks ?? []).map((item) => (
                  <li key={item.assignmentId} className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:gap-5">
                    <div>
                      <p className="font-semibold text-ink">{item.title}</p>
                      <p className="caption">Hạn {formatDateTime(item.dueAt)}</p>
                    </div>
                    <p className="text-sm"><strong>{item.atRiskCount}/{item.totalStudents}</strong> sinh viên chưa nộp</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-2 lg:gap-6">
            <Card aria-labelledby="trend">
              <CardHeader id="trend" title="Xu hướng hoàn thành" subtitle="Tỉ lệ nộp đúng hạn theo tuần có nhiệm vụ đến hạn" />
              {stats.weeklyCompletion.length === 0 && <p className="text-sm text-muted">Chưa có nhiệm vụ đến hạn để tính xu hướng.</p>}
              <ul className="space-y-4">
                {stats.weeklyCompletion.map((w) => (
                  <li key={w.week}>
                    <div className="mb-1.5 flex justify-between text-sm">
                      <span className="font-medium">{w.week}</span>
                      <span className="tabular-nums text-muted">
                        <strong className="text-ink">{pct(w.rate)}</strong> · {w.count}/{w.total}
                      </span>
                    </div>
                    <ProgressBar value={w.count} max={w.total} label={`${w.week}: ${pct(w.rate)}`} tone="success" />
                  </li>
                ))}
              </ul>
            </Card>

            <Card aria-labelledby="topics">
              <CardHeader id="topics" title="Chủ đề cần chú ý" subtitle="Bằng chứng điểm thấp gần nhất theo chủ đề, không thay thế đánh giá mức hiểu trong Do. Chỉ hiện chủ đề có đủ số sinh viên được quan sát." />
              {stats.topics.length === 0 && <p className="text-sm text-muted">Chưa có tín hiệu đủ dữ liệu để tổng hợp theo chủ đề.</p>}
              <ul className="space-y-4">
                {stats.topics.map((t) => (
                  <li key={t.topic} className="rounded-xl border border-line/60 bg-canvas/50 p-3">
                    <div className="mb-1.5 flex justify-between gap-3 text-sm">
                      <span className="font-semibold text-ink">{t.topic}</span>
                      <span className="shrink-0 tabular-nums text-muted">
                        <strong className="text-ink">{t.needsSupport}</strong>/{t.n} ({pct(t.needsSupport / t.n)})
                      </span>
                    </div>
                    <ProgressBar value={t.needsSupport} max={t.n} label={`${t.topic}: ${t.needsSupport} trên ${t.n}`} tone="warning" />
                    <div className="mt-3 flex items-center justify-end border-t border-line/50 pt-2.5">
                      <ButtonLink to="/instructor/assessment" size="sm" variant="ghost" icon="edit">
                        Xem thiết kế kiểm chứng
                      </ButtonLink>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <Card className="mt-5" tone="accent" aria-labelledby="rq">
            <CardHeader id="rq" title="Hàng chờ duyệt" subtitle={`${pending} ca cần xem lại bằng chứng hoặc kết luận`} action={<ButtonLink to="/instructor/review" size="sm">Mở hàng chờ</ButtonLink>} />
            <p className="text-[15px]">Sinh viên vẫn tiếp tục Plan–Do–Reflect trong khi chờ duyệt; kết luận chưa chắc chắn giữ trạng thái tạm thời. Quyết định của bạn được ghi vào nhật ký audit.</p>
          </Card>
        </>
      )}

    </div>
  );
}
