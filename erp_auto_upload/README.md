# ERP 自动上架商品工具

本项目是一个本地 Python + Playwright 自动化骨架，用于公司自研 ERP 后台新建商品并上传素材。当前所有 ERP 页面元素定位都集中在 `selectors.py`，需要你根据真实页面补齐后再执行浏览器自动化流程。

## 目录结构

```text
erp_auto_upload/
├─ .env.example
├─ requirements.txt
├─ README.md
├─ main.py
├─ config.py
├─ selectors.py
├─ erp/
│  ├─ __init__.py
│  ├─ login.py
│  ├─ create_product.py
│  ├─ price_query.py
│  └─ uploader.py
├─ parser/
│  ├─ __init__.py
│  ├─ folder_parser.py
│  └─ sku_parser.py
└─ logs/
```

## 安装

建议使用 Python 3.11+。

```powershell
cd C:\Users\LEEDIS\Desktop\codex项目\小程序自动上架\erp_auto_upload
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

脚本默认启动本机安装的 Google Chrome（`.env` 里的 `BROWSER_CHANNEL=chrome`）。如果你想改用 Microsoft Edge，可以设为 `BROWSER_CHANNEL=msedge`。只有需要使用 Playwright 自带 Chromium 时，才额外执行：

```powershell
playwright install chromium
```

如果需要读取视频分辨率，请额外安装 `ffprobe` 并确保命令行可直接执行：

```powershell
ffprobe -version
```

没有 `ffprobe` 也不影响上传流程，脚本只会跳过视频分辨率读取。

## 配置 `.env`

复制示例文件：

```powershell
Copy-Item .env.example .env
```

填写：

```dotenv
ERP_LOGIN_URL=https://你的ERP登录地址
ERP_USERNAME=你的账号
ERP_PASSWORD=你的密码
ERP_HOME_URL=https://你的ERP首页地址
BROWSER_CHANNEL=chrome
MATERIAL_ROOT=
```

`MATERIAL_ROOT` 可以留空。因为每次上架的商品素材路径都会变，推荐运行命令时用 `--material-root` 指定本次商品素材目录。链接标题会直接取这个目录名，例如 `2701云栖`。

`BROWSER_CHANNEL=chrome` 表示打开本机正常安装的 Google Chrome 浏览器。

## 素材目录约定

```text
MATERIAL_ROOT/
├─ 主图/     *.jpg *.png   （也支持：1440主图/ 等以“主图”结尾的目录）
├─ 无logo主图/ *.jpg *.png   （也支持：主图无logo/、无logo图/、无 logo 图/、去 logo 主图/、主图/无logo主图/）
├─ 详情页/   *.jpg *.png   （也支持并优先使用：详情页/images/ 或 详情/images/）
├─ 尺寸图/   *.jpg *.png
├─ 无色图/   *.jpg *.png   （也兼容：无色/）
└─ 视频/     *.mp4
```

规则：

- `主图` 至少 1 张，按文件名自然排序上传；也支持 `1440主图` 这类以“主图”结尾的目录；为空会直接终止。文件名里的数字前后空格不影响排序，例如 `主图 1` 会排在 `主图2` 前面。
- `无logo主图`、`主图无logo`、`无logo图`、`无 logo 图`、`去logo主图`、`去 logo 主图`，以及 `主图/无logo主图`、`主图/主图无logo`、`主图/无logo`、`主图/无 logo`、`主图/无logo图`、`主图/无 logo 图`、`主图/去logo主图`、`主图/去 logo 主图`、`主图/原图` 都支持，里面的图片会按文件名自然排序上传到 ERP 的“主图原图”。根目录下的 `原图` 不会作为主图原图上传，避免误传相机原片。
- `详情页` 按文件名自然排序上传；如果 `详情页/images` 或 `详情/images` 里有图片，会优先上传这个 `images` 子目录里的详情切片，避免误传根目录下的汇总图或 PSD 导出图。
- `尺寸图` 按文件名自然排序上传，同时文件名会用于生成 SKU。
- `尺寸图` 和 SKU 上架顺序会按孔距数字从小到大排序，例如 `64 -> 96 -> 128 -> 160 -> 192`；未识别到数字孔距的项目排在后面，并保持文件名自然排序。
- `无色图` 会在尺寸图上传完成后上传。匹配时只看主型号，也就是型号里 `-` 前面的主编号；例如 `6659-96`、`6659-128` 都匹配同一张 `6659` 无色图，`2705-30直径`、`2705-25直径` 都匹配同一张 `2705` 无色图。
- `无色图` 文件夹里每个主型号只需要一张图，会上传到该主型号下所有规格的“无色图”字段；如果尺寸图上传后页面已经显示某个规格的无色图，会跳过该规格不重复上传；如果某个主型号找不到对应无色图，只记录 warning 并继续上架。
- `视频` 只选择文件名包含 `1:1`、`1：1`、`1-1`、`800` 的 `.mp4`；多个匹配时取修改时间最新的；没有匹配只记录 warning。视频控件优先按 ERP 原生文件框 `input#file_upload3[name='litpic']` 定位；如果这个固定控件不存在，会自动尝试 `name=litpic`、`accept=video`、`id/name/class` 含 `video` 的真实文件框。脚本只通过文件框挂载视频，不点击非文件框上传按钮，避免弹出系统“打开”窗口；如果仍找不到文件框，会报出“视频上传文件框未找到”并列出页面上实际存在的上传相关控件，方便修正 selector。如果 ERP 弹出“上传进度”，脚本会等到弹窗里出现“上传成功”且“确定”按钮可点后，才自动点击“确定”。如果保存后 ERP 没有生成视频，优先检查视频大小、编码和服务器上传大小限制。脚本会对超过 80 MB 的视频输出 warning。

