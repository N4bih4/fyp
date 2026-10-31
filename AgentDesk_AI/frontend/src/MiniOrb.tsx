import { useEffect, useState } from 'react';
import { api, type Preferences, type TaskOut } from './api';
import { Orb } from './components/Orb';
import { expandPanel } from './desktop';
import { deriveVoiceState } from './voiceState';

/** Always-on-top mini window (?view=orb): shows the latest task's state; click expands the panel. */
export default function MiniOrb() {
  const [task, setTask] = useState<TaskOut | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    document.body.classList.add('mini-orb');
    void api.preferences().then(setPrefs).catch(() => {});
    const poll = async () => {
      try {
        const [latest] = await api.listTasks(1);
        setTask(latest ?? null);
        setOffline(false);
      } catch {
        setOffline(true);
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => window.clearInterval(timer);
  }, []);

  const state = deriveVoiceState({ listening: false, heard: '', submitting: false, speaking: false, task, error: offline });
  return (
    <main className="flex h-screen items-center justify-center" aria-label="Agent X mini orb">
      <Orb state={state} size="mini" color={prefs?.persona.orb_color} name={prefs?.persona.name}
        onActivate={() => void expandPanel()} activateHint="Press to open the panel" />
    </main>
  );
}
