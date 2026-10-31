import type { TaskOut } from './api';

/** What the assistant is doing right now; drives the orb animation and its spoken label. */
export type VoiceState =
  | 'idle'
  | 'listening'
  | 'transcribing'
  | 'thinking'
  | 'awaiting_approval'
  | 'awaiting_input'
  | 'executing'
  | 'verifying'
  | 'speaking'
  | 'error';

export interface VoiceInputs {
  listening: boolean;
  heard: string;
  submitting: boolean;
  speaking: boolean;
  task: TaskOut | null;
  error?: boolean;
}

export function deriveVoiceState({ listening, heard, submitting, speaking, task, error }: VoiceInputs): VoiceState {
  if (error) return 'error';
  if (speaking) return 'speaking';
  if (submitting) return 'thinking';
  if (task?.status === 'awaiting_approval') return 'awaiting_approval';
  if (task?.status === 'awaiting_input') return 'awaiting_input';
  if (task?.status === 'executing') {
    const actions = task.actions;
    // Every action already ran: the server is still checking the real outcome.
    const allRan = actions.length > 0 && actions.every((a) => a.status !== 'approved' && a.status !== 'pending');
    return allRan && !actions.some((a) => a.status === 'running') ? 'verifying' : 'executing';
  }
  if (task?.status === 'created' || task?.status === 'planned' || task?.status === 'approved') return 'thinking';
  if (listening && heard) return 'transcribing';
  if (listening) return 'listening';
  return 'idle';
}

export const STATE_LABEL: Record<VoiceState, string> = {
  idle: 'Ready',
  listening: 'Listening',
  transcribing: 'Hearing you',
  thinking: 'Thinking',
  awaiting_approval: 'Waiting for your approval',
  awaiting_input: 'Waiting for your answer',
  executing: 'Working',
  verifying: 'Checking the result',
  speaking: 'Speaking',
  error: 'Something went wrong',
};
