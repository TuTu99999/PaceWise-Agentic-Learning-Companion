/** Build-time UI contract matching the backend's selected course source. */
export const standaloneCourses = import.meta.env.VITE_COURSE_SOURCE_MODE === 'standalone';
const configuredMb = Number(import.meta.env.VITE_COURSE_PDF_MAX_MB || 50);
export const coursePdfMaxMb = standaloneCourses
  ? Number.isFinite(configuredMb) && configuredMb >= 1 && configuredMb <= 200 ? configuredMb : 50
  : 5;
