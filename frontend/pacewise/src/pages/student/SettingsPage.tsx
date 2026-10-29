import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, ButtonLink } from '../../components/ui/Button';
import { Card, CardHeader } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { PageHeader } from '../../components/ui/PageHeader';
import { useToast } from '../../components/ui/Toast';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import {
  connectGoogleCalendar,
  disconnectGoogleCalendar,
  downloadPlanIcs,
  exportPlanToGoogleCalendar,
  getGoogleCalendarStatus,
  syncGoogleCalendarBusy,
  type GoogleCalendarStatus,
} from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import { addDays } from '../../utils/time';
import { StudySettingsCards } from '../../components/domain/StudySettingsCards';
import { LmsConnectionCard } from '../../components/domain/LmsConnectionCard';
import { LanguageToggle } from '../../components/domain/LanguageToggle';
import { useLocale } from '../../i18n/LocaleContext';
import { downloadBlobFile } from '../../utils/download';
import { standaloneCourses } from '../../services/courseSource';

export function SettingsPage() {
  const { locale, t } = useLocale();
  useDocumentTitle('Cài đặt');
  const { state, dispatch, persistence } = useAppStore();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const handledOAuthResult = useRef<string | null>(null);
  const [calendar, setCalendar] = useState<GoogleCalendarStatus | null>(null);
  const [calendarLoaded, setCalendarLoaded] = useState(false);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [calendarBusy, setCalendarBusy] = useState(false);
  const [icsBusy, setIcsBusy] = useState(false);
  const [confirmExport, setConfirmExport] = useState(false);

  const weekStart = state.plan?.weekStart ?? new Date().toISOString().slice(0, 10);
  const draftBlockCount = state.planDraft?.blocks.length ?? 0;
  const calendarBlocks = useMemo(
    () =>
      (state.plan?.blocks ?? []).map((block) => ({
        blockId: block.id,
        title: `PaceWise: ${state.tasks.find((task) => task.id === block.taskId)?.title ?? 'Ca tự học'}`,
        start: `${block.date}T${block.start}:00+07:00`,
        end: `${block.date}T${block.end}:00+07:00`,
      })),
    [state.plan, state.tasks],
  );

  const refreshCalendarStatus = async () => {
    setCalendarError(null);
    try {
      setCalendar(await getGoogleCalendarStatus());
    } catch {
      setCalendarError('Không kiểm tra được kết nối Google. Hãy thử lại.');
    } finally {
      setCalendarLoaded(true);
    }
  };

  useEffect(() => {
    void refreshCalendarStatus();
  }, []);

  useEffect(() => {
    const result = searchParams.get('google_calendar');
    if (!result) {
      handledOAuthResult.current = null;
      return;
    }
    if (handledOAuthResult.current !== result) {
      handledOAuthResult.current = result;
      toast({
        tone: result === 'connected' ? 'success' : 'danger',
        title: result === 'connected' ? 'Đã kết nối Google Calendar' : 'Chưa thể kết nối Google Calendar',
        description: result === 'denied' ? 'Bạn đã từ chối cấp quyền.' : result === 'error' ? 'OAuth không hoàn tất. Hãy thử kết nối lại.' : undefined,
      });
      const cleanedParams = new URLSearchParams(searchParams);
      cleanedParams.delete('google_calendar');
      // Let HashRouter preserve its history index/key and update route state.
      setSearchParams(cleanedParams, { replace: true });
      void refreshCalendarStatus();
    }
  }, [searchParams, setSearchParams, toast]);

  const startGoogleConnect = async () => {
    setCalendarBusy(true);
    try {
      const result = await connectGoogleCalendar();
      window.location.assign(result.authorizationUrl);
    } catch (error) {
      toast({ tone: 'danger', title: 'Không thể bắt đầu kết nối', description: error instanceof Error ? error.message : undefined });
      setCalendarBusy(false);
    }
  };

  const importBusyTime = async () => {
    setCalendarBusy(true);
    try {
      const result = await syncGoogleCalendarBusy(
        `${weekStart}T00:00:00+07:00`,
        `${addDays(weekStart, 7)}T00:00:00+07:00`,
      );
      const manualSlots = state.unavailable.filter((slot) => !slot.id.startsWith('google-'));
      dispatch({ type: 'SAVE_AVAILABILITY', availability: state.availability, unavailable: [...manualSlots, ...result.unavailableSlots] });
      toast({ tone: 'success', title: 'Đã nhập lịch bận', description: `${result.unavailableSlots.length} khoảng bận được dùng khi lập kế hoạch.` });
      await refreshCalendarStatus();
    } catch (error) {
      toast({ tone: 'danger', title: 'Không đọc được lịch bận', description: error instanceof Error ? error.message : undefined });
    } finally {
      setCalendarBusy(false);
    }
  };

  const exportBlocks = async () => {
    setCalendarBusy(true);
    try {
      const result = await exportPlanToGoogleCalendar(calendarBlocks);
      toast({
        tone: 'success',
        title: 'Đã cập nhật Google Calendar',
        description: `${result.created.length} sự kiện mới, ${result.skipped.length} sự kiện đã tồn tại.`,
      });
      setConfirmExport(false);
    } catch (error) {
      toast({ tone: 'danger', title: 'Không thể tạo sự kiện', description: error instanceof Error ? error.message : undefined });
    } finally {
      setCalendarBusy(false);
    }
  };

  const disconnectCalendar = async () => {
    setCalendarBusy(true);
    try {
      await disconnectGoogleCalendar();
      setCalendar((current) => current ? { ...current, connected: false, connectedAt: null, lastFreeBusySyncAt: null } : current);
      toast({ tone: 'success', title: 'Đã ngắt kết nối và thu hồi quyền Google' });
    } catch (error) {
      toast({ tone: 'danger', title: 'Chưa thể ngắt kết nối', description: error instanceof Error ? error.message : undefined });
    } finally {
      setCalendarBusy(false);
    }
  };

  const downloadIcs = async () => {
    setIcsBusy(true);
    try {
      const file = await downloadPlanIcs(calendarBlocks);
      downloadBlobFile(file, 'pacewise-study-plan.ics');
      toast({ tone: 'success', title: 'Đã tải file lịch .ics' });
    } catch (error) {
      toast({ tone: 'danger', title: 'Không thể xuất file lịch', description: error instanceof Error ? error.message : undefined });
    } finally {
      setIcsBusy(false);
    }
  };

  return (
    <div className="page max-w-3xl">
      <PageHeader title="Cài đặt" description="Tài khoản, kết nối lịch và đồng bộ dữ liệu học tập." />
      {state.user?.courseIds?.length === 0 && <div className="rounded-2xl border border-line bg-primary-light p-4 text-sm">
        <h2 className="font-semibold">Tài khoản đã sẵn sàng</h2>
        <p className="mt-1">Bạn có thể kết nối Google Calendar bên dưới. Môn học sẽ xuất hiện sau khi giảng viên thêm bạn vào lớp; chưa có quyền xem học liệu hay kế hoạch của người khác.</p>
      </div>}
      <div className="space-y-5">
        <Card aria-labelledby="acc">
          <CardHeader id="acc" title="Tài khoản" />
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <dt className="caption">Họ tên</dt>
              <dd className="font-medium">{state.user?.name}</dd>
            </div>
            <div>
              <dt className="caption">Email</dt>
              <dd className="break-all font-medium">{state.user?.email}</dd>
            </div>
            <div>
              <dt className="caption">Nguồn dữ liệu</dt>
              <dd className="font-medium">{standaloneCourses
                ? t('PaceWise · dữ liệu nội bộ', 'PaceWise · internal data')
                : t('Canvas mô phỏng (chỉ đọc)', 'Simulated Canvas (read-only)')}</dd>
            </div>
            <div>
              <dt className="caption">Múi giờ</dt>
              <dd className="font-medium">GMT+7 (Asia/Ho_Chi_Minh)</dd>
            </div>
          </dl>
        </Card>

        <Card aria-labelledby="language-settings">
          <CardHeader id="language-settings" title={t('Ngôn ngữ', 'Language')} subtitle={t('Áp dụng cho toàn bộ giao diện PaceWise trên thiết bị này.', 'Applies to the full PaceWise interface on this device.')} />
          <LanguageToggle />
        </Card>

        <StudySettingsCards />
        <LmsConnectionCard />
        <Card aria-labelledby="workspace-sync">
          <CardHeader id="workspace-sync" title="Đồng bộ dữ liệu PaceWise" subtitle="Kế hoạch và tiến độ được lưu trên máy chủ để dùng tiếp ở thiết bị khác." />
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <span className={persistence.status === 'error' || persistence.status === 'conflict' ? 'font-medium text-danger-ink' : 'text-muted'}>
              {persistence.status === 'saving' && 'Đang lưu thay đổi…'}
              {persistence.status === 'saved' && 'Đã lưu an toàn'}
              {persistence.status === 'idle' && 'Chưa có thay đổi mới'}
              {persistence.status === 'error' && 'Lưu dữ liệu thất bại'}
              {persistence.status === 'conflict' && 'Dữ liệu đã đổi ở thiết bị khác; hãy tải lại trang trước khi sửa tiếp.'}
            </span>
            {persistence.savedAt && <span className="caption">{t('Lần lưu gần nhất:', 'Last saved:')} {new Date(persistence.savedAt).toLocaleString(locale === 'en' ? 'en-GB' : 'vi-VN')}</span>}
          </div>
          {persistence.message && <p className="mt-2 text-sm text-danger-ink">{persistence.message}</p>}
        </Card>

        <Card aria-labelledby="google-calendar">
          <CardHeader
            id="google-calendar"
            title="Lịch cá nhân"
            subtitle="Kết nối Google Calendar hoặc tải file .ics dùng với ứng dụng lịch khác."
          />
          <div className="space-y-5">
            <section className="space-y-3" aria-labelledby="google-direct-title">
              <h3 id="google-direct-title" className="font-semibold">Kết nối trực tiếp</h3>
              <p className="text-sm text-muted">
                Trước khi kết nối, hãy xem cách PaceWise truy cập, sử dụng, lưu trữ và chia sẻ dữ liệu Google trong{' '}
                <a className="font-medium text-primary underline" href="/privacy" target="_blank" rel="noreferrer">
                  Chính sách quyền riêng tư
                </a>.
              </p>
              {(calendarError || calendar?.error) && <p role="alert" className="text-sm text-danger-ink">{calendarError || calendar?.error}</p>}
              <Button size="sm" variant="secondary" icon="refresh" onClick={() => void refreshCalendarStatus()}>Kiểm tra kết nối Google lại</Button>
              {!calendarLoaded ? (
                <p className="text-sm text-muted">Đang kiểm tra trạng thái kết nối…</p>
              ) : calendarError && !calendar ? (
                <p className="text-sm text-muted">Chưa đọc được trạng thái; không thể kết luận Google chưa cấu hình.</p>
              ) : !calendar?.configured ? (
                <div className="rounded-xl border border-warning/40 bg-warning-light p-4 text-sm text-warning-ink">
                  Quản trị viên chưa cấu hình Google OAuth. Bạn vẫn có thể tải file .ics bên dưới.
                </div>
              ) : !calendar.connected ? (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-sm text-muted">Tài khoản Google có thể khác tài khoản trường. PaceWise chỉ đọc busy/free và quản lý sự kiện do ứng dụng tạo.</p>
                  <Button icon="calendar" loading={calendarBusy} onClick={startGoogleConnect}>Kết nối Google Calendar</Button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-xl border border-line p-4 text-sm">
                    {calendar.health === 'degraded'
                      ? t('Kết nối cần kiểm tra lại', 'The connection needs attention')
                      : t('Đã kết nối', 'Connected')}
                    {calendar.accountEmail
                      ? <>{t(' với ', ' to ')}<strong>{calendar.accountEmail}</strong></>
                      : ''}. {t('PaceWise không sửa hoặc xóa sự kiện khác của bạn.', 'PaceWise does not edit or delete your other events.')}
                  </div>
                  {!calendarBlocks.length && (
                    <div className="rounded-xl border border-warning/40 bg-warning-light p-4 text-sm text-warning-ink">
                      <p className="font-semibold">Google đã kết nối, nhưng chưa có ca tự học đã xác nhận để xuất.</p>
                      <p className="mt-1">
                        {draftBlockCount
                          ? `Bản nháp hiện có ${draftBlockCount} ca. Hãy xem và xác nhận trước khi ghi sang Google Calendar.`
                          : 'Bản nháp hiện chưa xếp được ca nào. Mở Plan để phân tích lại lịch và xử lý các cảnh báo.'}
                      </p>
                    </div>
                  )}
                  <div className="flex flex-wrap gap-3">
                    <Button variant="secondary" icon="refresh" loading={calendarBusy} onClick={importBusyTime}>Nhập lịch bận từ Google (7 ngày)</Button>
                    {calendarBlocks.length ? (
                      <Button icon="calendar" onClick={() => setConfirmExport(true)}>
                        {locale === 'en'
                          ? `Add ${calendarBlocks.length} ${calendarBlocks.length === 1 ? 'session' : 'sessions'} to Google`
                          : `Đưa ${calendarBlocks.length} ca lên Google`}
                      </Button>
                    ) : (
                      <ButtonLink to="/plan" icon="calendar">Mở Plan để tạo kế hoạch</ButtonLink>
                    )}
                    <Button variant="danger" disabled={calendarBusy} onClick={disconnectCalendar}>Ngắt kết nối</Button>
                  </div>
                  {calendar.lastFreeBusySyncAt && <p className="caption">{t('Nhập lịch bận gần nhất:', 'Busy times last imported:')} {new Date(calendar.lastFreeBusySyncAt).toLocaleString(locale === 'en' ? 'en-GB' : 'vi-VN')}</p>}
                  {calendar.health === 'degraded' && <Button variant="secondary" onClick={startGoogleConnect}>Cấp quyền Google lại</Button>}
                </div>
              )}
            </section>

            <section className="flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between" aria-labelledby="ics-title">
              <div>
                <h3 id="ics-title" className="font-semibold">Xuất file lịch</h3>
                <p className="caption mt-1">
                  {calendarBlocks.length
                    ? locale === 'en'
                      ? `${calendarBlocks.length} ${calendarBlocks.length === 1 ? 'study session' : 'study sessions'} in the current plan · can be exported as an .ics file independently of Google.`
                      : `${calendarBlocks.length} ca tự học trong kế hoạch hiện tại · có thể xuất file .ics độc lập với Google.`
                    : 'Chưa có ca tự học trong kế hoạch đã xác nhận để xuất. Kết nối Google không tự tạo nội dung file .ics.'}
                </p>
              </div>
              <Button variant="secondary" icon="calendar" loading={icsBusy} disabled={!calendarBlocks.length || icsBusy} onClick={downloadIcs}>
                Tải file .ics
              </Button>
            </section>
          </div>
        </Card>

      </div>
      <Modal
        open={confirmExport}
        onClose={() => !calendarBusy && setConfirmExport(false)}
        title="Xác nhận tạo sự kiện"
        description="Đây là hành động ghi dữ liệu ra Google Calendar."
        footer={(
          <>
            <Button variant="secondary" disabled={calendarBusy} onClick={() => setConfirmExport(false)}>Hủy</Button>
            <Button loading={calendarBusy} onClick={exportBlocks}>{locale === 'en'
              ? `Confirm creating ${calendarBlocks.length} ${calendarBlocks.length === 1 ? 'event' : 'events'}`
              : `Xác nhận tạo ${calendarBlocks.length} sự kiện`}</Button>
          </>
        )}
      >
        <div className="space-y-2 text-sm text-muted">
          {calendar?.accountEmail && <p>Tài khoản đích: <strong className="text-ink">{calendar.accountEmail}</strong></p>}
          <p>PaceWise sẽ tạo các ca tự học của kế hoạch hiện tại. Những block đã xuất trước đó sẽ được bỏ qua để tránh trùng lịch.</p>
          <p>Mỗi sự kiện mới được gắn nhắc Google trước 15 phút. Google tự gửi nhắc khi thiết bị cho phép nhận thông báo.</p>
        </div>
      </Modal>
    </div>
  );
}
