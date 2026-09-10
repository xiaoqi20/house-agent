import { useRef, useState } from 'react';
import { useStore } from '../store';
import type { House, SourceKey } from '../types';
import { SOURCE_LABEL, demoHouses, mkHouse, nextBatchId, parseHousesInput } from '../data/demo';
import { missingFields } from '../lib/calc';
import { esc } from '../lib/utils';
import {
  closeImport,
  confirmImport,
  doParseBatch,
  doParsePaste,
  fillDemoBatch,
  importHouseFile,
  isApiMode,
  setImportText,
  showConfirm,
  showImportFail,
  slicePendingImport,
  switchImportTab,
  updatePendingRow,
} from '../controller';

/** 真实解析进度（api 模式来自 SSE；demo 模式文件页沿用原有步骤动画） */
function ProgressBlock() {
  const progress = useStore((s) => s.importProgress);
  if (!progress) return null;
  return (
    <div className="bg-gray-50 border border-gray-100 rounded-2xl px-4 py-3.5 space-y-2 font-medium" id="fps">
      {progress.steps.map((s, j) => (
        <div
          key={j}
          className={`flex items-center gap-2.5 text-[13px] ${
            j < progress.index ? 'text-green-600' : j === progress.index ? 'text-gray-800' : 'text-gray-300'
          }`}
        >
          <i
            className={`fas ${
              j < progress.index ? 'fa-circle-check' : j === progress.index ? 'fa-circle-notch fa-spin' : 'fa-circle'
            } w-4 text-center`}
          ></i>{' '}
          {s}
        </div>
      ))}
    </div>
  );
}

type ManualForm = {
  name: string;
  region: string;
  rent: string;
  deposit: string;
  property: string;
  commute: string;
  layout: string;
  area: string;
  floor: string;
  available: string;
  bathroom: boolean;
  shared: boolean;
  pet: boolean;
};

const emptyManual: ManualForm = {
  name: '',
  region: '',
  rent: '',
  deposit: '',
  property: '',
  commute: '',
  layout: '',
  area: '',
  floor: '',
  available: '',
  bathroom: false,
  shared: false,
  pet: false,
};

function CiInput({
  index,
  field,
  label,
  value,
  type,
  empty,
  onChange,
}: {
  index: number;
  field: string;
  label: string;
  value: string;
  type: 'text' | 'number';
  empty: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <label className={`text-[10px] ${empty ? 'text-amber-600' : 'text-gray-400'}`}>
      {label}
      {empty ? '·待确认' : ''}
      <input
        id={`ci-${field}-${index}`}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="待确认"
        className={`mt-1 w-full bg-gray-50 border ${
          empty ? 'border-amber-200' : 'border-gray-200'
        } rounded-lg px-2.5 py-2 text-[12px] text-gray-800 outline-none focus:border-brand-400 focus:bg-white`}
      />
    </label>
  );
}

