import type { KeyboardEvent } from 'react';
import type { OrbColor } from '../api';
import { STATE_LABEL, type VoiceState } from '../voiceState';

const COLORS: Record<OrbColor, string> = {
  indigo: 'from-indigo-400 via-indigo-600 to-violet-700',
  emerald: 'from-emerald-300 via-emerald-500 to-teal-700',
  rose: 'from-rose-300 via-rose-500 to-pink-700',
  amber: 'from-amber-200 via-amber-400 to-orange-600',
  slate: 'from-slate-300 via-slate-500 to-slate-700',
};

interface OrbProps {
  state: VoiceState;
  color?: OrbColor;
  size?: 'mini' | 'full';
  name?: string;
  onActivate?: () => void;
  activateHint?: string;
}

/** The assistant's presence. One animation per voice state; the state is also announced as text. */
export function Orb({ state, color = 'indigo', size = 'full', name = 'Agent X', onActivate, activateHint }: OrbProps) {
  const dimension = size === 'mini' ? 'h-16 w-16' : 'h-28 w-28';
  const label = `${name}: ${STATE_LABEL[state]}${activateHint ? `. ${activateHint}` : ''}`;
  const onKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      onActivate?.();
    }
  };
  return (
    <div className="flex flex-col items-center gap-2">
      <button
        type="button"
        onClick={onActivate}
        onKeyDown={onKey}
        aria-label={label}
        title={label}
        data-testid="orb"
        data-state={state}
        className={`orb orb-${state} relative ${dimension} rounded-full bg-gradient-to-br ${COLORS[color]} shadow-lg outline-none focus-visible:ring-4 focus-visible:ring-blue-300`}
      >
        <span className="orb-ring" aria-hidden="true" />
        <span className="orb-core" aria-hidden="true" />
      </button>
      {size === 'full' && (
        <p className="text-sm font-medium text-slate-700" aria-live="polite" data-testid="orb-label">
          {STATE_LABEL[state]}
        </p>
      )}
    </div>
  );
}
