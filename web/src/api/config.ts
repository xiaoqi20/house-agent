/** API 连接配置：VITE_API_MODE=demo 时保持纯本地演示（像素回归用）。 */
export const API_MODE: 'api' | 'demo' =
  (import.meta.env.VITE_API_MODE as 'api' | 'demo' | undefined) ?? 'api';

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1';

export const RUN_TIMEOUT_MS = 180_000;
