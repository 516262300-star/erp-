"""Centralized ERP selectors.

This file is intentionally named selectors.py per project convention. Because
that name shadows Python's stdlib selectors module when running "python main.py",
we first load and re-export stdlib selectors symbols so Playwright/asyncio keep
working, then define ERP selector constants below.

All ERP selectors are placeholders. Replace them after inspecting the ERP pages.
Search for "# TODO(selector):" to find every selector that needs attention.
"""

from __future__ import annotations

import importlib.util
import sysconfig
from pathlib import Path


_stdlib_selectors_path = Path(sysconfig.get_path("stdlib")) / "selectors.py"
_stdlib_spec = importlib.util.spec_from_file_location("_stdlib_selectors", _stdlib_selectors_path)
if _stdlib_spec and _stdlib_spec.loader:
    _stdlib_module = importlib.util.module_from_spec(_stdlib_spec)
    _stdlib_spec.loader.exec_module(_stdlib_module)
    for _name in dir(_stdlib_module):
        if not _name.startswith("__"):
            globals()[_name] = getattr(_stdlib_module, _name)


# Login page
LOGIN_USERNAME_INPUT = "#phonenr"  # ERP 登录页账号/手机号输入框
LOGIN_PASSWORD_INPUT = "input[name='password']"  # ERP 登录页动态码/密码输入框
LOGIN_SUBMIT_BUTTON = "input.zcbtn.dl"  # ERP 登录确认按钮
LOGIN_SUCCESS_MARKER = "a[onclick='logout()']"  # ERP 登录成功后顶部退出按钮


# Navigation / create product page
NEW_PRODUCT_MENU = "a.btn.btn-primary[href='/leedis/index.php/wh/goods/info']"  # ERP 产品列表页新增产品按钮
NEW_PRODUCT_PAGE_MARKER = "input[name='name']"  # ERP 新增产品页链接标题输入框


# Product base fields
LINK_TITLE_INPUT = "input[name='name']"  # ERP 新增产品页链接标题输入框


# SKU / specification table
SKU_ADD_ROW_BUTTON = "#addsku"  # ERP SKU 加号按钮
SKU_ROW = "#skutable tr"  # ERP SKU 表格行
SKU_MODEL_INPUT_IN_ROW = "#autoproduct"  # ERP SKU 型号输入框
SKU_MODEL_DROPDOWN_OPTION = "#DropdownAutoP li a"  # ERP SKU 型号自动补全候选
SKU_COLOR_INPUT_IN_ROW = "#autocolor2"  # ERP SKU 入库颜色输入框
SKU_COLOR_DROPDOWN_OPTION = "#DropdownAutoColor2 li a"  # ERP SKU 颜色自动补全候选
SKU_SPEC_CODE_INPUT_IN_ROW = ""  # TODO(selector): 当前新增产品页未发现规格编码输入框
SKU_DISPLAY_NAME_INPUT_IN_ROW = "#outername"  # ERP SKU 外显名称输入框
SKU_PRICE_INPUT_IN_ROW = ""  # TODO(selector): 当前新增产品页未发现价格输入框


# Price query dialog / area
PRICE_QUERY_OPEN_BUTTON = ""  # TODO(selector): 打开查价/规格编码查询区域的按钮
PRICE_QUERY_MODEL_INPUT = ""  # TODO(selector): 查价型号输入框
PRICE_QUERY_COLOR_INPUT = ""  # TODO(selector): 查价颜色输入框
PRICE_QUERY_SEARCH_BUTTON = ""  # TODO(selector): 查价搜索按钮
PRICE_QUERY_FIRST_RESULT = ""  # TODO(selector): 查价第一条结果
PRICE_QUERY_RESULT_PRICE = ""  # TODO(selector): 查价结果价格
PRICE_QUERY_RESULT_SPEC_CODE = ""  # TODO(selector): 查价结果 ERP 规格编码
PRICE_QUERY_CONFIRM_BUTTON = ""  # TODO(selector): 选择/确认查价结果按钮
PRICE_QUERY_CLOSE_BUTTON = ""  # TODO(selector): 关闭查价弹窗按钮


# Upload triggers
MAIN_IMAGE_UPLOAD_TRIGGER = "i.uppic[name='images']"  # ERP 主图上传图标
MAIN_ORIGINAL_IMAGE_UPLOAD_TRIGGER = "i.uppic[name='images_photoes']"  # ERP 主图原图上传图标
DETAIL_EDITOR_GROUP_IMAGE_BUTTON = "#editor-toolbar button[data-menu-key='group-image']"  # ERP 内容编辑器“上传”菜单
DETAIL_EDITOR_UPLOAD_IMAGE_BUTTON = "#editor-toolbar button[data-menu-key='uploadImage']"  # ERP 内容编辑器“上传图片”按钮
DETAIL_EDITOR_BODY_TEXTAREA = "textarea#idimg[name='body']"  # ERP 内容编辑器提交用隐藏字段
DETAIL_EDITOR_CONTENT_AREA = "#w-e-textarea-1"  # ERP 内容编辑器正文可编辑区域
SIZE_IMAGE_UPLOAD_TRIGGER = "input#jpg[name='userfile']"  # ERP 上传尺寸图文件框
VIDEO_UPLOAD_TRIGGER = "input#video_upload_file"  # ERP 主图视频上传文件框


# Save
SAVE_BUTTON = "button[type='submit'].btn.btn-success"  # ERP 保存并进入下一步按钮
SAVE_SUCCESS_MARKER = "body"  # TODO(selector): 保存成功后的提示或状态元素
