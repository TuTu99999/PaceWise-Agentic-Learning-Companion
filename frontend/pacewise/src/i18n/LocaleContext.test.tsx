import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createPortal } from 'react-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import { LanguageToggle } from '../components/domain/LanguageToggle';
import { LocaleProvider, useLocale } from './LocaleContext';

function Probe() {
  const { t } = useLocale();
  return <p>{t('Đăng nhập')}</p>;
}

function RawInterfaceProbe() {
  return (
    <section>
      <h2>Phản tư cả tuần</h2>
      <button title="Tiếp tục học">Tiếp tục học</button>
      <input aria-label="Tìm kiếm" placeholder="Tìm kiếm" />
      <p>Hệ cơ sở dữ liệu</p>
      <p>Tuần này · Tuần 3 · 12/10–18/10: Chưa có deadline đến hạn</p>
      <p>4 môn mới · 20 buổi mới · 7 nhiệm vụ · 2 bộ trọng số · 9 học liệu · hủy 1 buổi tương lai</p>
      <p>Tìm sinh viên (28)</p>
      <p>Chưa xong; cần thêm 35 phút.</p>
      <p>Có phần lịch hợp lệ để xác nhận</p>
      <p>1 giờ 10 phút</p>
      <p>Thứ Năm 15/10</p>
      <p>Kế hoạch đang áp dụng</p>
      <p>4 ca tự học · 4 giờ</p>
      <p>3 ca tự học</p>
      <p>T7 17/10</p>
      <p>CN 18/10</p>
      <p>Kéo hoạt động vào lịch hoặc bấm để nhập giờ.</p>
      <p>Ăn uống</p>
      <p>3 mốc · tất cả môn · 05/10–11/10</p>
      <p>3 hoạt động gần nhất</p>
      <p>1. Tuần này việc gì đã hoàn thành hoặc chưa hoàn thành?</p>
      <p>0/500 ký tự</p>
      <p>Kế hoạch và tiến độ được lưu trên máy chủ để dùng tiếp ở thiết bị khác.</p>
      <p>Lần lưu gần nhất: 17:49:44 17/10/2026</p>
      <p>Nhập lịch bận gần nhất: 11:13:49 15/10/2026</p>
      <p>21 ca tự học trong kế hoạch hiện tại · không cần kết nối Google.</p>
      <p>Nhập chính xác đến từng phút hoặc kéo ca trực tiếp trên lịch.</p>
      <p>Thời lượng chính xác: 30 phút.</p>
      <p>Xác nhận hoàn tất phiên học</p>
      <p>Đồng hồ mới chạy 00:00:01. Chọn cách ghi nhận đúng với phiên này.</p>
      <p>Bản phản tư do AI đề xuất — chưa lưu</p>
      <p>Có thay đổi chưa lưu</p>
      <p>Lọc và hiển thị lịch</p>
      <p>Hiện lịch cá nhân và giờ tự học ưu tiên</p>
      <p>Các mục ẩn vẫn được kiểm tra xung đột khi xếp lịch.</p>
      <p>Ca học đã bị lỡ: Bài tập Chương 2</p>
      <p>Tiến độ thiếu 90 phút so với kế hoạch. Plan sẽ tính bản cập nhật lịch trước deadline.</p>
      <p>Xem cập nhật lịch</p>
      <p>Bật thông báo trình duyệt</p>
      <p>Đã đọc</p>
      <p>Giờ sinh hoạt</p>
      <p>PaceWise chỉ học theo nhịp của bạn sau khi bạn xác nhận, kể cả khi bạn thường học khuya.</p>
      <p>Thường thức dậy</p>
      <p>Thường đi ngủ</p>
      <p>Nhập chính xác từng phút: 23:10 hoặc 23h10. 00:00 là 12 giờ đêm.</p>
      <p>Khung giờ thích tự học</p>
      <p>Có thể chọn nhiều khung. “Khuya” chỉ được ưu tiên khi bạn chủ động chọn.</p>
      <p>Khuya</p>
      <p>Giờ ngủ là ràng buộc cứng. Khung ưa thích chỉ thay đổi thứ tự xếp lịch, không cho phép vượt deadline hoặc chèn vào lịch LMS.</p>
      <button>Lưu giờ sinh hoạt</button>
      <p data-i18n-skip="true">Kế hoạch đang áp dụng</p>
    </section>
  );
}

