from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


KNOWN_COLORS = [
    "哑镍拉丝",
    "珍珠黑",
    "铜拉丝",
    "铜本色",
    "咖啡铜",
    "古铜色",
    "玫瑰金",
    "亮镍",
    "钛银",
    "铬色",
    "亮金",
    "铝色",
    "古铜",
    "哑镍",
    "拉丝",
    "铬",
    "黑",
]


ERP_MODEL_ALIASES = {
    "8093-24": "8093-小",
    "8093-29": "8093-大",
    "8249-29": "8249-单孔",
    "8251-29": "8251-30",
    "8253-31": "8253-32",
    "8250-30": "8250-33",
}


DISPLAY_MODEL_ALIASES = {
    "8250-30": "8250-33",
}


@dataclass(frozen=True)
class ParsedSku:
    source_file: Path
    source_stem: str
    full_model_name: str
    erp_base_model: str
    source_color: str
    erp_model: str
    erp_color: str
    display_color: str
    display_name: str


def strip_parenthetical_note(value: str) -> str:
    value = re.sub(r"（[^）]*）", "", value)
    value = re.sub(r"\([^)]*\)", "", value)
    return value.strip()


def strip_series_name(value: str) -> str:
    match = re.match(r"^(\d+)", value.strip())
    return match.group(1) if match else value.strip()


def normalize_color(color: str) -> tuple[str, str]:
    color = color.strip()
    if color in {"钛银", "亮镍"}:
        return "亮镍", "钛银"
    if color in {"亮金", "玫瑰金"}:
        return "玫瑰金", "亮金"
    if color == "铬色":
        return "铬", "铬色"
    return color, color


def find_color_part(parts: list[str]) -> int:
    for idx, part in enumerate(parts):
        if split_color_part(part):
            return idx
    raise ValueError(f"无法从文件名中识别颜色段：{'-'.join(parts)}")


def split_color_part(part: str) -> tuple[str, str] | None:
    cleaned = strip_parenthetical_note(part)
    for color in sorted(KNOWN_COLORS, key=len, reverse=True):
        if cleaned == color:
            return "", color
        if cleaned.endswith(color):
            prefix = cleaned[: -len(color)]
            if prefix:
                return prefix, color
        if cleaned.startswith(color):
            suffix = cleaned[len(color) :]
            if suffix:
                return suffix, color
    return None


def parse_sku_from_stem(stem: str, source_file: Path | None = None) -> ParsedSku:
    parts = [part.strip() for part in stem.split("-") if part.strip()]
    if len(parts) < 2:
        raise ValueError(f"尺寸图文件名格式错误，至少需要 型号-颜色：{stem}")

    color_idx = find_color_part(parts)
    color_prefix, source_color = split_color_part(parts[color_idx]) or ("", strip_parenthetical_note(parts[color_idx]))
    model_name_parts = [strip_parenthetical_note(part) for part in parts[:color_idx]]
    if color_prefix:
        model_name_parts.append(strip_parenthetical_note(color_prefix))
    full_model_name = "-".join(model_name_parts)
    erp_color, display_color = normalize_color(source_color)

    if not model_name_parts:
        raise ValueError(f"尺寸图文件名缺少型号段：{stem}")

    erp_base_model = strip_series_name(model_name_parts[0])
    model_parts: list[str] = [erp_base_model]
    model_parts.extend(part for part in model_name_parts[1:] if part)
    for idx, part in enumerate(parts[1:], start=1):
        if idx == color_idx:
            continue
        cleaned = strip_parenthetical_note(part)
        if cleaned:
            model_parts.append(cleaned)

    parsed_erp_model = "-".join(model_parts)
    erp_model = ERP_MODEL_ALIASES.get(parsed_erp_model, parsed_erp_model)
    parsed_display_model_name = "-".join(
        [full_model_name, *[part for part in model_parts[1:] if part not in model_name_parts[1:]]]
    )
    display_model_name = DISPLAY_MODEL_ALIASES.get(parsed_display_model_name, parsed_display_model_name)
    display_name = f"{display_model_name}{display_color}"
    return ParsedSku(
        source_file=source_file or Path(stem),
        source_stem=stem,
        full_model_name=full_model_name,
        erp_base_model=erp_base_model,
        source_color=source_color,
        erp_model=erp_model,
        erp_color=erp_color,
        display_color=display_color,
        display_name=display_name,
    )
