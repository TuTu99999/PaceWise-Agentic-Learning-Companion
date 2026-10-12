import { useEffect, useRef, useState } from 'react';
import { Select } from '../ui/Field';
import { useToast } from '../ui/Toast';
import { switchCourse, syncCanvas } from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import { Icon } from '../ui/Icon';

export function CourseSwitcher({ allowAll = false, compact = false, notifyOnSuccess = true }: {
  allowAll?: boolean;
  compact?: boolean;
  notifyOnSuccess?: boolean;
}) {
  const { state, dispatch } = useAppStore();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const selectedScope = allowAll ? state.courseScope : state.user?.courseId ?? '';
  const [displayCourseId, setDisplayCourseId] = useState(selectedScope);
  const activeCourseRef = useRef(state.user?.courseId);
  const detailsRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    if (!busy) {
      setDisplayCourseId(allowAll ? state.courseScope : state.user?.courseId ?? state.courses[0]?.id ?? '');
      activeCourseRef.current = state.user?.courseId;
    }
  }, [allowAll, busy, state.courseScope, state.courses, state.user?.courseId]);

  if (!state.user || state.courses.length < 2) return null;

  const selectCourse = async (courseId: string) => {
    if (busy) return;
    if (courseId === displayCourseId) {
      detailsRef.current?.removeAttribute('open');
      return;
    }
    if (courseId === 'all') {
      setDisplayCourseId('all');
      dispatch({ type: 'SET_COURSE_SCOPE', courseScope: 'all' });
      if (notifyOnSuccess) toast({ tone: 'success', title: 'Đang xem tổng quan tất cả môn' });
      detailsRef.current?.removeAttribute('open');
      return;
    }
    const previousCourseId = state.user?.courseId;
    const previousScope = state.courseScope;
    setDisplayCourseId(courseId);
    activeCourseRef.current = courseId;
    setBusy(true);
    try {
      await switchCourse(courseId);
      activeCourseRef.current = courseId;
      dispatch({ type: 'SET_ACTIVE_COURSE', courseId });
      if (allowAll) dispatch({ type: 'SET_COURSE_SCOPE', courseScope: courseId });
      if (notifyOnSuccess) toast({ tone: 'success', title: 'Đã chuyển môn học' });
    } catch (error) {
      activeCourseRef.current = previousCourseId;
      setDisplayCourseId(allowAll ? previousScope : previousCourseId ?? state.courses[0]?.id ?? '');
      toast({
        tone: 'danger',
        title: 'Chưa chuyển được môn học',
        description: error instanceof Error ? error.message : 'Hãy thử lại.',
      });
      return;
    } finally {
      setBusy(false);
      detailsRef.current?.removeAttribute('open');
    }

    void syncCanvas()
      .then((synced) => {
        if (synced.activeCourseId !== activeCourseRef.current) return;
        dispatch({
          type: 'SYNC_CANVAS',
          courses: synced.courses,
          tasks: synced.tasks,
          guidance: synced.guidance,
          assessments: synced.assessments,
          courseData: synced.courseData,
        });
      })
      .catch(() => {
        toast({
          tone: 'warning',
          title: 'Đã chuyển môn, nhưng chưa làm mới được dữ liệu',
          description: 'PaceWise đang dùng dữ liệu đã đồng bộ gần nhất.',
        });
      });
  };

  if (compact) {
    const options = [
      ...(allowAll ? [{ value: 'all', label: 'Tất cả môn học' }] : []),
      ...state.courses.map((course) => ({ value: course.id, label: `${course.code} — ${course.name}` })),
    ];
    return (
      <details ref={detailsRef} className="group relative">
        <summary
          className="relative flex h-10 w-10 cursor-pointer list-none items-center justify-center rounded-xl text-slate-600 marker:hidden hover:bg-primary-light hover:text-primary-ink"
          aria-label="Chọn môn học"
          title="Chọn môn học"
        >
          <Icon name="book" size={20} />
          {busy && <span className="absolute inset-1 animate-pulse rounded-lg border border-primary" aria-hidden="true" />}
        </summary>
        <div className="absolute right-0 top-12 z-50 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-white shadow-xl">
          <div className="border-b border-line px-4 py-3">
            <p className="text-sm font-bold">Chọn môn học</p>
            <p className="mt-0.5 text-xs text-muted">Nội dung Hỏi đáp dùng dữ liệu của môn đang chọn.</p>
          </div>
          <div className="max-h-72 overflow-y-auto p-2">
            {options.map((option) => {
              const selected = option.value === displayCourseId;
              return (
                <button
                  key={option.value}
                  type="button"
                  disabled={busy}
                  onClick={() => void selectCourse(option.value)}
                  className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm ${selected ? 'bg-primary-light font-semibold text-primary-ink' : 'hover:bg-slate-50'}`}
                >
                  <Icon name={selected ? 'checkCircle' : 'book'} size={18} className="shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{option.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </details>
    );
  }

  return (
    <div className="border-b border-line bg-white px-4 py-3 sm:px-6 lg:px-10" aria-busy={busy}>
      <Select
        className="max-w-md"
        label={allowAll ? 'Phạm vi hiển thị' : 'Môn học đang thao tác'}
        value={displayCourseId || (allowAll ? 'all' : state.user.courseId || state.courses[0]?.id)}
        disabled={busy}
        options={[
          ...(allowAll ? [{ value: 'all', label: 'Tất cả môn học' }] : []),
          ...state.courses.map((course) => ({ value: course.id, label: `${course.code} — ${course.name}` })),
        ]}
        onChange={(event) => void selectCourse(event.target.value)}
      />
      <p className="caption mt-1">
        {busy
          ? 'Đang xác nhận môn học...'
          : allowAll
            ? 'Tổng quan mặc định so sánh deadline và tiến độ giữa tất cả môn; chọn một môn khi cần xem chi tiết.'
            : 'Học liệu và hoạt động bên dưới thuộc môn đang chọn.'}
      </p>
    </div>
  );
}
