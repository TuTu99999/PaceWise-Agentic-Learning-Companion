import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';

export function normalizeAssistantMarkdown(value: string): string {
  return value
    .replace(/\\\[([\s\S]*?)\\\]/g, (_match, math: string) => `\n$$\n${math.trim()}\n$$\n`)
    .replace(/\\\((.*?)\\\)/g, (_match, math: string) => `$${math.trim()}$`)
    .replace(/^(\s*\d+)\\\.(?=\s)/gm, '$1.')
    .replace(/\\([*_~#>`])/g, '$1');
}

export function safeSourceLink(href: string | undefined, allowedLinks: string[]): string | undefined {
  if (!href || !allowedLinks.includes(href)) return undefined;
  try {
    const parsed = new URL(href, window.location.origin);
    return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password ? href : undefined;
  } catch { return undefined; }
}

export function MarkdownContent({ children, allowedLinks = [] }: { children: string; allowedLinks?: string[] }) {
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
        {normalizeAssistantMarkdown(children)}
      </ReactMarkdown>
    </div>
  );
}
