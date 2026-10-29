import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InstructorCoursesPage } from './InstructorCoursesPage';
import { fetchManagedCourses, fetchTeacherRoster, manageCourse, getCurrentSession, syncCanvas, teacherScheduleAction } from '../../services/api';
import type { ManagedCourse } from '../../types/teacherManagement';
import { clearInstructorPageCache } from '../../services/instructorPageCache';

const { dispatch } = vi.hoisted(() => ({ dispatch: vi.fn() }));
vi.mock('../../services/api', () => ({ fetchManagedCourses: vi.fn(), fetchTeacherRoster: vi.fn(), manageCourse: vi.fn(), getCurrentSession: vi.fn(), syncCanvas: vi.fn(), teacherScheduleAction: vi.fn() }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: { user: { id: 'teacher', courseId: '1' } }, dispatch }) }));
vi.mock('../../components/domain/TeacherLessonManager', () => ({ TeacherLessonManager: () => <p>Lesson panel</p> }));
vi.mock('../../components/domain/TeacherMaterialsPanel', () => ({ TeacherMaterialsPanel: () => <p>Material panel</p> }));
vi.mock('../../components/domain/CourseMembersPanel', () => ({ CourseMembersPanel: () => <p>Members panel</p> }));
vi.mock('./InstructorTasksPage', () => ({ InstructorTasksPage: () => <p>Tasks panel</p> }));
vi.mock('../../components/domain/TeacherScheduleTools', () => ({ TeacherScheduleTools: () => <p>Schedule tools</p>, SchedulePreviewDetails: () => <p>Preview details</p> }));
const course: ManagedCourse = { id: 1, code: 'CS101', name: 'Programming', term: 'Demo', archived: false, version: 'v1' };
beforeEach(() => { clearInstructorPageCache(); vi.clearAllMocks(); vi.mocked(fetchManagedCourses).mockResolvedValue([course]); vi.mocked(fetchTeacherRoster).mockResolvedValue([{ id: 2, name: 'Student' }]);
  vi.mocked(syncCanvas).mockResolvedValue({ courses: [], tasks: [], courseData: {}, assessments: [], guidance: [] } as never); vi.mocked(getCurrentSession).mockResolvedValue(null); });
const mount = () => render(<MemoryRouter><InstructorCoursesPage /></MemoryRouter>);

describe('single-web teacher courses', () => {
  it('keeps authoring and course membership inside the course', async () => {
    mount(); await screen.findByText('Lesson panel');
    expect(screen.getAllByRole('tab')).toHaveLength(4);
    fireEvent.click(screen.getByRole('tab', { name: 'Nhiệm vụ & trọng số' })); expect(screen.getByText('Tasks panel')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Học liệu' })); expect(screen.getByText('Material panel')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: 'Sinh viên' })); expect(screen.getByText('Members panel')).toBeInTheDocument();
    expect(manageCourse).not.toHaveBeenCalled();
  });
  it('restores a fresh course list without requesting it again on tab return', async () => {
    const first = mount(); await screen.findByText('Lesson panel'); first.unmount();
    mount(); expect(screen.getByText('Lesson panel')).toBeInTheDocument();
    expect(fetchManagedCourses).toHaveBeenCalledTimes(1);
  });
  it('adds a course with explicitly selected Google students and does not re-login', async () => {
    vi.mocked(manageCourse).mockResolvedValue({ ...course, id: 4 });
    mount(); await screen.findByText('Lesson panel'); fireEvent.click(screen.getByRole('button', { name: 'Thêm môn' }));
    fireEvent.change(await screen.findByRole('textbox', { name: /Mã môn/ }), { target: { value: 'NEW101' } }); fireEvent.change(screen.getByRole('textbox', { name: /Tên môn/ }), { target: { value: 'New course' } });
    fireEvent.click(await screen.findByLabelText('Student')); fireEvent.click(screen.getByRole('button', { name: 'Lưu môn học' }));
    await waitFor(() => expect(manageCourse).toHaveBeenCalledWith('', { code: 'NEW101', name: 'New course', term: 'Demo', student_ids: [2], invite_emails: [] }, 'POST'));
    await waitFor(() => expect(syncCanvas).toHaveBeenCalled()); expect(dispatch).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'LOGIN' }));
  });
  it('soft-deletes only after confirmation and explains that related data is recoverable', async () => {
    vi.mocked(manageCourse).mockResolvedValue({ ...course, archived: true });
    vi.mocked(fetchManagedCourses).mockResolvedValueOnce([course]).mockResolvedValue([{ ...course, archived: true }]);
    mount(); await screen.findByText('Lesson panel'); fireEvent.click(screen.getByRole('button', { name: 'Xóa môn' }));
    expect(manageCourse).not.toHaveBeenCalled();
    expect(screen.getByText(/dữ liệu liên quan sẽ biến mất/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận xóa môn' }));
    await waitFor(() => expect(manageCourse).toHaveBeenCalledWith('/1/lifecycle/archive', { expected_version: 'v1' }));
    await waitFor(() => expect(screen.queryByText('Lesson panel')).not.toBeInTheDocument());
  });
  it('closes the create form after a successful write even when refreshing membership fails', async () => {
    vi.mocked(manageCourse).mockResolvedValue({ ...course, id: 4 });
    vi.mocked(syncCanvas).mockRejectedValueOnce(new Error('Network unavailable'));
    mount(); await screen.findByText('Lesson panel');
    fireEvent.click(screen.getByRole('button', { name: 'Thêm môn' }));
    fireEvent.change(await screen.findByRole('textbox', { name: /Mã môn/ }), { target: { value: 'NEW101' } });
    fireEvent.change(screen.getByRole('textbox', { name: /Tên môn/ }), { target: { value: 'New course' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu môn học' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Thay đổi đã được lưu');
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Lưu môn học' })).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Làm mới dữ liệu' }));
    await waitFor(() => expect(syncCanvas).toHaveBeenCalledTimes(2));
    expect(manageCourse).toHaveBeenCalledTimes(1);
  });
  it('does not display demo seeding controls or call the demo API', async () => {
    mount(); await screen.findByText('Lesson panel');
    expect(screen.queryByText(/Cần dữ liệu để test/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Xem kịch bản demo' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Thêm kịch bản demo đã xem' })).not.toBeInTheDocument();
    expect(teacherScheduleAction).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: 'Học liệu' }));
    expect(screen.queryByText(/Cần dữ liệu để test/)).not.toBeInTheDocument();
  });
});
