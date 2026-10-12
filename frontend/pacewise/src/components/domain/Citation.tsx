import { useState } from 'react';
import type { Source } from '../../types';
import { reportCitation } from '../../services/api';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import { Modal } from '../ui/Modal';
import { Badge } from '../ui/Badge';
import { useToast } from '../ui/Toast';

export function Citation({ index, source, onOpen }: { index: number; source: Source; onOpen: (s: Source) => void }) {
  return (
    <div className="group flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 rounded-xl border border-line bg-white p-3 hover:border-primary-dark/40 hover:bg-[#FBFCFF] transition">
      <button
        onClick={() => onOpen(source)}
        className="flex min-w-0 flex-1 items-start gap-3 text-left"
        aria-label={`Mở đoạn nguồn ${index}: ${source.name}, ${source.location}`}
      >
        <span className="flex h-7 min-w-[28px] items-center justify-center rounded-lg bg-primary-light text-xs font-bold text-primary-ink">
          {index}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-semibold text-ink group-hover:text-primary-dark">{source.name}</span>
            {source.sectionTitle && (
              <Badge tone="accent" className="!text-[11px] !py-0.5 !px-2">
                {source.sectionTitle}
              </Badge>
            )}
          </div>
          <span className="caption block text-muted mt-0.5 font-medium">{source.location}</span>
        </div>
      </button>

      <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
        {source.downloadUrl && (
          <a
            href={source.downloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 py-1.5 text-xs font-medium text-ink hover:border-primary-dark hover:bg-primary-light/40 transition"
            title="Xem tài liệu trong tab mới"
          >
            <Icon name="arrowRight" size={14} className="text-primary-dark" />
            <span>Xem file</span>
          </a>
        )}

        <button
          onClick={() => onOpen(source)}
          className="inline-flex items-center gap-1 text-xs font-semibold text-primary-dark hover:underline"
        >
          Xem đoạn trích <Icon name="arrowRight" size={14} />
        </button>
      </div>
    </div>
  );
}

export function SourceModal({ source, onClose }: { source: Source | null; onClose: () => void }) {
  const toast = useToast();
  const [reporting, setReporting] = useState(false);

  return (
    <Modal
      open={!!source}
      onClose={onClose}
      title={source?.name ?? ''}
      description={source?.location}
      footer={
        <>
          <Button
            variant="ghost"
            icon="flag"
            loading={reporting}
            onClick={async () => {
              if (!source) return;
              setReporting(true);
              try {
                const { disputeId } = await reportCitation(source.id);
                onClose();
                toast({ tone: 'info', title: 'Đã ghi nhận phản ánh', description: `Đoạn nguồn tạm không dùng làm căn cứ chính. Mã: ${disputeId}` });
              } catch {
                toast({ tone: 'danger', title: 'Chưa thể gửi phản ánh', description: 'Vui lòng thử lại sau.' });
              } finally {
                setReporting(false);
              }
            }}
          >
            Báo nguồn sai
          </Button>

          {source?.downloadUrl && (
            <a
              href={source.downloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="no-underline"
            >
              <Button variant="secondary" icon="arrowRight">
                Xem tài liệu ({source.fileName || 'tài liệu gốc'})
              </Button>
            </a>
          )}

          <Button onClick={onClose}>Quay lại câu trả lời</Button>
        </>
      }
    >
      {source && (
        <div className="space-y-4">
          {source.sectionTitle && (
            <div className="rounded-xl bg-primary-light/50 p-3 border border-primary/20">
              <p className="text-xs font-semibold uppercase tracking-wider text-primary-dark">Mục / Phần trong tài liệu:</p>
              <p className="mt-1 text-sm font-bold text-ink">{source.sectionTitle}</p>
              <p className="caption mt-0.5 text-muted">{source.location}</p>
            </div>
          )}

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Nội dung đoạn trích xuất đối chiếu</p>
            <blockquote className="mt-2 rounded-xl border border-[#F2E2A8] bg-[#FFF9E6] px-4 py-3 text-sm leading-relaxed text-ink/90">
              {source.excerpt}
            </blockquote>
          </div>

          {source.context && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted">Ngữ cảnh bổ sung</p>
              <p className="mt-1 text-muted text-sm">{source.context}</p>
            </div>
          )}

          <p className="caption flex items-center gap-2 text-xs text-muted">
            <Icon name="lock" size={14} /> Câu hỏi bạn đang soạn vẫn được lưu giữ nguyên vẹn.
          </p>
        </div>
      )}
    </Modal>
  );
}

