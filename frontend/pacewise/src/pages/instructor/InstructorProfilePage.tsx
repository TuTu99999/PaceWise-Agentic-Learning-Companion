import { useEffect, useRef, useState, type FormEvent } from 'react';
import { fetchTeacherProfile, saveTeacherProfile } from '../../services/api';
import { standaloneCourses } from '../../services/courseSource';
import { Card } from '../../components/ui/Card';
import { PageHeader } from '../../components/ui/PageHeader';
import { Input, Textarea } from '../../components/ui/Field';
import { Button } from '../../components/ui/Button';
import { useAppStore } from '../../store/AppStore';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { useInstructorData } from '../../hooks/useInstructorData';
import type { TeacherProfileData } from '../../types/teacherManagement';
import { useLocale } from '../../i18n/LocaleContext';
import { LanguageToggle } from '../../components/domain/LanguageToggle';

const PROFILE_CACHE_TTL_MS = 30_000;
const errorMessage = (reason: unknown, fallback: string) => reason instanceof Error ? reason.message : fallback;

export function InstructorProfilePage() {
  const { t } = useLocale();
  useDocumentTitle('Thông tin giảng viên');
  const { state } = useAppStore();
  const { profileCache } = useInstructorData();
  const dirty = useRef(false);
  const generation = useRef(0);
  const saving = useRef(false);
  const [profile, setProfile] = useState<TeacherProfileData | null>(profileCache.current?.data ?? null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(!profile);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const currentGeneration = ++generation.current;
    const cached = profileCache.current;
    dirty.current = false;
    setProfile(cached?.data ?? null);
    setError('');
    setSuccess(false);
    if (!retry && cached && Date.now() - cached.savedAt < PROFILE_CACHE_TTL_MS) {
      setLoading(false);
    } else {
      setLoading(true);
      void fetchTeacherProfile().then((data) => {
        if (generation.current !== currentGeneration) return;
        profileCache.current = { data, savedAt: Date.now() };
        if (!dirty.current) setProfile(data);
      }).catch((reason: unknown) => {
        if (generation.current === currentGeneration) setError(errorMessage(reason, 'Không tải được hồ sơ.'));
      }).finally(() => {
        if (generation.current === currentGeneration) setLoading(false);
      });
    }
    return () => { generation.current += 1; };
  }, [state.user?.id, retry, profileCache]);

  const change = (key: keyof TeacherProfileData['details'], value: string) => {
    dirty.current = true;
    setSuccess(false);
    setProfile((current) => current ? { ...current, details: { ...current.details, [key]: value } } : current);
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!profile || saving.current || loading) return;
    const currentGeneration = generation.current;
    saving.current = true;
    setBusy(true);
    setError('');
    setSuccess(false);
    try {
      const data = await saveTeacherProfile({ ...profile.details, expected_version: profile.version });
      if (generation.current !== currentGeneration) return;
      profileCache.current = { data, savedAt: Date.now() };
      setProfile(data);
      dirty.current = false;
      setSuccess(true);
    } catch (reason: unknown) {
      if (generation.current === currentGeneration) setError(errorMessage(reason, 'Không lưu được hồ sơ.'));
    } finally {
      saving.current = false;
      if (generation.current === currentGeneration) setBusy(false);
    }
  };
  return <div className="page max-w-3xl"><PageHeader title="Thông tin giảng viên" description={standaloneCourses ? 'Thông tin chuyên môn, liên hệ và tài khoản PaceWise của bạn.' : 'Thông tin chuyên môn và cách liên hệ. Tên đăng nhập, email và vai trò do LMS quản lý.'} />
    {error && <div className="mb-4 space-y-2"><p role="alert" className="text-danger-ink">{error}</p>
      <Button variant="secondary" disabled={busy || loading} onClick={() => {
        // Explicit reload must adopt the latest version, not keep a conflicted draft.
        dirty.current = false;
        setRetry((value) => value + 1);
      }}>{t('Tải lại hồ sơ')}</Button>
      {profile && <p className="caption">Tải lại sẽ thay các chỉnh sửa chưa lưu bằng hồ sơ mới nhất.</p>}
    </div>}
    {loading && <p role="status" className="mb-4">{t('Đang tải hồ sơ…')}</p>}
    <Card className="mb-5 p-5" aria-labelledby="instructor-language"><h2 id="instructor-language" className="font-semibold">{t('Ngôn ngữ', 'Language')}</h2><p className="mb-3 mt-1 text-sm text-muted">{t('Áp dụng cho toàn bộ giao diện PaceWise trên thiết bị này.', 'Applies to the full PaceWise interface on this device.')}</p><LanguageToggle /></Card>
    {profile && <Card className="p-5"><form onSubmit={(event) => void save(event)}>
      <fieldset disabled={busy || loading} className="min-w-0 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2"><Input label={standaloneCourses ? t('Họ tên') : `${t('Họ tên')} (LMS)`} readOnly value={profile.name} /><Input label={standaloneCourses ? t('Email đăng nhập') : `${t('Email đăng nhập')} (LMS)`} readOnly value={profile.email} />
        <Input label={t('Chức danh')} maxLength={120} value={profile.details.title} onChange={(event) => change('title', event.target.value)} />
        <Input label={t('Khoa / bộ môn')} maxLength={200} value={profile.details.department} onChange={(event) => change('department', event.target.value)} />
        <Input label={t('Văn phòng')} maxLength={200} value={profile.details.office} onChange={(event) => change('office', event.target.value)} />
        <Input label={t('Liên hệ / website (HTTPS)')} type="url" pattern="https://.*" maxLength={500} value={profile.details.contact_url} onChange={(event) => change('contact_url', event.target.value)} /></div>
      <Textarea label={t('Giờ tư vấn / cách đặt lịch')} maxLength={500} value={profile.details.office_hours} onChange={(event) => change('office_hours', event.target.value)} />
      <Textarea label={t('Giới thiệu chuyên môn')} maxLength={2000} value={profile.details.bio} onChange={(event) => change('bio', event.target.value)} />
      <p className="text-sm text-muted">{t(
        `Môn đang phụ trách: ${state.courses.map((course) => course.code).join(', ') || 'Đang đồng bộ'}. Hồ sơ này lưu theo tài khoản, không thay đổi khi chuyển môn.`,
        `Courses taught: ${state.courses.map((course) => course.code).join(', ') || 'Syncing'}. This profile belongs to the account and does not change when switching courses.`,
      )}</p>
      {success && <p role="status" className="text-success-ink">{t('Đã lưu thông tin giảng viên.')}</p>}<Button type="submit" loading={busy}>{t('Lưu thông tin')}</Button>
      </fieldset>
    </form></Card>}
  </div>;
}