function RawInstructorProbe() {
  return (
    <section>
      <p>Học kỳ 1 · 2026–2027</p>
      <button>Thêm buổi học / lặp tuần</button>
      <button>Sửa buổi</button>
      <button>Hủy buổi</button>
      <p>Mỗi cảnh báo tương ứng một sinh viên thuộc môn đang chọn.</p>
      <p> · 1 nhiệm vụ trễ hạn</p>
      <p> · 2 deadline trong 72 giờ</p>
      <p>Rà soát deadline · DB201</p>
      <p>10 sinh viên đang có ít nhất một nhiệm vụ quá hạn.</p>
      <p>Tổng hợp lớp đang chọn</p>
      <p>Mọi số liệu bên dưới chỉ thuộc môn học đang được chọn phía trên.</p>
      <p>Hệ cơ sở dữ liệu</p>
    </section>
  );
}

function PortalProbe() {
  return createPortal(
    <section role="dialog" aria-label="Nhập Excel">
      <h2>Nhập và dọn lịch</h2>
      <p>Chưa thể xác nhận: cần sửa 5 lỗi.</p>
      <button>Đóng</button>
    </section>,
    document.body,
  );
}

describe('shared PaceWise locale', () => {
  beforeEach(() => window.localStorage.clear());

  it('switches to English, updates the document language, and persists the landing-compatible key', () => {
    render(<LocaleProvider><LanguageToggle /><Probe /></LocaleProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Tiếng Anh' }));
    expect(screen.getByText('Sign in')).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('en');
    expect(window.localStorage.getItem('pacewise-language')).toBe('en');
  });

  it('restores English selected on the landing page', () => {
    window.localStorage.setItem('pacewise-language', 'en');
    render(<LocaleProvider><Probe /></LocaleProvider>);
    expect(screen.getByText('Sign in')).toBeInTheDocument();
  });

  it('localizes fixed interface copy while preserving course data, then restores Vietnamese', async () => {
    render(<LocaleProvider><LanguageToggle /><RawInterfaceProbe /></LocaleProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Tiếng Anh' }));
    await waitFor(() => expect(screen.getByText('Weekly reflection')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Continue studying' })).toHaveAttribute('title', 'Continue studying');
    expect(screen.getByRole('textbox', { name: 'Search' })).toHaveAttribute('placeholder', 'Search');
    expect(screen.getByText('Hệ cơ sở dữ liệu')).toBeInTheDocument();
    expect(screen.getByText('This week · Week 3 · 12/10–18/10: No due deadlines')).toBeInTheDocument();
    expect(screen.getByText('4 new courses · 20 new sessions · 7 tasks · 2 weight sets · 9 materials · cancel 1 future session')).toBeInTheDocument();
    expect(screen.getByText('Search students (28)')).toBeInTheDocument();
    expect(screen.getByText('Not finished; 35 more minutes needed.')).toBeInTheDocument();
    expect(screen.getByText('Valid schedule available for confirmation')).toBeInTheDocument();
    expect(screen.getByText('1 hour 10 minutes')).toBeInTheDocument();
    expect(screen.getByText('Thursday 15/10')).toBeInTheDocument();
    expect(screen.getByText('Active plan')).toBeInTheDocument();
    expect(screen.getByText('4 study sessions · 4 hours')).toBeInTheDocument();
    expect(screen.getByText('3 study sessions')).toBeInTheDocument();
    expect(screen.getByText('Sat 17/10')).toBeInTheDocument();
    expect(screen.getByText('Sun 18/10')).toBeInTheDocument();
    expect(screen.getByText('Drag an activity onto the calendar or click to enter a time.')).toBeInTheDocument();
    expect(screen.getByText('Meals')).toBeInTheDocument();
    expect(screen.getByText('3 activities · all courses · 05/10–11/10')).toBeInTheDocument();
    expect(screen.getByText('3 most recent activities')).toBeInTheDocument();
    expect(screen.getByText('1. What did you complete or leave unfinished this week?')).toBeInTheDocument();
    expect(screen.getByText('0/500 characters')).toBeInTheDocument();
    expect(screen.getByText('Your plan and progress are saved securely so you can continue on another device.')).toBeInTheDocument();
    expect(screen.getByText('Last saved: 17:49:44 17/10/2026')).toBeInTheDocument();
    expect(screen.getByText('Busy times last imported: 11:13:49 15/10/2026')).toBeInTheDocument();
    expect(screen.getByText('21 study sessions in the current plan · no Google connection required.')).toBeInTheDocument();
    expect(screen.getByText('Enter exact times to the minute or drag the session directly on the calendar.')).toBeInTheDocument();
    expect(screen.getByText('Exact duration: 30 minutes.')).toBeInTheDocument();
    expect(screen.getByText('Confirm study session completion')).toBeInTheDocument();
    expect(screen.getByText('The timer has run for only 00:00:01. Choose how this session should be recorded.')).toBeInTheDocument();
    expect(screen.getByText('AI-proposed reflection — not saved')).toBeInTheDocument();
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    expect(screen.getByText('Filter and display calendar')).toBeInTheDocument();
    expect(screen.getByText('Show personal calendar and preferred study time')).toBeInTheDocument();
    expect(screen.getByText('Hidden items are still checked for scheduling conflicts.')).toBeInTheDocument();
    expect(screen.getByText('Missed study session: Bài tập Chương 2')).toBeInTheDocument();
    expect(screen.getByText('90 minutes behind plan. Plan will calculate a schedule update before the deadline.')).toBeInTheDocument();
    expect(screen.getByText('View schedule update')).toBeInTheDocument();
    expect(screen.getByText('Enable browser notifications')).toBeInTheDocument();
    expect(screen.getByText('Mark all read')).toBeInTheDocument();
    expect(screen.getByText('Daily routine')).toBeInTheDocument();
    expect(screen.getByText('PaceWise follows your routine only after you confirm it, including when you usually study late at night.')).toBeInTheDocument();
    expect(screen.getByText('Usual wake-up time')).toBeInTheDocument();
    expect(screen.getByText('Usual bedtime')).toBeInTheDocument();
    expect(screen.getByText('Enter the exact minute: 23:10 or 23h10. 00:00 is midnight.')).toBeInTheDocument();
    expect(screen.getByText('Preferred study times')).toBeInTheDocument();
    expect(screen.getByText('You may select multiple periods. “Late night” is preferred only when you select it.')).toBeInTheDocument();
    expect(screen.getByText('Late night')).toBeInTheDocument();
    expect(screen.getByText('Sleep is a hard constraint. Preferred periods only affect scheduling priority; they never allow deadlines to be missed or LMS events to be overwritten.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save routine' })).toBeInTheDocument();
    expect(screen.getByText('Kế hoạch đang áp dụng')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Vietnamese' }));
    await waitFor(() => expect(screen.getByText('Phản tư cả tuần')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Tiếp tục học' })).toHaveAttribute('title', 'Tiếp tục học');
    expect(screen.getByText('Hệ cơ sở dữ liệu')).toBeInTheDocument();
    expect(screen.getByText('Tuần này · Tuần 3 · 12/10–18/10: Chưa có deadline đến hạn')).toBeInTheDocument();
    expect(screen.getByText('Tìm sinh viên (28)')).toBeInTheDocument();
  });

  it('localizes instructor modals and tooltips rendered outside the React root', async () => {
    const root = document.createElement('div');
    root.id = 'root';
    document.body.appendChild(root);
    const view = render(<LocaleProvider><LanguageToggle /><PortalProbe /></LocaleProvider>, { container: root });

    fireEvent.click(screen.getByRole('button', { name: 'Tiếng Anh' }));
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Import Excel' })).toBeInTheDocument());
    expect(screen.getByText('Import and clean schedule')).toBeInTheDocument();
    expect(screen.getByText('Cannot confirm yet: fix 5 errors.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument();

    view.unmount();
    root.remove();
  });

  it('localizes instructor course, schedule, alert, and overview copy while preserving course names', async () => {
    render(<LocaleProvider><LanguageToggle /><RawInstructorProbe /></LocaleProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Tiếng Anh' }));
    await waitFor(() => expect(screen.getByText('Semester 1 · 2026–2027')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Add class session / repeat weekly' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit session' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel session' })).toBeInTheDocument();
    expect(screen.getByText('Each alert represents one student in the selected course.')).toBeInTheDocument();
    expect(screen.getByText(/1 overdue task$/)).toBeInTheDocument();
    expect(screen.getByText(/2 deadlines within 72 hours$/)).toBeInTheDocument();
    expect(screen.getByText('Review deadlines · DB201')).toBeInTheDocument();
    expect(screen.getByText('10 students have at least one overdue task.')).toBeInTheDocument();
    expect(screen.getByText('Selected class summary')).toBeInTheDocument();
    expect(screen.getByText('All figures below apply only to the course selected above.')).toBeInTheDocument();
    expect(screen.getByText('Hệ cơ sở dữ liệu')).toBeInTheDocument();
  });
});
