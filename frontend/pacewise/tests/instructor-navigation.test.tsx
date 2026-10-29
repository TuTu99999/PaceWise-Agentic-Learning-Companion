import { render, screen } from '@testing-library/react';
import { MemoryRouter, Outlet } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { NavItem } from '../src/layouts/AppShell';
import type { ReactNode } from 'react';
import { AppRoutes } from '../src/routes/AppRoutes';

vi.mock('../src/store/AppStore', () => ({
  useAppStore: () => ({
    dispatch: vi.fn(),
    state: {
      authReady: true,
      user: { role: 'instructor' },
      reviewQueue: [{ status: 'pending' }],
      assessments: [{ status: 'review' }],
    },
  }),
}));

vi.mock('../src/components/domain/CourseSwitcher', () => ({
  CourseSwitcher: ({ notifyOnSuccess }: { notifyOnSuccess: boolean }) => (
    <span data-testid="course-switcher" data-notify-on-success={String(notifyOnSuccess)} />
  ),
}));

vi.mock('../src/layouts/AppShell', () => ({
  AppShell: ({ items, banner, iconOnly }: { items: NavItem[]; banner?: ReactNode; iconOnly?: boolean }) => (
    <>
      {banner}
      <nav aria-label="Giảng viên" data-icon-only={String(iconOnly)}>
        {items.map((item) => <a key={item.to} href={item.to}>{item.label}</a>)}
      </nav>
      <Outlet />
    </>
  ),
}));

vi.mock('../src/routes/instructorRouteLoaders', () => ({
  preloadInstructorRoutes: vi.fn().mockResolvedValue([]),
  instructorRouteLoaders: {
    overview: async () => ({ InstructorOverviewPage: () => <h1>Tổng quan lớp</h1> }),
    schedule: async () => ({ InstructorSchedulePage: () => <h1>Lịch dạy</h1> }),
    courses: async () => ({ InstructorCoursesPage: () => <h1>Môn học</h1> }),
    assessment: async () => ({ AssessmentPage: () => <h1>Thiết kế kiểm chứng</h1> }),
    assessmentEdit: vi.fn(),
  },
}));

describe('instructor navigation without duplicate LMS feedback', () => {
  it('redirects old feedback links to overview and removes the feedback tab', async () => {
    render(<MemoryRouter initialEntries={['/instructor/feedback']}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Tổng quan lớp' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Phản hồi & can thiệp' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Hàng chờ duyệt' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Thiết kế kiểm chứng' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Giảng viên' })).toHaveAttribute('data-icon-only', 'true');
  });

  it('redirects the old review queue link to assessment design', async () => {
    render(<MemoryRouter initialEntries={['/instructor/review']}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Thiết kế kiểm chứng' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Hàng chờ duyệt' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Phản hồi & can thiệp' })).not.toBeInTheDocument();
  });

  it.each(['/instructor/materials', '/instructor/course'])('groups old management links in the single course page %s', async (path) => {
    render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Môn học' })).toBeInTheDocument();
    expect(screen.queryByTestId('course-switcher')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Nội dung & học liệu' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Cấu trúc môn học' })).not.toBeInTheDocument();
  });

  it.each(['/instructor/schedule', '/instructor/schedule/'])(
    'does not display the course selection banner on %s',
    async (path) => {
      render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>);
      expect(await screen.findByRole('heading', { name: 'Lịch dạy' })).toBeInTheDocument();
      expect(screen.queryByTestId('course-switcher')).not.toBeInTheDocument();
    },
  );

  it('keeps course selection on the overview page', async () => {
    render(<MemoryRouter initialEntries={['/instructor']}><AppRoutes /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Tổng quan lớp' })).toBeInTheDocument();
    expect(screen.getByTestId('course-switcher')).toBeInTheDocument();
  });

  it('no longer preloads or bundles the removed feedback page', async () => {
    const actual = await vi.importActual<typeof import('../src/routes/instructorRouteLoaders')>(
      '../src/routes/instructorRouteLoaders',
    );
    expect(actual.instructorRouteLoaders).not.toHaveProperty('feedback');
    expect(actual.instructorRouteLoaders).not.toHaveProperty('materials');
    expect(actual.instructorRouteLoaders).not.toHaveProperty('courseSetup');
    expect(actual.instructorRouteLoaders).toHaveProperty('overview');
    expect(actual.instructorRouteLoaders).not.toHaveProperty('reviewQueue');
  });
});
