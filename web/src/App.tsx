import { Route, Routes } from "react-router-dom";
import { ContractDrawer } from "@/components/ContractDrawer";
import { Sidebar } from "@/components/Sidebar";
import { Toast } from "@/components/Toast";
import { useChat } from "@/stores/chatStore";
import { Workbench } from "@/routes/Workbench";

export default function App() {
  const title = useChat((s) => s.title);

  return (
    <div className="h-screen flex bg-white text-gray-800 overflow-hidden">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-16 border-b border-gray-100 flex items-center justify-between px-6 shrink-0">
          <h2 className="text-[15px] font-semibold text-gray-900">{title}</h2>
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
            </span>
            本机演示 · 未做登录与数据隔离，结论不构成法律意见
          </div>
        </header>
        <Routes>
          <Route path="/" element={<Workbench />} />
        </Routes>
      </main>
      <ContractDrawer />
      <Toast />
    </div>
  );
}
