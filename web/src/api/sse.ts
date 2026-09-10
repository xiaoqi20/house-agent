/** SSE 订阅：解析 run 事件，按 run_id 过滤（PRD §9.2 任务隔离），支持取消与重连。 */

import { API_BASE, RUN_TIMEOUT_MS } from './config';
import { ApiError } from './client';
import type { RunEventDto } from './types';

const TERMINAL = new Set(['done', 'error', 'cancelled']);

export function isTerminal(event: RunEventDto): boolean {
  return TERMINAL.has(event.type);
}

export interface SubscribeOptions {
  /** 外部取消（切换会话/房源时调用） */
  signal?: AbortSignal;
  /** 断线重连用 */
  lastEventId?: string;
  onEvent?: (event: RunEventDto) => void;
  timeoutMs?: number;
}

/**
 * 订阅运行事件直到终态。
 * 分帧必须用 /\r?\n\r?\n/：sse-starlette 用 \r\n，FastAPI 内置 SSE 用 \n，
 * 只认其中一种就会永远收不到事件（一期踩过的坑）。心跳注释帧（": ping"）没有 data 行，直接跳过。
 */
export async function waitRun(runId: string, options: SubscribeOptions = {}): Promise<RunEventDto | null> {
  const { signal, lastEventId, onEvent, timeoutMs = RUN_TIMEOUT_MS } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  let terminal: RunEventDto | null = null;
  let buffer = '';

  try {
    const response = await fetch(`${API_BASE}/runs/${runId}/events`, {
      headers: lastEventId ? { 'Last-Event-ID': lastEventId } : undefined,
      signal: controller.signal,
    });
    if (!response.ok || !response.body) {
      const text = await response.text().catch(() => '');
      let code = 'RUN_STREAM_FAILED';
      let message = `订阅运行失败（${response.status}）`;
      try {
        const parsed = JSON.parse(text) as { error?: { code?: string; message?: string } };
        code = parsed.error?.code ?? code;
        message = parsed.error?.message ?? message;
      } catch {
        /* 非 JSON 错误体，保留默认文案 */
      }
      throw new ApiError(response.status, code, message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? '';
      for (const frame of frames) {
        const dataLine = frame
          .split(/\r?\n/)
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('');
        if (!dataLine) continue;
        let event: RunEventDto;
        try {
          event = JSON.parse(dataLine) as RunEventDto;
        } catch {
          continue;
        }
        if (event.run_id && event.run_id !== runId) continue; // 迟到/串线事件直接丢弃
        onEvent?.(event);
        if (isTerminal(event)) {
          terminal = event;
          await reader.cancel().catch(() => undefined);
          return terminal;
        }
      }
    }
    return terminal;
  } catch (error) {
    if ((error as Error).name === 'AbortError') return terminal;
    throw error;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

/** 发起取消（停止生成 / 切换会话） */
export async function cancelRun(runId: string): Promise<void> {
  await fetch(`${API_BASE}/runs/${runId}/cancel`, { method: 'POST' }).catch(() => undefined);
}
