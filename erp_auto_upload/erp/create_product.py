from __future__ import annotations

import time

from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

import selectors as sel
from config import screenshot_path
from erp.price_query import PriceQueryResult, query_price_and_spec_code
from erp.uploader import upload_editor_images, upload_files, upload_gallery_files, upload_sku_no_color_images, upload_sku_size_images
from parser.folder_parser import MaterialBundle
from parser.sku_parser import ParsedSku


def _selector_required(selector: str, name: str) -> None:
    if not selector:
        raise RuntimeError(f"{name} selector 为空，请先补 selectors.py")


def open_create_product_page(page: Page, home_url: str | None = None) -> None:
    # TODO(selector): 如果 ERP 支持新建商品 URL 直达，可在 .env 扩展配置并改成 page.goto。
    if home_url:
        logger.info("打开 ERP 首页：{}", home_url)
        page.goto(home_url, wait_until="domcontentloaded")
    if sel.NEW_PRODUCT_MENU:
        logger.info("点击进入新建商品页")
        page.locator(sel.NEW_PRODUCT_MENU).click()
    else:
        logger.warning("NEW_PRODUCT_MENU 为空：当前仅等待 NEW_PRODUCT_PAGE_MARKER，占位流程需要后续补齐")

    # TODO(selector): 将 NEW_PRODUCT_PAGE_MARKER 改为新建商品页稳定出现的元素。
    page.locator(sel.NEW_PRODUCT_PAGE_MARKER).wait_for(state="visible", timeout=30_000)
    page.screenshot(path=str(screenshot_path("create_product_page.png")), full_page=True)


def fill_link_title(page: Page, link_title: str) -> None:
    _selector_required(sel.LINK_TITLE_INPUT, "LINK_TITLE_INPUT")
    logger.info("填写链接标题：{}", link_title)
    page.locator(sel.LINK_TITLE_INPUT).fill(link_title)


def select_autocomplete_option(
    page: Page,
    input_selector: str,
    option_selector: str,
    query: str,
    expected_text: str,
    field_name: str,
    fallback_queries: list[str] | None = None,
) -> str:
    _selector_required(input_selector, f"{field_name} input")
    _selector_required(option_selector, f"{field_name} dropdown")

    last_options: list[str] = []
    search_plan: list[tuple[str, str, bool]] = [(query, expected_text, False)]
    search_plan.extend((fallback_query, fallback_query, True) for fallback_query in (fallback_queries or []) if fallback_query)

    for current_query, current_expected, allow_unique_prefix in search_plan:
        page.locator(input_selector).click()
        page.evaluate("""(optionSelector) => document.querySelectorAll(optionSelector).forEach(el => el.remove())""", option_selector)
        if input_selector == sel.SKU_MODEL_INPUT_IN_ROW:
            page.evaluate(
                """({selector, value}) => {
                    const input = document.querySelector(selector);
                    if (!input) throw new Error(`未找到输入框: ${selector}`);
                    input.value = value;
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    input.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
                    if (typeof window.postProduct === 'function') window.postProduct();
                }""",
                {"selector": input_selector, "value": current_query},
            )
        else:
            page.locator(input_selector).fill("")
            type_query = "玫瑰" if expected_text == "玫瑰金" else current_query
            page.locator(input_selector).type(type_query, delay=120)
            page.evaluate(
                """(selector) => window.jQuery && window.jQuery(selector).trigger('keyup')""",
                input_selector,
            )

        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            options = page.locator(option_selector).evaluate_all(
                """els => els
                    .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length))
                    .map(el => (el.innerText || '').trim())"""
            )
            last_options = options
            matched_text = expected_text if expected_text in options else ""
            if not matched_text and input_selector == sel.SKU_MODEL_INPUT_IN_ROW:
                matched_text = next((option for option in options if option.startswith(expected_text)), "")
            if not matched_text and allow_unique_prefix:
                prefix_matches = [option for option in options if option.startswith(current_expected)]
                if len(prefix_matches) == 1:
                    matched_text = prefix_matches[0]
                    logger.info("{}未找到精确候选：{}，改用 ERP 唯一候选：{}", field_name, expected_text, matched_text)
                elif len(prefix_matches) > 1:
                    raise RuntimeError(f"{field_name}匹配到多个候选：{expected_text}，兜底查询：{current_query}，候选：{prefix_matches}")
            if matched_text:
                page.evaluate(
                    """({selector, text}) => {
                        const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                        const target = Array.from(document.querySelectorAll(selector))
                            .filter(visible)
                            .find(el => (el.innerText || '').trim() === text);
                        target.click();
                    }""",
                    {"selector": option_selector, "text": matched_text},
                )
                page.locator(input_selector).wait_for(state="visible", timeout=5_000)
                actual = page.locator(input_selector).input_value().strip()
                if matched_text not in actual and actual not in matched_text:
                    logger.warning("{}候选点击后输入框值与预期不同：actual={} expected={}", field_name, actual, matched_text)
                return matched_text
            page.wait_for_timeout(500)

    actual = page.locator(input_selector).input_value().strip()
    raise RuntimeError(f"{field_name}未找到候选：{expected_text}，输入框当前值：{actual}，当前候选：{last_options}")


