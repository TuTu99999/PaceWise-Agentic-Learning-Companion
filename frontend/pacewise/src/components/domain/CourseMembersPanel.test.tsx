import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CourseMembersPanel } from './CourseMembersPanel';
import { fetchCourseMembers, inviteCourseStudents, removeCourseStudent, revokeCourseInvitation } from '../../services/api';

vi.mock('../../services/api', () => ({ addKnownCourseStudents: vi.fn(), fetchTeacherRoster: vi.fn(), fetchCourseMembers: vi.fn(), inviteCourseStudents: vi.fn(), removeCourseStudent: vi.fn(), revokeCourseInvitation: vi.fn() }));
const data = { students: [{ id: 2, name: 'Student' }], invitations: [{ id: 'invite1', email: 'new@gmail.com', status: 'pending' as const, expiresAt: '2026-10-18T12:00:00Z' }] };
beforeEach(() => {
  vi.clearAllMocks(); vi.mocked(fetchCourseMembers).mockResolvedValue(data);
  vi.mocked(inviteCourseStudents).mockResolvedValue({ invitations: data.invitations, emailSent: false });
  vi.mocked(removeCourseStudent).mockResolvedValue({}); vi.mocked(revokeCourseInvitation).mockResolvedValue({});
});

describe('course-scoped student management', () => {
  it('supports search and does not remove students until a separate confirmation', async () => {
    render(<CourseMembersPanel courseId="1" />);
    await screen.findByText('Student');
    fireEvent.change(screen.getByRole('textbox', { name: /Tìm sinh viên/ }), { target: { value: 'absent' } });
    expect(screen.queryByText('Student')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: /Tìm sinh viên/ }), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^Gỡ khỏi môn$/ }));
    expect(removeCourseStudent).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Xác nhận gỡ khỏi môn' }));
    await waitFor(() => expect(removeCourseStudent).toHaveBeenCalledExactlyOnceWith('1', 2));
  });
  it('normalizes multiple emails and keeps acceptance inside PaceWise', async () => {
    render(<CourseMembersPanel courseId="1" />); await screen.findByText('Student');
    fireEvent.change(screen.getByLabelText('Mời bằng email'), { target: { value: 'NEW@gmail.com; other@gmail.com\nnew@gmail.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Gửi lời mời' }));
    await waitFor(() => expect(inviteCourseStudents).toHaveBeenCalledWith('1', ['new@gmail.com', 'other@gmail.com']));
    expect(await screen.findByRole('status')).toHaveTextContent('lời mời trong PaceWise');
    expect(screen.queryByRole('button', { name: 'Sao chép link' })).not.toBeInTheDocument();
  });
  it('revokes only the selected invitation', async () => {
    render(<CourseMembersPanel courseId="1" />); await screen.findByText('Student');
    fireEvent.click(screen.getByRole('button', { name: 'Hủy lời mời' }));
    await waitFor(() => expect(revokeCourseInvitation).toHaveBeenCalledExactlyOnceWith('1', 'invite1'));
  });
});
