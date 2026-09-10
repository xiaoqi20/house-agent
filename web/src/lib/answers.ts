import type { Contract, House } from '../types';
import type { AnswerDto } from '../api/types';
import { esc, fmt } from './utils';

/** 引用角标：使用 data 属性，由消息容器统一代理点击（定位合同原文） */
const cite = (clauseId: number, cid: string, label?: string) =>
  `<button type="button" data-cite="${clauseId}" data-cid="${cid}" class="cite-chip"><i class="fas fa-quote-left text-[8px]"></i>${
    label || '第 ' + clauseId + ' 条'
  }</button>`;

const ANSWER_MODE_NOTE: Record<AnswerDto['mode'], string> = {
  context: '',
  house_only: '仅基于当前房源信息，没有可引用的合同条款',
  general: '当前未绑定合同上下文，以上为通用建议',
  refusal: '这个问题缺少可核实依据，我没有给出结论',
  out_of_scope: '超出租房决策范围',
};

/** 服务端回答 → 消息 HTML：正文 + 可点引用 chip + 追问 + 依据来源 */
export function answerHTML(answer: AnswerDto): string {
  const citations = (answer.citations ?? []).filter((c) => c.clause_no != null);
  const cites = citations.length
    ? `<div class="flex flex-wrap gap-1.5 mt-2.5">${citations
        .map((c) =>
          cite(
            Number(c.clause_no),
            c.contract_id ?? '',
            `${c.label || '第 ' + c.clause_no + ' 条'}${c.page ? ' · P' + c.page : ''}`,
          ),
        )
        .join('')}</div>`
    : '';
  const followups = (answer.followups ?? []).length
    ? `<div class="flex flex-wrap gap-1.5 mt-2">${answer.followups
        .map(
          (f) =>
            `<button type="button" data-followup="${esc(f)}" class="text-[11px] bg-white border border-gray-200 hover:border-brand-300 hover:text-brand-600 text-gray-600 rounded-full px-3 py-1.5 transition-colors">${esc(f)}</button>`,
        )
        .join('')}</div>`
    : '';
  const sources = (answer.sources ?? []).length
    ? `<div class="text-[11px] text-gray-400 mt-2"><i class="fas fa-book-open mr-1 text-[9px]"></i>依据来源：${answer.sources
        .map((s) => esc(s))
        .join('、')} · 不构成法律结论</div>`
    : '';
  const note = ANSWER_MODE_NOTE[answer.mode] ?? '';
  const modeNote = note
    ? `<div class="text-[11px] text-gray-400 mt-2"><i class="fas fa-circle-info mr-1 text-[9px]"></i>${note}</div>`
    : '';
  return `<div class="text-[14px] text-gray-800 leading-7 answer-stream">${answer.html}${cites}${followups}${sources}${modeNote}</div>`;
}

export const KNOWLEDGE_ANSWER = `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-book-open text-brand-600"></i> 租房知识 · 通用建议（当前无房源 / 合同上下文）</p>
      这个问题我可以帮你拆解。为了给出更贴合的建议，可以补充一下：你所在的<b>城市</b>、目前处于<b>看房 / 已签约 / 租住中 / 退租</b>哪个阶段？<br><br>
      如果手里有候选房源或合同，也可以先导入 / 绑定，我会结合具体内容回答。`;

