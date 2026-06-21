from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values
from loguru import logger
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"
SCREENSHOT_DIR = LOG_DIR / "screenshots"


class Settings(BaseModel):
    erp_login_url: Optional[str] = Field(default=None, alias="ERP_LOGIN_URL")
    erp_username: Optional[str] = Field(default=None, alias="ERP_USERNAME")
    erp_password: Optional[str] = Field(default=None, alias="ERP_PASSWORD")
    erp_home_url: Optional[str] = Field(default=None, alias="ERP_HOME_URL")
    material_root: Optional[Path] = Field(default=None, alias="MATERIAL_ROOT")
    browser_channel: Optional[str] = Field(default="chrome", alias="BROWSER_CHANNEL")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
        "arbitrary_types_allowed": True,
    }

    def require_material_root(self) -> Path:
        if not self.material_root:
            raise RuntimeError("缺少 MATERIAL_ROOT：请在 .env 中填写桌面素材根目录")
        return self.material_root

    def require_login(self) -> tuple[str, str, str]:
        missing = []
        if not self.erp_login_url:
            missing.append("ERP_LOGIN_URL")
        if not self.erp_username:
            missing.append("ERP_USERNAME")
        if not self.erp_password:
            missing.append("ERP_PASSWORD")
        if missing:
            raise RuntimeError(f"缺少登录配置：{', '.join(missing)}")
        return self.erp_login_url or "", self.erp_username or "", self.erp_password or ""


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level="INFO", enqueue=True)
    logger.add(LOG_DIR / "run_{time:YYYYMMDD}.log", level="DEBUG", rotation="10 MB", retention="14 days", encoding="utf-8")


def load_settings(env_path: Path = ENV_PATH) -> Settings:
    values: dict[str, str] = {}
    if env_path.exists():
        values.update({k: v for k, v in dotenv_values(env_path).items() if v is not None})
    values.update({k: v for k, v in os.environ.items() if k.startswith("ERP_") or k in {"MATERIAL_ROOT", "BROWSER_CHANNEL"}})
    values = {key: value for key, value in values.items() if str(value).strip()}

    settings = Settings.model_validate(values)
    if settings.material_root:
        settings.material_root = settings.material_root.expanduser()
    return settings


def screenshot_path(name: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = name if name.lower().endswith(".png") else f"{name}.png"
    return SCREENSHOT_DIR / safe_name
