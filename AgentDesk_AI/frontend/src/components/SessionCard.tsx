import { useEffect, useState } from 'react';
import { voiceApi, type TaskSessionState, type TaskOut } from '../api';

/** The open task: what it is about, where it is working, and each step with a tick (verified), a warning (ran, not verified) or a cross (failed). */
export function SessionCard({ activeTask }: { activeTask: TaskOut | null }) {
  const [session, setSession] = useState<TaskSessionState | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => voiceApi.session().then((s) => { if (alive) setSession(s); }).catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 4000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [activeTask?.id, activeTask?.status]);

  if (!session?.open) return null;
  const steps = (session.steps_done ?? []).slice(-6);
  return (
    <section aria-label="Open task" data-testid="session-card" className="rounded-xl border border-indigo-200 bg-indigo-50 p-4 text-sm shadow-sm">
      <div className="flex flex-wrap items-baseline gap-x-3">
        <h3 className="font-semibold text-indigo-900">Task open</h3>
        {session.goal && <span className="truncate text-indigo-800" data-testid="session-goal">{session.goal}</span>}
      </div>
      <p className="mt-1 text-xs text-indigo-700">
        {session.current_app ? <>In: <strong data-testid="session-app">{session.current_app}</strong>. </> : null}
        {session.current_folder ? <>Folder: <strong data-testid="session-folder">{session.current_folder}</strong>. </> : null}
        Say <em>"end task"</em>, <em>"that's all"</em> or <em>"bas"</em> to finish.
        {session.awaiting === 'end_task' && <strong className="ml-1 text-amber-700">Waiting: end this task?</strong>}
      </p>
      {steps.length > 0 && (
        <ul className="mt-2 space-y-0.5" data-testid="session-steps">
          {steps.map((s) => (
            <li key={s.key} className="flex items-center gap-2 text-xs text-slate-700">
              <span aria-hidden="true" className={s.ok ? (s.verified ? 'text-emerald-600' : 'text-amber-600') : 'text-red-600'}>{s.ok ? (s.verified ? '✓' : '!') : '✗'}</span>
              <span>{s.tool}</span>
              <span className="text-slate-500">{s.ok ? (s.verified ? 'checked on the PC' : 'ran, not checked') : 'failed'}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
