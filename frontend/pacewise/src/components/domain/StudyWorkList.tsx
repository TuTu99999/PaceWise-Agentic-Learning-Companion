import { cx } from '../../utils/cx';

export function splitStudyWorkTitle(title: string) {
  const [work = '', ...taskParts] = title.split(/\s+—\s+/);
  const parsedItems = work
    .replace(/^Làm\s+/i, '')
    .split(/\s*;\s*/)
    .map((item) => item.trim())
    .filter(Boolean);
  const seen = new Set<string>();
  const items = parsedItems.filter((item) => {
    const identity = item.toLocaleLowerCase().replace(/\s+/g, ' ');
    if (seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });

  return {
    items: items.length ? items : [title.trim()],
    taskTitle: taskParts.join(' — ').trim(),
  };
}

export function StudyWorkList({ title, className }: { title: string; className?: string }) {
  const { items, taskTitle } = splitStudyWorkTitle(title);

  return (
    <div className={cx('min-w-0', className)}>
      <ul aria-label="Nội dung ca tự học" className="space-y-2">
        {items.map((item, index) => (
          <li key={`${item}-${index}`} className="flex min-w-0 items-start gap-2.5">
            <span aria-hidden="true" className="mt-[0.55em] h-1.5 w-1.5 shrink-0 rounded-full bg-primary-ink" />
            <span className="min-w-0 break-words font-semibold leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
      {taskTitle && (
        <p className="mt-3 border-t border-line pt-3 text-sm leading-relaxed text-muted">
          <span className="font-medium text-ink">Thuộc nhiệm vụ:</span>{' '}{taskTitle}
        </p>
      )}
    </div>
  );
}
