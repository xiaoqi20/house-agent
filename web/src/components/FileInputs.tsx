import { addPendingAttachment } from '../controller';

/** 全局隐藏文件输入：合同 PDF / 文本 走「附件暂存」流程 */
export function FileInputs() {
  return (
    <input
      type="file"
      id="fileInput"
      accept=".pdf,.txt"
      className="hidden"
      onChange={(e) => {
        const f = e.target.files?.[0];
        e.target.value = '';
        if (f) addPendingAttachment(f);
      }}
    />
  );
}
