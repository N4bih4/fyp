import { useEffect, useRef, useState } from 'react';
import { api, voiceApi, type AgentRow, type Preferences } from '../api';
import type { VoiceCore } from './useVoiceCore';

interface Params {
  voice: VoiceCore;
  prefs: Preferences | null;
  /** The task the normal spoken reply already handles; the announcer never repeats it. */
  activeTaskId: string | null;
}

/**
 * Parallel agents: watches who is busy and, when an agent finishes a job that is not the one being answered normally,
 * says it ("Scout: ..."). Returns the agents that are working now, for the orb.
 */
export function useAgentAnnouncer({ voice: v, prefs, activeTaskId }: Params) {
  const [working, setWorking] = useState<AgentRow[]>([]);
  const seen = useRef(new Map<string, { task: string; agent: string }>());   // agent name -> the job it was busy with
  const activeRef = useRef<string | null>(null);
  activeRef.current = activeTaskId;
  const queue = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => {
    let stopped = false;
    const speak = (agent: string, taskId: string) => {
      queue.current = queue.current.then(async () => {
        if (!v.speechReadyRef.current || prefs?.persona.speak_replies === false) return;
        try {
          const task = await api.getTask(taskId);
          const line = await voiceApi.line({ task, ...v.wording() });
          while (v.voiceSpeakingRef.current && !stopped) await new Promise((r) => window.setTimeout(r, 400));   // never talk over a normal reply
          await v.playerRef.current?.speak(`${agent}: ${line}`);
        } catch {
          // an announcement is optional
        }
      });
    };
    const poll = async () => {
      try {
        const rows = await api.agents();
        if (stopped) return;
        setWorking(rows.filter((r) => r.busy));
        for (const row of rows) {
          const before = seen.current.get(row.name);
          if (row.busy && row.task_id) seen.current.set(row.name, { task: row.task_id, agent: row.name });
          else if (before) {
            seen.current.delete(row.name);
            if (before.task !== activeRef.current) speak(row.name, before.task);
          }
        }
      } catch {
        // the backend may be restarting
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [prefs?.persona.speak_replies]);

  return { working };
}
