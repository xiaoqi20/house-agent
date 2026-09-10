import { useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { ChatView } from './components/ChatView';
import { HousesView } from './components/HousesView';
import { ContractsView } from './components/ContractsView';
import { HouseDrawer } from './components/HouseDrawer';
import { ContractDrawer } from './components/ContractDrawer';
import { ImportModal } from './components/ImportModal';
import { PrefsModal } from './components/PrefsModal';
import { ConfirmModal } from './components/ConfirmModal';
import { Toast } from './components/Toast';
import { FileInputs } from './components/FileInputs';
import { useStore } from './store';
import { bootstrap, closeContract, closeHouseDrawer } from './controller';

export default function App() {
  const currentView = useStore((s) => s.currentView);

  // api 模式：启动时探测服务并加载本次工作台（demo 模式不做任何事）
  useEffect(() => {
    void bootstrap();
  }, []);

  // 与原型一致：Esc 优先关闭房源抽屉，其次关闭合同抽屉
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      const s = useStore.getState();
      if (s.houseDrawer.open) closeHouseDrawer();
      else if (s.contractDrawer.open) closeContract();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="bg-white text-gray-800 overflow-hidden h-full flex">
      <Sidebar />
      <main className="flex-1 flex flex-col min-w-0 bg-white">
        <Header />
        <ChatView visible={currentView === 'chat'} />
        <HousesView visible={currentView === 'houses'} />
        <ContractsView visible={currentView === 'contracts'} />
      </main>
      <HouseDrawer />
      <ContractDrawer />
      <ImportModal />
      <PrefsModal />
      <ConfirmModal />
      <Toast />
      <FileInputs />
    </div>
  );
}
