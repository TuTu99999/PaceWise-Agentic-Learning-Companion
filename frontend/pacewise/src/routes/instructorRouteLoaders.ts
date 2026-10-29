const loadOverview = () => import('../pages/instructor/InstructorOverviewPage');
const loadSchedule = () => import('../pages/instructor/InstructorSchedulePage');
const loadAssessment = () => import('../pages/instructor/AssessmentPage');
const loadAssessmentEdit = () => import('../pages/instructor/AssessmentEditPage');
const loadTasks = () => import('../pages/instructor/InstructorTasksPage');
const loadProfile = () => import('../pages/instructor/InstructorProfilePage');
const loadCourses = () => import('../pages/instructor/InstructorCoursesPage');

export const instructorRouteLoaders = {
  overview: loadOverview,
  schedule: loadSchedule,
  assessment: loadAssessment,
  assessmentEdit: loadAssessmentEdit,
  tasks: loadTasks,
  profile: loadProfile,
  courses: loadCourses,
};

let preloadPromise: Promise<unknown[]> | null = null;

export function preloadInstructorOverview() {
  return loadOverview();
}

/** Warm route chunks once so navigation inside the instructor workspace is instant. */
export function preloadInstructorRoutes() {
  if (!preloadPromise) {
    preloadPromise = Promise.all(Object.values(instructorRouteLoaders).map((load) => load()))
      .catch((error) => { preloadPromise = null; throw error; });
  }
  return preloadPromise;
}
