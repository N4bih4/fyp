import { useEffect, useRef, useState } from 'react';
import { api, voiceApi, type Catalog, type Preferences, type TaskOut } from './api';
import { accentFor, loadCustomImage } from './characters';
import { Avatar, moodFor } from './components/Avatar';
import { Orb } from './components/Orb';
import { expandPanel } from './desktop';
import { useAgentAnnouncer } from './hooks/useAgentAnnouncer';
import { useAppData } from './hooks/useAppData';
import { useSpokenReplies } from './hooks/useSpokenReplies';
import { useTasks } from './hooks/useTasks';
import { useVoiceCore } from './hooks/useVoiceCore';
import { useVoiceInput } from './hooks/useVoiceInput';
import { applyTheme, loadTheme } from './theme';
import { deriveVoiceState, STATE_LABEL } from './voiceState';

/**
 * Always-on-top mini window (?view=orb). It is also the microphone of the desktop app: it listens all the time (hands-free),
 * runs each spoken command and speaks the answer, so nothing has to be pressed. The small mic button mutes / unmutes it.
 * Click on the character expands the panel.
 */
export default function MiniOrb() {
  const [banner, setBanner] = useState<string | null>(null);
  const [voiceLanguage, setVoiceLanguage] = useState('auto');
  const [polled, setPolled] = useState<TaskOut | null>(null);
  const [offline, setOffline] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);

  const commandStartRef = useRef<(command: string) => void>(() => {});
  const commandFailedRef = useRef<() => void>(() => {});
  const toggleVoiceRef = useRef<() => void>(() => {});
  const backgroundStartedRef = useRef<() => void>(() => {});
  // Parallel agents: every spoken command becomes a background job, so the next one can start while this one still runs.
  const tasks = useTasks({
    setBanner, onCommandFailed: () => commandFailedRef.current(), onCommandStart: (c) => commandStartRef.current(c),
    background: true, onBackgroundStarted: () => backgroundStartedRef.current(),
  });
  const { config, prefs } = useAppData({ setBanner, setVoiceLanguage, loadHistory: tasks.loadHistory });
  const voice = useVoiceCore({ prefs: prefs as Preferences | null, config, voiceLanguage });
  const input = useVoiceInput({
    voice, prefs, voiceLanguage, setCommand: tasks.setCommand, setBanner,
    submittingRef: tasks.submittingRef, runCommandRef: tasks.runCommandRef,
  });
  const { earlyAck } = useSpokenReplies({ voice, activeTask: tasks.activeTask, prefs, voiceLanguage, beginFollowUp: input.beginFollowUp });
  commandStartRef.current = earlyAck;
  commandFailedRef.current = () => {
    if (!voice.voiceWaitingForTaskRef.current) return;
    voice.voiceWaitingForTaskRef.current = false;
    voice.voiceTaskActiveRef.current = false;
    if (voice.handsFreeRef.current) {
      voice.voiceRestartRef.current = window.setTimeout(() => {
        voice.voiceRestartRef.current = null;
        voice.drainVoiceQueueRef.current();
        voice.startListeningRef.current();
      }, 1500);
    }
  };
  toggleVoiceRef.current = input.toggleVoiceInput;
  backgroundStartedRef.current = () => {
    voice.voiceWaitingForTaskRef.current = false;
    voice.voiceTaskActiveRef.current = false;
    voice.drainVoiceQueueRef.current();
  };
  const { working } = useAgentAnnouncer({ voice, prefs, activeTaskId: tasks.activeTask?.id ?? null });

  useEffect(() => {
    document.body.classList.add('mini-orb');
    applyTheme(loadTheme());
    void voiceApi.catalog().then(setCatalog).catch(() => {});
    // The tray menu ("Start / stop listening") calls this in the orb window.
    (window as unknown as { __agentx?: unknown }).__agentx = { toggleVoice: () => toggleVoiceRef.current(), openView: () => {} };
    // Tasks started from the panel are still shown here.
    const poll = async () => {
      try {
        const [latest] = await api.listTasks(1);
        setPolled(latest ?? null);
        setOffline(false);
      } catch {
        setOffline(true);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => window.clearInterval(timer);
  }, []);

  // Always listening: start by itself once the app is ready (Settings > Listen mode > Off turns it off).
  const startedRef = useRef(false);
  useEffect(() => {
    if (startedRef.current || !prefs || !config || prefs.listen_mode === 'off') return;
    startedRef.current = true;
    if (!voice.handsFreeRef.current) toggleVoiceRef.current();
  }, [prefs, config]);

  const task = tasks.activeTask ?? polled;
  const state = deriveVoiceState({
    listening: voice.listening, heard: voice.heard, submitting: tasks.submitting, speaking: voice.speaking, task, error: offline,
  });
  const needsApproval = task?.status === 'awaiting_approval';
  const muted = !voice.handsFree;
  const caption = voice.heard || (muted ? 'Mic off' : working.map((a) => a.name).join(' · '));
  const label = `${prefs?.persona.name ?? 'Agent X'}: ${STATE_LABEL[state]}${muted ? ' (microphone off)' : ''}. Press to open the panel`;
  const accent = prefs ? accentFor(prefs.persona, catalog) : '#38E1FF';
  return (
    <main className="flex h-screen flex-col items-center justify-center gap-1" aria-label="Agent X mini orb" title={banner ?? undefined}>
      {prefs?.persona.show_avatar !== false && prefs ? (
        <button type="button" data-testid="orb" data-state={state} aria-label={label} title={label}
          onClick={() => void expandPanel()}
          className="relative rounded-full outline-none focus-visible:ring-4 focus-visible:ring-blue-300"
          style={{ filter: `drop-shadow(0 0 ${state === 'idle' ? 6 : 12}px ${accent})`, opacity: muted ? 0.55 : 1 }}>
          <Avatar id={prefs.persona.avatar_id} color={accent} mood={moodFor(state)} size={72}
            image={prefs.persona.avatar_id === 'custom' ? loadCustomImage() : null} label={label} />
          {needsApproval && (
            <span role="status" data-testid="mini-approval"
              className="absolute -top-1 -right-1 rounded-full bg-amber-100 px-1.5 text-[10px] font-bold text-amber-800 ring-1 ring-amber-300">
              Approve?
            </span>
          )}
        </button>
      ) : (
        <Orb state={state} size="mini" color={prefs?.persona.orb_color} name={prefs?.persona.name}
          onActivate={() => void expandPanel()} activateHint="Press to open the panel" />
      )}
      <button type="button" data-testid="orb-mic" onClick={() => input.toggleVoiceInput()}
        aria-label={muted ? 'Microphone is off. Press to listen' : 'Listening. Press to mute'} title={muted ? 'Mic off: press to listen' : 'Listening: press to mute'}
        className={`rounded-full px-2 text-[11px] font-semibold ring-1 ${muted ? 'bg-slate-200 text-slate-600 ring-slate-400' : 'bg-emerald-100 text-emerald-800 ring-emerald-300'}`}>
        {muted ? 'Mic off' : 'Listening'}
      </button>
      {caption && !muted && (
        <p className="line-clamp-2 max-w-[120px] break-words rounded bg-black/55 px-1 text-center text-[10px] leading-tight text-white" data-testid="orb-heard">{caption}</p>
      )}
    </main>
  );
}
