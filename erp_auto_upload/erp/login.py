from __future__ import annotations

from loguru import logger
from playwright.sync_api import Page

import selectors as sel
from config import screenshot_path


def login(page: Page, login_url: str, username: str, password: str) -> None:
    logger.info("打开 ERP 登录页：{}", login_url)
    page.goto(login_url, wait_until="domcontentloaded")
    page.locator(sel.LOGIN_USERNAME_INPUT).fill(username)
    page.locator(sel.LOGIN_PASSWORD_INPUT).fill(password)
    page.locator(sel.LOGIN_SUBMIT_BUTTON).click()

    # TODO(selector): 将 LOGIN_SUCCESS_MARKER 改成 ERP 首页登录成功后一定出现的元素。
    page.locator(sel.LOGIN_SUCCESS_MARKER).wait_for(state="attached", timeout=30_000)
    page.screenshot(path=str(screenshot_path("login_success.png")), full_page=True)
    logger.info("ERP 登录完成")