## SKU 文件名解析

尺寸图文件名格式：

```text
<价格册完整型号名称>-<颜色>[-<其他后缀，如 单孔/96/24>]
```

也兼容孔距和颜色连写：

```text
2701-96亮金
2701-128钛银
2701-192珍珠黑
```

示例：

```text
2715云栖-铬色-单孔       -> erp_model=2715-单孔, erp_color=铬色, display_name=2715云栖铬色
6601-古铜色-单孔（24）   -> erp_model=6601-单孔, erp_color=古铜色, display_name=6601古铜色
8256-古铜色-96           -> erp_model=8256-96, erp_color=古铜色, display_name=8256古铜色
2701-96-亮镍             -> erp_model=2701-96, erp_color=亮镍, display_name=2701钛银
```

型号特殊规则：

- 文件名型号 `6601-24`：ERP 实际型号使用 `6601-单孔`，外显名称仍按文件名解析。
- 文件名型号 `8251-单孔` 或 `8251-29`：ERP 实际型号使用 `8251-30直径`，外显名称仍按文件名解析。
- 文件名型号 `9090-单孔`：ERP 实际型号使用 `9090-29直径`，外显名称仍按文件名解析。
- 文件名型号 `9096-单孔`：ERP 实际型号使用 `9096-28直径`，外显名称仍按文件名解析。
- 上架填写型号时，如果文件名解析出的完整型号在 ERP 自动补全里没有候选，会快速改用基础数字型号搜索；当 ERP 只返回一个同基础型号开头的候选时，脚本会自动选用该 ERP 候选。例如文件名解析为 `9091-单孔`，ERP 只有 `9091-27直径` 时会直接使用 `9091-27直径`。
- 尺寸图上传行也会用同样的基础型号唯一候选兜底；如果 ERP 返回多个候选，脚本会报错停下，避免选错型号。

颜色特殊规则：

- 文件名颜色 `钛银`：ERP 查价用 `亮镍`，外显显示 `钛银`。
- 文件名颜色 `亮镍`：ERP 查价仍用 `亮镍`，外显显示 `钛银`。
- 文件名颜色 `亮金` 或 `玫瑰金`：ERP 入库颜色/查价用 `玫瑰金`，外显显示 `亮金`。
- 文件名颜色 `咖啡铜`：ERP 入库颜色/查价和外显都使用 `咖啡铜`。
- 其他颜色保持原样。

## 补 selectors 的步骤

所有需要补的页面定位都在 `selectors.py`，并且统一带有：

```python
# TODO(selector):
```

建议顺序：

1. 先补登录页：`LOGIN_USERNAME_INPUT`、`LOGIN_PASSWORD_INPUT`、`LOGIN_SUBMIT_BUTTON`、`LOGIN_SUCCESS_MARKER`。
2. 再补进入新建商品页：`NEW_PRODUCT_MENU`、`NEW_PRODUCT_PAGE_MARKER`。
3. 补基础字段：`LINK_TITLE_INPUT`。
4. 补查价相关：`PRICE_QUERY_*`。
5. 补规格行相关：`SKU_*`。
6. 补上传按钮：`MAIN_IMAGE_UPLOAD_TRIGGER`、`DETAIL_EDITOR_GROUP_IMAGE_BUTTON`、`DETAIL_EDITOR_UPLOAD_IMAGE_BUTTON`、`DETAIL_EDITOR_BODY_TEXTAREA`、`DETAIL_EDITOR_CONTENT_AREA`、`SIZE_IMAGE_UPLOAD_TRIGGER`、`VIDEO_UPLOAD_TRIGGER`。
7. 最后补保存：`SAVE_BUTTON`、`SAVE_SUCCESS_MARKER`。

如果某个 ERP 页面交互不是简单点击/输入，可以在对应模块里调整流程：

- 登录：`erp/login.py`
- 查价：`erp/price_query.py`
- 新建商品：`erp/create_product.py`
- 文件上传：`erp/uploader.py`

