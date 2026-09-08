"""存储抽象：一期 LocalStorage（磁盘 uploads/），二期换 OSS 只替换本实现，接口不变。"""

import uuid
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path

from ..config import settings


class Storage(ABC):
    @abstractmethod
    def save(self, filename: str, data: bytes) -> str: ...

    @abstractmethod
    def local_path(self, key: str) -> Path | None:
        """OSS 实现返回 None（届时 /file 端点改 302 到签名 URL）。"""


class LocalStorage(Storage):
    def save(self, filename: str, data: bytes) -> str:
        ext = Path(filename).suffix.lower()[:12] or ".bin"
        key = f"{date.today():%Y%m}/{uuid.uuid4().hex[:12]}{ext}"
        target = settings.upload_dir / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return key

    def local_path(self, key: str) -> Path | None:
        p = (settings.upload_dir / key).resolve()
        return p if p.is_file() and p.is_relative_to(settings.upload_dir.resolve()) else None


storage: Storage = LocalStorage()
