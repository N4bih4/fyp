import type { FormEvent } from 'react';
import type { ActionOut, TaskOut } from '../api';
import { useFocusTrap } from './useFocusTrap';

const RISK_STYLE: Record<ActionOut['risk'], { border: string; badge: string; text: string }> = {
  low: { border: 'border-emerald-400', badge: 'bg-emerald-100 text-emerald-900', text: 'Low risk: opens or reads something.' },
  medium: { border: 'border-amber-400', badge: 'bg-amber-100 text-amber-900', text: 'Medium risk: changes files or settings. Can usually be undone.' },
  high: { border: 'border-red-500', badge: 'bg-red-100 text-red-900', text: 'High risk: deletes, overwrites, downloads or sends input. Needs your click.' },
};

const TARGET_KEYS: [string, string][] = [
  ['path', 'Location'], ['source', 'From'], ['destination', 'To'], ['folder_path', 'Folder'], ['zip_path', 'Archive'],
  ['url', 'Website'], ['app_name', 'App'], ['target_window', 'Window'], ['query', 'Search'], ['to', 'Email to'],
  ['new_name', 'New name'], ['setting', 'Setting'], ['action', 'Action'], ['value', 'Value'], ['page', 'Settings page'],
];

/** Human-readable targets of an action: what exactly will be touched. */
export function actionTargets(action: ActionOut): { label: string; value: string }[] {
  const args = action.args ?? {};
  const out: { label: string; value: string }[] = [];
  for (const [key, label] of TARGET_KEYS) {
    const value = args[key];
    if (value === undefined || value === null || value === '') continue;
    out.push({ label, value: String(value) });
  }
  if (Array.isArray(args.steps)) {
    out.push({ label: 'Steps', value: (args.steps as { action?: string }[]).map((s) => s.action ?? '?').join(', ') });
  }
  if (args.include_contents === true) out.push({ label: 'Includes', value: 'everything inside the folder' });
  return out;
}

export function actionTitle(tool: string): string {
  return tool.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

interface ActionPreviewProps {
  task: TaskOut;
  busy: boolean;
  reply: string;
  onReplyChange: (value: string) => void;
  onReplySubmit: (e: FormEvent) => void;
  onApprove: (actionIds: string[]) => void;
  onReject: () => void;
  micLabel?: string;
  onMic?: () => void;
}

/** Approval dialog: one card per pending action with risk colour, exact targets, approve / reject. */
export function ActionPreview({ task, busy, reply, onReplyChange, onReplySubmit, onApprove, onReject, micLabel, onMic }: ActionPreviewProps) {
  const pending = task.actions.filter((a) => a.status === 'pending').sort((a, b) => a.seq - b.seq);
  const ref = useFocusTrap<HTMLElement>(true, busy ? undefined : onReject);
  const highest = pending.some((a) => a.risk === 'high') ? 'high' : pending.some((a) => a.risk === 'medium') ? 'medium' : 'low';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <section
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirmation-title"
        aria-describedby="confirmation-help"
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        data-testid="action-preview"
      >
        <h2 id="confirmation-title" className="text-xl font-semibold">Shall I do this?</h2>
        <p id="confirmation-help" className="mt-1 text-sm text-slate-600">
          “{task.command}” — review exactly what will be touched. Esc rejects.
        </p>
        {task.plan_note && /click|Approve/.test(task.plan_note) && (
          <p role="status" className="mt-2 rounded bg-amber-50 p-2 text-sm text-amber-900" data-testid="preview-note">{task.plan_note}</p>
        )}
        <ul className="mt-3 flex flex-col gap-3" aria-label="Actions waiting for approval">
          {pending.map((a) => {
            const style = RISK_STYLE[a.risk];
            return (
              <li key={a.id} className={`rounded-lg border-l-4 ${style.border} border border-slate-200 p-3`} data-testid="preview-card" data-risk={a.risk}>
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold">{actionTitle(a.tool_name)}</p>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${style.badge}`}>{a.risk} risk</span>
                </div>
                <p className="mt-1 text-xs text-slate-600">{style.text}</p>
                <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                  {actionTargets(a).map((t) => (
                    <div key={t.label + t.value} className="contents">
                      <dt className="font-medium text-slate-500">{t.label}</dt>
                      <dd className="break-all font-mono text-slate-900">{t.value}</dd>
                    </div>
                  ))}
                </dl>
                {pending.length > 1 && (
                  <button type="button" disabled={busy} onClick={() => onApprove([a.id])}
                    className="mt-2 rounded border border-emerald-600 px-3 py-1 text-sm text-emerald-800 disabled:opacity-50"
                    aria-label={`Approve only: ${actionTitle(a.tool_name)}`}>
                    Approve only this
                  </button>
                )}
              </li>
            );
          })}
        </ul>
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" data-autofocus={highest === 'high' ? undefined : true} disabled={busy}
            onClick={() => onApprove(pending.map((a) => a.id))}
            className="rounded-lg bg-emerald-700 px-4 py-2 font-semibold text-white disabled:opacity-50">
            {pending.length > 1 ? 'Approve all' : 'Approve'}
          </button>
          <button type="button" data-autofocus={highest === 'high' ? true : undefined} disabled={busy} onClick={onReject}
            className="rounded-lg border border-red-300 px-4 py-2 font-semibold text-red-700 disabled:opacity-50">
            Reject
          </button>
          {onMic && (
            <button type="button" disabled={busy} onClick={onMic} className="rounded-lg border px-4 py-2">{micLabel}</button>
          )}
        </div>
        <form className="mt-4 flex gap-2" onSubmit={onReplySubmit}>
          <label htmlFor="confirmation-reply" className="sr-only">Reply: yes, no, or a corrected path</label>
          <input id="confirmation-reply" value={reply} onChange={(e) => onReplyChange(e.target.value)}
            className="min-w-0 flex-1 rounded border p-2" placeholder="Or type: yes / no / a corrected path" />
          <button disabled={busy} className="rounded bg-blue-700 px-3 text-white disabled:opacity-50">Reply</button>
        </form>
      </section>
    </div>
  );
}