## 逐步测试

调试期间默认 `headless=False`，方便你看浏览器动作。流程跑通后再考虑改成 `True`。

## 桌面软件

可以直接双击：

```text
启动桌面软件.bat
```

桌面软件里可以：

- 填写或选择本次商品素材文件夹。
- 点击“解析检查”查看链接标题、图片数量、SKU 列表。
- 点击“ERP核对”打开 ERP，只核对每个 SKU 的实际型号、颜色和成本，不填写标题、不新增 SKU、不上传素材。
- 点击“开始上架（不保存）”自动打开浏览器并填写上传。
- “开始上架（不保存）”不会预先完整核对全部 SKU；填写型号时如果完整型号没有候选，才会用基础型号搜索 ERP 唯一候选并继续填写。
- 上架完成后浏览器会保持打开，方便人工检查；软件不会自动点击保存。
- 如需中途停止，点击“停止脚本”。

### 1. 只解析素材

```powershell
python main.py parse --material-root "C:\Users\LEEDIS\Desktop\待上架\2701云栖"
```

输出链接标题、主图/详情图/尺寸图/视频路径、视频大小、SKU 解析结果，不打开浏览器。

### 2. 只登录

```powershell
python main.py login
```

登录成功后会停在首页，并保存截图：

```text
logs/screenshots/login_success.png
```

### 3. 查价

```powershell
python main.py price-query --material-root "C:\Users\LEEDIS\Desktop\待上架\2701云栖"
```

会登录 ERP，对每个 SKU 调用查价流程，并输出价格与 ERP 规格编码。这个阶段需要先补齐登录和 `PRICE_QUERY_*` 选择器。

### 4. 上架前 ERP 核对

```powershell
python main.py precheck --material-root "C:\Users\LEEDIS\Desktop\待上架\2701云栖"
```

会登录 ERP 并打开新建商品页，对每个 SKU 先查成本，再核对新增商品页里的型号自动补全和入库颜色自动补全。输出内容包含：

- 尺寸图文件名解析出的型号、颜色。
- ERP 实际匹配到的型号、颜色。
- ERP 成本。
- 外显名称。

如果文件名解析出的完整型号在 ERP 自动补全里没有候选，会再用基础数字型号搜索；当 ERP 只返回一个同基础型号开头的候选时，脚本会自动选用该候选。如果返回多个候选或没有候选，会停下报错，避免继续上架到错误型号。

这个命令不填写标题、不新增 SKU、不上传素材，适合需要整批确认型号、颜色和成本时单独运行。

### 5. 完整填写但不保存

先做安全表单测试：

```powershell
python main.py form-test --material-root "C:\Users\LEEDIS\Desktop\待上架\2701云栖"
```

这个命令只填写新增产品页，挂载本地文件到上传框，不提交上传，不保存商品。
它不会先完整执行 ERP 核对；填写型号时如果完整型号没有候选，才会用基础型号搜索 ERP 唯一候选。
默认会停在浏览器页面方便人工检查；如果要跑完自动关闭，追加 `--no-pause`。

再做上传测试：

```powershell
python main.py upload-test --material-root "C:\Users\LEEDIS\Desktop\待上架\2701云栖"
```

这个命令会实际触发素材上传，但不会点击保存商品。
它不会先完整执行 ERP 核对；填写型号时如果完整型号没有候选，才会用基础型号搜索 ERP 唯一候选，并把实际选中的 ERP 型号用于后续尺寸图上传。
默认会停在浏览器页面方便人工检查；如果要跑完自动关闭，追加 `--no-pause`。

```powershell
python main.py upload --material-root "C:\Users\LEEDIS\Desktop\待上架\2701云栖"
```

流程：

```text
登录 -> 新建商品 -> 填链接标题 -> 填 SKU/规格（完整型号无候选时才用基础型号兜底）-> 上传主图/内容详情图/尺寸图/无色图 -> 挂载视频并等待上传进度完成 -> 截图 -> 停在保存前
```

默认不会点击保存，会保存：

```text
logs/screenshots/final_before_save.png
```

默认会停在浏览器页面方便人工检查；如果要跑完自动关闭，追加 `--no-pause`。
如果正式上架流程中途失败，会停在失败现场，不会立刻自动关闭浏览器；运行日志会写出“失败位置”、失败原因和 `logs/screenshots/failed_*.png` 截图路径。确认页面后可以手动关闭浏览器，或在 GUI 里点击“停止脚本”。

### 5. 确认真正保存

```powershell
python main.py upload --material-root "C:\Users\LEEDIS\Desktop\待上架\2701云栖" --save
```

只有带 `--save` 才会点击保存按钮。

## 日志

日志文件在：

```text
logs/run_YYYYMMDD.log
logs/screenshots/
```

关键步骤都会输出 loguru 日志，失败时优先看当天日志和最近截图。
