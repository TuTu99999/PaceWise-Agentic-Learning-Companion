import { useLocation } from 'react-router-dom';
import { CourseSwitcher } from '../components/domain/CourseSwitcher';
import { ReminderCenter } from '../components/domain/ReminderCenter';
import { AppShell, type NavItem } from './AppShell';
import { useAppStore } from '../store/AppStore';
import { useActiveStudySessionHeartbeat } from '../hooks/useActiveStudySessionHeartbeat';

function StudentUtilityHeader({ showCourse }: { showCourse: boolean }) {
  return (
    <div className="sticky top-16 z-40 flex h-14 items-center justify-end gap-1 border-b border-line bg-white/95 px-4 backdrop-blur lg:top-0 lg:px-5" aria-label="Công cụ nhanh">
      {showCourse && <CourseSwitcher compact />}
      <ReminderCenter compact />
    </div>
  );
}

export function StudentLayout() {
  const location = useLocation();
  const { state } = useAppStore();
  const isPlan = location.pathname.startsWith('/plan');
  const onSessionRoute = location.pathname.includes('/session');
  useActiveStudySessionHeartbeat(onSessionRoute);
  const active = state.activeSession;
  const doHref = active?.taskId && active.blockId
    ? `/study/${encodeURIComponent(active.taskId)}/session?blockId=${encodeURIComponent(active.blockId)}`
    : '/learn';
  const items: NavItem[] = [
    { to: '/plan', label: 'Plan', icon: 'calendar', primary: true },
    { to: doHref, label: 'Do', icon: 'play', primary: true },
    { to: '/reflect', label: 'Reflect tuần', icon: 'history', primary: true },
    { to: '/settings', label: 'Cài đặt', icon: 'settings' },
  ];
  return (
    <AppShell
      items={items}
      roleLabel="Sinh viên"
      roleTone="primary"
      iconOnly
      banner={isPlan ? undefined : <StudentUtilityHeader showCourse={location.pathname.startsWith('/learn')} />}
    />
  );
}
