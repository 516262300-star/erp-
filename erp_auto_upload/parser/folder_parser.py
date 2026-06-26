from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from parser.sku_parser import ParsedSku, parse_sku_from_stem


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4"}
VIDEO_KEYWORDS = ("1:1", "1：1", "1-1", "800")
MAIN_IMAGE_EXCLUDE_KEYWORDS = ("无牛皮癣", "无皮癣")
MAIN_IMAGE_EXCLUDE_PATTERNS = (r"c\s*类\s*主图",)


@dataclass(frozen=True)
class MaterialBundle:
    material_root: Path
    link_title: str
    main_images: list[Path]
    main_original_images: list[Path]
    detail_images: list[Path]
    size_images: list[Path]
    no_color_images: list[Path]
    video: Path | None
    skus: list[ParsedSku]


def natural_key(path: Path) -> list[tuple[int, int | str]]:
    text = path.name.lower()
    parts = [part for part in re.split(r"\s*(\d+)\s*", text) if part]
    return [(1, int(part)) if part.isdigit() else (0, part) for part in parts]


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
    nested_images_dir = detail_dir / "images"
    nested_images = list_files(nested_images_dir, IMAGE_EXTENSIONS)
    if nested_images:
        return nested_images
    return list_files(detail_dir, IMAGE_EXTENSIONS)


def is_main_image_excluded(path: Path) -> bool:
    text = " ".join(part.lower() for part in path.parts)
    if any(keyword.lower() in text for keyword in MAIN_IMAGE_EXCLUDE_KEYWORDS):
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in MAIN_IMAGE_EXCLUDE_PATTERNS)


def list_filtered_main_images(folder: Path) -> list[Path]:
    images = list_files(folder, IMAGE_EXTENSIONS)
    skipped = [path.name for path in images if is_main_image_excluded(path)]
    if skipped:
        logger.info("主图中检测到不上传图片，已跳过：{}", skipped)
    return [path for path in images if not is_main_image_excluded(path)]


def list_root_main_images(material_root: Path) -> list[Path]:
    images = [path for path in list_filtered_main_images(material_root) if "主图" in path.stem]
    if images:
        logger.info("使用素材根目录顶层主图文件：{}", [path.name for path in images])
    return images


def candidate_main_dirs(material_root: Path) -> list[Path]:
    candidates = [material_root / "主图", material_root / "1920主图"]
    if material_root.exists():
        candidates.extend(
            path
            for path in sorted(material_root.iterdir(), key=natural_key)
            if path.is_dir()
            and path.name.endswith("主图")
            and "无logo" not in path.name
            and "无 logo" not in path.name
            and "原图" not in path.name
            and path not in candidates
        )
    return candidates


def list_main_images(main_dir: Path) -> list[Path]:
    return list_filtered_main_images(main_dir)


def resolve_main_images(material_root: Path) -> tuple[Path, list[Path]]:
    root_images = list_root_main_images(material_root)
    if root_images:
        return material_root, root_images

    for candidate in candidate_main_dirs(material_root):
        images = list_main_images(candidate)
        if images:
            return candidate, images

    return material_root / "主图", []


def pick_video(video_dir: Path) -> Path | None:
    videos = list_files(video_dir, VIDEO_EXTENSIONS)
    matched = [path for path in videos if any(keyword in path.name for keyword in VIDEO_KEYWORDS)]
    if not matched:
        logger.warning("视频缺失或未匹配关键字：{}，将跳过视频上传", video_dir)
        return None
    return max(matched, key=lambda path: path.stat().st_mtime)


def sku_order_key(sku: ParsedSku) -> tuple[list[tuple[int, int | str]], int, list[tuple[int, int | str]]]:
    numeric_sizes: list[int] = []
    for part in sku.erp_model.split("-")[1:]:
        match = re.search(r"\d+", part)
        if match:
            numeric_sizes.append(int(match.group(0)))
    size_order = min(numeric_sizes) if numeric_sizes else 10**9
    return natural_key(Path(sku.erp_base_model)), size_order, natural_key(sku.source_file)


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

    main_dir, main_images = resolve_main_images(material_root)
    main_original_dir = first_existing_dir(
        main_dir / "无logo主图",
        main_dir / "主图无logo",
        main_dir / "无logo图",
        main_dir / "无 logo 图",
        main_dir / "去logo主图",
        main_dir / "去 logo 主图",
        main_dir / "无logo",
        main_dir / "无 logo",
        main_dir / "原图",
        material_root / "无logo主图",
        material_root / "主图无logo",
        material_root / "无logo图",
        material_root / "无 logo 图",
        material_root / "去logo主图",
        material_root / "去 logo 主图",
    )
    detail_dir = first_existing_dir(material_root / "详情页", material_root / "详情")
    size_dir = material_root / "尺寸图"
    no_color_dir = first_existing_dir(material_root / "无色图", material_root / "无色")
    video_dir = material_root / "视频"

    if not main_images:
        raise RuntimeError("主图缺失：MATERIAL_ROOT/主图、MATERIAL_ROOT/1920主图 或素材根目录顶层主图为空")

    main_original_images = list_files(main_original_dir, IMAGE_EXTENSIONS)
    detail_images = list_detail_images(detail_dir)
    no_color_images = list_files(no_color_dir, IMAGE_EXTENSIONS)
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
        no_color_images=no_color_images,
        video=video,
        skus=skus,
    )
