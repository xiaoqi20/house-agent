import { API_BASE } from './config';
import type { WorkspaceDto } from './types';

export class ApiError extends Error {
  code: string;
  hint: string;
  status: number;

  constructor(status: number, code: string, message: string, hint = '') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.hint = hint;
  }
}

async function request<T>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const isForm = body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: isForm || body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: isForm ? body : body === undefined ? undefined : JSON.stringify(body),
    ...init,
  });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const error = (payload as { error?: { code?: string; message?: string; hint?: string } }).error ?? {};
    throw new ApiError(response.status, error.code ?? 'HTTP_ERROR', error.message ?? `请求失败（${response.status}）`, error.hint ?? '');
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
};

export function createWorkspace(): Promise<WorkspaceDto> {
  return request<WorkspaceDto>('POST', '/workspaces');
}

export interface HealthDto {
  ok: boolean;
  db: string;
  llm_provider: string;
  version: string;
}

/** /healthz 不在 /api/v1 前缀下，单独走一次 fetch。 */
export async function health(): Promise<HealthDto> {
  const root = API_BASE.replace(/\/api\/v1$/, '');
  const response = await fetch(`${root}/healthz`);
  if (!response.ok) throw new ApiError(response.status, 'HEALTH_FAILED', '服务不可用');
  return (await response.json()) as HealthDto;
}
