"""LLM 输出契约（Pydantic）：mock 与真实模型共用同一份 schema。

产品约束（后端契约 §2、PRD §3）：缺失字段一律 null，禁止用 0/"" 冒充已确认值；
每个结论都要能回到原文（evidence / clause_no / char_start）。
"""

from typing import Literal

from pydantic import BaseModel, Field

# 核验结论枚举（契约 §4.7）：未匹配到条款必须是「未约定」，禁止推断为已承诺
VerifyResult = Literal["一致", "冲突", "未约定", "无法判断"]
Severity = Literal["high", "medium", "low"]
# 问答模式（契约 §4.8）：上下文 / 仅房源 / 通用 / 拒答 / 超范围
AnswerMode = Literal["context", "house_only", "general", "refusal", "out_of_scope"]


class ListingDraft(BaseModel):
    """单套房源草稿：PRD §7 字段组 + 原文证据 + 缺失清单"""

    name: str | None = Field(default=None, description="房源名称，如「望京南湖东园一居 整租」")
    region: str | None = Field(default=None, description="区域，如「朝阳·望京」")
    address: str | None = Field(default=None, description="详细地址")
    rent: int | None = Field(default=None, description="月租（元，整数）")
    deposit: str | None = Field(default=None, description="押金/付款方式原文，如「押一付一」「押二付一」")
    agency_fee: int | None = Field(default=None, description="中介费（元）")
    property_fee: int | None = Field(default=None, description="物业费（元/月）")
    property_bear: str | None = Field(default=None, description="物业费承担方，如「房东承担」「租客承担」")
    net_fee: int | None = Field(default=None, description="网络/宽带费（元/月）")
    other_fee: str | None = Field(default=None, description="其他费用原文，如「网费 50/月」")
    area: float | None = Field(default=None, description="面积（平方米）")
    layout: str | None = Field(default=None, description="户型，如「一居」「开间」「两居合租次卧」「主卧」")
    floor: str | None = Field(default=None, description="楼层，如「12/18层」")
    orientation: str | None = Field(default=None, description="朝向，如「南向」")
    bathroom: bool | None = Field(default=None, description="是否独立卫浴；原文未提及为 null")
    lighting: str | None = Field(default=None, description="采光，如「采光好」")
    furniture: str | None = Field(default=None, description="家具家电情况")
    commute_min: int | None = Field(default=None, description="通勤时间（分钟）")
    commute_mode: str | None = Field(default=None, description="通勤方式，如「地铁」「公交」")
    metro: str | None = Field(default=None, description="地铁信息，如「14号线望京站」")
    nearby: str | None = Field(default=None, description="周边配套")
    pet: str | None = Field(default=None, description="宠物约定，如「允许宠物」「禁止宠物」")
    shared: bool | None = Field(default=None, description="是否合租；原文未提及为 null")
    sublet: str | None = Field(default=None, description="转租约定")
    max_people: int | None = Field(default=None, description="入住人数上限")
    lease_req: str | None = Field(default=None, description="租期要求，如「一年起租」")
    available: str | None = Field(default=None, description="可入住时间，如「10月1日可入住」")
    notes: str | None = Field(default=None, description="备注（原文其他信息）")
    raw: str | None = Field(default=None, description="该条房源的原始文本（确认面板与详情展示用）")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="整体置信度 0-1")
    evidence: dict[str, str] = Field(
        default_factory=dict, description="字段名 → 原文片段；片段必须逐字来自输入，否则该字段作废"
    )
    missing: list[str] = Field(default_factory=list, description="未提取到的字段中文名（对应值保持 null）")


class ListingExtraction(BaseModel):
    """一次导入解析出的全部候选房源（契约 §4.2：3—10 套）"""

    drafts: list[ListingDraft] = Field(default_factory=list, description="候选房源草稿")
    truncated: int = Field(default=0, description="超出 10 套上限被截断的房源数（必须显式上报，不静默丢弃）")


