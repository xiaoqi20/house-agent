import { useEffect, useState } from 'react';
import { useStore } from '../store';

export function Toast() {
  const toastState = useStore((s) => s.toast);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!toastState) return;
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), 2400);
    return () => clearTimeout(timer);
  }, [toastState?.key]);

  if (!toastState || !visible) return null;
  return (
    <div
      key={toastState.key}
      role="status"
      aria-live="polite"
      className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-xs px-4 py-2.5 rounded-full shadow-lg z-[60] fade-in"
    >
      {toastState.msg}
    </div>
  );
}