export function ImportModal() {
  const modal = useStore((s) => s.importModal);
  const texts = useStore((s) => s.importTexts);
  const rows = useStore((s) => s.pendingRows);
  const pendingTitle = useStore((s) => s.pendingTitle);
  const pendingCount = useStore((s) => s.pendingCount);
  const pendingSource = useStore((s) => s.pendingSource);
  const importFail = useStore((s) => s.importFail);
  const pendingError = useStore((s) => s.pendingError);
  const houses = useStore((s) => s.houses);

  const [manual, setManual] = useState<ManualForm>(emptyManual);
  const [manualError, setManualError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const fileTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const activeHouses = houses.filter((h) => h.status === 'active');
  const curCount = activeHouses.length;
  const totalCount = curCount + rows.length;

  const switchManual = (patch: Partial<ManualForm>) => setManual((m) => ({ ...m, ...patch }));

  const doManual = () => {
    if (!manual.name.trim()) {
      setManualError('请填写房源名称');
      return;
    }
    if (!manual.rent.trim()) {
      setManualError('请填写月租；如确实未知，可先通过「粘贴单条」录入原文并标记待确认');
      return;
    }
    setManualError('');
    const floorRaw = manual.floor;
    const orM = floorRaw.match(/([东西南北]+向)/);
    const h = mkHouse({
      source: 'manual',
      name: manual.name.trim(),
      region: manual.region.trim(),
      rent: manual.rent ? parseInt(manual.rent, 10) : null,
      deposit: manual.deposit,
      propertyFee: manual.property ? parseInt(manual.property, 10) : null,
      commuteMin: manual.commute ? parseInt(manual.commute, 10) : null,
      layout: manual.layout.trim(),
      area: manual.area ? parseFloat(manual.area) : null,
      floor: floorRaw.replace(/[东西南北]+向/, '').replace(/[·\s]+$/, ''),
      orientation: orM ? orM[1] : '',
      available: manual.available.trim(),
      bathroom: manual.bathroom ? true : null,
      shared: manual.shared,
      pet: manual.pet ? '允许宠物' : '',
      raw: '手动填写，无原始文本',
    });
    showConfirm([h], '手动填写');
  };

  const parseHouseFile = (file: File) => {
    if (isApiMode) {
      void importHouseFile(file);
      return;
    }
    const ext = (file.name.match(/\.([^.]+)$/) || [])[1]?.toLowerCase() || '';
    const kind: SourceKey = ['xlsx', 'xls'].includes(ext)
      ? 'file-xlsx'
      : ['docx', 'doc'].includes(ext)
        ? 'file-docx'
        : 'file-txt';
    const steps = [
      '上传文件（' + file.name + '）',
      kind === 'file-xlsx'
        ? '解析表格行列并映射字段'
        : kind === 'file-docx'
          ? '解析文档段落并识别房源条目'
          : '读取文本并识别房源条目',
      'AI 提取字段',
    ];
    if (fileTimer.current) clearInterval(fileTimer.current);
    useStore.setState({ importProgress: { steps, index: 0 } });
    let i = 0;
    fileTimer.current = setInterval(() => {
      i++;
      if (i >= steps.length) {
        if (fileTimer.current) clearInterval(fileTimer.current);
        fileTimer.current = null;
        useStore.setState({ importProgress: null });
        if (kind === 'file-txt') {
          const reader = new FileReader();
          reader.onload = () => {
            const list = parseHousesInput(String(reader.result || ''));
            if (!list.length) {
              showImportFail('file', '文件中未识别到有效房源条目，请确认每行包含租金或户型信息。');
              return;
            }
            const batchId = nextBatchId();
            list.forEach((h) => {
              h.source = kind;
              h.batch = batchId;
            });
            showConfirm(list, SOURCE_LABEL[kind] + '：' + file.name);
          };
          reader.onerror = () => showImportFail('file', '文件读取失败，请重试或改用粘贴。');
          reader.readAsText(file);
        } else {
          // Excel / Word：原型以演示解析呈现，产出可确认字段
          const list = demoHouses(kind).slice(0, 3);
          list.forEach((h) => {
            h.source = kind;
            if (!h.name.includes('演示解析')) h.name += '（演示解析）';
          });
          showConfirm(list, SOURCE_LABEL[kind] + '：' + file.name + '（演示解析）');
        }
      } else {
        useStore.setState({ importProgress: { steps, index: i } });
      }
    }, 550);
  };

  const isDemoFile =
    pendingSource.includes('演示解析') ||
    rows.some((r) => (r.house.source || '').includes('file-xls') || (r.house.source || '').includes('file-doc'));

  const panelClass = (name: string) => (modal.panel === name ? '' : 'hidden');

  return (
    <div
      id="importModal"
      className={`${modal.open ? '' : 'hidden'} fixed inset-0 z-50 flex items-center justify-center bg-black/30 fade-in p-4`}
      role="dialog"
      aria-modal="true"
      aria-labelledby="importModalTitle"
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col">
        <div className="flex items-center justify-between px-6 pt-5 pb-3 shrink-0">
          <div>
            <h3 className="text-[15px] font-semibold text-gray-900" id="importModalTitle">
              导入候选房源
            </h3>
            <p className="text-[11px] text-gray-400 mt-0.5">所有非结构化输入都会先经 AI 提取字段，由你确认后才加入候选</p>
          </div>
          <button
            onClick={closeImport}
            aria-label="关闭导入候选房源窗口"
            className="w-8 h-8 rounded-lg hover:bg-gray-100 text-gray-400 flex items-center justify-center"
          >
            <i className="fas fa-times"></i>
          </button>
        </div>
        <div className="flex gap-1 px-6 border-b border-gray-100 shrink-0 overflow-x-auto" id="importTabs">
          {(
            [
              ['paste', '粘贴单条'],
              ['manual', '手动填写'],
              ['batch', '批量粘贴'],
              ['file', '上传文件'],
            ] as Array<['paste' | 'manual' | 'batch' | 'file', string]>
          ).map(([tab, label]) => (
            <button
              key={tab}
              data-tab={tab}
              onClick={() => switchImportTab(tab)}
              className={`imp-tab ${
                modal.tab === tab ? 'active' : ''
              } px-3 py-2.5 text-[12px] font-medium text-gray-500 border-b-2 border-transparent -mb-px whitespace-nowrap`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-5" id="importBody">
          {/* 粘贴单条 */}
          <div data-panel="paste" className={panelClass('paste')}>
            <textarea
              id="impPasteText"
              rows={6}
              value={texts.paste}
              onChange={(e) => setImportText('paste', e.target.value)}
              className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-[13px] outline-none focus:border-gray-300 focus:bg-white placeholder:text-gray-400 custom-scrollbar"
              placeholder={
                '粘贴一条房源描述，例如：\n望京 南湖东园一区 南向一居 5800/月 押一付一 68.5平 12/18层 独立卫浴 地铁14号线望京站350米 通勤约35分钟 物业费房东承担 允许养猫 10月1日可入住'
              }
            ></textarea>
            <div className="mt-3">
              <ProgressBlock />
            </div>
            <div className="flex justify-end mt-3">
              <button
                onClick={() => doParsePaste(texts.paste)}
                className="bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium rounded-xl px-4 py-2.5 transition-colors"
              >
                <i className="fas fa-wand-magic-sparkles mr-1.5"></i>AI 提取字段
              </button>
            </div>
          </div>

          {/* 手动填写 */}
          <div data-panel="manual" className={panelClass('manual')}>
            <div className="grid grid-cols-2 gap-3" id="manualForm">
              <label className="text-[12px] text-gray-600">
                名称 / 小区
                <input
                  id="mf-name"
                  value={manual.name}
                  onChange={(e) => switchManual({ name: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="如：望京·南湖东园一居"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                区域
                <input
                  id="mf-region"
                  value={manual.region}
                  onChange={(e) => switchManual({ region: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="如：朝阳区 望京"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                月租（元）
                <input
                  id="mf-rent"
                  type="number"
                  value={manual.rent}
                  onChange={(e) => switchManual({ rent: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="5800"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                押金 / 付款方式
                <select
                  id="mf-deposit"
                  value={manual.deposit}
                  onChange={(e) => switchManual({ deposit: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                >
                  <option value="">待确认</option>
                  <option>押一付一</option>
                  <option>押一付三</option>
                  <option>押二付一</option>
                  <option>押一付六</option>
                  <option>无押金</option>
                </select>
              </label>
              <label className="text-[12px] text-gray-600">
                物业费（元/月，留空为待确认）
                <input
                  id="mf-property"
                  type="number"
                  value={manual.property}
                  onChange={(e) => switchManual({ property: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="120"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                通勤（分钟）
                <input
                  id="mf-commute"
                  type="number"
                  value={manual.commute}
                  onChange={(e) => switchManual({ commute: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="35"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                户型
                <input
                  id="mf-layout"
                  value={manual.layout}
                  onChange={(e) => switchManual({ layout: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="一居 / 两居合租次卧"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                面积（㎡）
                <input
                  id="mf-area"
                  type="number"
                  value={manual.area}
                  onChange={(e) => switchManual({ area: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="68.5"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                楼层 / 朝向
                <input
                  id="mf-floor"
                  value={manual.floor}
                  onChange={(e) => switchManual({ floor: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="12/18层 · 南向"
                />
              </label>
              <label className="text-[12px] text-gray-600">
                可入住时间
                <input
                  id="mf-available"
                  value={manual.available}
                  onChange={(e) => switchManual({ available: e.target.value })}
                  className="mt-1 w-full bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5 text-[13px] outline-none focus:border-gray-300 focus:bg-white"
                  placeholder="2026-10-01"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-4 mt-3 text-[12px] text-gray-600">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  id="mf-bathroom"
                  checked={manual.bathroom}
                  onChange={(e) => switchManual({ bathroom: e.target.checked })}
                  className="w-3.5 h-3.5 rounded border-gray-300 text-brand-500"
                />{' '}
                独立卫浴
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  id="mf-shared"
                  checked={manual.shared}
                  onChange={(e) => switchManual({ shared: e.target.checked })}
                  className="w-3.5 h-3.5 rounded border-gray-300 text-brand-500"
                />{' '}
                合租
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  id="mf-pet"
                  checked={manual.pet}
                  onChange={(e) => switchManual({ pet: e.target.checked })}
                  className="w-3.5 h-3.5 rounded border-gray-300 text-brand-500"
                />{' '}
                允许宠物
              </label>
            </div>
            {manualError && <div className="mt-3 text-[12px] text-red-500">{manualError}</div>}
            <div className="flex justify-end mt-4">
              <button
                onClick={doManual}
                className="bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium rounded-xl px-4 py-2.5 transition-colors"
              >
                <i className="fas fa-arrow-right mr-1.5"></i>生成待确认字段
              </button>
            </div>
          </div>

          {/* 批量粘贴 */}
          <div data-panel="batch" className={panelClass('batch')}>
            <textarea
              id="impBatchText"
              rows={7}
              value={texts.batch}
              onChange={(e) => setImportText('batch', e.target.value)}
              className="w-full bg-gray-50 border border-gray-200 rounded-xl px-4 py-3 text-[13px] outline-none focus:border-gray-300 focus:bg-white placeholder:text-gray-400 custom-scrollbar"
              placeholder="每行一条房源，或点击左下方按钮填入示例"
            ></textarea>
            <div className="mt-3">
              <ProgressBlock />
            </div>
            <div className="flex justify-between mt-3">
              <button onClick={fillDemoBatch} className="text-xs text-brand-600 hover:text-brand-700 font-medium">
                <i className="fas fa-circle-down mr-1"></i>填入 5 套演示房源
              </button>
              <button
                onClick={() => doParseBatch(texts.batch)}
                className="bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium rounded-xl px-4 py-2.5 transition-colors"
              >
                <i className="fas fa-wand-magic-sparkles mr-1.5"></i>AI 批量提取
              </button>
            </div>
          </div>

          {/* 上传文件 */}
          <div data-panel="file" className={panelClass('file')}>
            <input
              ref={fileRef}
              type="file"
              id="houseFileInput"
              accept=".xlsx,.xls,.docx,.doc,.txt,.csv,.md"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) parseHouseFile(f);
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              aria-label="点击选择房源文件"
              className="w-full text-left border-2 border-dashed border-gray-200 hover:border-brand-300 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded-2xl py-10 flex flex-col items-center justify-center cursor-pointer transition-colors group"
            >
              <i className="fas fa-cloud-arrow-up text-2xl text-gray-300 group-hover:text-brand-400 mb-3"></i>
              <div className="text-[13px] font-medium text-gray-700">点击选择房源文件</div>
              <div className="text-[11px] text-gray-400 mt-1.5">
                支持 Excel（.xlsx / .xls）、Word（.docx / .doc）、文本文件（.txt / .csv / .md）
              </div>
              <div className="text-[10px] text-gray-300 mt-1">图片与扫描件 OCR 为规划能力，暂不支持</div>
            </button>
            <div id="fileParseState" role="status" aria-live="polite" className="mt-4">
              <ProgressBlock />
            </div>
          </div>

          {/* 字段确认（解析后） */}
          <div data-panel="confirm" className={panelClass('confirm')}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-[13px] font-semibold text-gray-900" id="confirmTitle">
                {importFail ? '导入失败' : pendingTitle}
              </div>
              <button
                onClick={() => switchImportTab('batch')}
                className="text-xs text-gray-400 hover:text-gray-600"
              >
                <i className="fas fa-arrow-left mr-1"></i>返回重新导入
              </button>
            </div>
            <div className="text-[11px] text-amber-600 bg-amber-50 border border-amber-100 rounded-xl px-3 py-2 mb-3 flex items-start gap-1.5">
              <i className="fas fa-circle-info mt-0.5"></i>
              <span>
                请逐套确认或修改<b>租金、押金/付款方式、物业费、通勤、户型</b>；留空字段将标记为「待确认」，缺少租金/通勤等关键信息的房源将作为待完善候选保存，不会直接进入推荐比较。
              </span>
            </div>
            {pendingError && (
              <div className="mb-3 text-[12px] text-red-600 bg-red-50 border border-red-100 rounded-xl px-3.5 py-2.5 flex items-start gap-2">
                <i className="fas fa-triangle-exclamation mt-0.5 shrink-0"></i>
                <div>
                  <b>未能加入候选：</b>
                  {pendingError}
                </div>
              </div>
            )}
            <div id="confirmList" className="space-y-3">
              {importFail ? (
                <div className="text-center py-10">
                  <i className="fas fa-circle-exclamation text-3xl text-red-300 mb-3"></i>
                  <div className="text-[13px] text-gray-700 font-medium">未能加入候选房源</div>
                  <div className="text-[12px] text-gray-400 mt-1.5 max-w-sm mx-auto leading-relaxed">
                    {importFail.reason}
                  </div>
                  <button
                    onClick={() => switchImportTab(importFail.backTab)}
                    className="mt-4 text-xs bg-gray-900 text-white rounded-xl px-4 py-2.5"
                  >
                    返回修改重试
                  </button>
                </div>
              ) : (
                <>
                  {isDemoFile && (
                    <div className="mb-3 text-[12px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5 flex items-start gap-2">
                      <i className="fas fa-flask mt-0.5 text-amber-600 shrink-0"></i>
                      <div>
                        <b>原型演示解析提示：</b>当前前端原型未接入真实文件解析服务，已提取生成 <b>{rows.length} 套演示房源</b>，核对后可加入候选。
                      </div>
                    </div>
                  )}
                  {totalCount > 10 && (
                    <div className="mb-3 text-[12px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5 flex items-start gap-2">
                      <i className="fas fa-triangle-exclamation mt-0.5 text-amber-600 shrink-0"></i>
                      <div className="flex-1">
                        <div className="font-semibold">
                          候选上限与降级说明（当前已有 {curCount} 套，本次新增 {rows.length} 套，确认后达 {totalCount} 套）
                        </div>
                        <div className="text-[11px] text-amber-700 mt-0.5 leading-relaxed">
                          候选房源库允许保存超过 10 套房源，但<b>智能推荐与横向比较单次最多支持 10 套</b>。导入后若超过 10
                          套，需在房源库中移除或精简至 10 套以内再开始筛选。
                        </div>
                        {10 - curCount > 0 && rows.length > 10 - curCount && (
                          <div className="mt-2">
                            <button
                              type="button"
                              onClick={() => slicePendingImport(10 - curCount)}
                              className="text-[11px] font-medium bg-amber-200/70 hover:bg-amber-200 text-amber-900 rounded-lg px-2.5 py-1 transition-colors"
                            >
                              <i className="fas fa-scissors mr-1"></i>仅导入前 {10 - curCount} 套（凑满 10 套比较上限）
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                  {rows.map((r, i) => {
                    const h: House = r.house;
                    const dup =
                      (r.duplicateOf ? activeHouses.find((x) => x.id === r.duplicateOf) : undefined) ??
                      activeHouses.find(
                        (x) =>
                          x.rent === h.rent &&
                          x.rent != null &&
                          (x.name === h.name || (!!x.region && !!h.region && x.region === h.region)),
                      );
                    const miss = r.missing ?? missingFields(h);
                    return (
                      <div
                        key={i}
                        className={`border border-gray-200 rounded-2xl p-4 ${dup ? 'border-amber-300 bg-amber-50/40' : ''}`}
                      >
                        <div className="flex items-center gap-2 mb-3 flex-wrap">
                          <span className="text-[10px] font-bold text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">
                            #{i + 1}
                          </span>
                          <input
                            id={`ci-name-${i}`}
                            value={r.name}
                            onChange={(e) => updatePendingRow(i, { name: e.target.value })}
                            className="flex-1 min-w-[140px] text-[13px] font-semibold text-gray-900 bg-transparent border-b border-transparent hover:border-gray-200 focus:border-brand-400 outline-none px-1 py-0.5"
                            placeholder="房源名称"
                          />
                          {dup && (
                            <span className="text-[10px] font-semibold text-amber-600 bg-amber-100 border border-amber-200 rounded-full px-2 py-0.5">
                              <i className="fas fa-copy mr-1"></i>疑似与「{dup.name}」重复，确认时将跳过
                            </span>
                          )}
                          {miss.length ? (
                            <span className="text-[10px] text-amber-500">
                              待确认：{miss.slice(0, 4).join('、')}
                              {miss.length > 4 ? ' 等' : ''}
                            </span>
                          ) : (
                            <span className="text-[10px] text-green-600">
                              <i className="fas fa-check mr-0.5"></i>关键字段完整
                            </span>
                          )}
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                          <CiInput
                            index={i}
                            field="rent"
                            label="租金(元/月)"
                            value={r.rent}
                            type="number"
                            empty={h.rent == null}
                            onChange={(v) => updatePendingRow(i, { rent: v })}
                          />
                          <CiInput
                            index={i}
                            field="deposit"
                            label="押金/付款方式"
                            value={r.deposit}
                            type="text"
                            empty={!h.deposit}
                            onChange={(v) => updatePendingRow(i, { deposit: v })}
                          />
                          <CiInput
                            index={i}
                            field="property"
                            label="物业费(元/月)"
                            value={r.property}
                            type="number"
                            empty={h.propertyFee == null}
                            onChange={(v) => updatePendingRow(i, { property: v })}
                          />
                          <CiInput
                            index={i}
                            field="commute"
                            label="通勤(分钟)"
                            value={r.commute}
                            type="number"
                            empty={h.commuteMin == null}
                            onChange={(v) => updatePendingRow(i, { commute: v })}
                          />
                          <CiInput
                            index={i}
                            field="layout"
                            label="户型"
                            value={r.layout}
                            type="text"
                            empty={!h.layout}
                            onChange={(v) => updatePendingRow(i, { layout: v })}
                          />
                        </div>
                        {h.raw && h.raw !== '手动填写，无原始文本' && (
                          <div className="mt-2.5 text-[11px] text-gray-400 bg-gray-50 rounded-lg px-3 py-2 leading-relaxed">
                            <i className="fas fa-quote-left mr-1 text-[9px]"></i>原始内容：
                            <mark className="raw">
                              {esc(h.raw.slice(0, 90))}
                              {h.raw.length > 90 ? '…' : ''}
                            </mark>
                          </div>
                        )}
                        {r.evidence && Object.keys(r.evidence).length > 0 && (
                          <div className="mt-2.5 text-[11px] text-gray-400 bg-gray-50 rounded-lg px-3 py-2 leading-relaxed">
                            <div className="text-gray-400">
                              <i className="fas fa-fingerprint mr-1 text-[9px]"></i>字段依据（原文片段）
                            </div>
                            {Object.entries(r.evidence).map(([field, snippet]) => (
                              <div key={field} className="truncate">
                                <span className="text-gray-500">{field}</span>：{snippet}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </>
              )}
            </div>
            <div className="flex items-center justify-between mt-5 sticky bottom-0 bg-white pt-3 border-t border-gray-100">
              <span className="text-[11px] text-gray-400" id="confirmCount">
                {importFail ? '' : pendingCount}
              </span>
              <button
                onClick={confirmImport}
                className="bg-gray-900 hover:bg-gray-700 text-white text-xs font-medium rounded-xl px-5 py-2.5 transition-colors"
              >
                <i className="fas fa-check mr-1.5"></i>加入本次候选房源
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
