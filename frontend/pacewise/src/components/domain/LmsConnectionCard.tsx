import { useState } from 'react';
import { Button } from '../ui/Button';
import { Card, CardHeader } from '../ui/Card';
import { useToast } from '../ui/Toast';
import { syncCanvas } from '../../services/api';
import { standaloneCourses } from '../../services/courseSource';
import { useAppStore } from '../../store/AppStore';

export function LmsConnectionCard() {
  const { state, dispatch } = useAppStore();
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
    <CardHeader id="lms-connection" title={standaloneCourses ? 'Dữ liệu PaceWise' : 'Kết nối Canvas'} subtitle={standaloneCourses ? 'Môn học, lịch và học liệu được quản lý ngay trong PaceWise, không cần kết nối LMS.' : 'Đọc lịch, nhiệm vụ và học liệu được phép; không sửa deadline hay ghi điểm lên LMS.'} />
    <p className="text-sm">{state.settings?.staleData ? 'Dữ liệu có thể đã cũ' : state.settings?.lastSync ? (standaloneCourses ? 'Đã cập nhật dữ liệu nội bộ' : 'Đã đồng bộ LMS') : 'Chưa ghi nhận lần cập nhật'}</p>
    <p className="caption mt-2">Đồng bộ gần nhất: {state.settings?.lastSync ? new Date(state.settings.lastSync).toLocaleString('vi-VN') : 'Chưa có'}</p>
    {error && <p role="alert" className="mt-2 text-sm text-danger-ink">{error}</p>}
    <Button className="mt-3" variant="secondary" icon="refresh" loading={busy} onClick={retry}>{standaloneCourses ? 'Làm mới dữ liệu' : 'Đồng bộ Canvas lại'}</Button>
  </Card>;
}
