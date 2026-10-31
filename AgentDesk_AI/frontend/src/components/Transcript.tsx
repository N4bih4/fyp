interface TranscriptProps {
  heard: string;
  lastCommand?: string;
  reply?: string | null;
  name: string;
}

/** Live words while the user speaks, then the command and the assistant's last reply. */
export function Transcript({ heard, lastCommand, reply, name }: TranscriptProps) {
  return (
    <div className="w-full rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm" data-testid="transcript">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Live transcript</p>
      <p aria-live="polite" className="mt-1 min-h-[1.5rem] text-slate-900" data-testid="transcript-heard">
        {heard ? <>“{heard}”</> : lastCommand ? <>You: “{lastCommand}”</> : <span className="text-slate-400">Say a command…</span>}
      </p>
      {reply && (
        <p className="mt-1 text-slate-700" data-testid="transcript-reply">
          <span className="font-medium">{name}:</span> {reply}
        </p>
      )}
    </div>
  );
}
