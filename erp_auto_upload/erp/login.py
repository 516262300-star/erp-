from __future__ import annotations
from loguru import logger
from playwright.sync_api import Page
import selectors as sel
from config import screenshot_path
from erp_desktop_auth import get_client_cookies, is_login_page, DesktopLoginRequired

def login(page: Page, login_url: str) -> None:
    logger.info("通过 Leedis 桌面客户端取得 ERP 登录态")
    for force in (False, True):
        cookies = get_client_cookies(force=force)
        page.context.clear_cookies()
        page.context.add_cookies(cookies)
        page.goto(login_url, wait_until="domcontentloaded")
        if not is_login_page(page.content(), page.url):
            page.locator(sel.LOGIN_SUCCESS_MARKER).wait_for(state="attached", timeout=30_000)
            page.screenshot(path=str(screenshot_path("login_success.png")), full_page=True)
            logger.info("ERP 登录完成（Leedis 客户端）")
            return
    raise DesktopLoginRequired("ERP 登录态未生效，请在 Leedis 桌面客户端登录后重试。")
