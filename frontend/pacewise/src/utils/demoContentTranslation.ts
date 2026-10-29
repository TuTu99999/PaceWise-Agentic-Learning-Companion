const ENGLISH_DEMO_TOPICS: Record<string, string> = {
  'Khái quát về hệ cơ sở dữ liệu': 'Overview of database systems',
  'Mô hình cơ sở dữ liệu': 'Database models',
  'Tổng quan cấu trúc dữ liệu và giải thuật': 'Introduction to data structures and algorithms',
  'Kỹ thuật tìm kiếm': 'Searching techniques',
  'Giới thiệu lập trình hướng đối tượng': 'Introduction to object-oriented programming',
  'Mở rộng C++ phần 1': 'Extended C++ — Part 1',
  'Giới thiệu môn học': 'Course introduction',
  'Công nghệ Web': 'Web technologies',
  'Hàm': 'Functions',
};

const ENGLISH_DEMO_REFLECTIONS: Record<string, string> = {
  'Tuần này đã hoàn thành': "I completed this week's work.",
  'Nguyên nhân kế hoạch đúng là do t cố gắng học ở trên trường, trao dồi kiến thức.': 'The plan stayed on track because I worked hard in class and strengthened my knowledge.',
  'Tuần sau vẫn giữ nguyên thời lượng như này': 'Keep the same study duration next week.',
};

export function englishDemoTaskTitle(title: string) {
  const monthlyQuiz = title.match(/^Quiz tháng (\d{2}) · (\d+) phút$/);
  if (monthlyQuiz) return `Monthly quiz ${monthlyQuiz[1]} · ${monthlyQuiz[2]} minutes`;

  const completedHomework = title.match(/^Hoàn thành BTVN (.+?): (.+)$/);
  if (completedHomework) {
    return `Complete homework ${completedHomework[1]}: ${ENGLISH_DEMO_TOPICS[completedHomework[2]] ?? completedHomework[2]}`;
  }

  const completedAssignment = title.match(/^Hoàn thành Bài tập Chương (\d+): (.+)$/);
  if (completedAssignment) {
    return `Complete Chapter ${completedAssignment[1]} assignment: ${ENGLISH_DEMO_TOPICS[completedAssignment[2]] ?? completedAssignment[2]}`;
  }

  const assignment = title.match(/^Bài tập Chương (\d+): (.+)$/);
  if (assignment) return `Chapter ${assignment[1]} assignment: ${ENGLISH_DEMO_TOPICS[assignment[2]] ?? assignment[2]}`;
  return ENGLISH_DEMO_TOPICS[title] ?? title;
}

export function englishDemoReflectionAnswer(answer: string) {
  return ENGLISH_DEMO_REFLECTIONS[answer.trim()] ?? answer;
}
