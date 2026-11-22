import { useEffect, useState } from 'react';
import { api, type AgentRow } from '../api';

/** The whole team, refreshed every second: who is working on what, and how each one's last job ended. Quietly keeps the old rows if the server blinks. */
export function useAgentsBoard(everyMs = 1000): AgentRow[] {
  const [rows, setRows] = useState<AgentRow[]>([]);
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const next = await api.agents();
        if (!stopped) setRows(next);
      } catch {
        // the backend may be restarting
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), everyMs);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [everyMs]);
  return rows;
}
