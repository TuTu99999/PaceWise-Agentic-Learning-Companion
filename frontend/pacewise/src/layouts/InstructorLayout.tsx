import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAppStore } from '../store/AppStore';
import { CourseSwitcher } from '../components/domain/CourseSwitcher';
import { AppShell, type NavItem } from './AppShell';
import { preloadInstructorRoutes } from '../routes/instructorRouteLoaders';
import { InstructorDataProvider } from '../hooks/useInstructorData';

export function InstructorLayout() {
  const { state } = useAppStore();
  const { pathname } = useLocation();
  const pagePath = pathname.replace(/\/$/, '');
  // Assessment authoring uses a small database-only projection, including on a
  // direct edit-page load. Student answers remain Plan signals, not teacher work.
  const needsInstructorAggregate = pagePath.startsWith('/instructor/assessment');
  useEffect(() => {
    void preloadInstructorRoutes().catch(() => { /* Navigation can retry a failed chunk download. */ });
  }, []);
  const toReview = state.assessments.filter((a) => a.status === 'review').length;
  const items: NavItem[] = [
    { to: '/instructor', label: 'Tổng quan lớp', icon: 'chart', end: true, primary: true },
    { to: '/instructor/schedule', label: 'Lịch dạy', icon: 'calendar', primary: true },
    { to: '/instructor/courses', label: 'Môn học', icon: 'book', primary: true },
    { to: '/instructor/assessment', label: 'Thiết kế kiểm chứng', icon: 'clipboard', badge: toReview },
    { to: '/instructor/profile', label: 'Thông tin giảng viên', icon: 'users' },
  ];
  return <InstructorDataProvider enabled={needsInstructorAggregate}><AppShell items={items} roleLabel="Giảng viên" roleTone="accent" iconOnly banner={
    pagePath !== '/instructor/schedule' && pagePath !== '/instructor/profile' && pagePath !== '/instructor/courses'
      ? <CourseSwitcher />
      : undefined
  } /></InstructorDataProvider>;
}
