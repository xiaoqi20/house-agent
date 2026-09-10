import { useEffect, useState } from 'react';

/**
 * 复刻原型抽屉的过渡行为：
 * 打开时先挂载再移除 translate-x-full（触发滑入），关闭时先加上 translate-x-full，300ms 后卸载。
 */
export function useDrawerTransition(open: boolean) {
  const [mounted, setMounted] = useState(false);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (open) {
      setMounted(true);
      const raf = requestAnimationFrame(() => setShown(true));
      return () => cancelAnimationFrame(raf);
    }
    setShown(false);
    const timer = setTimeout(() => setMounted(false), 300);
    return () => clearTimeout(timer);
  }, [open]);

  return { mounted, shown };
}
