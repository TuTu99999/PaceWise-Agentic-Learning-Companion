import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InstructorProfilePage } from './InstructorProfilePage';
import { fetchTeacherProfile, saveTeacherProfile } from '../../services/api';
import type { TeacherProfileData } from '../../types/teacherManagement';

const { cache } = vi.hoisted(() => ({ cache: { current: null as { data: TeacherProfileData; savedAt: number } | null } }));
vi.mock('../../services/api', () => ({ fetchTeacherProfile: vi.fn(), saveTeacherProfile: vi.fn() }));
vi.mock('../../hooks/useInstructorData', () => ({ useInstructorData: () => ({ profileCache: cache }) }));
vi.mock('../../store/AppStore', () => ({ useAppStore: () => ({ state: { user: { id: 'teacher-qa' }, courses: [{ code: 'TRR' }] } }) }));
const profile: TeacherProfileData = { name: 'Teacher QA', email: 'teacher@example.invalid', version: 'v1',
  details: { title: '', department: '', office: '', office_hours: '', bio: '', contact_url: '' } };

beforeEach(() => { vi.clearAllMocks(); cache.current = null; vi.mocked(fetchTeacherProfile).mockResolvedValue(profile); });

describe('instructor profile', () => {
  it('loads editable details but keeps LMS identity read-only', async () => {
    render(<InstructorProfilePage />);
    expect(screen.getByRole('status')).toHaveTextContent('Đang tải hồ sơ');
    expect(await screen.findByLabelText('Họ tên (LMS)')).toHaveValue('Teacher QA');
    expect(screen.getByLabelText('Họ tên (LMS)')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('Email đăng nhập (LMS)')).toHaveAttribute('readonly');
    expect(cache.current?.data).toEqual(profile);
  });

  it('uses a fresh cache when returning to the tab', () => {
    cache.current = { data: profile, savedAt: Date.now() };
    render(<InstructorProfilePage />);
    expect(screen.getByLabelText('Họ tên (LMS)')).toHaveValue(profile.name);
    expect(fetchTeacherProfile).not.toHaveBeenCalled();
  });

  it('retries an unavailable profile and recovers without a full page reload', async () => {
    vi.mocked(fetchTeacherProfile).mockRejectedValueOnce(new Error('Dịch vụ tạm thời chưa sẵn sàng.'));
    render(<InstructorProfilePage />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Dịch vụ tạm thời');
    fireEvent.click(screen.getByRole('button', { name: 'Tải lại hồ sơ' }));
    expect(await screen.findByLabelText('Chức danh')).toBeEnabled();
    expect(fetchTeacherProfile).toHaveBeenCalledTimes(2);
  });

  it('reloads the server version after a save conflict instead of keeping a stale dirty draft', async () => {
    const latest = { ...profile, version: 'v2', details: { ...profile.details, title: 'Server title' } };
    vi.mocked(fetchTeacherProfile).mockResolvedValueOnce(profile).mockResolvedValueOnce(latest);
    vi.mocked(saveTeacherProfile).mockRejectedValueOnce(new Error('Dữ liệu đã thay đổi.'))
      .mockResolvedValueOnce({ ...latest, version: 'v3', details: { ...latest.details, title: 'Updated title' } });
    render(<InstructorProfilePage />);
    fireEvent.change(await screen.findByLabelText('Chức danh'), { target: { value: 'Unsaved title' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu thông tin' }));
    await screen.findByRole('alert');
    fireEvent.click(screen.getByRole('button', { name: 'Tải lại hồ sơ' }));
    await waitFor(() => expect(screen.getByLabelText('Chức danh')).toHaveValue('Server title'));
    fireEvent.change(screen.getByLabelText('Chức danh'), { target: { value: 'Updated title' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu thông tin' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Đã lưu');
    expect(saveTeacherProfile).toHaveBeenLastCalledWith({ ...latest.details, title: 'Updated title', expected_version: 'v2' });
    expect(cache.current?.data.version).toBe('v3');
  });

  it('locks inputs during save and does not restore private cache after leaving the page', async () => {
    let resolve!: (value: TeacherProfileData) => void;
    vi.mocked(saveTeacherProfile).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const { unmount } = render(<InstructorProfilePage />);
    fireEvent.change(await screen.findByLabelText('Chức danh'), { target: { value: 'Saving' } });
    fireEvent.click(screen.getByRole('button', { name: 'Lưu thông tin' }));
    expect(screen.getByLabelText('Chức danh')).toBeDisabled();
    expect(screen.getByRole('button', { name: /Lưu thông tin/ })).toBeDisabled();
    unmount(); cache.current = null;
    await act(async () => resolve(profile));
    expect(cache.current).toBeNull();
  });
});
