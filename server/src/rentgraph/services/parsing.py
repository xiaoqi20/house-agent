"""文件解析层：把上传文件/粘贴文本统一成 `ParsedDoc`，供字段抽取、条款切分与原文定位复用。

一期覆盖：.txt/.csv/.md（纯文本，utf-8 → gb18030 兜底）、.xlsx（openpyxl read_only）、
.xls（xlrd，库为只读，测试夹具由 LibreOffice 预生成并入库）、.docx（python-docx）、
.pdf（pdfplumber，必须有文字层）。

.docx 里不做 LibreOffice 转换（一期明确不做 PDF/Office 版式还原），因此 .doc 一律返回
`DOC_UNSUPPORTED`，由前端引导用户另存为 .docx 或直接粘贴全文（契约 §4.6）。

失败一律抛带 code 的 `ParseError`（契约：PDF 无文字层 → `NO_TEXT_LAYER`，.doc → `UNSUPPORTED_FORMAT`），
不做静默降级；PDF 的 200 字符合同门槛由 API 层决定，本层只负责把字符数写进 hint。
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".txt", ".csv", ".md", ".xlsx", ".xls", ".docx", ".pdf"})

_TEXT_EXTENSIONS = frozenset({".txt", ".md"})

_CSV_EXTENSIONS = frozenset({".csv"})
_MAX_SHEETS = 5
_MAX_ROWS_PER_SHEET = 2000

# 扫描件判定阈值：正文不足 20 个非空字符即视为没有文字层（OCR 一期不做）
_MIN_PDF_TEXT_CHARS = 20


@dataclass(frozen=True)
class Page:
    number: int  # 从 1 起，与合同条款 page 定位一致
    text: str


@dataclass(frozen=True)
class ParsedDoc:
    text: str
    pages: list[Page]
    rows: list[list[str]] | None
    page_count: int
    kind: str  # txt | csv | md | xlsx | xls | docx | pdf | text(粘贴)


class ParseError(Exception):
    """解析层统一错误：带 code/message/hint，直接映射到契约 §2 错误体"""

    def __init__(self, code: str, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


class UnsupportedFormat(ParseError):
    """格式不在一期范围。.doc 用 DOC_UNSUPPORTED 区分（前端要引导转换，而非泛化地报不支持）"""

    def __init__(self, message: str, hint: str = "", code: str = "UNSUPPORTED_FORMAT") -> None:
        super().__init__(code, message, hint)


class NoTextLayer(ParseError):
    """PDF 无文字层（扫描件/纯图片），一期引导用户粘贴全文，不做 OCR"""

    def __init__(self, message: str = "扫描件或无文字层 PDF", hint: str = "") -> None:
        super().__init__("NO_TEXT_LAYER", message, hint)


class EmptyDocument(ParseError):
    def __init__(self, message: str = "文件内容为空", hint: str = "请确认文件非空且包含文字内容") -> None:
        super().__init__("EMPTY_DOCUMENT", message, hint)


def _decode_text(data: bytes) -> str:
    """国标/中文 Excel 导出的 txt/csv 常是 GBK，先严格试 utf-8，失败再按 gb18030 忽略坏字节"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gb18030", errors="ignore")


