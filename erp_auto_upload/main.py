from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from loguru import logger

from config import load_settings, setup_logging
from parser.folder_parser import MaterialBundle, parse_material_folder, probe_video_resolution


def path_to_str(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [path_to_str(item) for item in value]
    if isinstance(value, dict):
        return {key: path_to_str(item) for key, item in value.items()}
    return value


def bundle_to_dict(bundle: MaterialBundle) -> dict[str, Any]:
    video_resolution = probe_video_resolution(bundle.video) if bundle.video else None
    return {
        "material_root": str(bundle.material_root),
        "link_title": bundle.link_title,
        "main_images": [str(path) for path in bundle.main_images],
        "main_original_images": [str(path) for path in bundle.main_original_images],
        "detail_images": [str(path) for path in bundle.detail_images],
        "size_images": [str(path) for path in bundle.size_images],
        "video": str(bundle.video) if bundle.video else None,
        "video_resolution": video_resolution,
        "skus": [path_to_str(asdict(sku)) for sku in bundle.skus],
    }


def print_parse_result(bundle: MaterialBundle) -> None:
    print(json.dumps(bundle_to_dict(bundle), ensure_ascii=False, indent=2))


def launch_page(headless: bool = False):
    from playwright.sync_api import Error as PlaywrightError, sync_playwright

    settings = load_settings()
    playwright = sync_playwright().start()
    browser_channel = settings.browser_channel or "chrome"
    try:
        logger.info("启动浏览器：{}", browser_channel)
        browser = playwright.chromium.launch(channel=browser_channel, headless=headless)
    except PlaywrightError as exc:
        playwright.stop()
        raise RuntimeError(
            f"启动浏览器失败：{browser_channel}。请确认本机已安装 Google Chrome，"
            "或在 .env 设置 BROWSER_CHANNEL=msedge / chromium。"
        ) from exc
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.on("dialog", lambda dialog: (logger.warning("浏览器弹窗：{}", dialog.message), dialog.accept()))
    return playwright, browser, context, page


def close_browser(playwright, browser, context) -> None:
    context.close()
    browser.close()
    playwright.stop()


def keep_browser_open(page) -> None:
    logger.info("浏览器将保持打开，按 Ctrl+C 结束脚本")
    try:
        while True:
            page.wait_for_timeout(1_000)
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，准备关闭浏览器")


def resolve_material_root(cli_material_root: str | None) -> Path:
    settings = load_settings()
    if cli_material_root:
        return Path(cli_material_root).expanduser()
    return settings.require_material_root()


def cmd_parse(material_root_arg: str | None) -> None:
    bundle = parse_material_folder(resolve_material_root(material_root_arg))
    print_parse_result(bundle)


def cmd_login() -> None:
    from erp.login import login

    settings = load_settings()
    login_url, username, password = settings.require_login()
    playwright, browser, context, page = launch_page(headless=False)
    try:
        login(page, login_url, username, password)
        keep_browser_open(page)
    finally:
        close_browser(playwright, browser, context)


def cmd_price_query(material_root_arg: str | None) -> None:
    from erp.login import login
    from erp.price_query import query_price_and_spec_code

    settings = load_settings()
    bundle = parse_material_folder(resolve_material_root(material_root_arg))
    login_url, username, password = settings.require_login()
    playwright, browser, context, page = launch_page(headless=False)
    try:
        login(page, login_url, username, password)
        results = [query_price_and_spec_code(page, sku) for sku in bundle.skus]
        payload = [
            {
                "source_stem": result.sku.source_stem,
                "erp_model": result.sku.erp_model,
                "erp_color": result.sku.erp_color,
                "display_name": result.sku.display_name,
                "price": result.price,
                "spec_code": result.spec_code,
            }
            for result in results
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        keep_browser_open(page)
    finally:
        close_browser(playwright, browser, context)


def precheck_result_to_dict(result) -> dict[str, Any]:
    return {
        "source_stem": result.sku.source_stem,
        "parsed_erp_model": result.sku.erp_model,
        "resolved_erp_model": result.resolved_erp_model,
        "parsed_erp_color": result.sku.erp_color,
        "resolved_erp_color": result.resolved_erp_color,
        "display_name": result.sku.display_name,
        "price": result.price,
        "spec_code": result.spec_code,
    }


def cmd_precheck(material_root_arg: str | None, pause: bool) -> None:
    from erp.create_product import open_create_product_page, precheck_skus
    from erp.login import login

    settings = load_settings()
    bundle = parse_material_folder(resolve_material_root(material_root_arg))
    login_url, username, password = settings.require_login()
    playwright, browser, context, page = launch_page(headless=False)
    try:
        login(page, login_url, username, password)
        open_create_product_page(page, settings.erp_home_url)
        results = precheck_skus(page, bundle)
        print(json.dumps([precheck_result_to_dict(result) for result in results], ensure_ascii=False, indent=2))
        logger.info("ERP 核对完成：未填写标题，未新增 SKU，未上传素材")
        if pause:
            keep_browser_open(page)
    finally:
        close_browser(playwright, browser, context)


def cmd_upload(save: bool, material_root_arg: str | None, pause: bool) -> None:
    from erp.create_product import create_product
    from erp.login import login

    settings = load_settings()
    bundle = parse_material_folder(resolve_material_root(material_root_arg))
    login_url, username, password = settings.require_login()
    playwright, browser, context, page = launch_page(headless=False)
    try:
        login(page, login_url, username, password)
        create_product(page, bundle, home_url=settings.erp_home_url, save=save)
        logger.info("流程完成")
        if pause:
            keep_browser_open(page)
    finally:
        close_browser(playwright, browser, context)


def cmd_form_test(material_root_arg: str | None, pause: bool) -> None:
    from config import screenshot_path
    from erp.create_product import fill_link_title, fill_skus_with_results, open_create_product_page, precheck_skus
    from erp.login import login
    import selectors as sel

    settings = load_settings()
    bundle = parse_material_folder(resolve_material_root(material_root_arg))
    login_url, username, password = settings.require_login()
    playwright, browser, context, page = launch_page(headless=False)
    try:
        login(page, login_url, username, password)
        open_create_product_page(page, settings.erp_home_url)
        sku_results = precheck_skus(page, bundle)
        fill_link_title(page, bundle.link_title)
        fill_skus_with_results(page, sku_results)

        page.locator(sel.MAIN_IMAGE_UPLOAD_TRIGGER).set_input_files([str(path) for path in bundle.main_images])
        page.locator(sel.SIZE_IMAGE_UPLOAD_TRIGGER).set_input_files(str(bundle.size_images[0]) if bundle.size_images else [])
        if bundle.video:
            page.locator(sel.VIDEO_UPLOAD_TRIGGER).set_input_files(str(bundle.video))

        page.screenshot(path=str(screenshot_path("form_test_filled.png")), full_page=True)
        logger.info("表单测试已完成：已填标题/SKU，并挂载文件到上传框；未提交上传，未保存商品")
        if pause:
            keep_browser_open(page)
    finally:
        close_browser(playwright, browser, context)


def cmd_upload_test(material_root_arg: str | None, pause: bool) -> None:
    from config import screenshot_path
    from erp.create_product import fill_link_title, fill_skus_with_results, open_create_product_page, precheck_skus, upload_materials
    from erp.login import login

    settings = load_settings()
    bundle = parse_material_folder(resolve_material_root(material_root_arg))
    login_url, username, password = settings.require_login()
    playwright, browser, context, page = launch_page(headless=False)
    try:
        login(page, login_url, username, password)
        open_create_product_page(page, settings.erp_home_url)
        sku_results = precheck_skus(page, bundle)
        fill_link_title(page, bundle.link_title)
        fill_skus_with_results(page, sku_results)
        upload_materials(page, bundle, sku_results)
        page.screenshot(path=str(screenshot_path("upload_test_done.png")), full_page=True)
        logger.info("上传测试已完成：未点击保存")
        if pause:
            keep_browser_open(page)
    finally:
        close_browser(playwright, browser, context)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="公司自研 ERP 后台自动上架商品工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser("parse", help="只解析素材目录，不打开浏览器")
    parse_parser.add_argument("--material-root", required=True, help="本次商品素材目录，例如 C:\\Users\\LEEDIS\\Desktop\\待上架\\2701云栖")

    subparsers.add_parser("login", help="仅登录 ERP，停在首页")

    price_parser = subparsers.add_parser("price-query", help="逐个 SKU 查价并输出价格/规格编码")
    price_parser.add_argument("--material-root", required=True, help="本次商品素材目录")

    precheck_parser = subparsers.add_parser("precheck", help="上架前核对 ERP 型号、颜色和成本，不填写、不上传")
    precheck_parser.add_argument("--material-root", required=True, help="本次商品素材目录")
    precheck_parser.add_argument("--pause", dest="pause", action="store_true", help="核对完成后停在浏览器页面")
    precheck_parser.add_argument("--no-pause", dest="pause", action="store_false", help="核对完成后自动关闭浏览器")
    precheck_parser.set_defaults(pause=False)

    form_test_parser = subparsers.add_parser("form-test", help="安全测试：填写新增产品页表单，不提交上传，不保存")
    form_test_parser.add_argument("--material-root", required=True, help="本次商品素材目录")
    form_test_parser.add_argument("--pause", dest="pause", action="store_true", help="测试完成后停在浏览器页面")
    form_test_parser.add_argument("--no-pause", dest="pause", action="store_false", help="测试完成后自动关闭浏览器")
    form_test_parser.set_defaults(pause=True)

    upload_test_parser = subparsers.add_parser("upload-test", help="上传测试：填写表单并上传素材，不保存商品")
    upload_test_parser.add_argument("--material-root", required=True, help="本次商品素材目录")
    upload_test_parser.add_argument("--pause", dest="pause", action="store_true", help="测试完成后停在浏览器页面")
    upload_test_parser.add_argument("--no-pause", dest="pause", action="store_false", help="测试完成后自动关闭浏览器")
    upload_test_parser.set_defaults(pause=True)

    upload_parser = subparsers.add_parser("upload", help="完整填写流程，默认停在保存前")
    upload_parser.add_argument("--material-root", required=True, help="本次商品素材目录")
    upload_parser.add_argument("--save", action="store_true", help="填写完成后点击保存")
    upload_parser.add_argument("--pause", dest="pause", action="store_true", help="流程完成后停在浏览器页面")
    upload_parser.add_argument("--no-pause", dest="pause", action="store_false", help="流程完成后自动关闭浏览器")
    upload_parser.set_defaults(pause=True)
    return parser


def main() -> None:
    setup_logging()
    args = build_parser().parse_args()
    if args.command == "parse":
        cmd_parse(args.material_root)
    elif args.command == "login":
        cmd_login()
    elif args.command == "price-query":
        cmd_price_query(args.material_root)
    elif args.command == "precheck":
        cmd_precheck(args.material_root, pause=args.pause)
    elif args.command == "form-test":
        cmd_form_test(args.material_root, pause=args.pause)
    elif args.command == "upload-test":
        cmd_upload_test(args.material_root, pause=args.pause)
    elif args.command == "upload":
        cmd_upload(save=args.save, material_root_arg=args.material_root, pause=args.pause)
    else:
        raise RuntimeError(f"未知命令：{args.command}")


if __name__ == "__main__":
    main()