def _row_locator(page: Page, index: int):
    _selector_required(sel.SKU_ROW, "SKU_ROW")
    return page.locator(sel.SKU_ROW).nth(index)


def _sku_form_state(page: Page) -> dict[str, str | int]:
    state = page.evaluate(
        """({modelSelector, colorSelector, displaySelector}) => {
            const valueOf = (selector) => document.querySelector(selector)?.value ?? "";
            const visibleText = (selector) => Array.from(document.querySelectorAll(selector))
                .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length))
                .map(el => (el.innerText || "").trim())
                .join(" | ");
            return {
                model_input: valueOf(modelSelector),
                color_input: valueOf(colorSelector),
                display_input: valueOf(displaySelector),
                sku_hidden_count: document.querySelectorAll("input[name='skulist[]']").length,
                model_dropdown: visibleText("#DropdownAutoP li a"),
                color_dropdown: visibleText("#DropdownAutoColor2 li a"),
            };
        }""",
        {
            "modelSelector": sel.SKU_MODEL_INPUT_IN_ROW,
            "colorSelector": sel.SKU_COLOR_INPUT_IN_ROW,
            "displaySelector": sel.SKU_DISPLAY_NAME_INPUT_IN_ROW,
        },
    )
    return state


def fill_sku_row(page: Page, index: int, sku: ParsedSku, result: PriceQueryResult) -> None:
    logger.info(
        "填写 SKU 行 {}：erp_model={} erp_base_model={} erp_color={} display_name={} cost={}",
        index + 1,
        result.resolved_erp_model,
        sku.erp_base_model,
        result.resolved_erp_color,
        sku.display_name,
        result.price,
    )
    _selector_required(sel.SKU_ADD_ROW_BUTTON, "SKU_ADD_ROW_BUTTON")
    _selector_required(sel.SKU_DISPLAY_NAME_INPUT_IN_ROW, "SKU_DISPLAY_NAME_INPUT_IN_ROW")

    before_count = page.locator("input[name='skulist[]']").count()
    select_autocomplete_option(
        page,
        sel.SKU_MODEL_INPUT_IN_ROW,
        sel.SKU_MODEL_DROPDOWN_OPTION,
        result.resolved_erp_model,
        result.resolved_erp_model,
        "型号",
        fallback_queries=[sku.erp_base_model] if sku.erp_base_model != result.resolved_erp_model else None,
    )
    select_autocomplete_option(
        page,
        sel.SKU_COLOR_INPUT_IN_ROW,
        sel.SKU_COLOR_DROPDOWN_OPTION,
        result.resolved_erp_color,
        result.resolved_erp_color,
        "入库颜色",
    )
    page.locator(sel.SKU_DISPLAY_NAME_INPUT_IN_ROW).fill(sku.display_name)
    logger.debug("SKU 行 {} 加号前状态：{}", index + 1, _sku_form_state(page))
    for attempt in range(1, 4):
        page.locator(sel.SKU_ADD_ROW_BUTTON).click()
        try:
            page.wait_for_function(
                "before => document.querySelectorAll(\"input[name='skulist[]']\").length > before",
                arg=before_count,
                timeout=10_000,
            )
            break
        except PlaywrightTimeoutError:
            logger.warning("SKU 行 {} 点击加号后未新增，重试 {}/3", index + 1, attempt)
    else:
        logger.error("SKU 行 {} 添加失败状态：{}", index + 1, _sku_form_state(page))
        page.screenshot(path=str(screenshot_path(f"sku_add_failed_{index + 1}.png")), full_page=True)
        raise RuntimeError(f"SKU 行 {index + 1} 添加失败：{sku.display_name}")


def fill_skus(page: Page, bundle: MaterialBundle) -> list[PriceQueryResult]:
    results = precheck_skus(page, bundle)
    fill_skus_with_results(page, results)
    return results


