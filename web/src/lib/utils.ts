/** 通用工具函数（与原型脚本保持一致） */

let uid = 0;

export const nid = () => 'x' + ++uid;

export function esc(s: unknown): string {
  return String(s ?? '').replace(
    /[&<>"']/g,
    (c) =>
      ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
      })[c] as string,
  );
}

export const fmt = (n: number | null | undefined) =>
  n == null ? '' : Number(n).toLocaleString();

export function fmtSize(size: number): string {
  return size > 1048576
    ? (size / 1048576).toFixed(1) + ' MB'
    : Math.max(1, Math.round(size / 1024)) + ' KB';
}
