from __future__ import annotations

import re
import time
from pathlib import Path

from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


LARGE_VIDEO_WARNING_MB = 80
VIDEO_PROGRESS_APPEAR_TIMEOUT_MS = 8_000
VIDEO_PROGRESS_TIMEOUT_MS = 15 * 60_000


def ensure_files_exist(file_paths: list[Path]) -> None:
    missing = [str(path) for path in file_paths if not path.exists()]
    if missing:
        raise RuntimeError(f"待上传文件不存在：{', '.join(missing)}")


def file_size_mb(path: Path) -> float:
    return round(path.stat().st_size / 1024 / 1024, 1)


def wait_for_video_progress_modal(page: Page, timeout: int = VIDEO_PROGRESS_TIMEOUT_MS) -> None:
    find_progress_dialog = """
        () => {
            const visible = el => !!(
                el &&
                (el.offsetWidth || el.offsetHeight || el.getClientRects().length)
            );
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(
                ".modal, .modal-dialog, .layui-layer, .bootbox, [role='dialog'], body > div"
            ));
            return candidates.find(el => visible(el) && textOf(el).includes("上传进度")) || null;
        }
    """
    try:
        page.wait_for_function(find_progress_dialog, timeout=VIDEO_PROGRESS_APPEAR_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        logger.info("未检测到视频上传进度弹窗，继续后续流程")
        return

    logger.info("检测到视频上传进度弹窗，等待上传完成")
    page.wait_for_function(
        """
        () => {
            const visible = el => !!(
                el &&
                (el.offsetWidth || el.offsetHeight || el.getClientRects().length)
            );
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(
                ".modal, .modal-dialog, .layui-layer, .bootbox, [role='dialog'], body > div"
            ));
            const dialog = candidates.find(el => visible(el) && textOf(el).includes("上传进度"));
            if (!dialog) return true;
            const buttons = Array.from(dialog.querySelectorAll("button, input[type='button'], input[type='submit'], a"));
            return buttons.some(el => {
                const text = (el.value || el.innerText || el.textContent || "").trim();
                return visible(el) && text === "确定" && !el.disabled && !el.classList.contains("disabled");
            });
        }
        """,
        timeout=timeout,
    )
    page.evaluate(
        """
        () => {
            const visible = el => !!(
                el &&
                (el.offsetWidth || el.offsetHeight || el.getClientRects().length)
            );
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const candidates = Array.from(document.querySelectorAll(
                ".modal, .modal-dialog, .layui-layer, .bootbox, [role='dialog'], body > div"
            ));
            const dialog = candidates.find(el => visible(el) && textOf(el).includes("上传进度"));
            if (!dialog) return;
            const button = Array.from(dialog.querySelectorAll("button, input[type='button'], input[type='submit'], a"))
                .find(el => {
                    const text = (el.value || el.innerText || el.textContent || "").trim();
                    return visible(el) && text === "确定" && !el.disabled && !el.classList.contains("disabled");
                });
            if (button) button.click();
        }
        """
    )
    try:
        page.wait_for_function(
            """
            () => {
                const visible = el => !!(
                    el &&
                    (el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                );
                const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
                const candidates = Array.from(document.querySelectorAll(
                    ".modal, .modal-dialog, .layui-layer, .bootbox, [role='dialog'], body > div"
                ));
                return !candidates.some(el => visible(el) && textOf(el).includes("上传进度"));
            }
            """,
            timeout=10_000,
        )
    except PlaywrightTimeoutError:
        logger.warning("视频上传进度弹窗点击确定后仍未关闭，继续后续流程")
    logger.info("视频上传进度已完成")


def upload_files(page: Page, trigger_selector: str, file_paths: list[Path], label: str = "文件") -> None:
    if not file_paths:
        logger.info("{}为空，跳过上传", label)
        return
    if not trigger_selector:
        raise RuntimeError(f"{label}上传 selector 为空，请先补 selectors.py")

    ensure_files_exist(file_paths)
    logger.info("开始处理{}：{} 个", label, len(file_paths))
    if label == "视频":
        for path in file_paths:
            size_mb = file_size_mb(path)
            logger.info("视频文件：{}，大小 {} MB", path.name, size_mb)
            if size_mb > LARGE_VIDEO_WARNING_MB:
                logger.warning(
                    "视频 {} 大小 {} MB，保存后如果 ERP 没有生成视频，优先压缩视频或检查服务器上传大小限制",
                    path.name,
                    size_mb,
                )

    trigger = page.locator(trigger_selector)
    element_type = trigger.first.evaluate("(el) => el.tagName.toLowerCase() + ':' + (el.getAttribute('type') || '')")
    if element_type == "input:file":
        trigger.set_input_files([str(path) for path in file_paths])
        selected_names = trigger.first.evaluate("el => Array.from(el.files || []).map(file => file.name)")
        expected_names = [path.name for path in file_paths]
        if selected_names != expected_names:
            raise RuntimeError(f"{label}文件框校验失败：页面 {selected_names}，期望 {expected_names}")
        if label == "视频":
            wait_for_video_progress_modal(page)
            logger.info("{}上传完成：{}", label, selected_names)
        else:
            logger.info("{}已挂载到文件框，将随保存商品提交：{}", label, selected_names)
        return

    with page.expect_file_chooser() as file_chooser_info:
        page.locator(trigger_selector).click()
    file_chooser = file_chooser_info.value
    file_chooser.set_files([str(path) for path in file_paths])
    logger.info("{}已选择文件：{}", label, [path.name for path in file_paths])


def upload_gallery_files(page: Page, icon_selector: str, input_name: str, file_paths: list[Path], label: str) -> None:
    if not file_paths:
        logger.info("{}为空，跳过上传", label)
        return
    ensure_files_exist(file_paths)
    clear_gallery_files(page, input_name, label, icon_selector)
    before_count = page.locator(f"input[name='{input_name}[]']").count()
    logger.info("开始上传{}：{} 个", label, len(file_paths))
    reset_shared_upload_dialog(page)
    page.locator(icon_selector).click()
    page.locator("input#upload_file[name='litpic[]']").set_input_files([str(path) for path in file_paths])
    page.evaluate("() => window.jQuery && window.jQuery('#upload_file_form').submit()")
    page.wait_for_function(
        """({name, expected}) => document.querySelectorAll(`input[name="${name}[]"]`).length >= expected""",
        arg={"name": input_name, "expected": before_count + len(file_paths)},
        timeout=120_000,
    )
    wait_for_gallery_settle(page, input_name)
    close_upload_modal(page)
    reset_shared_upload_dialog(page)
    normalize_gallery_files(page, input_name, label, icon_selector, before_count + len(file_paths))
    logger.info("{}上传完成", label)


def reset_shared_upload_dialog(page: Page) -> None:
    page.evaluate(
        """() => {
            const input = document.querySelector("input#upload_file[name='litpic[]']");
            if (input) input.value = "";
            const form = document.querySelector("#upload_file_form");
            if (form) form.reset();
            for (const selector of [
                "#upload_file_queue",
                "#upload_file-queue",
                ".uploadify-queue",
                ".fileupload-process",
                ".files"
            ]) {
                document.querySelectorAll(selector).forEach(el => {
                    if (el.id !== "upload_file_form") el.innerHTML = "";
                });
            }
        }"""
    )


def wait_for_gallery_settle(page: Page, input_name: str, stable_seconds: float = 1.5, timeout: float = 30.0) -> None:
    started = time.monotonic()
    last_count = page.locator(f"input[name='{input_name}[]']").count()
    stable_from = time.monotonic()
    while time.monotonic() - started < timeout:
        page.wait_for_timeout(300)
        count = page.locator(f"input[name='{input_name}[]']").count()
        if count == last_count:
            if time.monotonic() - stable_from >= stable_seconds:
                return
        else:
            last_count = count
            stable_from = time.monotonic()
    logger.warning("{}[] 上传数量等待稳定超时，当前数量：{}", input_name, last_count)


def normalize_gallery_files(page: Page, input_name: str, label: str, icon_selector: str, expected_count: int) -> None:
    count = gallery_file_count(page, input_name, label, icon_selector)
    if count == expected_count:
        return
    if count < expected_count:
        raise RuntimeError(f"{label}上传数量不足：页面 {count} 张，期望 {expected_count} 张")

    logger.warning("{}上传后多出 {} 张，自动删除旧项，只保留最后 {} 张", label, count - expected_count, expected_count)
    page.evaluate(
        """({name, label, iconSelector, expected}) => {
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const icon = document.querySelector(iconSelector);
            const findSection = () => {
                if (icon && icon.closest(".form-group")) return icon.closest(".form-group");
                for (let node = icon; node; node = node.parentElement) {
                    if (textOf(node).includes(label)) return node;
                }
                return document;
            };
            const itemForInput = input => {
                let node = input;
                for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                    const text = node.innerText || "";
                    if (node.querySelector("img") && text.includes("删除")) return node;
                }
                return input;
            };
            const section = findSection();
            const inputs = Array.from(document.querySelectorAll(`input[name="${name}[]"]`));
            const inputItems = inputs.map(itemForInput);
            const seenInputItems = [...new Set(inputItems)];
            const removeCount = Math.max(0, seenInputItems.length - expected);
            for (const item of seenInputItems.slice(0, removeCount)) item.remove();

            const hiddenLeft = document.querySelectorAll(`input[name="${name}[]"]`).length;
            if (hiddenLeft > expected) {
                Array.from(document.querySelectorAll(`input[name="${name}[]"]`))
                    .slice(0, hiddenLeft - expected)
                    .forEach(input => input.remove());
            }

            const visualItems = Array.from(section.querySelectorAll("img"))
                .filter(img => !img.closest("label"))
                .map(img => {
                    let node = img;
                    for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                        if (node.contains(icon)) break;
                        if ((node.innerText || "").includes("删除")) return node;
                    }
                    return null;
                })
                .filter(Boolean);
            const seenVisualItems = [...new Set(visualItems)].filter(el => el.isConnected);
            const visualRemoveCount = Math.max(0, seenVisualItems.length - expected);
            for (const item of seenVisualItems.slice(0, visualRemoveCount)) item.remove();
        }""",
        {"name": input_name, "label": label, "iconSelector": icon_selector, "expected": expected_count},
    )
    page.wait_for_timeout(500)
    final_count = gallery_file_count(page, input_name, label, icon_selector)
    if final_count != expected_count:
        raise RuntimeError(f"{label}上传数量校验失败：页面 {final_count} 张，期望 {expected_count} 张")


def gallery_file_count(page: Page, input_name: str, label: str, icon_selector: str) -> int:
    state = page.evaluate(
        """({name, label, iconSelector}) => {
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const icon = document.querySelector(iconSelector);
            const findSection = () => {
                if (icon && icon.closest(".form-group")) return icon.closest(".form-group");
                for (let node = icon; node; node = node.parentElement) {
                    if (textOf(node).includes(label)) return node;
                }
                return null;
            };
            const section = findSection();
            const hiddenCount = document.querySelectorAll(`input[name="${name}[]"]`).length;
            const visualCount = section
                ? Array.from(section.querySelectorAll("img")).filter(img => !img.closest("label")).length
                : 0;
            return {hiddenCount, visualCount};
        }""",
        {"name": input_name, "label": label, "iconSelector": icon_selector},
    )
    return max(int(state["hiddenCount"]), int(state["visualCount"]))


def clear_gallery_files(page: Page, input_name: str, label: str, icon_selector: str) -> None:
    state = page.evaluate(
        """({name, label, iconSelector}) => {
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const icon = document.querySelector(iconSelector);
            const findSection = () => {
                if (icon && icon.closest(".form-group")) return icon.closest(".form-group");
                for (let node = icon; node; node = node.parentElement) {
                    if (textOf(node).includes(label)) return node;
                }
                return null;
            };
            const section = findSection();
            const hiddenCount = document.querySelectorAll(`input[name="${name}[]"]`).length;
            const visualCount = section
                ? Array.from(section.querySelectorAll("img")).filter(img => !img.closest("label")).length
                : 0;
            return {hiddenCount, visualCount};
        }""",
        {"name": input_name, "label": label, "iconSelector": icon_selector},
    )
    existing_count = max(int(state["hiddenCount"]), int(state["visualCount"]))
    if existing_count == 0:
        return
    logger.warning("{}已有临时图片 {} 张，上传前先清空", label, existing_count)
    page.evaluate(
        """({name, label, iconSelector}) => {
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const icon = document.querySelector(iconSelector);
            const findSection = () => {
                if (icon && icon.closest(".form-group")) return icon.closest(".form-group");
                for (let node = icon; node; node = node.parentElement) {
                    if (textOf(node).includes(label)) return node;
                }
                return document;
            };
            const section = findSection();
            const inputs = Array.from(document.querySelectorAll(`input[name="${name}[]"]`));
            for (const input of inputs) {
                let node = input;
                let removed = false;
                for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                    const text = node.innerText || "";
                    if (node.querySelector("img") && text.includes("删除")) {
                        node.remove();
                        removed = true;
                        break;
                    }
                }
                if (!removed) input.remove();
            }
            const thumbs = Array.from(section.querySelectorAll("img"))
                .map(img => {
                    let node = img;
                    for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                        if (node.contains(icon)) break;
                        if ((node.innerText || "").includes("删除")) return node;
                    }
                    return null;
                })
                .filter(Boolean);
            for (const thumb of [...new Set(thumbs)]) thumb.remove();
        }""",
        {"name": input_name, "label": label, "iconSelector": icon_selector},
    )
    page.wait_for_function(
        """({name, label, iconSelector}) => {
            const textOf = el => (el.innerText || el.textContent || "").replace(/\\s+/g, " ").trim();
            const icon = document.querySelector(iconSelector);
            let section = icon && icon.closest(".form-group");
            if (!section) {
                for (let node = icon; node; node = node.parentElement) {
                    if (textOf(node).includes(label)) {
                        section = node;
                        break;
                    }
                }
            }
            const hiddenCount = document.querySelectorAll(`input[name="${name}[]"]`).length;
            const visualCount = section
                ? Array.from(section.querySelectorAll("img")).filter(img => !img.closest("label")).length
                : 0;
            return hiddenCount === 0 && visualCount === 0;
        }""",
        arg={"name": input_name, "label": label, "iconSelector": icon_selector},
        timeout=10_000,
    )


def upload_editor_images(
    page: Page,
    group_button_selector: str,
    upload_button_selector: str,
    body_textarea_selector: str,
    content_area_selector: str,
    file_paths: list[Path],
) -> None:
    if not file_paths:
        logger.info("详情页为空，跳过上传")
        return
    if not group_button_selector or not upload_button_selector or not body_textarea_selector or not content_area_selector:
        raise RuntimeError("详情页内容上传 selector 为空，请先补 selectors.py")

    ensure_files_exist(file_paths)
    textarea = page.locator(body_textarea_selector)
    textarea.wait_for(state="attached", timeout=30_000)
    content_area = page.locator(content_area_selector)
    content_area.wait_for(state="visible", timeout=30_000)
    before_count = _editor_image_count(page, body_textarea_selector)
    logger.info("开始上传详情页内容图片：{} 张", len(file_paths))

    content_area.scroll_into_view_if_needed()
    content_area.click()
    file_chooser = _open_editor_image_file_chooser(page, group_button_selector, upload_button_selector)
    if file_chooser.is_multiple():
        file_chooser.set_files([str(path) for path in file_paths])
        page.wait_for_function(
            """({selector, expected}) => {
                const textarea = document.querySelector(selector);
                if (!textarea) return false;
                return ((textarea.value || '').match(/<img\\b/g) || []).length >= expected;
            }""",
            arg={"selector": body_textarea_selector, "expected": before_count + len(file_paths)},
            timeout=120_000,
        )
    else:
        file_chooser.set_files(str(file_paths[0]))
        page.wait_for_function(
            """({selector, expected}) => {
                const textarea = document.querySelector(selector);
                if (!textarea) return false;
                return ((textarea.value || '').match(/<img\\b/g) || []).length >= expected;
            }""",
            arg={"selector": body_textarea_selector, "expected": before_count + 1},
            timeout=60_000,
        )
        if len(file_paths) > 1:
            raise RuntimeError("详情页上传控件不支持批量选择图片")

    logger.info("详情页内容图片上传完成：{} 张", len(file_paths))


def _open_editor_image_file_chooser(page: Page, group_button_selector: str, upload_button_selector: str):
    last_error: Exception | None = None
    for attempt in range(1, 4):
        upload_button = page.locator(upload_button_selector)
        if not _upload_button_ready(page, upload_button_selector):
            group_button = page.locator(group_button_selector)
            group_button.scroll_into_view_if_needed()
            group_button.click()
            page.wait_for_function(
                """(selector) => {
                    const button = document.querySelector(selector);
                    const rect = button ? button.getBoundingClientRect() : null;
                    return button
                        && rect
                        && rect.width > 0
                        && rect.height > 0
                        && !button.classList.contains('disabled')
                        && !button.disabled;
                }""",
                arg=upload_button_selector,
                timeout=10_000,
            )
        page.wait_for_timeout(300)
        try:
            with page.expect_file_chooser(timeout=8_000) as file_chooser_info:
                upload_button.click()
            return file_chooser_info.value
        except PlaywrightTimeoutError as exc:
            last_error = exc
            logger.warning("详情页上传图片按钮未弹出文件选择器，重试 {}/3", attempt)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
    raise RuntimeError("详情页上传图片按钮未弹出文件选择器") from last_error


def _upload_button_ready(page: Page, upload_button_selector: str) -> bool:
    return page.evaluate(
        """(selector) => {
            const button = document.querySelector(selector);
            if (!button) return false;
            const rect = button.getBoundingClientRect();
            return rect.width > 0
                && rect.height > 0
                && !button.classList.contains('disabled')
                && !button.disabled;
        }""",
        upload_button_selector,
    )


def _editor_image_count(page: Page, body_textarea_selector: str) -> int:
    return page.evaluate(
        """(selector) => {
            const textarea = document.querySelector(selector);
            return textarea ? ((textarea.value || '').match(/<img\\b/g) || []).length : 0;
        }""",
        body_textarea_selector,
    )


def _resolve_sku_size_index(page: Page, sku_value: str) -> str:
    model, _, color = sku_value.partition("#")
    expected = f"{sku_value.replace('#', '_').replace('/', '_')}.jpg"
    if page.locator(f"td[index='{expected}']").count() > 0:
        return expected

    indexes = page.locator("td[index]").evaluate_all("els => els.map(el => el.getAttribute('index')).filter(Boolean)")
    suffix = f"_{color}.jpg"
    candidates = [
        index
        for index in indexes
        if isinstance(index, str)
        and index.startswith(model)
        and index.endswith(suffix)
    ]
    if len(candidates) == 1:
        logger.debug("尺寸图行使用 ERP 实际型号：{} -> {}", expected, candidates[0])
        return candidates[0]
    if len(candidates) > 1:
        raise RuntimeError(f"SKU 尺寸图上传行匹配到多个候选：{expected} -> {candidates}")

    base_model = model.split("-", 1)[0]
    base_candidates = [
        index
        for index in indexes
        if isinstance(index, str)
        and index.startswith(base_model)
        and index.endswith(suffix)
    ]
    if len(base_candidates) == 1:
        logger.debug("尺寸图行使用 ERP 基础型号唯一候选：{} -> {}", expected, base_candidates[0])
        return base_candidates[0]
    if len(base_candidates) > 1:
        raise RuntimeError(f"SKU 尺寸图上传行按基础型号匹配到多个候选：{expected} -> {base_candidates}")
    raise RuntimeError(f"未找到 SKU 尺寸图上传行：{expected}，页面候选：{indexes}")


def upload_sku_size_images(page: Page, sku_image_pairs: list[tuple[str, Path]]) -> None:
    if not sku_image_pairs:
        logger.info("尺寸图为空，跳过上传")
        return
    ensure_files_exist([path for _sku_value, path in sku_image_pairs])
    for sku_value, image_path in sku_image_pairs:
        img_name = _resolve_sku_size_index(page, sku_value)
        row = page.locator(f"td[index='{img_name}']").first
        logger.info("上传尺寸图：{} -> {}", sku_value, image_path.name)
        row.locator("label.click2upload[for='jpg']").click()
        page.locator("input#jpg[name='userfile']").set_input_files(str(image_path))
        page.evaluate("() => window.jQuery && window.jQuery('#upload_file_form_jpg').submit()")
        page.wait_for_function(
            """(indexValue) => {
                const cell = document.querySelector(`td[index="${indexValue}"]`);
                if (!cell) return false;
                const labelOk = (cell.innerText || '').includes('上传成功');
                const img = cell.querySelector('img');
                return labelOk && img && img.complete && img.naturalWidth > 0;
            }""",
            arg=img_name,
            timeout=60_000,
        )
        close_upload_modal(page)
    logger.info("尺寸图上传完成：{} 张", len(sku_image_pairs))


def main_model_key(value: str) -> str:
    model = Path(str(value)).stem.split("_", 1)[0].split("#", 1)[0].split("-", 1)[0].strip()
    match = re.match(r"\d+[A-Za-z]*", model)
    return (match.group(0) if match else model).lower()


def build_no_color_image_map(file_paths: list[Path]) -> dict[str, Path]:
    image_map: dict[str, Path] = {}
    for path in file_paths:
        key = main_model_key(path.stem)
        if not key:
            logger.warning("无色图文件名无法识别主型号，跳过：{}", path.name)
            continue
        if key in image_map:
            logger.warning("主型号 {} 匹配到多张无色图，仅使用第一张：{}，忽略 {}", key, image_map[key].name, path.name)
            continue
        image_map[key] = path
    return image_map


def sku_image_cell_has_uploaded_image(page: Page, index_value: str) -> bool:
    return bool(
        page.locator(f"td[index='{index_value}']").first.evaluate(
            """cell => {
                const img = cell.querySelector('img');
                if (!img) return false;
                const src = (img.getAttribute('src') || '').trim();
                return src && !src.startsWith('data:') && img.complete && img.naturalWidth > 0;
            }"""
        )
    )


def upload_sku_no_color_images(page: Page, file_paths: list[Path]) -> None:
    if not file_paths:
        logger.info("无色图为空，跳过上传")
        return
    ensure_files_exist(file_paths)
    image_map = build_no_color_image_map(file_paths)
    if not image_map:
        logger.warning("无色图文件夹未识别到可用主型号，跳过上传")
        return

    indexes = page.locator("td[index$='_无色.jpg']").evaluate_all(
        "els => els.map(el => el.getAttribute('index')).filter(Boolean)"
    )
    if not indexes:
        logger.warning("ERP 页面未找到无色图上传行，跳过无色图上传")
        return

    uploaded_count = 0
    skipped_existing_count = 0
    missing_keys: set[str] = set()
    for index_value in indexes:
        if not isinstance(index_value, str):
            continue
        if sku_image_cell_has_uploaded_image(page, index_value):
            logger.info("无色图已存在，跳过：{}", index_value)
            skipped_existing_count += 1
            continue
        key = main_model_key(index_value)
        image_path = image_map.get(key)
        if not image_path:
            missing_keys.add(key)
            continue

        row = page.locator(f"td[index='{index_value}']").first
        logger.info("上传无色图：{} -> {}", index_value, image_path.name)
        row.locator("label.click2upload[for='jpg']").click()
        page.locator("input#jpg[name='userfile']").set_input_files(str(image_path))
        page.evaluate("() => window.jQuery && window.jQuery('#upload_file_form_jpg').submit()")
        page.wait_for_function(
            """(indexValue) => {
                const cell = document.querySelector(`td[index="${indexValue}"]`);
                if (!cell) return false;
                const labelOk = (cell.innerText || '').includes('上传成功');
                const img = cell.querySelector('img');
                return labelOk && img && img.complete && img.naturalWidth > 0;
            }""",
            arg=index_value,
            timeout=60_000,
        )
        close_upload_modal(page)
        uploaded_count += 1

    for key in sorted(missing_keys):
        logger.warning("无色图缺失：主型号 {} 未在无色图文件夹中找到对应图片，已跳过该主型号", key)
    logger.info("无色图上传完成：{} 个规格行，已存在跳过：{} 个规格行", uploaded_count, skipped_existing_count)


def close_upload_modal(page: Page) -> None:
    page.evaluate(
        """() => {
            if (window.jQuery) {
                window.jQuery('#modal').modal && window.jQuery('#modal').modal('hide');
                window.jQuery('#modal').hide().removeClass('in').attr('aria-hidden', 'true');
                window.jQuery('.modal-backdrop').remove();
                document.body.classList.remove('modal-open');
                document.body.style.paddingRight = '';
            }
        }"""
    )
