import { useEffect, useState } from 'react';
import { Button } from '../ui/Button';
import { Card, CardHeader } from '../ui/Card';
import { useToast } from '../ui/Toast';
import { useAppStore } from '../../store/AppStore';
import { defaultReminderPreferences, normalizeStudyPreferences } from '../../utils/studyPreferences';
import { disablePushNotifications, enablePushNotifications, supportsPush } from '../../services/pushNotifications';
import { getPushStatus, type PushStatus } from '../../services/api';
import { RhythmProposalCard } from './RhythmProposalCard';
import { ActivityRhythmSettings } from './ActivityRhythmSettings';

export function StudySettingsCards() {
  const { state, dispatch } = useAppStore();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [pushStatus, setPushStatus] = useState<PushStatus | null>(null);
  const [pushError, setPushError] = useState(false);
  useEffect(() => {
    if (!supportsPush()) return;
    let active = true;
    void (async () => {
      try { const result = await getPushStatus(); if (active) setPushStatus(result); }
      catch { if (active) setPushError(true); }
    })();
    return () => { active = false; };
  }, [state.user?.id]);
  const preferences = { ...defaultReminderPreferences, ...state.reminders?.preferences };
  const rhythm = normalizeStudyPreferences(state.studyPreferences);
  const update = (patch: Partial<typeof preferences>) => dispatch({ type: 'UPDATE_REMINDER_PREFERENCES', patch });
  const togglePush = async () => {
    setBusy(true);
    try {
      if (preferences.pushEnabled && pushStatus?.subscribed) {
        await disablePushNotifications();
        update({ pushEnabled: false });
        setPushStatus((status) => status ? { ...status, subscribed: false } : null);
        toast({ tone: 'success', title: 'Đã tắt nhắc nền PaceWise' });
      } else {
        await enablePushNotifications();
        update({ browserEnabled: true, pushEnabled: true });
        setPushError(false);
        setPushStatus((status) => ({ configured: true, publicKey: status?.publicKey ?? null, subscribed: true }));
        toast({ tone: 'success', title: 'Đã bật nhắc khi đóng tab PaceWise' });
      }
    } catch (error) {
      toast({ tone: 'danger', title: 'Chưa thể đổi chế độ nhắc nền', description: error instanceof Error ? error.message : undefined });
    } finally { setBusy(false); }
  };
  return <>
    <Card aria-labelledby="notification-settings">
      <CardHeader id="notification-settings" title="Cấu hình nhắc học" subtitle="Nhắc trong PaceWise và thông báo nền; không tự bật quyền thiết bị." />
      <div className="space-y-4">
        <label className="flex items-center gap-3"><input type="checkbox" checked={preferences.enabled} onChange={(event) => update({ enabled: event.target.checked })} />Bật nhắc học</label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex items-center gap-3"><input type="checkbox" checked={preferences.deadlineEnabled} onChange={(event) => update({ deadlineEnabled: event.target.checked })} />Nhắc deadline</label>
          <label className="flex items-center gap-3"><input type="checkbox" checked={preferences.studyEnabled} onChange={(event) => update({ studyEnabled: event.target.checked })} />Nhắc bắt đầu Do và lịch học</label>
          <label className="flex items-center gap-3"><input type="checkbox" checked={preferences.reflectEnabled} onChange={(event) => update({ reflectEnabled: event.target.checked })} />Nhắc hoàn thành Reflect</label>
          <label className="flex flex-col gap-1 text-sm">Nhắc Do trước (phút)
            <select className="rounded-lg border border-line bg-white p-2" value={preferences.studyBlockLeadMinutes} onChange={(event) => update({ studyBlockLeadMinutes: Number(event.target.value) })}>
              {[0, 5, 10, 15, 30, 60].map((minutes) => <option key={minutes} value={minutes}>{minutes}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">Tối đa thông báo mỗi ngày
            <select className="rounded-lg border border-line bg-white p-2" value={preferences.dailyCap} onChange={(event) => update({ dailyCap: Number(event.target.value) })}>
              {[1, 2, 3].map((count) => <option key={count} value={count}>{count}</option>)}
            </select>
          </label>
        </div>
        <label className="flex items-center gap-3"><input type="checkbox" checked={preferences.quietHoursEnabled} onChange={(event) => update({ quietHoursEnabled: event.target.checked })} />Giờ không làm phiền</label>
        {preferences.quietHoursEnabled && <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">Bắt đầu không làm phiền<input className="mt-1 block w-full rounded-lg border border-line p-2" type="time" value={preferences.quietStart} onChange={(event) => {
            if (event.target.value && event.target.value !== preferences.quietEnd) update({ quietStart: event.target.value });
          }} /></label>
          <label className="text-sm">Kết thúc không làm phiền<input className="mt-1 block w-full rounded-lg border border-line p-2" type="time" value={preferences.quietEnd} onChange={(event) => {
            if (event.target.value && event.target.value !== preferences.quietStart) update({ quietEnd: event.target.value });
          }} /></label>
        </div>}
        <p className="caption">Giờ Việt Nam. Giờ yên lặng chặn thông báo PaceWise, nhưng không ẩn nhắc trong icon chuông. Reflect được nhắc sau 5 phút nếu chưa lưu.</p>
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="secondary" icon="bell" loading={busy} disabled={!supportsPush()} onClick={togglePush}>{preferences.pushEnabled && pushStatus?.subscribed ? 'Tắt nhắc nền' : 'Bật nhắc khi đóng tab'}</Button>
          <span className="caption">{!supportsPush() ? 'Thiết bị chưa hỗ trợ Web Push/HTTPS.' : pushError ? 'Chưa kiểm tra được kết nối push; có thể bấm bật để thử lại.' : pushStatus?.configured === false ? 'Backend chưa cấu hình Web Push.' : pushStatus?.subscribed && preferences.pushEnabled ? 'Thiết bị này đã đăng ký nhắc nền.' : 'Cần đăng ký thiết bị và cấp quyền thông báo một lần.'}</span>
        </div>
        <p className="caption">Cấu hình nhắc áp dụng cho tài khoản; mỗi thiết bị cần đăng ký push riêng. Nhắc nền cần backend/worker đang chạy và thiết bị cho phép nhận push. Giờ yên lặng PaceWise không thay cài đặt thông báo của Google.</p>
      </div>
    </Card>
    <Card aria-labelledby="study-rhythm">
      <CardHeader id="study-rhythm" title="Nhịp học cá nhân" subtitle="Áp dụng khi tạo hoặc phân tích lại kế hoạch; không thay lịch LMS hay lịch đã xác nhận." />
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">Tối đa mỗi ca ưu tiên (phút)
          <select className="rounded-lg border border-line bg-white p-2" value={rhythm.sessionMinutes} onChange={(event) => dispatch({ type: 'UPDATE_STUDY_PREFERENCES', patch: { sessionMinutes: Number(event.target.value) } })}>
            {[...new Set([20, 25, 30, 40, 45, 60, 75, 90, 105, 120, rhythm.sessionMinutes])].sort((a, b) => a - b).map((minutes) => <option key={minutes} value={minutes}>{minutes}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">Nghỉ giữa phiên (phút)
          <select className="rounded-lg border border-line bg-white p-2" value={rhythm.breakMinutes} onChange={(event) => dispatch({ type: 'UPDATE_STUDY_PREFERENCES', patch: { breakMinutes: Number(event.target.value) } })}>
            {[5, 10, 15, 20, 30].map((minutes) => <option key={minutes} value={minutes}>{minutes}</option>)}
          </select>
        </label>
      </div>
      <p className="caption mt-3">Ví dụ chọn 90 phút nghĩa là mỗi ca không vượt 90 phút. Ca cuối còn 70 phút hoặc khung rảnh chỉ còn 70 phút vẫn được xếp 70 phút; tổng công việc không bị giảm. Deadline và ca học LMS luôn được giữ nguyên.</p>
      <label className="mt-3 flex flex-col gap-1 text-sm">Dự phòng thêm cho checkpoint Assessment (phút mỗi phiên)
        <select className="rounded-lg border border-line bg-white p-2" value={rhythm.checkpointMinutes ?? 0} onChange={(event) => dispatch({ type: 'UPDATE_STUDY_PREFERENCES', patch: { checkpointMinutes: Number(event.target.value) } })}>
          {[0, 5, 10, 15].map((minutes) => <option key={minutes} value={minutes}>{minutes === 0 ? '0 — đã tính trong estimate công việc' : minutes}</option>)}
        </select>
      </label>
      <p className="caption mt-2">Phần dự phòng nằm trong ca, được tính vào capacity và deadline, không làm giảm số phút công việc. Giữ 0 nếu estimate đã bao gồm kiểm tra.</p>
      <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={rhythm.adaptiveSuggestionsEnabled ?? true} onChange={(event) => dispatch({ type: 'UPDATE_STUDY_PREFERENCES', patch: { adaptiveSuggestionsEnabled: event.target.checked } })} />Nhận đề xuất nhịp học dựa trên bằng chứng</label>
      <RhythmProposalCard />
      <ActivityRhythmSettings />
    </Card>
  </>;
}
