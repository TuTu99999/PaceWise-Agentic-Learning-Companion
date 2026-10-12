import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { PACEWISE_LANGUAGE_STORAGE_KEY } from '../utils/uiPreferences';

export type Locale = 'vi' | 'en';

const EN: Record<string, string> = {
  'Đăng nhập': 'Sign in',
  'Đăng xuất': 'Sign out',
  'Đăng xuất PaceWise': 'Sign out of PaceWise',
  'Cài đặt': 'Settings',
  'Sinh viên': 'Student',
  'Giảng viên': 'Instructor',
  'Tổng quan': 'Overview',
  'Tổng quan lớp': 'Class overview',
  'Lịch dạy': 'Teaching schedule',
  'Môn học': 'Courses',
  'Thiết kế kiểm chứng': 'Assessment design',
  'Hàng chờ duyệt': 'Review queue',
  'Thông tin giảng viên': 'Instructor profile',
  'Nhiệm vụ học tập': 'Learning tasks',
  'Nhiệm vụ & trọng số': 'Tasks & grading weights',
  'Phản tư học tập': 'Learning reflection',
  'Phục hồi kế hoạch': 'Replan',
  'Bản thay đổi': 'Plan changes',
  'Tiến độ': 'Progress',
  'Kiểm tra nhanh': 'Quick check',
  'Học tập & Hỏi đáp': 'Learning & Q&A',
  'Phiên học': 'Study session',
  'Nhiệm vụ': 'Task',
  'Tham gia môn': 'Join course',
  'Không tìm thấy trang': 'Page not found',
  'Không có quyền': 'Access denied',
  'Sửa câu hỏi': 'Edit question',
  'Quay lại LMS': 'Back to LMS',
  'Thêm': 'More',
  'Bỏ qua tới nội dung chính': 'Skip to main content',
  'Điều hướng chính': 'Main navigation',
  'Giao diện': 'Appearance',
  'Chuyển giao diện sáng / tối': 'Toggle light / dark theme',
  'Đang mở trang…': 'Opening page…',
  'Đang kiểm tra phiên đăng nhập…': 'Checking your session…',
  'Lập kế hoạch học tập nhẹ nhàng hơn.': 'Make study planning feel lighter.',
  'Biết việc cần làm tiếp theo, hiểu vì sao — và luôn là người quyết định cuối cùng.': 'Know what to do next, understand why, and remain the final decision-maker.',
  'Xác nhận đề xuất trước khi áp dụng vào lịch': 'Review suggestions before applying them to your calendar',
  'Hỏi đáp dựa trên học liệu được phép truy cập': 'Get answers grounded in authorized course materials',
  'Theo dõi tiến độ và điều chỉnh kế hoạch': 'Track progress and adjust your plan',
  'Hệ thống tự nhận vai trò từ tài khoản của bạn.': 'Your role is detected from your account.',
  'Mật khẩu': 'Password',
  'Nhập email để đăng nhập.': 'Enter your email to sign in.',
  'Email chưa đúng định dạng.': 'Enter a valid email address.',
  'Nhập mật khẩu.': 'Enter your password.',
  'Chưa thể đăng nhập. Vui lòng thử lại.': 'Unable to sign in. Please try again.',
  'hoặc': 'or',
  'Tiếp tục với Google': 'Continue with Google',
  'Chọn tài khoản Google': 'Choose a Google account',
  'Dùng cho cả đăng nhập và tạo tài khoản sinh viên mới. PaceWise không yêu cầu mật khẩu Google.': 'Use this to sign in or create a new student account. PaceWise never asks for your Google password.',
  'Nếu Gmail đã liên kết với PaceWise, bạn sẽ được đăng nhập. Nếu chưa, PaceWise sẽ tạo tài khoản sinh viên sau khi Google xác minh.': 'If your Gmail is linked to PaceWise, you will be signed in. Otherwise, PaceWise creates a student account after Google verifies you.',
  'Đăng nhập Google chỉ xác minh danh tính. Sau khi vào PaceWise, bạn có thể cấp riêng quyền Google Calendar trong Cài đặt.': 'Google sign-in only verifies your identity. You can grant Google Calendar access separately in Settings.',
  'Dùng email và mật khẩu?': 'Use email and password?',
  'Quay lại đăng nhập': 'Back to sign in',
  'Thông tin chuyên môn, liên hệ và tài khoản PaceWise của bạn.': 'Your professional, contact, and PaceWise account information.',
  'Họ tên': 'Full name',
  'Email đăng nhập': 'Sign-in email',
  'Chức danh': 'Title',
  'Khoa / bộ môn': 'Faculty / department',
  'Văn phòng': 'Office',
  'Liên hệ / website (HTTPS)': 'Contact / website (HTTPS)',
  'Giờ tư vấn / cách đặt lịch': 'Office hours / booking instructions',
  'Giới thiệu chuyên môn': 'Professional bio',
  'Lưu thông tin': 'Save profile',
  'Đã lưu thông tin giảng viên.': 'Instructor profile saved.',
  'Tải lại hồ sơ': 'Reload profile',
  'Đang tải hồ sơ…': 'Loading profile…',
  'Tài khoản, kết nối lịch và đồng bộ dữ liệu học tập.': 'Account, calendar connections, and learning-data synchronization.',
  'Quản lý môn, buổi học, nhiệm vụ và học liệu ngay trong PaceWise.': 'Manage courses, classes, tasks, and materials directly in PaceWise.',
  'Quản lý hoạt động dạy và học ngay trong PaceWise.': 'Manage teaching and learning activity directly in PaceWise.',
  'Các ca hệ thống không đủ tin cậy để tự kết luận. Chỉ hiển thị trích đoạn liên quan tới rubric.': 'Sessions that require human review. Only rubric-relevant excerpts are shown.',
  'Bài tập, quiz tính điểm và kỳ thi. Kiểm chứng mức hiểu trong Do là luồng riêng.': 'Assignments, graded quizzes, and exams. Understanding checks in Do are handled separately.',
  'Duyệt KC, tiêu chí, nguồn và cách tạo biến thể một lần. Câu mẫu làm fallback; không phải duyệt từng câu AI hỏi sinh viên.': 'Review knowledge components, criteria, sources, and variation rules once. Sample questions are fallbacks, not per-question approvals.',
};

