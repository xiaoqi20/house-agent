import { useStore } from '../store';
import { closeModal, confirmModal } from '../controller';

export function ConfirmModal() {
  const modal = useStore((s) => s.confirmModal);
  if (!modal.open) return null;
  return (
    <div id="modal" className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 fade-in">
      <div className="bg-white rounded-2xl p-6 w-[340px] shadow-2xl mx-4">
        <div className="w-10 h-10 rounded-full bg-red-50 text-red-500 flex items-center justify-center mb-4">
          <i className="fas fa-trash-can text-sm"></i>
        </div>
        <h3 className="text-[15px] font-semibold text-gray-900" id="modalTitle">
          {modal.title}
        </h3>
        <p className="text-[13px] text-gray-500 mt-1.5 leading-relaxed" id="modalDesc">
          {modal.desc}
        </p>
        <div className="flex gap-2.5 mt-6">
          <button
            onClick={closeModal}
            className="flex-1 border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-xl py-2.5 text-[13px] font-medium transition-colors"
          >
            取消
          </button>
          <button
            onClick={confirmModal}
            className="flex-1 bg-red-500 hover:bg-red-600 text-white rounded-xl py-2.5 text-[13px] font-medium transition-colors"
            id="modalConfirmBtn"
          >
            {modal.okText || '删除'}
          </button>
        </div>
      </div>
    </div>
  );
}