class ClauseData(BaseModel):
    """单条合同条款：原文逐字 + 定位（页码与归一化全文偏移）"""

    clause_no: int | None = Field(default=None, description="条号（阿拉伯数字）；无法解析为 null")
    title: str = Field(description="条标题，如「第九条 物业费」")
    text: str = Field(description="条款原文，必须逐字来自合同全文，不得改写或摘要")
    clause_type: str = Field(
        default="其他", description="条款类型：押金|违约金|租期|租金|维修|续租|解约|转租|其他"
    )
    page: int | None = Field(default=None, description="页码（从 1 开始）；无分页信息为 null")
    char_start: int | None = Field(
        default=None, description="在归一化全文（去空白）中的起始偏移，用于原文定位"
    )
    char_end: int | None = Field(default=None, description="在归一化全文中的结束偏移（不含）")
    amount: float | None = Field(default=None, description="条款主金额（元）")
    months: int | None = Field(
        default=None, description="以「月」为单位的数量：违约金倍数、押金月数、租期月数"
    )
    date_from: str | None = Field(default=None, description="起始日期 ISO8601（YYYY-MM-DD）")
    date_to: str | None = Field(default=None, description="结束日期 ISO8601（YYYY-MM-DD）")
    party_liable: str | None = Field(default=None, description="责任方：甲方|乙方|双方|null")


class ClauseExtraction(BaseModel):
    """条款抽取输出；dropped = 因无法在原文定位被丢弃的幻觉条款数（必须显式上报）"""

    clauses: list[ClauseData] = Field(default_factory=list)
    dropped: int = Field(default=0, description="因原文不可定位被丢弃的条款数量")


class PromiseItem(BaseModel):
    """待核验的房源承诺（契约 §4.7 items 左侧）：claim/field/anchor 三元组"""

    claim: str = Field(description="房源承诺原文，如「月租 5,800 元」")
    field: str = Field(description="对应字段中文名，如「租金」「物业费承担方」")
    anchor: str | None = Field(default=None, description="前端定位锚点，如 hd-rent")


class VerifyJudgement(BaseModel):
    """承诺 × 条款的语义核验结论（契约 §4.7）"""

    result: VerifyResult = Field(description="一致|冲突|未约定|无法判断；未匹配到条款必须为「未约定」")
    advice: str = Field(description="给用户的一句话建议或给房东的措辞")
    severity: Severity = Field(default="medium", description="严重程度 high|medium|low")
    clause_no: int | None = Field(default=None, description="依据的条款号；未约定时通常为 null")
    reason: str = Field(description="判断理由，需引用合同原文或说明为何认定未约定")


class Citation(BaseModel):
    """回答中的可点引用（契约 §4.8）：必须能在该合同条款集合中定位"""

    clause_id: int | None = Field(default=None, description="条款主键（落库后回填）；未落库为 null")
    clause_no: int | None = Field(default=None, description="条号，用于与条款集合做存在性校验")
    label: str = Field(description="展示文案，如「第 9 条」")
    page: int | None = Field(default=None, description="页码")
    char_start: int | None = Field(default=None, description="原文起始偏移")
    char_end: int | None = Field(default=None, description="原文结束偏移")
    contract_id: str | None = Field(default=None, description="所属合同 id")


class AnswerResult(BaseModel):
    """问答输出（契约 §4.8）：html 只含白名单标签，引用 chip 由前端按 citations 渲染"""

    mode: AnswerMode = Field(description="context|house_only|general|refusal|out_of_scope")
    html: str = Field(description="标题行 + 正文的受限 HTML；不含脚本/样式/事件属性")
    citations: list[Citation] = Field(default_factory=list)
    followups: list[str] = Field(default_factory=list, description="建议追问")
    sources: list[str] = Field(default_factory=list, description="法规类问题的来源（如 flk.npc.gov.cn）")


class ExplanationItem(BaseModel):
    """单套房源的解释五段（PRD §8 / 契约 §4.5）"""

    why: list[str] = Field(default_factory=list, description="为什么推荐")
    tradeoffs: list[str] = Field(default_factory=list, description="取舍")
    risks: list[str] = Field(default_factory=list, description="风险与待核验")
    todos: list[str] = Field(default_factory=list, description="看房/签约前待确认")
    next: list[str] = Field(default_factory=list, description="下一步动作")


class RecommendationExplanation(BaseModel):
    """推荐解释：house_id → 五段解释。数字必须来自确定性排序结果，否则整句剔除"""

    items: dict[str, ExplanationItem] = Field(default_factory=dict)
