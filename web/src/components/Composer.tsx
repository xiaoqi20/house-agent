import { useRef, useState } from "react";
import {
  ArrowUp,
  FileText,
  Image as ImageIcon,
  Paperclip,
  X,
} from "lucide-react";
import { useChat } from "@/stores/chatStore";

interface PendingFile {
  file: File;
  previewUrl: string | null;
}

const IMAGE_RE = /^image\//;
const DOC_RE = /\.(pdf|txt)$/i;

function describe(f: File, idx: number): string {
  const name =
    f.name ||
    (IMAGE_RE.test(f.type) ? `粘贴图片-${idx + 1}.png` : "粘贴文件.txt");
  return `${name}（${Math.max(1, Math.round(f.size / 1024))} KB）`;
}

export function Composer() {
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const send = useChat((s) => s.send);
  const uploadFile = useChat((s) => s.uploadFile);
  const uploadImages = useChat((s) => s.uploadImages);
  const showToast = useChat((s) => s.showToast);

  const addFiles = (files: File[]) => {
    const accepted: PendingFile[] = [];
    for (const f of files) {
      if (IMAGE_RE.test(f.type) || DOC_RE.test(f.name)) {
        accepted.push({
          file: f,
          previewUrl: IMAGE_RE.test(f.type) ? URL.createObjectURL(f) : null,
        });
      } else {
        showToast(
          `「${f.name || f.type}」暂不支持，一期仅：PDF / TXT / 图片存档`,
        );
      }
    }
    if (accepted.length) setPending((p) => [...p, ...accepted]);
  };

  const removeFile = (i: number) =>
    setPending((p) => {
      URL.revokeObjectURL(p[i].previewUrl ?? "");
      return p.filter((_, idx) => idx !== i);
    });

  const submit = () => {
    if (pending.length) {
      const imgs = pending
        .filter((p) => IMAGE_RE.test(p.file.type))
        .map((p) => p.file);
      const docs = pending.filter((p) => !IMAGE_RE.test(p.file.type));
      if (imgs.length) uploadImages(imgs);
      docs.forEach((p) =>
        uploadFile(
          p.file,
          `${p.file.name || "粘贴文件.txt"}（${Math.max(1, Math.round(p.file.size / 1024))} KB）`,
        ),
      );
      setPending([]);
    }
    const text = draft.trim();
    if (text) {
      setDraft("");
      send(text);
    }
  };

  return (
    <div
      className={`bg-white border rounded-2xl shadow-[0_2px_12px_rgba(0,0,0,0.04)] p-2 transition-all ${
        dragOver
          ? "border-brand-400 ring-2 ring-brand-100"
          : "border-gray-200 focus-within:border-gray-400 focus-within:shadow-[0_2px_16px_rgba(0,0,0,0.08)]"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        addFiles(Array.from(e.dataTransfer.files));
      }}
    >
      {/* 附件预览区（输入框上方） */}
      {pending.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1.5 pt-1 pb-2">
          {pending.map((p, i) => (
            <div
              key={i}
              className="relative group bg-gray-50 border border-gray-200 rounded-xl px-2.5 py-2 flex items-center gap-2 max-w-[240px]"
            >
              {p.previewUrl ? (
                <img
                  src={p.previewUrl}
                  alt=""
                  className="w-10 h-10 rounded-lg object-cover border border-gray-200 shrink-0"
                />
              ) : (
                <div className="w-10 h-10 rounded-lg bg-red-50 border border-red-100 flex items-center justify-center text-red-500 shrink-0">
                  <FileText size={16} />
                </div>
              )}
              <div className="min-w-0">
                <div className="text-xs font-medium text-gray-800 truncate">
                  {describe(p.file, i).split("（")[0]}
                </div>
                <div className="text-[10px] text-gray-400">
                  {Math.max(1, Math.round(p.file.size / 1024))} KB ·
                  点击发送后上传
                </div>
              </div>
              <button
                onClick={() => removeFile(i)}
                className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-gray-700 text-white items-center justify-center hidden group-hover:flex"
                title="移除"
              >
                <X size={11} />
              </button>
            </div>
          ))}
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        multiple
        accept=".pdf,.txt,image/*"
        className="hidden"
        onChange={(e) => {
          addFiles(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      <textarea
        rows={2}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onPaste={(e) => {
          const files = Array.from(e.clipboardData?.files ?? []);
          if (files.length) {
            e.preventDefault();
            addFiles(files);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="上传合同、粘贴图片或文本，或直接问我任何租房问题…"
        className="w-full bg-transparent resize-none outline-none text-sm p-2 text-gray-800 placeholder-gray-400 custom-scrollbar max-h-40"
      />
      <div className="flex justify-between items-center px-1">
        <div className="flex gap-0.5">
          <button
            onClick={() => fileRef.current?.click()}
            title="上传文件（PDF / TXT / 图片）· 也支持直接粘贴或拖入"
            className="w-8 h-8 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
          >
            <Paperclip size={14} />
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            title="上传图片（拍照合同 · OCR 二期上线，先存档）"
            className="w-8 h-8 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 flex items-center justify-center transition-colors"
          >
            <ImageIcon size={14} />
          </button>
        </div>
        <button
          onClick={submit}
          className="bg-brand-500 hover:bg-brand-600 text-white rounded-xl px-4 py-2 text-[13px] font-medium shadow-sm transition-colors flex items-center gap-1.5"
        >
          {pending.length ? `发送并上传 ${pending.length} 个文件` : "发送"}{" "}
          <ArrowUp size={11} />
        </button>
      </div>
    </div>
  );
}
