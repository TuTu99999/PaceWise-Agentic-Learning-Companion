import type { QAKind, Source } from '../../types';
import { cx } from '../../utils/cx';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import { Citation } from './Citation';
import { MarkdownContent } from './MarkdownContent';

interface GroundedMessage {
  text: string;
  kind?: QAKind;
  sources?: Source[];
  suggestions?: string[];
}

function sourceLocationSummary(sources: Source[]) {
  const sections = [...new Set(sources.map((source) => source.sectionTitle?.trim()).filter(Boolean))];
  const pages = sources
    .flatMap((source) => [source.locationDetail, source.location])
    .flatMap((value) => [...String(value || '').matchAll(/trang\s+(\d+)/gi)].map((match) => Number(match[1])))
    .filter(Number.isFinite);
  const section = sections.length === 1 ? sections[0] : sections.length > 1 ? `${sections[0]} và phần liên quan` : '';
  const page = pages.length
    ? `trang ${Math.min(...pages)}${Math.max(...pages) !== Math.min(...pages) ? `–${Math.max(...pages)}` : ''}`
    : '';
  return [section, page].filter(Boolean).join(' · ');
}

export function GroundedAssistantReply({
  message,
  onOpen,
  onAsk,
  compact = false,
}: {
  message: GroundedMessage;
  onOpen: (source: Source) => void;
  onAsk?: (question: string) => void;
  compact?: boolean;
}) {
  const sources = message.sources ?? [];
  const location = sourceLocationSummary(sources);

  return (
    <Card as="article" className="min-w-0 !p-4 shadow-sm border border-line/80 bg-white">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {message.kind === 'grounded' && <Badge tone="success" icon="checkCircle">Có nguồn</Badge>}
        {message.kind === 'abstained' && <Badge tone="warning" icon="info">Chưa đủ nguồn</Badge>}
        {message.kind === 'out_of_scope' && <Badge tone="neutral" icon="info">Ngoài phạm vi môn</Badge>}
        {message.kind === 'hint' && <Badge tone="accent" icon="lightbulb">Gợi ý từng bước</Badge>}
      </div>
      {message.kind === 'abstained' && <h3 className="mb-1 font-semibold">Chưa đủ nguồn để trả lời chắc chắn</h3>}
      <div className={cx(compact && 'auto-hide-scrollbar max-h-72 overflow-y-auto pr-1')}>
        <MarkdownContent allowedLinks={sources.flatMap((source) => [source.previewUrl, source.downloadUrl].filter((url): url is string => !!url))}>
          {message.text}
        </MarkdownContent>
      </div>
      {message.kind === 'abstained' && <p className="caption mt-2">Bạn có thể xem syllabus của môn hoặc hỏi giảng viên trong office hour.</p>}
      {!!sources.length && (
        <details className="mt-3 border-t border-line pt-3">
          <summary className="cursor-pointer text-xs font-semibold text-primary-ink">
            Đã kiểm tra {sources.length} nguồn{location ? ` · ${location}` : ''}
          </summary>
          <div className="mt-3 space-y-2" aria-label="Nguồn học liệu đối chiếu">
            {sources.map((source, index) => (
              <Citation key={source.id} index={index + 1} source={source} onOpen={onOpen} />
            ))}
          </div>
        </details>
      )}
      {!!message.suggestions?.length && onAsk && (
        <div className="mt-4 flex flex-wrap gap-2">
          {message.suggestions.map((suggestion) => (
            <button key={suggestion} onClick={() => onAsk(suggestion)} className="min-h-[40px] rounded-full border border-line bg-white px-3.5 text-sm font-medium transition hover:border-[#C9D8FB] hover:bg-primary-light">
              {suggestion}
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}
