/**
 * Typed fetch client for the AgentDesk AI FastAPI backend.
 * Base URL points at the local backend; no secrets are ever stored here.
 */

export type TaskStatus =
  | 'created'
  | 'planned'
  | 'awaiting_approval'
  | 'awaiting_input'
  | 'approved'
  | 'executing'
  | 'completed'
  | 'waiting_retry'
  | 'failed'
  | 'cancelled'
  | 'rejected';

export type ActionStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'skipped'
  | 'cancelled';

export type RiskLevel = 'low' | 'medium' | 'high';

export interface ActionOut {
  id: string;
  seq: number;
  tool_name: string;
  args: Record<string, unknown>;
  risk: RiskLevel;
  status: ActionStatus;
  result?: unknown;
  verification?: unknown;
  error?: string | null;
}

export interface TaskOut {
  id: string;
  command: string;
  status: TaskStatus;
  plan_note?: string | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
  retry_at?: number | null;
  provider_note?: string | null;
  actions: ActionOut[];
}

export interface ConfigStatus {
  ai_provider: string;
  ai_model: string;
  ai_configured: boolean;
  mock_mode: boolean;
  groq_configured?: boolean;
  agent_max_steps?: number;
  fallback_provider?: string;
  fallback_configured?: boolean;
  local_commands?: boolean;
  cloud_mode?: string;
  browser_connected?: boolean;
  browser_profiles?: number;
  allowed_directories: string[];
  approved_applications: string[];
  platform: string;
}

export interface HealthOut {
  status: string;
  version: string;
}

// Use the page's own origin. Vite proxies API paths during development;
// the normal launcher serves both the UI and API from the backend.
const BASE_URL = '';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers ?? {}) },
    });
  } catch {
    throw new Error(
      'Backend se connection nahi ho raha. START_AGENT_X.cmd se project kholein; connection wapas aane par screen khud reconnect karegi.',
    );
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body);
    } catch {
      detail = await res.text().catch(() => '');
    }
    throw new Error(`Request failed (${res.status}): ${detail || res.statusText}`);
  }
  return (await res.json()) as T;
}

export const api = {
  replyTask: (id: string, message: string) => request<TaskOut>(`/tasks/${id}/reply`, { method: 'POST', body: JSON.stringify({ message }) }),

  health: () => request<HealthOut>('/health'),
  config: () => request<ConfigStatus>('/config/status'),

  createTask: (command: string, idempotency_key?: string, auto_approve?: boolean) =>
    request<TaskOut>('/tasks', {
      method: 'POST',
      body: JSON.stringify({
        command,
        ...(idempotency_key ? { idempotency_key } : {}),
        ...(auto_approve !== undefined ? { auto_approve } : {}),
      }),
    }),

  listTasks: (limit = 20) => request<TaskOut[]>(`/tasks?limit=${limit}`),

  getTask: (id: string) => request<TaskOut>(`/tasks/${id}`),

  approve: (id: string, action_ids?: string[]) =>
    request<TaskOut>(`/tasks/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ action_ids }),
    }),

  reject: (id: string, action_ids?: string[]) =>
    request<TaskOut>(`/tasks/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ action_ids }),
    }),

  run: (id: string) => request<TaskOut>(`/tasks/${id}/run`, { method: 'POST' }),

  cancel: (id: string) => request<TaskOut>(`/tasks/${id}/cancel`, { method: 'POST' }),
};
