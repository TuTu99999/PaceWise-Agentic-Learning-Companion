(function connectLandingToPaceWise() {
  var APP_LOGIN_URL = '/app#/login';
  var LANGUAGE_KEY = 'pacewise-language';
  var THEME_KEY = 'pacewise-theme';
  var LEGACY_LANDING_THEME_KEY = 'pacewise:landing-theme';
  var root = document.documentElement;
  var theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  try { theme = localStorage.getItem(THEME_KEY) || localStorage.getItem(LEGACY_LANDING_THEME_KEY) || theme; } catch (_) {}
  root.dataset.theme = theme === 'dark' ? 'dark' : 'light';

  var translations = {
    'Đến nội dung chính': 'Skip to main content', 'Cách hoạt động': 'How it works', 'Giảng viên': 'Instructors',
    'Hỏi đáp': 'FAQ', 'Đăng nhập': 'Sign in', 'Đăng ký': 'Sign up', 'Trợ lý tổ chức việc học': 'A study organization assistant',
    'Học có kế hoạch.': 'Study with a plan.', 'Tiến bộ từng phiên.': 'Progress one session at a time.',
    'Từ deadline đến ca tự học phù hợp. PaceWise giúp bạn biết việc cần làm tiếp theo, học với tài liệu đúng môn và điều chỉnh theo tiến độ thực tế.': 'From deadlines to focused study sessions, PaceWise helps you know what to do next, use the right course materials, and adjust to real progress.',
    'Bắt đầu với Google': 'Continue with Google', 'Xem cách hoạt động': 'See how it works',
    'Bạn xem và xác nhận đề xuất trước khi áp dụng vào lịch.': 'You review and confirm every suggestion before it changes your calendar.',
    'Lịch học sinh viên': 'Student study calendar', 'Giao diện PaceWise hiện tại, dùng dữ liệu minh họa.': 'Current PaceWise interface with sample data.',
    'Một vòng học tập, ba bước rõ ràng.': 'One learning loop, three clear steps.', 'Lập kế hoạch': 'Plan',
    'Xếp ca học từ nhiệm vụ, deadline và thời gian rảnh. Xem phần khả thi và cảnh báo phần còn thiếu trước khi xác nhận.': 'Schedule sessions from tasks, deadlines, and availability. Review feasible work and capacity warnings before confirming.',
    'Bắt đầu tự học': 'Do',
    'Mở ca đã xác nhận, dùng học liệu đúng phạm vi và hỏi đáp có trích nguồn khi đủ bằng chứng. AI gợi mở, không làm hộ bài tính điểm.': 'Open a confirmed session, use scoped materials, and get cited answers when evidence is sufficient. AI guides without completing graded work.',
    'Nhìn lại và điều chỉnh': 'Reflect and adjust',
    'Ghi nhận tiến độ, gián đoạn và cảm nhận phiên học. Đề xuất điều chỉnh không tự thay đổi deadline hay tự áp dụng lịch mới.': 'Record progress, interruptions, and session feedback. Suggestions never change deadlines or apply a new schedule automatically.',
    'Dành cho giảng viên': 'For instructors', 'Quản lý môn học.': 'Manage courses.', 'Nắm tiến độ tổng quan.': 'Understand class progress.',
    'Buổi học, nhiệm vụ, trọng số và học liệu được quản lý ngay trong PaceWise. Người thử nghiệm không cần mở thêm một web LMS.': 'Manage classes, tasks, grading weights, and materials directly in PaceWise. Testers do not need a separate LMS website.',
    'Nhập lịch từ Excel, thêm học liệu theo chương.': 'Import schedules from Excel and attach chapter materials.',
    'Xem chỉ số tổng hợp và cảnh báo nguy cơ trễ.': 'Review aggregate metrics and delay-risk alerts.',
    'Hội thoại riêng của sinh viên không hiển thị trong dashboard giảng viên.': 'Private student conversations are never shown on the instructor dashboard.',
    'Đăng nhập tài khoản giảng viên': 'Sign in as an instructor', 'Quản lý môn học': 'Course management',
    'Giao diện giảng viên hiện tại, dùng dữ liệu minh họa.': 'Current instructor interface with sample data.',
    'Bạn giữ quyền quyết định': 'You remain in control',
    'Đề xuất của AI cần xác nhận. PaceWise không tự nộp bài hay ghi điểm.': 'AI suggestions require confirmation. PaceWise never submits work or records grades automatically.',
    'Kết nối theo sự đồng ý': 'Consent-based connections',
    'Google Calendar chỉ được kết nối sau khi bạn cấp quyền. Đăng ký không tự xuất lịch.': 'Google Calendar connects only after you grant permission. Signing up never exports a calendar.',
    'Đúng quyền, đúng nguồn': 'Right access, right sources',
    'Học liệu được lọc theo quyền truy cập. Nếu chưa đủ nguồn, trợ lý cần nói rõ thay vì bịa tài liệu.': 'Materials are filtered by access rights. If sources are insufficient, the assistant says so instead of fabricating them.',
    'Trước khi bắt đầu.': 'Before you begin.',
    'Đăng ký bằng Gmail có tự kết nối Google Calendar không?': 'Does Gmail sign-up automatically connect Google Calendar?',
    'Không. Google xác minh tài khoản khi đăng ký. Sau đó vào Cài đặt, chọn kết nối Google Calendar và cấp quyền. Khi xuất kế hoạch, PaceWise gắn nhắc trước 15 phút cho ca tự học.': 'No. Google verifies your identity during sign-up. Then connect Google Calendar separately in Settings. Exported study sessions include a 15-minute reminder.',
    'Tài khoản mới có xem được tất cả môn học không?': 'Can a new account see every course?',
    'Không. Tài khoản tự đăng ký là sinh viên. Giảng viên cần thêm bạn vào lớp trước khi bạn truy cập học liệu và nhiệm vụ của môn đó.': 'No. Self-registered accounts are students. An instructor must add you to a course before you can access its tasks and materials.',
    'AI có giải hộ bài tập tính điểm không?': 'Does AI complete graded assignments?',
    'Không. Trợ lý hỗ trợ giải thích khái niệm, gợi ý từng bước và tổ chức việc học; không tạo bài nộp thay sinh viên.': 'No. The assistant explains concepts, offers step-by-step hints, and organizes study; it does not create submissions for students.',
    'Giảng viên thấy những dữ liệu nào?': 'What data can instructors see?',
    'Dashboard dùng số liệu tổng hợp theo nhóm đủ kích thước để hạn chế nhận diện cá nhân. Nội dung hỏi đáp và phản hồi riêng không hiển thị cho giảng viên trong dashboard.': 'The dashboard uses sufficiently large aggregate groups to reduce identification risk. Private Q&A and reflections are not shown to instructors.',
    'Bắt đầu bằng một kế hoạch rõ ràng.': 'Start with a clear plan.',
    'Tạo tài khoản sinh viên bằng Google hoặc đăng nhập tài khoản hiện tại.': 'Create a student account with Google or sign in to an existing account.',
    'Đăng ký bằng Google': 'Continue with Google', 'Thông tin sử dụng và quyền truy cập': 'Usage and access information'
  };

  var originalText = new WeakMap();
  function translateTextNodes(language) {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node;
    while ((node = walker.nextNode())) {
      if (!originalText.has(node)) originalText.set(node, node.nodeValue);
      var source = originalText.get(node);
      var trimmed = source.trim();
      var translated = language === 'en' ? translations[trimmed] : null;
      node.nodeValue = translated ? source.replace(trimmed, translated) : source;
    }
  }

  var language = 'vi';
  try { language = localStorage.getItem(LANGUAGE_KEY) === 'en' ? 'en' : 'vi'; } catch (_) {}
  var languageToggle = document.querySelector('.language-toggle');
  function applyLanguage(next) {
    language = next === 'en' ? 'en' : 'vi';
    root.lang = language;
    translateTextNodes(language);
    document.title = language === 'en' ? 'PaceWise — Plan. Do. Reflect.' : 'PaceWise — Lập kế hoạch. Tự học. Nhìn lại.';
    if (languageToggle) {
      languageToggle.textContent = language === 'vi' ? 'EN' : 'VI';
      languageToggle.setAttribute('aria-label', language === 'vi' ? 'Switch to English' : 'Chuyển sang tiếng Việt');
    }
    updateThemeLabel();
    try { localStorage.setItem(LANGUAGE_KEY, language); } catch (_) {}
  }
  if (languageToggle) languageToggle.addEventListener('click', function () { applyLanguage(language === 'vi' ? 'en' : 'vi'); });
  applyLanguage(language);

  var toggle = document.querySelector('.theme-toggle');
  function updateThemeLabel() {
    if (toggle) toggle.setAttribute('aria-label', root.dataset.theme === 'dark'
      ? (language === 'en' ? 'Use light theme' : 'Bật giao diện sáng')
      : (language === 'en' ? 'Use dark theme' : 'Bật giao diện tối'));
  }
  if (toggle) {
    updateThemeLabel();
    toggle.addEventListener('click', function () {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      updateThemeLabel();
      try {
        localStorage.setItem(THEME_KEY, root.dataset.theme);
        localStorage.removeItem(LEGACY_LANDING_THEME_KEY);
      } catch (_) {}
    });
  }
  window.addEventListener('storage', function (event) {
    if (event.key === LANGUAGE_KEY) applyLanguage(event.newValue === 'en' ? 'en' : 'vi');
    if (event.key === THEME_KEY && (event.newValue === 'dark' || event.newValue === 'light')) {
      root.dataset.theme = event.newValue;
      updateThemeLabel();
    }
  });
  document.querySelectorAll('[data-login]').forEach(function (button) {
    button.addEventListener('click', function () { window.location.assign(APP_LOGIN_URL); });
  });
})();
