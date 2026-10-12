export interface GradedQuestion { prompt: string; options: string[]; correct_answer: string; points: number }
export interface TeacherTask {
  id: number; title: string; description: string; kind: 'assignment' | 'quiz' | 'midterm' | 'final_exam';
  due_at: string; points_possible: number; published: boolean; archived: boolean; group_id: number | null;
  resource_ids: number[]; questions: GradedQuestion[]; version: string; has_submissions: boolean;
  chapter?: string;
}
export interface TeacherLesson {
  id: number; title: string; description: string; starts_at: string; ends_at: string;
  mode: 'offline' | 'online'; location: string; meeting_url: string; resource_ids: number[]; cancelled: boolean; version: string;
  series_key?: string | null;
  removed?: boolean;
  event_kind?: string;
}
export interface TeacherManagementData {
  tasks: TeacherTask[]; lessons: TeacherLesson[]; resources: { id: number; title: string; chapter?: string }[];
  calendar_events?: TeacherLesson[];
  materials?: { id: number; title: string; chapter: string; content: string; published: boolean }[];
  weights: { groups: { id?: number; name: string; weight: number }[]; version: string };
}

export interface ManagedCourse { id: number; code: string; name: string; term: string; archived: boolean; version: string }
export interface SchedulePreview {
  ticket: string | null; applied: boolean; restored?: boolean; mode?: string; courses?: string[];
  counts: Partial<Record<'courses' | 'lessons' | 'historical_lessons' | 'tasks' | 'weights' | 'materials' | 'cancelled_lessons' | 'removed_lessons', number>>;
  errors: { source: string; message: string }[];
  items: { sheet: string; row: number; course_id: number; course_code?: string; title: string;
    details?: { starts_at?: string; ends_at?: string; repeat_count?: number; due_at?: string; points_possible?: number;
      published?: boolean; chapter?: string; groups?: { name: string; weight: number }[] } }[];
  cancellations: { id: number; course_id: number; title: string; starts_at: string }[];
}
export interface TeacherProfileData {
  name: string; email: string; version: string;
  details: { title: string; department: string; office: string; office_hours: string; bio: string; contact_url: string };
}
