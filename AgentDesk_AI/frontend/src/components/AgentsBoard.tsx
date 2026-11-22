import type { AgentRow } from '../api';
import { useAgentsBoard } from '../hooks/useAgentsBoard';

const TOOL_WORDS: Record<string, string> = {
  open_application: 'opening an app', open_url: 'opening a website', web_search: 'searching', play_youtube_video: 'playing on YouTube',
  control_browser: 'controlling the browser', control_desktop: 'controlling the desktop', take_screenshot: 'taking a screenshot',
  manage_system_setting: 'changing a setting', ui_act: 'clicking on screen', screen_act: 'looking at the screen', drive_coding_agent: 'driving a coding agent',
  winget_uninstall: 'uninstalling an app', winget_install: 'installing an app', open_browser_profile: 'opening a browser profile',
};

function finishedWord(status: string): { text: string; tone: string } {
  if (status === 'completed') return { text: 'done', tone: 'text-emerald-700' };
  if (status === 'failed') return { text: 'failed', tone: 'text-red-700' };
  if (status === 'cancelled' || status === 'rejected') return { text: 'stopped', tone: 'text-slate-500' };
  return { text: status.replace(/_/g, ' '), tone: 'text-slate-500' };
}

export function AgentCard({ agent, onOpenTask }: { agent: AgentRow; onOpenTask?: (taskId: string) => void }) {
  const waiting = agent.busy && agent.status === 'awaiting_approval';
  const doing = agent.doing ?? '';
  const tool = agent.tool ? TOOL_WORDS[agent.tool] ?? agent.tool.replace(/_/g, ' ') : null;
  const last = agent.last ? finishedWord(agent.last.status) : null;
  return (
    <li
      data-testid={`agent-${agent.name}`}
      data-busy={agent.busy}
      className={`flex min-w-0 flex-col gap-1 rounded-lg border p-3 ${agent.busy ? 'border-blue-300 bg-blue-50' : 'border-slate-200 bg-slate-50'}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-full ${agent.busy ? 'animate-pulse bg-blue-600' : 'bg-slate-300'}`} />
          {agent.name}
          {agent.lead && <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-medium uppercase text-slate-600">lead</span>}
        </span>
        <span className="text-xs text-slate-500">{agent.busy ? `${agent.seconds}s` : 'free'}</span>
      </div>
      <p className="truncate text-xs text-slate-500">{agent.role}</p>
      {agent.lane && (
        <p data-testid={`lane-${agent.name}`} className="min-w-0 truncate text-xs text-slate-600" title={agent.lane.folder ?? agent.lane.app ?? agent.lane.label}>
          <span className={`mr-1 rounded px-1 py-0.5 text-[10px] font-semibold uppercase ${agent.lane.current ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>
            {agent.lane.current ? 'in this' : 'parked'}
          </span>
          {agent.lane.label}{agent.lane.folder ? `: ${agent.lane.folder}` : agent.lane.app ? `: ${agent.lane.app}` : ''} · {agent.lane.minutes_left} min left
          {agent.lane.waiting && <span className="ml-1 font-semibold text-amber-700">(waiting for your answer)</span>}
        </p>
      )}
      {agent.busy ? (
        <div className="min-w-0 text-sm text-slate-800">
          <span className="block truncate" title={doing}>{doing}</span>
          {waiting ? (
            <button
              type="button"
              onClick={() => agent.task_id && onOpenTask?.(agent.task_id)}
              className="mt-1 rounded bg-amber-500 px-2 py-0.5 text-xs font-semibold text-white hover:bg-amber-600"
            >
              Waiting for your OK: review
            </button>
          ) : (
            tool && <span className="text-xs text-blue-700">{tool}…</span>
          )}
        </div>
      ) : last && agent.last ? (
        <p className="min-w-0 truncate text-xs text-slate-500" title={agent.last.command}>
          <span className={`font-medium ${last.tone}`}>{last.text}</span>: {agent.last.command}
        </p>
      ) : (
        <p className="text-xs text-slate-400">Waiting for work</p>
      )}
    </li>
  );
}

/** The team board: every agent, who is working on which task right now (several at once), and how the last job of each one ended. */
export function AgentsBoard({ onOpenTask }: { onOpenTask?: (taskId: string) => void }) {
  const rows = useAgentsBoard();
  if (rows.length === 0) return null;
  const working = rows.filter((r) => r.busy).length;
  return (
    <section aria-label="Agents" className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">Agents</h2>
        <span data-testid="agents-working" className="text-sm text-slate-500">{working === 0 ? 'all free' : `${working} working`}</span>
      </div>
      <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {rows.map((a) => <AgentCard key={a.name} agent={a} onOpenTask={onOpenTask} />)}
      </ul>
    </section>
  );
}