/** 上下文租房常识问答（与原型口径一致：优先引用合同与房源，找不到依据时降级为通用建议） */
export function answerFor(
  text: string,
  houseInput: House | null | undefined,
  contractInput: Contract | null | undefined,
): string {
  const h = houseInput ?? null;
  const c = contractInput ?? null;
  if (/买房|房价|走势|预测/.test(text)) {
    return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-circle-minus text-gray-400"></i> 超出当前能力范围</p>
          我专注于<b>租房决策</b>（候选房源比较、合同核验、租房常识），不做房价走势预测——这类问题缺乏可核实的依据，我不想给你看似确定的误导性结论。`;
  }
  if (/法律|法规|民法典|政策|规定/.test(text)) {
    return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-scale-balanced text-brand-600"></i> 法规政策 · 请注意适用范围</p>
          与租房最相关的是《中华人民共和国民法典》合同编租赁合同章节（第 703—734 条），例如第 710 条：承租人按约定方法使用租赁物致损耗的，不承担赔偿责任。<br><br>
          <b>来源：</b>国家法律法规数据库（flk.npc.gov.cn） · <b>适用范围：</b>全国，地方性租赁条例可能另有规定。<br>
          <span class="text-amber-600"><i class="fas fa-triangle-exclamation mr-1"></i>涉及具体纠纷时，请以官方文本为准或咨询专业人士，我不输出法律结论。</span>`;
  }
  if (/物业费/.test(text)) {
    if (c && h) {
      return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-check-circle text-green-500"></i> 结合你的合同与房源 · 引用 ${cite(9, c.id)}</p>
            ${cite(9, c.id)} 约定：<b>物业费由乙方（你）承担</b>。但你的房源 ${h.no} 记录的是「${esc(
              h.propertyBear || '物业费 ' + (h.propertyFee || '?') + ' 元/月',
            )}」，两者<b class="text-red-600">冲突</b>。<br><br>
            <b>建议：</b>签约前把物业费承担方写回与沟通一致的版本；如果房东不愿修改，至少把金额 ${
              h.propertyFee != null ? fmt(h.propertyFee) + ' 元/月' : '（待确认）'
            } 写进合同，避免后期加价。`;
    }
    if (h) {
      return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-building text-emerald-500"></i> 基于当前房源 ${h.no}（尚未绑定合同）</p>
            房源记录：物业费 ${
              h.propertyFee != null ? fmt(h.propertyFee) + ' 元/月' : '<span class="text-amber-600">待确认</span>'
            }${h.propertyBear ? '，' + esc(h.propertyBear) : ''}。<br><br>
            注意：这只是房源侧信息，<b>最终要以合同条款为准</b>。绑定合同后我可以逐项核验是否一致。`;
    }
    return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-book-open text-brand-600"></i> 租房知识 · 通用建议</p>
          物业费承担没有统一规定，常见三种：房东全包、租客全付、按约定分摊。<b>关键是在合同里写清楚金额与承担方</b>，口头承诺退租时很难举证。<br><br>
          你目前在哪个城市、处于看房还是已签约阶段？有合同的话可以直接绑定，我帮你看具体条款。`;
  }
  if (/退租|解约|提前退/.test(text)) {
    if (c) {
      return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-check-circle text-green-500"></i> 优先引用你的合同 · ${cite(8, c.id)}</p>
            你的合同没有单独的「提前退租」条款，但 ${cite(8, c.id)} 约定违约金为<b class="text-red-600">三个月租金</b>——提前退租在合同法理上常被认定为违约并适用该条。<br><br>
            <b>法律依据与酌减参考：</b>根据《中华人民共和国民法典》第五百八十五条第二款及相关司法解释，约定的违约金过分高于造成的损失的，当事人可以请求人民法院或者仲裁机构予以适当减少。实践中通常以房东因提前解约产生的实际直接损失（如房屋重新出租合理空置期，通常在 1 个月左右）为衡量基础，具体视个案证据综合认定，不宜直接推定为某一固定减免标准。<br><br>
            <b>签约协商建议（非确定性裁判结论）：</b>建议签约前协商将违约金修改为 1 个月租金，并补充「提前 30 日书面通知且协助转租可免责退押金」。`;
    }
    if (h) {
      return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-building text-emerald-500"></i> 当前只有房源 ${h.no}，未绑定合同</p>
            提前退租的成本主要看合同里的<b>违约金条款</b>和<b>押金退还条件</b>，这些房源信息里没有。建议先绑定合同，我可以帮你定位对应条款。<br><br>
            <b>通用经验：</b>提前 30 日书面通知、配合找到下家、保留沟通记录，能显著降低纠纷风险。具体权利义务以最终签订的合同为准。`;
    }
    return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-book-open text-brand-600"></i> 租房知识 · 通用建议</p>
          提前退租一般涉及：① 违约金约定；② 押金结算退还；③ 转租免责约定。<br><br>
          你所在的城市和租住阶段是？有合同可以绑定后我给你逐条分析。`;
  }
  if (/违约金/.test(text)) {
    if (c) {
      return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-check-circle text-green-500"></i> 已检索你的合同 · 引用 ${cite(8, c.id)}</p>
            你的合同约定违约金为 <span class="text-red-600 font-medium">3 个月租金（18,000 元）</span>。<br><br>
            <b>法律依据与考量依据：</b>根据《民法典》第五百八十五条及《最高人民法院关于适用〈民法典〉合同编通则若干问题的解释》第六十五条，约定的违约金超过造成损失的百分之三十的，一般可以认定为“过分高于造成的损失”。裁判中通常以房东实际空置期损失为基础进行综合裁量，具体视实际损失、合同履行情况等认定，不构成确定性胜诉或调减结论。<br><br>
            <b>协商话术参考（仅供沟通建议）：</b>“三个月租金作为违约金相对偏高，签约前建议参考行业通常做法调整为一个月的违约金标准，双方履行都更安心。”`;
    }
    return KNOWLEDGE_ANSWER;
  }
  if (/押金/.test(text)) {
    if (c) {
      return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-check-circle text-green-500"></i> 结合你的合同 · 引用 ${cite(5, c.id)}</p>
            ${cite(5, c.id)} 约定<b>押二付一</b>，押金 12,000 元，但未写明退还时限与扣款标准——退租时容易扯皮。<br><br>
            <b>证据链建议：</b>① 入住拍全屋视频并让房东确认；② 退租前 7 日书面通知；③ 交房当天双方签《房屋交接单》。`;
    }
    return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-book-open text-brand-600"></i> 租房知识 · 经验建议，各地执行有差异</p>
          退押金关键在<b>证据链</b>：① 入住时拍全屋视频并让房东确认；② 退租前 7 日发书面《退租通知》；③ 交房当天双方签《房屋交接单》。<br><br>
          若房东无正当理由克扣，可凭合同 + 转账记录向 12345 或住建委投诉。你在哪个城市、现在到哪个阶段了？`;
  }
  // 默认：有上下文则总结上下文，否则通用引导
  if (h || c) {
    return `<p class="font-medium text-gray-900 mb-1.5 flex items-center gap-1.5"><i class="fas fa-check-circle text-green-500"></i> 当前上下文</p>
          ${
            h
              ? `当前房源 <b>${h.no} ${esc(h.name)}</b>：月租 ${
                  h.rent ? fmt(h.rent) : '待确认'
                } 元，${h.deposit || '押金待确认'}，通勤 ${h.commuteMin ? h.commuteMin + ' 分钟' : '待确认'}。<br>`
              : ''
          }
          ${c ? `当前合同 <b>${c.no}</b> 已绑定，可问“物业费谁承担”“提前退租要付什么”“违约金怎么谈”。` : '尚未绑定合同，绑定后可逐项核验承诺与条款。'}`;
  }
  return KNOWLEDGE_ANSWER;
}
