(() => {
  const STORAGE_KEY = "canvas_locale";
  const translations = {
    "Log In": "Đăng nhập",
    "Email": "Email",
    "Password": "Mật khẩu",
    "Stay signed in": "Duy trì đăng nhập",
    "Forgot Password?": "Quên mật khẩu?",
    "Open Source LMS": "Hệ thống quản lý học tập mã nguồn mở",
    "Account": "Tài khoản",
    "Dashboard": "Bảng điều khiển",
    "Courses": "Khóa học",
    "Calendar": "Lịch",
    "Inbox": "Hộp thư",
    "History": "Lịch sử",
    "Help": "Trợ giúp",
    "Loading...": "Đang tải...",
    "Close": "Đóng",
    "Notifications": "Thông báo",
    "Profile": "Hồ sơ",
    "Files": "Tệp",
    "Settings": "Cài đặt",
    "Logout": "Đăng xuất",
    "All Courses": "Tất cả khóa học",
    "Search the Canvas Guides": "Tìm kiếm hướng dẫn Canvas",
    "Report a Problem": "Báo cáo sự cố",
    "Ask Your Instructor a Question": "Đặt câu hỏi cho giảng viên",
    "Submit a Feature Idea": "Đề xuất tính năng",
    "Search": "Tìm kiếm",
    "To Do": "Việc cần làm",
    "Recent Feedback": "Phản hồi gần đây",
    "Nothing for now": "Hiện chưa có việc nào",
    "Home": "Trang chủ",
    "Announcements": "Thông báo",
    "Assignments": "Bài tập",
    "Discussions": "Thảo luận",
    "Grades": "Điểm",
    "People": "Mọi người",
    "Pages": "Trang",
    "Syllabus": "Đề cương",
    "Outcomes": "Chuẩn đầu ra",
    "Quizzes": "Bài kiểm tra",
    "Modules": "Học phần",
    "Coming Up": "Sắp tới",
    "Course Status: Published": "Trạng thái khóa học: Đã xuất bản",
    "Import Existing Content": "Nhập nội dung có sẵn",
    "Choose Home Page": "Chọn trang chủ",
    "View Course Stream": "Xem hoạt động khóa học",
    "View Course Calendar": "Xem lịch khóa học",
    "View Course Notifications": "Xem thông báo khóa học",
    "No assignments found.": "Không tìm thấy bài tập.",
    "No content is available.": "Chưa có nội dung.",
    "No files.": "Chưa có tệp.",
    "Submit Assignment": "Nộp bài",
    "Resubmit Assignment": "Nộp lại bài",
    "Edit": "Chỉnh sửa",
    "Delete": "Xóa",
    "Upload": "Tải lên",
    "Published": "Đã xuất bản",
    "Student": "Sinh viên",
    "Teacher": "Giảng viên",
    "Instructor": "Giảng viên",
    "Course": "Khóa học",
    "Term": "Học kỳ",
    "Enrolled as": "Vai trò",
    "Favorite": "Yêu thích",
    "Nickname": "Tên gọi khác",
    "Notification Settings": "Cài đặt thông báo",
    "Choose how often Canvas sends notifications for each activity group.": "Chọn tần suất Canvas gửi thông báo cho từng nhóm hoạt động.",
    "Activity": "Hoạt động",
    "Email frequency": "Tần suất email",
    "Course Activities": "Hoạt động khóa học",
    "Assignments, grades and course content changes": "Thay đổi về bài tập, điểm và nội dung khóa học",
    "New topics, replies and mentions": "Chủ đề, phản hồi và lượt nhắc mới",
    "Conversations": "Hội thoại",
    "Inbox messages and replies": "Tin nhắn và phản hồi trong hộp thư",
    "Scheduling": "Lịch học",
    "Due dates and calendar changes": "Hạn nộp và thay đổi lịch",
    "Notify me right away": "Thông báo ngay",
    "Daily summary": "Tổng hợp hằng ngày",
    "Weekly summary": "Tổng hợp hằng tuần",
    "Notifications off": "Tắt thông báo",
    "Save Settings": "Lưu cài đặt",
    "Profile updated": "Đã cập nhật hồ sơ",
    "Edit Profile": "Chỉnh sửa hồ sơ",
    "Full Name": "Họ và tên",
    "Display Name": "Tên hiển thị",
    "Pronouns": "Đại từ nhân xưng",
    "Biography": "Giới thiệu",
    "No biography has been added.": "Chưa có thông tin giới thiệu.",
    "Ways to Contact": "Thông tin liên hệ",
    "Save Profile": "Lưu hồ sơ",
    "Cancel": "Hủy",
    "My Files": "Tệp của tôi",
    "No personal files.": "Chưa có tệp cá nhân.",
    "File uploaded": "Đã tải tệp lên",
    "File deleted": "Đã xóa tệp",
    "Delete this file?": "Xóa tệp này?",
    "Account Settings": "Cài đặt tài khoản",
    "Your login email is managed by the institution.": "Email đăng nhập do nhà trường quản lý.",
    "Time Zone": "Múi giờ",
    "Language": "Ngôn ngữ",
    "English": "Tiếng Anh",
    "Update Settings": "Cập nhật cài đặt",
    "Change Password": "Đổi mật khẩu",
    "Current Password": "Mật khẩu hiện tại",
    "New Password": "Mật khẩu mới",
    "Confirm New Password": "Xác nhận mật khẩu mới",
    "New passwords do not match.": "Mật khẩu mới không khớp.",
    "Password changed. Other sessions were signed out.": "Đã đổi mật khẩu. Các phiên đăng nhập khác đã được đăng xuất.",
    "Account settings updated": "Đã cập nhật cài đặt tài khoản",
    "Notification settings saved": "Đã lưu cài đặt thông báo",
    "Today": "Hôm nay",
    "+ Event": "+ Sự kiện",
    "All Calendars": "Tất cả lịch",
    "Drag a personal event to another day to reschedule it.": "Kéo sự kiện cá nhân sang ngày khác để đổi lịch.",
    "No details": "Không có mô tả",
    "New Event": "Sự kiện mới",
    "Edit Event": "Chỉnh sửa sự kiện",
    "Title": "Tiêu đề",
    "Date and time": "Ngày và giờ",
    "Details": "Chi tiết",
    "Repeat weekly": "Lặp lại hằng tuần",
    "Does not repeat": "Không lặp lại",
    "Submit": "Xác nhận",
    "Event saved": "Đã lưu sự kiện",
    "Compose a new message": "Soạn tin nhắn mới",
    "Unread": "Chưa đọc",
    "Sent": "Đã gửi",
    "Archived": "Đã lưu trữ",
    "No conversations.": "Chưa có hội thoại.",
    "No conversations selected": "Chưa chọn hội thoại",
    "Reply": "Trả lời",
    "Mark Read": "Đánh dấu đã đọc",
    "Mark Unread": "Đánh dấu chưa đọc",
    "Archive": "Lưu trữ",
    "Move to Inbox": "Chuyển vào hộp thư",
    "Send": "Gửi",
    "Compose Message": "Soạn tin nhắn",
    "Subject": "Chủ đề",
    "Message": "Nội dung",
    "Message sent": "Đã gửi tin nhắn",
    "Recent History": "Lịch sử gần đây",
    "No recent page views.": "Chưa có trang xem gần đây.",
    "Something went wrong": "Đã xảy ra lỗi",
    "Retry": "Thử lại",
  };

  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  let locale = localStorage.getItem(STORAGE_KEY) === "vi" ? "vi" : "en";

  function translateDynamic(value, targetLocale) {
    if (targetLocale !== "vi") return value;
    const rules = [
      [/^Due (.+)$/u, "Hạn nộp $1"],
      [/^(.+) of (.+) used$/u, "$1 đã dùng trên $2"],
      [/^Account: (.+)$/u, "Tài khoản: $1"],
      [/^Welcome to (.+)\.$/u, "Chào mừng đến với $1."],
      [/^Out of (.+)$/u, "Tối đa $1"],
    ];
    for (const [pattern, replacement] of rules) {
      if (pattern.test(value)) return value.replace(pattern, replacement);
    }
    return value;
  }

  function translateValue(value, targetLocale = locale) {
    if (!value) return value;
    if (targetLocale !== "vi") return value;
    return translations[value] || translateDynamic(value, targetLocale);
  }

  function translateTextNode(node, targetLocale) {
    if (node.parentElement?.closest("[data-no-i18n], script, style")) return;
    const raw = node.nodeValue;
    const trimmed = raw.trim();
    if (!trimmed) return;
    if (!originalText.has(node)) originalText.set(node, trimmed);
    const original = originalText.get(node);
    const translated = translateValue(original, targetLocale);
    const leading = raw.match(/^\s*/u)?.[0] || "";
    const trailing = raw.match(/\s*$/u)?.[0] || "";
    const nextValue = `${leading}${translated}${trailing}`;
    if (node.nodeValue !== nextValue) node.nodeValue = nextValue;
  }

  function translateElement(element, targetLocale) {
    if (!(element instanceof Element) || element.closest("[data-no-i18n]")) return;
    const savedAttributes = originalAttributes.get(element) || {};
    for (const attribute of ["placeholder", "title", "aria-label"]) {
      if (element.hasAttribute(attribute)) {
        if (!(attribute in savedAttributes)) savedAttributes[attribute] = element.getAttribute(attribute);
        element.setAttribute(attribute, translateValue(savedAttributes[attribute], targetLocale));
      }
    }
    originalAttributes.set(element, savedAttributes);
    for (const child of element.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) translateTextNode(child, targetLocale);
      else if (child.nodeType === Node.ELEMENT_NODE) translateElement(child, targetLocale);
    }
  }

  function translate(root = document.body, targetLocale = locale) {
    if (root.nodeType === Node.TEXT_NODE) translateTextNode(root, targetLocale);
    else translateElement(root, targetLocale);
    document.documentElement.lang = targetLocale === "vi" ? "vi" : "en";
  }

  function setLocale(nextLocale) {
    const normalized = nextLocale === "vi" ? "vi" : "en";
    locale = normalized;
    localStorage.setItem(STORAGE_KEY, normalized);
    translate(document.body, normalized);
    window.dispatchEvent(new CustomEvent("canvas:locale-changed", { detail: { locale: normalized } }));
  }

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) translate(node, locale);
    }
  });

  window.CanvasI18n = {
    getLocale: () => locale,
    setLocale,
    t: (value) => translateValue(value, locale),
    translate: (root) => translate(root, locale),
  };

  translate(document.body, locale);
  observer.observe(document.body, { childList: true, subtree: true });
})();
