import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Icon } from '../../components/ui/Icon';
import { PageHeader } from '../../components/ui/PageHeader';
import { ErrorState } from '../../components/ui/States';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { ApiError, fetchInstructorDashboard } from '../../services/api';
import {
  isFresh,
  readInstructorDashboardCache,
  writeInstructorDashboardCache,
} from '../../services/instructorPageCache';
import { useAppStore } from '../../store/AppStore';
import type { InstructorDashboard } from '../../types';
import { APP_TIMEZONE } from '../../utils/time';
import { useLocale } from '../../i18n/LocaleContext';

const percent = (value: number) => `${Math.round(value * 100)}%`;
const dashboardRequests = new Map<string, Promise<InstructorDashboard>>();

function requestDashboard(key: string, courseId: string) {
  const pending = dashboardRequests.get(key);
  if (pending) return pending;
  const request = fetchInstructorDashboard(courseId).finally(() => dashboardRequests.delete(key));
  dashboardRequests.set(key, request);
  return request;
}

const formatTimestamp = (value: string, locale = 'vi') => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(locale === 'en' ? 'en-GB' : 'vi-VN', {
    timeZone: APP_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour12: false,
  }).format(date);
};

const formatCalendarDate = (value: string) => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[3]}/${match[2]}` : value;
};

const weekRange = (weekStart: string, weekEnd: string) =>
  `${formatCalendarDate(weekStart)}–${formatCalendarDate(weekEnd)}`;

function csvCell(value: string | number | null) {
  let text = value == null ? '' : String(value);
  if (/^[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function exportDashboard(dashboard: InstructorDashboard) {
  const rows = [
    ['Mã lớp', 'Tên lớp', 'Sĩ số', 'Cảnh báo mở', 'Trễ hạn', 'Tỉ lệ hoàn thành'],
    ...dashboard.courses.map((course) => [
      course.code,
      course.name,
      course.studentCount,
      course.highRisk + course.openWarnings,
      course.overdue,
      course.completionRate == null ? '' : percent(course.completionRate),
    ]),
  ];
  const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`;
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `pacewise-tong-quan-${dashboard.generatedAt.slice(0, 10)}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function StudentAlertList({ dashboard }: { dashboard: InstructorDashboard }) {
  const { t } = useLocale();
  const [showAll, setShowAll] = useState(false);
  const visibleAlerts = showAll ? dashboard.studentAlerts : dashboard.studentAlerts.slice(0, 4);
  return (
    <Card aria-labelledby="student-alerts-title">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 id="student-alerts-title" className="flex items-center gap-2 text-lg font-bold">
          <Icon name="bell" size={20} className="text-slate-600" />
          {t('Sinh viên cần chú ý')}
        </h2>
        {dashboard.studentAlerts.length > 4 && (
          <Button size="sm" variant="ghost" iconRight="chevronDown" onClick={() => setShowAll((current) => !current)}>
            {showAll ? t('Thu gọn') : t('Xem tất cả')}
          </Button>
        )}
      </div>
      {dashboard.studentAlerts.length === 0 ? (
        <p className="rounded-xl bg-slate-50 px-4 py-5 text-sm text-muted">{t('Chưa có sinh viên nào cần chú ý theo deadline hiện tại.')}</p>
      ) : (
        <ul className="space-y-2">
          {visibleAlerts.map((alert) => (
            <li key={alert.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-slate-50/80 px-4 py-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm">
                <Icon name="users" size={17} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-ink">{alert.studentName}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {alert.courseCode}
                  {alert.overdueCount > 0 && t(` · ${alert.overdueCount} nhiệm vụ trễ hạn`)}
                  {alert.upcomingCount > 0 && t(` · ${alert.upcomingCount} deadline trong 72 giờ`)}
                </p>
              </div>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ${
                alert.severity === 'high' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-700'
              }`}>
                {alert.severity === 'high' ? t('Cần xử lý sớm') : t('Cần nhắc deadline')}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function SystemNotices({ dashboard }: { dashboard: InstructorDashboard }) {
  const { locale, t } = useLocale();
  return (
    <Card aria-labelledby="system-notices-title">
      <h2 id="system-notices-title" className="mb-4 flex items-center gap-2 text-lg font-bold">
        <Icon name="message" size={20} className="text-primary" />
        {t('Từ PaceWise')}
      </h2>
      {dashboard.systemNotices.length === 0 ? (
        <p className="rounded-xl bg-slate-50 px-4 py-5 text-sm text-muted">{t('Không có thông báo mới.')}</p>
      ) : (
        <ul className="space-y-2">
          {dashboard.systemNotices.map((notice) => (
            <li key={notice.id} className="rounded-xl border border-line bg-slate-50/80 px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <p className="font-semibold text-ink">{t(notice.title)}</p>
                <time className="shrink-0 text-xs tabular-nums text-muted" dateTime={notice.at}>{formatTimestamp(notice.at, locale)}</time>
              </div>
              <p className="mt-1 text-sm text-muted">{t(notice.message)}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function CourseSummary({ dashboard }: { dashboard: InstructorDashboard }) {
  const { t } = useLocale();
  return (
    <Card className="mt-5" aria-labelledby="course-summary-title">
      <div className="mb-4">
        <h2 id="course-summary-title" className="flex items-center gap-2 text-lg font-bold">
          <Icon name="book" size={20} className="text-primary" />
          {t('Tổng hợp lớp đang chọn')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('Mọi số liệu bên dưới chỉ thuộc môn học đang được chọn phía trên.')}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-y border-line bg-slate-50 text-xs font-semibold text-muted">
              <th className="px-3 py-2.5">{t('Lớp')}</th>
              <th className="px-3 py-2.5 text-center">{t('Sĩ số')}</th>
              <th className="px-3 py-2.5 text-center">{t('Cảnh báo mở')}</th>
              <th className="px-3 py-2.5 text-center">{t('Trễ hạn')}</th>
              <th className="px-3 py-2.5 text-right">{t('Tỉ lệ hoàn thành')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {dashboard.courses.map((course) => (
              <tr key={course.id} className="transition-colors hover:bg-slate-50/70">
                <td className="px-3 py-3">
                  <p className="font-bold text-primary-dark">{course.code}</p>
                  <p className="mt-0.5 max-w-sm truncate text-xs text-muted" title={course.name}>{course.name}</p>
                </td>
                <td className="px-3 py-3 text-center tabular-nums">{course.studentCount}</td>
                <td className="px-3 py-3 text-center font-semibold tabular-nums">{course.highRisk + course.openWarnings}</td>
                <td className="px-3 py-3 text-center font-semibold tabular-nums">{course.overdue}</td>
                <td className="px-3 py-3 text-right font-semibold tabular-nums">
                  {course.completionRate == null ? t('Chưa có dữ liệu') : percent(course.completionRate)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function WeeklyTrend({ dashboard }: { dashboard: InstructorDashboard }) {
  const { t } = useLocale();
  const current = dashboard.currentWeek;
  const course = dashboard.courses[0];
  const currentLabel = weekRange(current.weekStart, current.weekEnd);
  const currentWeekText = `Tuần này${current.weekNumber ? ` · Tuần ${current.weekNumber}` : ''} · ${currentLabel}: ${
    current.rate == null ? 'Chưa có deadline đến hạn' : percent(current.rate)
  }`;
  return (
    <Card className="mt-5" aria-labelledby="weekly-trend-title">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="weekly-trend-title" className="flex items-center gap-2 text-lg font-bold">
            <Icon name="chart" size={21} className="text-primary" />
            {t('Xu hướng hoàn thành theo tuần')}
          </h2>
          <p className="mt-1 text-sm text-muted">
            {course ? `${course.code} · ${course.name}` : t('Môn đang chọn')} · {t(`${dashboard.weeklyCompletion.length} tuần theo lịch học và deadline.`)}{' '}
            {t('Tiến độ chỉ tính nhiệm vụ đã đến hạn.')}
          </p>
        </div>
        <p className="text-sm font-semibold text-primary-dark">{t(currentWeekText)}</p>
      </div>
      {current.rate == null && (
        <p className="mb-5 rounded-xl border border-blue-100 bg-blue-50/60 px-4 py-3 text-sm text-slate-700">
          {t('Tuần hiện tại chưa có deadline đã đến hạn. Những tuần chưa có deadline hoặc chưa tới hạn vẫn được hiển thị để lịch môn học không bị nhảy tuần.')}
        </p>
      )}
      {dashboard.weeklyCompletion.length === 0 ? (
        <p className="rounded-xl bg-slate-50 px-4 py-5 text-sm text-muted">{t('Chưa có nhiệm vụ đến hạn để tạo xu hướng.')}</p>
      ) : (
        <ul className="space-y-4">
          {dashboard.weeklyCompletion.map((week, index) => {
            const width = week.rate == null ? 0 : Math.max(0, Math.min(100, Math.round(week.rate * 100)));
            const result = week.rate == null
              ? (week.taskCount > 0 && week.status !== 'past' ? t('Chưa đến hạn') : t('Không có deadline'))
              : percent(week.rate);
            const schedule = [
              week.lessonCount > 0 ? t(`${week.lessonCount} buổi học`) : '',
              week.taskCount > 0 ? t(`${week.taskCount} nhiệm vụ`) : '',
            ].filter(Boolean).join(' · ') || t('Không có hoạt động theo lịch');
            return (
              <li key={`${week.weekStart}-${index}`} className={week.status === 'current' ? 'rounded-xl border border-blue-200 bg-blue-50/40 p-3' : ''}>
                <div className="mb-1.5 flex items-center justify-between gap-4 text-sm">
                  <span className="font-semibold">
                    {week.weekNumber ? t(`Tuần ${week.weekNumber}`) : t('Tuần')} · {weekRange(week.weekStart, week.weekEnd)}
                    {week.status === 'current' && <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-primary-dark">{t('Hiện tại')}</span>}
                  </span>
                  <span className={`font-bold tabular-nums ${week.rate == null ? 'text-muted' : ''}`}>{result}</span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-slate-200" role="img" aria-label={`${t(`Tuần ${week.week}`)}: ${result}`}>
                  <div className="h-full rounded-full bg-amber-500 transition-[width]" style={{ width: `${width}%` }} />
                </div>
                <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
                  <span>{schedule}</span>
                  <span className="tabular-nums">
                    {week.total > 0
                      ? t(`${week.count}/${week.total} lượt đúng hạn`)
                      : week.scheduledTotal > 0 ? t(`${week.scheduledTotal} lượt theo lịch`) : t('Chưa có lượt phải nộp')}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function InstructorOverviewPage() {
  const { t } = useLocale();
  useDocumentTitle('Tổng quan giảng viên');
  const { state } = useAppStore();
  const activeCourseId = state.user?.courseId;
  const userId = state.user?.id;
  const initialCache = readInstructorDashboardCache(userId, activeCourseId);
  const [dashboard, setDashboard] = useState<InstructorDashboard | null>(initialCache?.data ?? null);
  const [loadedCourseId, setLoadedCourseId] = useState<string | null>(initialCache ? activeCourseId ?? null : null);
  const [loading, setLoading] = useState(Boolean(activeCourseId) && !initialCache);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async (refresh = false) => {
    const courseId = activeCourseId;
    if (!courseId || courseId === '0') {
      setDashboard(null);
      setLoadedCourseId(null);
      setLoading(false);
      return;
    }
    if (!userId) return;
    const requestId = ++requestSequence.current;
    const cached = readInstructorDashboardCache(userId, courseId);
    if (!refresh && isFresh(cached, state.lmsRevision)) {
      setDashboard(cached!.data);
      setLoadedCourseId(courseId);
      setLoading(false);
      return;
    }
    if (cached) {
      setDashboard(cached.data);
      setLoadedCourseId(courseId);
      setRefreshing(true);
    } else if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const nextDashboard = await requestDashboard(`${userId}:${courseId}:${state.lmsRevision}`, courseId);
      if (requestId !== requestSequence.current) return;
      writeInstructorDashboardCache(userId, courseId, state.lmsRevision, nextDashboard);
      setDashboard(nextDashboard);
      setLoadedCourseId(courseId);
    } catch (reason) {
      if (requestId !== requestSequence.current) return;
      setError(reason instanceof ApiError ? reason : new ApiError('UNKNOWN', 'Không thể tải tổng quan giảng viên.'));
    } finally {
      if (requestId === requestSequence.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [activeCourseId, state.lmsRevision, userId]);

  useEffect(() => { void load(); }, [load, state.lmsRevision]);

  if (!activeCourseId || activeCourseId === '0') {
    return (
      <div className="page">
        <PageHeader title={t('Tổng quan giảng viên')} description={t('Theo dõi nhanh lớp học và các tín hiệu cần xử lý.')} />
        <Card className="flex flex-col items-center px-6 py-12 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-light text-primary"><Icon name="book" size={28} /></span>
          <h2 className="mt-4 text-xl font-semibold">{t('Tạo môn học đầu tiên')}</h2>
          <p className="mt-2 max-w-md text-muted">{t('Sau khi tạo hoặc nhập môn học, số liệu tổng quan sẽ xuất hiện tại đây.')}</p>
          <ButtonLink className="mt-6" to="/instructor/courses" icon="plus">{t('Quản lý môn học')}</ButtonLink>
        </Card>
      </div>
    );
  }

  if (loadedCourseId !== activeCourseId && error && !loading) {
    return <div className="page"><ErrorState title="Không thể tải tổng quan giảng viên" description={error.message} requestId={error.requestId} onRetry={() => void load()} /></div>;
  }

  if (loadedCourseId !== activeCourseId || (loading && !dashboard)) {
    return (
      <div className="page" aria-busy="true">
        <PageHeader title={t('Tổng quan giảng viên')} description={t('Đang tổng hợp dữ liệu các lớp…')} />
        <Card className="flex items-center gap-4 px-5 py-6">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-r-transparent" aria-hidden="true" />
          <p className="font-semibold">{t('Đang chuẩn bị số liệu tổng quan')}</p>
        </Card>
      </div>
    );
  }

  if (!dashboard) {
    return <div className="page"><ErrorState title="Không thể tải tổng quan giảng viên" description={error?.message ?? 'Vui lòng thử lại.'} requestId={error?.requestId} onRetry={() => void load()} /></div>;
  }

  return (
    <div className="page">
      <PageHeader
        title={t('Tổng quan giảng viên')}
        description={t('Tín hiệu cần xử lý và xu hướng hoàn thành của môn học đang chọn.')}
        actions={<Button variant="secondary" icon="refresh" loading={refreshing} onClick={() => void load(true)}>{t('Làm mới')}</Button>}
      />

      {error && <div className="mb-5"><ErrorState title={t('Chưa làm mới được số liệu')} description={t('Đang hiển thị dữ liệu gần nhất.')} onRetry={() => void load(true)} /></div>}

      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="border-blue-200 bg-blue-50/45 px-5 py-5">
          <p className="text-sm font-semibold text-primary-dark">{t('Cảnh báo mở')}</p>
          <p className="mt-2 text-4xl font-bold tabular-nums text-ink">{dashboard.summary.highRisk + dashboard.summary.openWarnings}</p>
          <p className="mt-2 text-xs text-muted">{t('Sinh viên có deadline đang cần chú ý.')}</p>
        </Card>
        <Card className="border-amber-200 bg-amber-50/45 px-5 py-5">
          <p className="text-sm font-semibold text-amber-700">{t('Trễ hạn')}</p>
          <p className="mt-2 text-4xl font-bold tabular-nums text-ink">{dashboard.summary.overdue}</p>
          <p className="mt-2 text-xs text-muted">{t('Sinh viên có ít nhất một nhiệm vụ quá hạn.')}</p>
        </Card>
      </div>

      <div className="my-5 flex flex-wrap items-center justify-between gap-3">
        <Button variant="secondary" size="sm" icon="download" onClick={() => exportDashboard(dashboard)}>{t('Xuất báo cáo')}</Button>
        <p className="text-xs text-muted">{t('Mỗi cảnh báo tương ứng một sinh viên thuộc môn đang chọn.')}</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <StudentAlertList dashboard={dashboard} />
        <SystemNotices dashboard={dashboard} />
      </div>

      <CourseSummary dashboard={dashboard} />
      <WeeklyTrend dashboard={dashboard} />
    </div>
  );
}
