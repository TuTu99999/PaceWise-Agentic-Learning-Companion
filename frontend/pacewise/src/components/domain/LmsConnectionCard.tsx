import { useState } from 'react';
import { Button } from '../ui/Button';
import { Card, CardHeader } from '../ui/Card';
import { useToast } from '../ui/Toast';
import { syncCanvas } from '../../services/api';
import { standaloneCourses } from '../../services/courseSource';
import { useAppStore } from '../../store/AppStore';
import { useLocale } from '../../i18n/LocaleContext';

export function LmsConnectionCard() {
  const { state, dispatch } = useAppStore();
  const { locale, t } = useLocale();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const retry = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await syncCanvas();
      dispatch({ type: 'SYNC_CANVAS', ...result });
      toast({ tone: 'success', title: standaloneCourses ? 'Đã cập nhật dữ liệu PaceWise' : 'Đã đồng bộ dữ liệu Canvas' });
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : 'Không truy cập được LMS. Hãy thử lại.';
      setError(message);
      dispatch({ type: 'UPDATE_SETTINGS', patch: { staleData: true } });
    } finally { setBusy(false); }
  };
  return <Card aria-labelledby="lms-connection">
    <CardHeader
      id="lms-connection"
      title={standaloneCourses ? t('Dữ liệu PaceWise', 'PaceWise data') : t('Kết nối Canvas', 'Canvas connection')}
      subtitle={standaloneCourses
        ? t('Môn học, lịch và học liệu được quản lý ngay trong PaceWise, không cần kết nối LMS.', 'Courses, schedules, and learning materials are managed directly in PaceWise; no LMS connection is required.')
        : t('Đọc lịch, nhiệm vụ và học liệu được phép; không sửa deadline hay ghi điểm lên LMS.', 'Reads permitted schedules, tasks, and materials; it does not change deadlines or post grades to the LMS.')}
    />
    <p className="text-sm">{state.settings?.staleData
      ? t('Dữ liệu có thể đã cũ', 'Data may be out of date')
      : state.settings?.lastSync
        ? standaloneCourses ? t('Đã cập nhật dữ liệu nội bộ', 'PaceWise data is up to date') : t('Đã đồng bộ LMS', 'LMS data is synchronized')
        : t('Chưa ghi nhận lần cập nhật', 'No update has been recorded')}</p>
    <p className="caption mt-2">{state.settings?.lastSync
      ? `${t('Đồng bộ gần nhất:', 'Last synchronized:')} ${new Date(state.settings.lastSync).toLocaleString(locale === 'en' ? 'en-GB' : 'vi-VN')}`
      : t('Đồng bộ gần nhất: Chưa có', 'Last synchronized: Not yet')}</p>
    {error && <p role="alert" className="mt-2 text-sm text-danger-ink">{error}</p>}
    <Button className="mt-3" variant="secondary" icon="refresh" loading={busy} onClick={retry}>{standaloneCourses ? 'Làm mới dữ liệu' : 'Đồng bộ Canvas lại'}</Button>
  </Card>;
}
