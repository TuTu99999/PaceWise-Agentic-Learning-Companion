import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TeacherMaterialsPanel } from './TeacherMaterialsPanel';

const { removeResource } = vi.hoisted(() => ({ removeResource: vi.fn().mockResolvedValue(undefined) }));

vi.mock('../../hooks/useTeacherManagement', () => ({ useTeacherManagement: () => ({
  loading: false,
  error: '',
  mutate: vi.fn(),
  removeResource,
  refreshAfterMutation: vi.fn(),
  data: {
    lessons: [], tasks: [], materials: [], weights: { groups: [], version: 'v1' },
    resources: [{ id: 41, title: 'WEB201_Bai_tap_Chuong_01.docx', chapter: 'Chương 1' }],
  },
}) }));
vi.mock('./TeacherAuthoringForms', () => ({ PdfUpload: () => <div>Tải tài liệu</div> }));
vi.mock('./LmsMaterialStatus', () => ({ LmsMaterialStatus: () => null }));

describe('teacher material deletion', () => {
  it('requires confirmation then deletes the selected resource', async () => {
    render(<TeacherMaterialsPanel courseId="1" />);

    fireEvent.click(screen.getByRole('button', { name: 'Xóa' }));
    expect(screen.getByRole('dialog', { name: 'Xóa tài liệu?' })).toBeInTheDocument();
    expect(removeResource).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Xóa tài liệu' }));
    await waitFor(() => expect(removeResource).toHaveBeenCalledWith(41));
  });
});
