import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useToast } from '../ui/Toast';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { useAppStore } from '../../store/AppStore';
import type { Reminder } from '../../types';
import { activeReminders, buildReminders, selectBrowserDeliveries } from '../../utils/reminders';
import {
  acceptMyCourseInvitation,
  claimReminders,
  fetchMyCourseInvitations,
  getCurrentSession,
  type MyCourseInvitation,
} from '../../services/api';

const formatTime = (value: string) => new Date(value).toLocaleString('vi-VN', {
  hour: '2-digit',
  minute: '2-digit',
  day: '2-digit',
  month: '2-digit',
  timeZone: 'Asia/Ho_Chi_Minh',
});

const tone = (item: Reminder) => item.urgency === 'critical' ? 'danger' : item.urgency === 'urgent' ? 'warning' : 'primary';

export function ReminderCenter({ compact = false }: { compact?: boolean }) {
  const { state, dispatch } = useAppStore();
  const toast = useToast();
  const [clock, setClock] = useState(() => Date.now());
  const [courseInvites, setCourseInvites] = useState<MyCourseInvitation[]>([]);
  const [inviteBusy, setInviteBusy] = useState<string | null>(null);
  const now = useMemo(() => new Date(clock), [clock]);

  const refreshCourseInvites = useCallback(async () => {
    if (state.user?.role !== 'student') return;
    try {
      const result = await fetchMyCourseInvitations();
      setCourseInvites(result.invitations);
    } catch {
      // Reminders must remain usable when the invitation inbox is temporarily unavailable.
    }
  }, [state.user?.id, state.user?.role]);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    void refreshCourseInvites();
    const timer = window.setInterval(() => void refreshCourseInvites(), 30_000);
    window.addEventListener('pacewise:membership-change', refreshCourseInvites);
    window.addEventListener('pacewise:source-change', refreshCourseInvites);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('pacewise:membership-change', refreshCourseInvites);
      window.removeEventListener('pacewise:source-change', refreshCourseInvites);
    };
  }, [refreshCourseInvites]);

  const reminders = useMemo(() => buildReminders({
    now,
    plan: state.plan,
    tasks: state.tasks,
    courses: state.courses,
    courseData: state.courseData,
    sessions: state.sessions,
    planImpacts: state.planImpacts,
    studyBlockLeadMinutes: state.reminders.preferences.studyBlockLeadMinutes,
    digestHour: state.reminders.preferences.digestHour,
    preferences: state.reminders.preferences,
    reflections: state.reflections,
  }), [
    now,
    state.plan,
    state.tasks,
    state.courses,
    state.courseData,
    state.sessions,
    state.planImpacts,
    state.reminders.preferences.studyBlockLeadMinutes,
    state.reminders.preferences.digestHour,
    state.reminders.preferences,
    state.reflections,
  ]);

  const active = useMemo(() => activeReminders(reminders, now), [reminders, now]);
  const upcoming = useMemo(() => reminders
    .filter((item) => {
      const at = new Date(item.scheduledAt).getTime();
      return at > now.getTime() && at <= now.getTime() + 24 * 60 * 60 * 1000;
    })
    .slice(0, 3), [reminders, now]);
  const visible = active.length ? active : upcoming;
  const unread = active.filter((item) => !state.reminders.readIds.includes(item.id));
  const unreadCount = unread.length + courseInvites.length;

  const acceptInvite = async (invite: MyCourseInvitation) => {
    if (inviteBusy) return;
    setInviteBusy(invite.id);
    try {
      await acceptMyCourseInvitation(invite.id);
      setCourseInvites((current) => current.filter((item) => item.id !== invite.id));
      const user = await getCurrentSession();
      if (user) dispatch({ type: 'REFRESH_SESSION', user });
      window.dispatchEvent(new Event('pacewise:membership-change'));
      toast({
        tone: 'success',
        title: `Đã tham gia ${invite.code}`,
        description: 'Lịch, nhiệm vụ và học liệu của môn đang được đồng bộ vào PaceWise.',
      });
    } catch (error) {
      toast({ tone: 'danger', title: 'Chưa thể tham gia môn', description: error instanceof Error ? error.message : undefined });
    } finally {
      setInviteBusy(null);
    }
  };

  const invitationCards = courseInvites.map((invite) => (
    <li key={invite.id} className="rounded-xl border border-primary/30 bg-primary-light/40 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="primary">Lời mời môn học</Badge>
        <span className="caption ml-auto">Hạn {formatTime(invite.expiresAt)}</span>
      </div>
      <p className="mt-1.5 text-sm font-semibold">{invite.code} · {invite.name}</p>
      <p className="mt-0.5 text-xs text-muted">{invite.teacher}{invite.term ? ` · ${invite.term}` : ''}</p>
      <Button className="mt-2" size="sm" loading={inviteBusy === invite.id} disabled={!!inviteBusy} onClick={() => void acceptInvite(invite)}>
        Tham gia và đồng bộ lịch
      </Button>
    </li>
  ));

  useEffect(() => {
    // Background push owns delivery when enabled; do not duplicate it locally.
    if (state.reminders.preferences.pushEnabled) return;
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    const deliveries = selectBrowserDeliveries(reminders, state.reminders, now);
    if (!deliveries.length) return;
    void claimReminders(deliveries.map((item) => item.id)).then((claimed) => {
      if (!claimed.ids.length) return;
      deliveries.filter((item) => claimed.ids.includes(item.id)).forEach((item) => {
        const notification = new Notification(item.title, {
          body: item.message,
          tag: item.id,
        });
        notification.onclick = () => {
          window.focus();
          if (item.href) window.location.hash = item.href;
          notification.close();
        };
      });
      dispatch({ type: 'RECORD_REMINDER_DELIVERY', ids: claimed.ids, deliveredAt: now.toISOString() });
    }).catch(() => { /* A failed claim must not bypass the server's cap. */ });
  }, [dispatch, now, reminders, state.reminders]);

  const enableBrowserNotifications = async () => {
    if (typeof Notification === 'undefined') {
      toast({ tone: 'warning', title: 'Trình duyệt này không hỗ trợ thông báo.' });
      return;
    }
    const permission = await Notification.requestPermission();
    dispatch({ type: 'UPDATE_REMINDER_PREFERENCES', patch: { browserEnabled: permission === 'granted' } });
    toast({
      tone: permission === 'granted' ? 'success' : 'warning',
      title: permission === 'granted' ? 'Đã bật nhắc việc trên trình duyệt' : 'Chưa được cấp quyền thông báo',
      description: permission === 'granted' ? 'PaceWise giới hạn tối đa 3 thông báo chủ động mỗi ngày.' : 'Bạn vẫn xem được mọi nhắc việc trong PaceWise.',
    });
  };

  if (compact) {
    return (
      <details className="group relative">
        <summary
          className="relative flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded-xl text-slate-600 marker:hidden hover:bg-primary-light hover:text-primary-ink"
          aria-label={`Nhắc việc${unreadCount ? `, ${unreadCount} chưa đọc` : ''}`}
          title="Nhắc việc"
        >
          <Icon name="bell" size={20} />
          {unreadCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-warning px-1 text-[10px] font-bold text-warning-ink">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </summary>

        <div className="reminder-popover absolute right-0 top-12 z-50 w-[min(26rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-white shadow-xl">
          <div className="flex items-center gap-2 border-b border-line px-4 py-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-light text-primary-ink"><Icon name="bell" size={17} /></span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold">Nhắc việc</p>
              <p className="truncate text-xs text-muted">{courseInvites[0] ? `Mời tham gia ${courseInvites[0].code}` : active[0]?.title ?? upcoming[0]?.title ?? 'Không có cảnh báo mới'}</p>
            </div>
            {unread.length > 0 && (
              <button type="button" className="text-xs font-semibold text-primary-ink hover:underline" onClick={() => dispatch({ type: 'MARK_REMINDERS_READ', ids: unread.map((item) => item.id) })}>
                Đã đọc
              </button>
            )}
          </div>

          <div className="auto-hide-scrollbar max-h-[60vh] overflow-y-auto p-3">
            {courseInvites.length === 0 && visible.length === 0 ? (
              <p className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-muted">Kế hoạch đang ổn. PaceWise sẽ báo khi có việc cần xử lý.</p>
            ) : (
              <ul className="space-y-2">
                {invitationCards}
                {visible.slice(0, 5).map((item) => (
                  <li key={item.id} className="rounded-xl border border-line px-3 py-3">
                    <div className="flex items-center gap-2">
                      <Badge tone={tone(item)}>{item.urgency === 'critical' ? 'Khẩn' : item.urgency === 'urgent' ? 'Cần chú ý' : 'Sắp tới'}</Badge>
                      <span className="caption ml-auto">{formatTime(item.scheduledAt)}</span>
                    </div>
                    <p className="mt-1.5 text-sm font-semibold">{item.title}</p>
                    <p className="mt-0.5 text-xs text-muted">{item.message}</p>
                    {item.href && (
                      <Link to={item.href} onClick={event => {
                        dispatch({ type: 'MARK_REMINDERS_READ', ids: [item.id] });
                        const popup = event.currentTarget.closest('details');
                        if (popup) popup.open = false;
                      }} className="mt-2 inline-flex text-xs font-semibold text-primary-ink hover:underline">
                        {item.kind === 'missed_block' || item.kind === 'lms_change' || item.kind === 'deadline_2h' ? 'Xem cập nhật lịch' : 'Xem chi tiết'}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {!state.reminders.preferences.browserEnabled && (
            <div className="border-t border-line p-3">
              <Button block size="sm" variant="secondary" icon="bell" onClick={() => void enableBrowserNotifications()}>Bật thông báo trình duyệt</Button>
            </div>
          )}
        </div>
      </details>
    );
  }

  return (
    <div className="px-4 pt-4 sm:px-6 lg:px-10">
      <details className="group rounded-2xl border border-line bg-white shadow-card">
        <summary className="flex min-h-[56px] cursor-pointer list-none items-center gap-3 px-4 py-3 marker:hidden">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary-light text-primary-ink">
            <Icon name="bell" size={19} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2 font-semibold">
              Nhắc việc
              {unreadCount > 0 && <Badge tone="warning">{unreadCount} mới</Badge>}
            </span>
            <span className="caption block truncate">
              {courseInvites[0] ? `Lời mời: ${courseInvites[0].code} · ${courseInvites[0].name}` : active[0]?.title ?? upcoming[0] ? `Tiếp theo: ${(active[0] ?? upcoming[0]).title}` : 'Không có cảnh báo cần xử lý trong 24 giờ tới'}
            </span>
          </span>
          <Icon name="chevronDown" size={18} className="transition-transform group-open:rotate-180" />
        </summary>

        <div className="border-t border-line px-4 pb-4 pt-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="caption">Nhắc theo Do, deadline và Reflect · tối đa {state.reminders.preferences.dailyCap} thông báo/ngày</p>
            <div className="flex flex-wrap gap-2">
              {!state.reminders.preferences.browserEnabled && (
                <Button size="sm" variant="secondary" icon="bell" onClick={() => void enableBrowserNotifications()}>
                  Bật thông báo
                </Button>
              )}
              {unread.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => dispatch({ type: 'MARK_REMINDERS_READ', ids: unread.map((item) => item.id) })}
                >
                  Đánh dấu đã đọc
                </Button>
              )}
            </div>
          </div>

          {courseInvites.length === 0 && visible.length === 0 ? (
            <p className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-muted">Kế hoạch đang ổn. PaceWise sẽ nhắc khi có ca học, deadline hoặc thay đổi lịch cần chú ý.</p>
          ) : (
            <ul className="space-y-2">
              {invitationCards}
              {visible.slice(0, 5).map((item) => (
                <li key={item.id} className="flex flex-col gap-2 rounded-xl border border-line px-4 py-3 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={tone(item)}>{item.urgency === 'critical' ? 'Khẩn' : item.urgency === 'urgent' ? 'Cần chú ý' : 'Sắp tới'}</Badge>
                      <span className="caption">{formatTime(item.scheduledAt)}</span>
                    </div>
                    <p className="mt-1 font-semibold">{item.title}</p>
                    <p className="mt-0.5 text-sm text-muted">{item.message}</p>
                  </div>
                  {item.href && (
                    <Link
                      to={item.href}
                      onClick={() => dispatch({ type: 'MARK_REMINDERS_READ', ids: [item.id] })}
                      className="inline-flex min-h-[40px] shrink-0 items-center justify-center rounded-xl px-3 text-sm font-semibold text-primary-ink hover:bg-primary-light"
                    >
                      {item.kind === 'missed_block' || item.kind === 'lms_change' || item.kind === 'deadline_2h' ? 'Xem cập nhật lịch' : 'Xem chi tiết'}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </div>
  );
}