def fill_skus_with_results(page: Page, results: list[PriceQueryResult]) -> None:
    for index, result in enumerate(results):
        fill_sku_row(page, index, result.sku, result)


def precheck_skus(page: Page, bundle: MaterialBundle) -> list[PriceQueryResult]:
    logger.info("开始 ERP 上架前核对：{} 个 SKU", len(bundle.skus))
    results: list[PriceQueryResult] = []
    errors: list[str] = []
    for index, sku in enumerate(bundle.skus, start=1):
        try:
            price_result = query_price_and_spec_code(page, sku)
            resolved_model = select_autocomplete_option(
                page,
                sel.SKU_MODEL_INPUT_IN_ROW,
                sel.SKU_MODEL_DROPDOWN_OPTION,
                sku.erp_model,
                sku.erp_model,
                "型号",
                fallback_queries=[sku.erp_base_model] if sku.erp_base_model != sku.erp_model else None,
            )
            resolved_color = select_autocomplete_option(
                page,
                sel.SKU_COLOR_INPUT_IN_ROW,
                sel.SKU_COLOR_DROPDOWN_OPTION,
                sku.erp_color,
                sku.erp_color,
                "入库颜色",
            )
            result = PriceQueryResult(
                sku=sku,
                price=price_result.price,
                spec_code=price_result.spec_code,
                raw=price_result.raw,
                erp_model=resolved_model,
                erp_color=resolved_color,
            )
            logger.info(
                "ERP 核对 {}：{} -> 型号 {} / 颜色 {} / 成本 {} / 外显 {}",
                index,
                sku.source_stem,
                result.resolved_erp_model,
                result.resolved_erp_color,
                result.price,
                sku.display_name,
            )
            results.append(result)
        except Exception as exc:
            message = f"{index}. {sku.source_stem}: {exc}"
            logger.error("ERP 核对失败：{}", message)
            errors.append(message)
            page.keyboard.press("Escape")
    if errors:
        raise RuntimeError("ERP 上架前核对失败，已停止上架：\n" + "\n".join(errors))
    logger.info("ERP 上架前核对通过：{} 个 SKU", len(results))
    return results


def upload_materials(page: Page, bundle: MaterialBundle, sku_results: list[PriceQueryResult] | None = None) -> None:
    resolved_results = sku_results or [PriceQueryResult(sku=sku, price="", spec_code="") for sku in bundle.skus]
    upload_gallery_files(page, sel.MAIN_IMAGE_UPLOAD_TRIGGER, "images", bundle.main_images, "主图")
    upload_gallery_files(
        page,
        sel.MAIN_ORIGINAL_IMAGE_UPLOAD_TRIGGER,
        "images_photoes",
        bundle.main_original_images,
        "主图原图",
    )
    upload_editor_images(
        page,
        sel.DETAIL_EDITOR_GROUP_IMAGE_BUTTON,
        sel.DETAIL_EDITOR_UPLOAD_IMAGE_BUTTON,
        sel.DETAIL_EDITOR_BODY_TEXTAREA,
        sel.DETAIL_EDITOR_CONTENT_AREA,
        bundle.detail_images,
    )
    upload_sku_size_images(
        page,
        [
            (f"{result.resolved_erp_model}#{result.resolved_erp_color}", result.sku.source_file)
            for result in resolved_results
        ],
    )
    upload_sku_no_color_images(page, bundle.no_color_images)
    if bundle.video:
        upload_files(page, sel.VIDEO_UPLOAD_TRIGGER, [bundle.video], "视频")
    else:
        logger.warning("未找到符合规则的视频，跳过视频上传")


def create_product(page: Page, bundle: MaterialBundle, home_url: str | None = None, save: bool = False) -> None:
    open_create_product_page(page, home_url)
    sku_results = precheck_skus(page, bundle)
    fill_link_title(page, bundle.link_title)
    fill_skus_with_results(page, sku_results)
    upload_materials(page, bundle, sku_results)
    page.screenshot(path=str(screenshot_path("final_before_save.png")), full_page=True)
    logger.info("已完成上架信息填写，默认停在保存前")

    if save:
        _selector_required(sel.SAVE_BUTTON, "SAVE_BUTTON")
        logger.info("点击保存按钮")
        page.locator(sel.SAVE_BUTTON).click()
        # TODO(selector): 将 SAVE_SUCCESS_MARKER 改为保存成功提示或状态。
        page.locator(sel.SAVE_SUCCESS_MARKER).wait_for(state="visible", timeout=30_000)
        page.screenshot(path=str(screenshot_path("save_success.png")), full_page=True)
        logger.info("商品保存完成")
