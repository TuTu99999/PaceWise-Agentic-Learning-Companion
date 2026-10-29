import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MarkdownContent, normalizeAssistantMarkdown } from './MarkdownContent';

describe('MarkdownContent', () => {
  it('normalizes model-escaped markdown and renders lists', () => {
    render(<MarkdownContent>{'\\*\\*Khái niệm\\*\\*\n\n1\\. Phản xạ\n2\\. Đối xứng'}</MarkdownContent>);

    expect(screen.getByText('Khái niệm').tagName).toBe('STRONG');
    expect(screen.getByRole('list')).toBeTruthy();
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });

  it('renders inline and display LaTeX through KaTeX', () => {
    const { container } = render(
      <MarkdownContent>{'Với \\(a \\in A\\).\n\n\\[aRb \\land bRc \\Rightarrow aRc\\]'}</MarkdownContent>,
    );

    expect(container.querySelectorAll('.katex')).toHaveLength(2);
    expect(container.querySelector('.katex-display')).not.toBeNull();
  });

  it('turns provider triangle bullets into a readable Markdown list', () => {
    render(
      <MarkdownContent>
        {'Song song là thiết kế chức năng.▶ Thiếu bước khái niệm.▶ Sửa ERD trước khi sửa CSDL.▶ Nhập môn Cơ sở dữ liệu Chương 2.'}
      </MarkdownContent>,
    );

    expect(screen.getByText('Song song là thiết kế chức năng.')).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.getByText('Thiếu bước khái niệm.')).toBeInTheDocument();
    expect(screen.getByText('Sửa ERD trước khi sửa CSDL.')).toBeInTheDocument();
    expect(screen.getByText('Nhập môn Cơ sở dữ liệu Chương 2.')).toBeInTheDocument();
  });

  it('preserves complex source notation instead of simplifying it', () => {
    const formula = String.raw`\[M_R^{n \times m} = [\delta_{ij}]\quad(i=\overline{1,n},\;j=\overline{1,m})\]`;
    const { container } = render(<MarkdownContent>{formula}</MarkdownContent>);

    const annotation = container.querySelector('annotation[encoding="application/x-tex"]');
    expect(annotation?.textContent).toContain('M_R^{n \\times m}');
    expect(annotation?.textContent).toContain('[\\delta_{ij}]');
    expect(annotation?.textContent).toContain('\\overline{1,n}');
    expect(container.querySelector('.katex-error')).toBeNull();
  });

  it('removes duplicate inline file citations because grounded replies render source cards', () => {
    render(
      <MarkdownContent hideInlineSourceCitations>
        {'Searching uses algorithms over data structures. [Buoi02_Ky_thuat_tim_kiem.pdf, Trang 1, Đoạn 1][Buoi02_Ky_thuat_tim_kiem.pdf, Trang 2, Đoạn 1]\n\nIt includes linear and binary search. [Buoi02_Ky_thuat_tim_kiem.pdf, Page 2, Paragraph 1]'}
      </MarkdownContent>,
    );

    expect(screen.getByText('Searching uses algorithms over data structures.')).toBeVisible();
    expect(screen.getByText('It includes linear and binary search.')).toBeVisible();
    expect(screen.queryByText(/Buoi02_Ky_thuat_tim_kiem\.pdf/)).not.toBeInTheDocument();
  });

  it('keeps raw HTML inert and protects external links', () => {
    const { container } = render(
      <MarkdownContent allowedLinks={['https://example.com']}>{'<script>alert(1)</script>\n\n[Tài liệu](https://example.com)'}</MarkdownContent>,
    );

    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByRole('link', { name: 'Tài liệu' }).getAttribute('rel')).toBe('noopener noreferrer nofollow');
  });
});

describe('markdown safety', () => {
  it('blocks invented URLs, active protocols, remote images and trusted LaTeX commands', () => {
    const { container } = render(<MarkdownContent allowedLinks={['javascript:alert(1)']}>{String.raw`[Fake](https://attacker.invalid) [Bad](javascript:alert(1)) ![pixel](https://attacker.invalid/pixel) \(\href{javascript:alert(1)}{x}\)`}</MarkdownContent>);
    expect(container.querySelector('a')).toBeNull();
    expect(container.querySelector('img')).toBeNull();
  });
});

describe('normalizeAssistantMarkdown', () => {
  it('does not alter ordinary backslashes inside LaTeX', () => {
    expect(normalizeAssistantMarkdown('\\(\\mathbb{Z}\\)')).toBe('$\\mathbb{Z}$');
  });
});
