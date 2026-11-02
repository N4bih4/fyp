import { useEffect, useState } from 'react';
import { api } from '../api';

/** What a long task (a document, a research) is doing right now: the latest lines it reported, refreshed every second while it runs. */
export function ProgressLines({ taskId, running }: { taskId: string; running: boolean }) {
  const [lines, setLines] = useState<{ text: string; step: number | null; of: number | null }[]>([]);

  useEffect(() => {
    if (!running) return;
    let alive = true;
    const load = () => api.progress(taskId).then((r) => { if (alive) setLines(r.lines); }).catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 1000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [taskId, running]);

  if (lines.length === 0) return null;
  const last = lines[lines.length - 1];
  return (
    <div className="mt-2 text-xs text-blue-900" data-testid="progress-lines" aria-live="polite">
      {last.step != null && last.of ? (
        <div className="h-1.5 w-full overflow-hidden rounded bg-blue-100" aria-hidden="true">
          <div className="h-full bg-blue-500 transition-all" style={{ width: `${Math.min(100, Math.round((last.step / last.of) * 100))}%` }} />
        </div>
      ) : null}
      <ul className="mt-1 space-y-0.5">
        {lines.slice(-4).map((l, i, arr) => (
          <li key={i} className={i === arr.length - 1 ? 'font-semibold' : 'text-blue-700'}>{i === arr.length - 1 ? '▸ ' : '✓ '}{l.text}</li>
        ))}
      </ul>
    </div>
  );
}
