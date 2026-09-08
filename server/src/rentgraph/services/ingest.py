import io
import re

import pdfplumber

MIN_TEXT_CHARS = 200


class NoTextLayer(Exception):
    """PDF 无文字层（扫描件），一期降级为引导用户粘贴文本"""


class TextTooShort(Exception):
    """TXT/PDF 提取到的正文过短：多半不是完整合同，同样引导粘贴全文"""


def clean_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(data: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = clean_text("\n".join(parts))
    if len(text) < MIN_TEXT_CHARS:
        raise NoTextLayer(f"仅提取到 {len(text)} 字符")
    return text


def extract_txt(data: bytes) -> str:
    text = clean_text(data.decode("utf-8", errors="ignore"))
    if len(text) < MIN_TEXT_CHARS:
        raise TextTooShort(f"仅 {len(text)} 字符，疑似不完整")
    return text