def _normalise(text: str) -> str:
    """NBSP/全角空格归一 + 折叠 3 个以上空行；保留单/双换行，供后续「第 N 条」切分定位"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _cell_to_str(value: object) -> str:
    if value is None:
        return ""
    # xlrd 把整数读成 5800.0，直接 str 会污染房源字段抽取
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# 首行是否像表头：出现纯数字/金额多半是首条数据；列名简短且有业务关键词才当表头
_NUMERIC_CELL_RE = re.compile(
    r"^[¥￥$]?\s*[\d,，．.]+(?:\.\d+)?\s*(?:元|万元|w|k|平|㎡|m2|个月|/月)?$", re.IGNORECASE
)
_HEADER_KEYWORD_RE = re.compile(
    r"名称|小区|楼盘|地址|位置|区域|租金|价格|押金|面积|户型|楼层|朝向|通勤|交通|地铁|费用|物业"
    r"|备注|联系|序号|编号|来源|标签|name|region|address|rent|price|area|layout",
    re.IGNORECASE,
)
_MAX_HEADER_CELL_LEN = 10


def _looks_like_header(cells: list[str]) -> bool:
    values = [str(c).strip() for c in cells if str(c).strip()]
    if len(values) < 2 or any(_NUMERIC_CELL_RE.match(v) for v in values):
        return False
    if any(len(v) > _MAX_HEADER_CELL_LEN for v in values):
        return False
    return bool(any(_HEADER_KEYWORD_RE.search(v) for v in values)) or all(len(v) <= 6 for v in values)


def rows_to_text(rows: list[list[str]]) -> str:
    """表格 → 文本：每行渲染成「表头: 值 | 表头: 值」。

    表头取首行；首行不像表头（含数字/过长）时退回「列1..列N」，避免把第一套房源当表头吃掉。
    """
    body = [r for r in rows if any(str(c).strip() for c in r)]
    if not body:
        return ""
    width = max(len(r) for r in body)
    if _looks_like_header(body[0]):
        header = [str(c).strip() for c in body[0]]
        data = body[1:]
    else:
        header = [f"列{i + 1}" for i in range(width)]
        data = body
    lines: list[str] = []
    for row in data:
        parts = [
            f"{header[i] if i < len(header) and header[i] else f'列{i + 1}'}: {str(cell).strip()}"
            for i, cell in enumerate(row)
            if str(cell).strip()
        ]
        if parts:
            lines.append(" | ".join(parts))
    return "\n".join(lines)


def parse_text(text: str) -> ParsedDoc:
    """粘贴路径：不做文件解码，但仍归一空白，保证与文件路径的条款切分行为一致"""
    cleaned = _normalise(text)
    if not cleaned:
        raise EmptyDocument(message="粘贴内容为空", hint="请粘贴房源信息或合同全文后再试")
    return ParsedDoc(text=cleaned, pages=[], rows=None, page_count=1, kind="text")


def _parse_plain_text(data: bytes, ext: str) -> ParsedDoc:
    text = _normalise(_decode_text(data))
    if not text:
        raise EmptyDocument()
    return ParsedDoc(text=text, pages=[], rows=None, page_count=1, kind=ext[1:])


def _parse_csv(data: bytes) -> ParsedDoc:
    """CSV 按表格解析：表头 + 数据行 → rows_to_text（与 Excel 走同一套列名映射）。"""

    import csv
    import io

    text = _decode_text(data)
    rows = [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text)) if any(row)]
    return _from_rows(rows, "csv")


def _parse_xlsx(data: bytes) -> ParsedDoc:
    import openpyxl  # 延迟导入：纯文本/粘贴路径不必加载 Excel 依赖

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        rows: list[list[str]] = []
        for ws in wb.worksheets[:_MAX_SHEETS]:
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= _MAX_ROWS_PER_SHEET:
                    break
                rows.append([_cell_to_str(v) for v in row])
    finally:
        wb.close()
    return _from_rows(rows, kind="xlsx")


def _parse_xls(data: bytes) -> ParsedDoc:
    import xlrd

    book = xlrd.open_workbook(file_contents=data)
    rows: list[list[str]] = []
    for sheet in book.sheets()[:_MAX_SHEETS]:
        limit = min(sheet.nrows, _MAX_ROWS_PER_SHEET)
        for r in range(limit):
            rows.append([_cell_to_str(sheet.cell_value(r, c)) for c in range(sheet.ncols)])
    return _from_rows(rows, kind="xls")


def _from_rows(rows: list[list[str]], kind: str) -> ParsedDoc:
    text = rows_to_text(rows)
    if not text:
        raise EmptyDocument()
    return ParsedDoc(text=text, pages=[], rows=rows, page_count=1, kind=kind)


def _parse_docx(data: bytes) -> ParsedDoc:
    import docx

    document = docx.Document(io.BytesIO(data))
    blocks = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    # 合同里的费用/押金常以表格呈现，统一渲染成「表头: 值」再并入正文，保证条款文本可定位
    for table in document.tables:
        table_text = rows_to_text([[_cell_to_str(c.text) for c in row.cells] for row in table.rows])
        if table_text:
            blocks.append(table_text)
    text = _normalise("\n".join(blocks))
    if not text:
        raise EmptyDocument()
    return ParsedDoc(text=text, pages=[], rows=None, page_count=1, kind="docx")


def _parse_pdf(data: bytes) -> ParsedDoc:
    import pdfplumber

    pages: list[Page] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            pages.append(Page(number=number, text=_normalise(page.extract_text() or "")))
    text = _normalise("\n".join(p.text for p in pages))
    if len(text) < _MIN_PDF_TEXT_CHARS:
        raise NoTextLayer(
            hint=f"仅提取到 {len(text)} 个字符（低于 {_MIN_PDF_TEXT_CHARS} 字门槛），请粘贴合同全文"
        )
    return ParsedDoc(text=text, pages=pages, rows=None, page_count=len(pages), kind="pdf")


_PARSERS = {
    ".csv": _parse_csv,
    ".xlsx": _parse_xlsx,
    ".xls": _parse_xls,
    ".docx": _parse_docx,
    ".pdf": _parse_pdf,
}


def parse_document(filename: str, data: bytes) -> ParsedDoc:
    ext = Path(filename).suffix.lower()
    if ext == ".doc":
        raise UnsupportedFormat(
            "暂不支持 .doc 格式",
            hint="请用 Word/WPS 另存为 .docx 后重新上传，或直接粘贴合同全文（一期不做 .doc 转换）",
            code="DOC_UNSUPPORTED",
        )
    if ext not in SUPPORTED_EXTENSIONS:
        supported = "、".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFormat(f"暂不支持 {ext or '无扩展名'} 格式", hint=f"当前支持：{supported}")
    if ext in _TEXT_EXTENSIONS:
        return _parse_plain_text(data, ext)
    try:
        return _PARSERS[ext](data)
    except ParseError:
        raise
    except Exception as exc:  # 损坏/加密/伪扩展名：报错而不是给一份空结果
        raise ParseError(
            "PARSE_FAILED",
            f"{ext} 解析失败：{type(exc).__name__}",
            hint="文件可能已损坏或格式不符，请重新导出后上传",
        ) from exc