function initialLocale(): Locale {
  try { return window.localStorage.getItem(PACEWISE_LANGUAGE_STORAGE_KEY) === 'en' ? 'en' : 'vi'; }
  catch { return 'vi'; }
}

interface LocaleValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLocale: () => void;
  t: (vietnamese: string, english?: string) => string;
}

const LocaleContext = createContext<LocaleValue>({
  locale: 'vi',
  setLocale: () => undefined,
  toggleLocale: () => undefined,
  t: (vietnamese) => vietnamese,
});

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, updateLocale] = useState<Locale>(initialLocale);
  const setLocale = useCallback((next: Locale) => {
    updateLocale(next);
    try { window.localStorage.setItem(PACEWISE_LANGUAGE_STORAGE_KEY, next); } catch { /* Preference remains in memory. */ }
  }, []);
  useEffect(() => {
    document.documentElement.lang = locale;
    const sync = (event: StorageEvent) => {
      if (event.key === PACEWISE_LANGUAGE_STORAGE_KEY) updateLocale(event.newValue === 'en' ? 'en' : 'vi');
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, [locale]);
  const t = useCallback((vietnamese: string, english?: string) => locale === 'en' ? english ?? EN[vietnamese] ?? vietnamese : vietnamese, [locale]);
  const value = useMemo(() => ({ locale, setLocale, toggleLocale: () => setLocale(locale === 'vi' ? 'en' : 'vi'), t }), [locale, setLocale, t]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  return useContext(LocaleContext);
}

