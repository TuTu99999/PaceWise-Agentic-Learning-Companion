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
  useEffect(() => {
    void preloadInstructorRoutes().catch(() => { /* Navigation can retry a failed chunk download. */ });
  }, []);
  const pending = state.reviewQueue.filter((r) => r.status === 'pending' || r.status === 'in_review').length;
  const toReview = state.assessments.filter((a) => a.status === 'review').length;
  const items: NavItem[] = [
    { to: '/instructor', label: 'Tổng quan lớp', icon: 'chart', end: true, primary: true },
    { to: '/instructor/schedule', label: 'Lịch dạy', icon: 'calendar', primary: true },
    { to: '/instructor/courses', label: 'Môn học', icon: 'book', primary: true },
    { to: '/instructor/assessment', label: 'Thiết kế kiểm chứng', icon: 'clipboard', badge: toReview },
    { to: '/instructor/review', label: 'Hàng chờ duyệt', icon: 'inbox', badge: pending, primary: true },
    { to: '/instructor/profile', label: 'Thông tin giảng viên', icon: 'users' },
  ];
  return <InstructorDataProvider><AppShell items={items} roleLabel="Giảng viên" roleTone="accent" iconOnly banner={
    pagePath !== '/instructor/schedule' && pagePath !== '/instructor/profile' && pagePath !== '/instructor/courses'
      ? <CourseSwitcher />
      : undefined
  } /></InstructorDataProvider>;
}
