import type { DoSessionPreparation } from '../../types';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { Icon } from '../ui/Icon';

const LMS_URL = (import.meta.env.VITE_LMS_URL || 'http://localhost:8010').replace(/\/$/, '');

const resourceUrl = (url?: string | null) => {
  if (!url) return null;
  if (/^https?:\/\//i.test(url)) {
    if (import.meta.env.VITE_LMS_WEB_ENABLED === 'false' && new URL(url).origin === new URL(LMS_URL).origin) return null;
    return url;
  }
  if (url.startsWith('/api/v1/')) {
    const apiBase = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/$/, '');
    return `${apiBase}${url.slice('/api/v1'.length)}`;
  }
  if (import.meta.env.VITE_LMS_WEB_ENABLED === 'false') return null;
  return `${LMS_URL}${url.startsWith('/') ? '' : '/'}${url}`;
};

export function DoSessionSupport({
  preparation,
  loading,
  error,
  onRetry,
}: {
  preparation: DoSessionPreparation | null;
  loading: boolean;
  error?: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="!p-4">
      <div className="flex items-center gap-2">
        <Icon name="book" size={18} className="text-primary-ink" />
        <h2 className="font-bold">Tài liệu gợi ý</h2>
      </div>
      <p className="mt-1 text-xs text-muted">Học liệu được phép truy cập trong chương của ca này.</p>
      {loading && preparation && <p className="mt-2 text-xs text-muted" role="status">Đang cập nhật…</p>}
      {loading && !preparation ? (
        <p className="mt-4 flex items-center gap-2 text-sm text-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-r-transparent" />
          Đang chuẩn bị học liệu…
        </p>
      ) : error ? (
        <div role="alert" className="mt-4 rounded-lg bg-danger-light p-3 text-sm text-danger-ink">
          {error}
          {onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Thử tải lại học liệu</Button>}
        </div>
      ) : preparation?.recommended_resources.length ? (
        <ul className="mt-3 space-y-2">
          {preparation.recommended_resources.map((resource) => {
            const href = resourceUrl(resource.url);
            const content = (
              <>
                <span className="block truncate text-sm font-semibold">{resource.title}</span>
                <span className="mt-0.5 block truncate text-[11px] text-muted">{resource.module} · {resource.kind}</span>
              </>
            );
            return (
              <li key={`${resource.id}:${resource.citation}`} className="rounded-xl border border-line bg-canvas px-3 py-2.5">
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    title={`Mở ${resource.title} trong tab mới`}
                    className="block hover:text-primary-ink"
                  >
                    {content}
                    <span className="mt-1 block text-[11px] font-semibold text-primary-ink">Mở tài liệu trong tab mới</span>
                  </a>
                ) : (
                  <>
                    {content}
                    {resource.excerpt && (
                      <details className="mt-2 text-xs">
                        <summary className="cursor-pointer font-semibold text-primary-ink">Xem nội dung</summary>
                        <p className="mt-2 whitespace-pre-wrap break-words">{resource.excerpt}</p>
                      </details>
                    )}
                  </>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-muted">
          {preparation?.scope?.status === 'unmapped'
            ? 'Chưa xác định được học liệu đúng chương cho nhiệm vụ này.'
            : 'Chưa có học liệu được phép truy cập trong chương này.'}
        </p>
      )}
    </Card>
  );
}
