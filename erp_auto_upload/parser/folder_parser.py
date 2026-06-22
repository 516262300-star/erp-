from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from parser.sku_parser import ParsedSku, parse_sku_from_stem


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4"}
VIDEO_KEYWORDS = ("1:1", "1-1", "800")


@dataclass(frozen=True)
class MaterialBundle:
    material_root: Path
    link_title: str
    main_images: list[Path]
    main_original_images: list[Path]
    detail_images: list[Path]
    size_images: list[Path]
    video: Path | None
    skus: list[ParsedSku]


def natural_key(path: Path) -> list[object]:
    text = path.name.lower()
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", text)]


def list_files(folder: Path, extensions: set[str]) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in extensions],
        key=natural_key,
    )


def first_existing_dir(*folders: Path) -> Path:
    for folder in folders:
        if folder.exists():
            return folder
    return folders[0]


def first_matching_child_dir(
    parent: Path,
    *names: str,
    suffix: str | None = None,
    exclude_keywords: tuple[str, ...] = (),
) -> Path | None:
    if not parent.exists():
        return None
    for name in names:
        exact = parent / name
        if exact.is_dir() and not any(keyword in exact.name for keyword in exclude_keywords):
            return exact
    candidates = [
        path
        for path in parent.iterdir()
        if path.is_dir()
        and not any(keyword in path.name for keyword in exclude_keywords)
        and suffix is not None
        and path.name.endswith(suffix)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=natural_key)[0]


def list_detail_images(detail_dir: Path) -> list[Path]:
    images = list_files(detail_dir, IMAGE_EXTENSIONS)
    if images:
        return images
    nested_images_dir = detail_dir / "images"
    return list_files(nested_images_dir, IMAGE_EXTENSIONS)


def pick_video(video_dir: Path) -> Path | None:
    videos = list_files(video_dir, VIDEO_EXTENSIONS)
    matched = [path for path in videos if any(keyword in path.name for keyword in VIDEO_KEYWORDS)]
    if not matched:
        logger.warning("视频缺失或未匹配关键字：{}，将跳过视频上传", video_dir)
        return None
    return max(matched, key=lambda path: path.stat().st_mtime)


def sku_order_key(sku: ParsedSku) -> tuple[int, list[object]]:
    numeric_sizes: list[int] = []
    for part in sku.erp_model.split("-")[1:]:
        if part.isdigit():
            numeric_sizes.append(int(part))
    if numeric_sizes:
        return min(numeric_sizes), natural_key(sku.source_file)
    return 10**9, natural_key(sku.source_file)


def probe_video_resolution(video_path: Path) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("未找到 ffprobe，跳过视频分辨率读取：{}", video_path)
        return None

    output = result.stdout.strip()
    if result.returncode != 0 or "x" not in output:
        logger.warning("ffprobe 读取视频分辨率失败：{} {}", video_path, result.stderr.strip())
        return None
    width, height = output.split("x", 1)
    return int(width), int(height)


def parse_material_folder(material_root: Path) -> MaterialBundle:
    material_root = material_root.resolve()
    if not material_root.exists():
        raise RuntimeError(f"MATERIAL_ROOT 不存在：{material_root}")
    if not material_root.is_dir():
        raise RuntimeError(f"MATERIAL_ROOT 不是目录：{material_root}")

    main_dir = first_matching_child_dir(
        material_root,
        "主图",
        suffix="主图",
        exclude_keywords=("无logo", "无 logo", "原图"),
    ) or material_root / "主图"
    main_original_dir = first_existing_dir(
        material_root / "无logo主图",
        material_root / "主图无logo",
        material_root / "无logo图",
        material_root / "无 logo 图",
        material_root / "原图",
        main_dir / "无logo",
        main_dir / "无 logo",
        main_dir / "无logo图",
        main_dir / "无 logo 图",
        main_dir / "原图",
    )
    detail_dir = first_existing_dir(material_root / "详情页", material_root / "详情")
    size_dir = material_root / "尺寸图"
    video_dir = material_root / "视频"

    main_images = list_files(main_dir, IMAGE_EXTENSIONS)
    if not main_images:
        raise RuntimeError("主图缺失：MATERIAL_ROOT/主图 或以“主图”结尾的目录为空")

    main_original_images = list_files(main_original_dir, IMAGE_EXTENSIONS)
    detail_images = list_detail_images(detail_dir)
    parsed_pairs = [(path, parse_sku_from_stem(path.stem, path)) for path in list_files(size_dir, IMAGE_EXTENSIONS)]
    parsed_pairs = sorted(parsed_pairs, key=lambda item: sku_order_key(item[1]))
    size_images = [path for path, _sku in parsed_pairs]
    skus = [sku for _path, sku in parsed_pairs]
    video = pick_video(video_dir)

    return MaterialBundle(
        material_root=material_root,
        link_title=material_root.name,
        main_images=main_images,
        main_original_images=main_original_images,
        detail_images=detail_images,
        size_images=size_images,
        video=video,
        skus=skus,
    )
