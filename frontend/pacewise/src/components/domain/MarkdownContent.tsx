import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';

export function normalizeAssistantMarkdown(value: string): string {
  return value
    .replace(/[ \t]+(?=\r?\n)/g, '')
    .replace(/ {2,}/g, ' ')
    // Some providers use triangle glyphs as inline bullets without preserving
    // the preceding newline. Convert only sentence/start-of-line triangles so
    // legitimate arrow notation inside course content remains untouched.
    .replace(/(^|\n)[\t ]*[▶►▸][\t ]*/g, '$1- ')
    .replace(/([.!?;)])[\t ]*[▶►▸][\t ]+/g, '$1\n\n- ')
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, math: string) => `\n$$\n${math.trim()}\n$$\n`)
    .replace(/\\\((.*?)\\\)/g, (_match, math: string) => `$${math.trim()}$`)
    .replace(/^(\s*\d+)\\\.(?=\s)/gm, '$1.')
    .replace(/\\([*_~#>`])/g, '$1')
    .trim();
}

export function removeInlineSourceCitations(value: string): string {
  return value
    // Grounded replies render these sources as accessible cards below. Keeping
    // the provider tokens here duplicates information and creates ragged lines
    // in the narrow in-session assistant panel.
    .replace(
      /\[\s*[^\]\r\n]+?\.(?:pdf|docx?|pptx?|txt)\s*,\s*(?:trang|page)\s+\d+(?:\s*,\s*(?:đoạn|paragraph)\s+\d+)?\s*\]/gi,
      '',
    )
    .replace(/ {2,}/g, ' ')
    .trim();
}

export function safeSourceLink(href: string | undefined, allowedLinks: string[]): string | undefined {
  if (!href || !allowedLinks.includes(href)) return undefined;
  try {
    const parsed = new URL(href, window.location.origin);
    return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password ? href : undefined;
  } catch { return undefined; }
}

export function MarkdownContent({
  children,
  allowedLinks = [],
  hideInlineSourceCitations = false,
}: {
  children: string;
  allowedLinks?: string[];
  hideInlineSourceCitations?: boolean;
}) {
  return (
    <div className="chat-markdown min-w-0 text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { trust: false, strict: 'ignore', maxExpand: 200, throwOnError: false }]]}
        skipHtml
        components={{
          a: ({ children: linkChildren, href }) => safeSourceLink(href, allowedLinks) ? (
            <a href={href} className="link break-words" target="_blank" rel="noopener noreferrer nofollow">
              {linkChildren}
            </a>
          ) : <span>{linkChildren}</span>,
          img: ({ alt }) => <span>{alt || 'Ảnh chưa được xác minh'}</span>,
          code: ({ children: codeChildren, className, ...props }) => (
            <code {...props} className={className ?? 'rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em]'}>
              {codeChildren}
            </code>
          ),
        }}
      >
        {normalizeAssistantMarkdown(hideInlineSourceCitations ? removeInlineSourceCitations(children) : children)}
      </ReactMarkdown>
    </div>
  );
}
