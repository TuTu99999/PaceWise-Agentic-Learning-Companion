import { useEffect, useState } from 'react';
import { confirmRhythmProposal, getRhythmProposal } from '../../services/api';
import { useAppStore } from '../../store/AppStore';
import type { RhythmReport, RhythmTrialSummary } from '../../types';
import { Button } from '../ui/Button';
import { activityLabels } from '../../utils/studyPreferences';
import { useLocale } from '../../i18n/LocaleContext';

const percentage = (value: number | null | undefined) => value == null ? 'Chưa có dữ liệu' : `${Math.round(value * 100)}%`;
function TrialSummary({ label, summary }: { label: string; summary: RhythmTrialSummary | null | undefined }) {
  return <div className="min-w-0 rounded-lg bg-canvas p-2">
    <p className="font-semibold">{label} · {summary?.sessions ?? 0} phiên</p>
    <p>Hoàn thành ca: {percentage(summary?.completionRate)}</p>
    <p>Báo dài/quá dài: {percentage(summary?.longSessionRate)}</p>
    <p>Phiên có Assessment dùng gợi ý: {percentage(summary?.assistedAssessmentRate)}</p>
    {(['conceptual', 'application', 'transfer', 'retention'] as const).map((dimension, index) => {
      const evidence = summary?.assessment?.[dimension];
      return <p key={dimension}>{['Giải thích', 'Vận dụng', 'Chuyển giao', 'Nhớ sau một thời gian'][index]}: {evidence?.testedSessions ? `${percentage(evidence.passRate)} · ${evidence.testedSessions} phiên được kiểm tra` : 'Chưa kiểm tra'}</p>;
    })}
  </div>;
}

export function RhythmProposalCard() {
  const { state, dispatch } = useAppStore();
  const { t } = useLocale();
  const [report, setReport] = useState<RhythmReport | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    if (!state.workspaceReady) return;
    let active = true;
    void getRhythmProposal().then((next) => { if (active) { setReport(next); setError(''); } })
      .catch(() => { if (active) setError('Chưa tải được bằng chứng nhịp học; preference hiện tại vẫn được giữ.'); });
    return () => { active = false; };
  }, [state.workspaceReady, state.user?.id, state.studyPreferences?.sessionMinutes, state.studyPreferences?.breakMinutes,
    state.studyPreferences?.checkpointMinutes, state.studyPreferences?.adaptiveSuggestionsEnabled, state.studyPreferences?.activityRhythms, refresh]);
  const proposal = report?.proposal;
  const confirm = async () => {
    if (!proposal) return;
    setBusy(true); setError('');
    try {
      const result = await confirmRhythmProposal(proposal.id);
      dispatch({ type: 'UPSERT_ACTIVITY_RHYTHM', rhythm: { ...result.scope, ...result.preferences } });
      setReport(null);
      setRefresh((value) => value + 1);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Chưa xác nhận được đề xuất.'); }
    finally { setBusy(false); }
  };
  return <div className="mt-4 rounded-xl border border-line p-3 text-sm">
    {error ? <p role="alert">{error} <button type="button" className="text-primary-ink underline" onClick={() => setRefresh((value) => value + 1)}>Thử lại</button></p>
      : proposal ? <>
        <p className="font-semibold">Thử phiên {proposal.preferences.sessionMinutes} phút, nghỉ {proposal.preferences.breakMinutes} phút?</p>
        <p className="mt-1 text-primary-ink">Chỉ cho {state.courses?.find((course) => Number(course.id) === proposal.courseId)?.name ?? `môn ${proposal.courseId}`} · {activityLabels[proposal.activityType]}.</p>
        <p className="mt-1">Bạn nhiều lần báo phiên dài ở cùng nhiệm vụ và trạng thái kiến thức nền. Đây là thử nghiệm nhỏ, không phải thời lượng tập trung tối ưu.</p>
        <details className="mt-2"><summary className="cursor-pointer">Bằng chứng và giới hạn</summary>
          <p>Nguồn phiên: {proposal.sourceRefs.join(', ')}.</p><p>{report.excludedCount} phiên không phù hợp bị loại.</p>
          <p>{proposal.assessmentEvidenceIds.length ? `Evidence Assessment: ${proposal.assessmentEvidenceIds.join(', ')}. Chưa chứng minh nhịp mới giúp hiểu tốt hơn.` : 'Chưa có evidence Assessment phù hợp; chất lượng học chưa được đánh giá.'}</p>
        </details>
        <Button className="mt-3" size="sm" loading={busy} onClick={() => void confirm()}>Xác nhận thử nhịp mới</Button>
        <p className="caption mt-2">Chỉ cập nhật preference và tự lưu. Tổng công việc không giảm; lịch đã xác nhận không đổi. Khi muốn đổi lịch, phân tích lại và xác nhận bản preview.</p>
      </> : <p className="text-muted">{report?.status === 'disabled'
        ? t('Đã tắt đề xuất nhịp tự động.', 'Automatic rhythm suggestions are turned off.')
        : t('Chưa đủ bằng chứng tương đồng để đề xuất nhịp khác. Giữ lựa chọn của bạn.', 'There is not enough comparable evidence to suggest a different rhythm. Your current choices remain unchanged.')}</p>}
    {report?.comparison?.before && <p className="caption mt-2">Theo dõi thử nhịp: {report.comparison.before.sessions} phiên trước · {report.comparison.after?.sessions ?? 0} phiên sau tương đồng.
      {report.comparison.status === 'descriptive_not_causal' ? ' Có số liệu mô tả, chưa chứng minh hiệu quả nhân quả.' : ' Chưa đủ dữ liệu so sánh; chưa kết luận nhịp nào tốt hơn.'}</p>}
    {report?.comparison?.before && <details className="mt-2"><summary className="cursor-pointer">Tiến độ và bằng chứng Assessment trước/sau</summary>
      <div className="mt-2 grid gap-2 text-xs sm:grid-cols-2"><TrialSummary label="Trước thử nhịp" summary={report.comparison.before} /><TrialSummary label="Sau thử nhịp" summary={report.comparison.after} /></div>
      <p className="caption mt-2">Tỷ lệ hoàn thành ca không phải mức hiểu. Assessment dùng bằng chứng độc lập đã được chấp nhận; số liệu này không chứng minh nhịp mới là nguyên nhân cải thiện.</p>
    </details>}
  </div>;
}
