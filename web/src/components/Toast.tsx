import { useChat } from "@/stores/chatStore";

export function Toast() {
  const toast = useChat((s) => s.toast);
  if (!toast) return null;
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-brand-600 text-white text-xs px-4 py-2.5 rounded-full shadow-lg z-50 fade-in">
      {toast}
    </div>
  );
}
