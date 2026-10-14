# 智旅纪

把旅行照片整理成可以编辑、保存和下载的手帐。支持多图排序、五种排版、正文编辑、撤销重做、草稿恢复和高清 PNG 导出，也可选择把成品发布到手帐大厅。

## 本地运行

项目使用 conda 环境 `shouzhang`（Python 3.12，依赖见 `requirements.txt`）。已经建好环境的机器直接激活；新机器用 `environment.yml` 重建：

```bash
conda activate shouzhang
# 新机器: conda env create -f environment.yml
# 依赖变更后: conda run -n shouzhang python -m pip install -r requirements.txt
python app.py
```

Windows 上建议先执行 `set PYTHONUTF8=1`，否则中文日志和测试输出在 GBK 控制台可能抛 `UnicodeEncodeError`。旧的 macOS 命令 `python3 -m venv .venv && source .venv/bin/activate` 只在 macOS/Linux 可用。

打开 http://127.0.0.1:5001。开发服务默认仅在本机运行，调试模式关闭。

照片分析与地图连接保持原配置，文字生成和语气改写使用 DeepSeek 官方服务。密钥保存在 `instance/provider-secrets.json`，该目录不应提交或共享；也可用环境变量覆盖：

- `VISION_API_KEY`：照片分析服务密钥。
- `TEXT_API_KEY`：文字生成服务密钥。
- `TEXT_MODEL`：文字模型，默认 `deepseek-flash`。
- `TEXT_API_URL`：完整的文字生成接口地址，默认 `https://api.deepseek.com/chat/completions`。更换供应商时需一并核对地址、模型和密钥。
- `BAIDU_MAP_API_KEY`：地图服务密钥。
- `JOURNAL_SECRET_KEY`：可选的会话签名密钥；本地默认自动生成并持久保存。
- `JOURNAL_HTTPS=1`：通过 HTTPS 部署时启用安全 Cookie。
- `JOURNAL_HOST`：可选监听地址，本地默认 `127.0.0.1`。
- `JOURNAL_FONT_PATH`：可选中文字体文件路径。也支持 `static/fonts/NotoSansSC-Regular.ttf`、`NotoSansSC-Bold.ttf`，或系统中文字体。

`TEXT_MODEL` 和 `TEXT_API_URL` 也可写入本机的 `instance/provider-secrets.json`。配置修改后需重新启动网站服务。DeepSeek 写作关闭思考模式，直接生成手帐正文；认证失败、余额不足、模型不可用、限流等错误会显示具体原因，配置恢复后可重试原任务并复用已经完成的照片分析。

## 使用与保存

最多 9 张照片，单张 16MB、合计 50MB，支持 JPG/PNG/WebP。手机 HEIC 照片请先转换。上传前后都会校验图片，上传副本会自动转正并移除 EXIF；拍摄日期和地点线索只用于当前会话内的生成流程。正文优先采用用户填写的地点与日期，附近景点不作为到访经历。

照片和任务保存 7 天，过期后在服务收到请求时自动清理。清理仅针对本版本登记的上传文件，不会删除此前已有的文件。照片只能通过上传时的浏览器会话访问。清除浏览器 Cookie 会失去这些照片的访问权限。

草稿及照片素材保存在当前浏览器设备中，不会跨设备同步。编辑文字和调整成品设置会自动更新 PNG 预览；下载复用同一张成品图，避免预览与导出不一致。过期照片会从成品中移除，文字仍可编辑或导出，素材可重新选择后生成。

## 手帐大厅

顶部导航可在创作页与 `/hall` 大厅之间切换。完成手帐后，点击作品区的“发布到大厅”，填写分享标题、说明、昵称和最多 5 个话题，每个话题最多 20 字。确认公开后再发布；生成和编辑草稿不会自动发布。

所有访客都可以浏览公开作品、搜索分享内容、按话题筛选、打开完整长图。大厅使用服务器保存的发布快照，后续修改草稿不影响已发布作品。公开长图及缩略图独立保存，原始上传副本过期后仍可展示；未经选择发布的原照片继续保持私有。

“我的发布”显示当前浏览器身份发布的作品，可以撤回公开展示。撤回后帖子及图片不再对外提供，数据库记录保留，避免误作永久删除。发布通过幂等键防止网络重试产生重复帖子；每个浏览器身份每天最多发布 20 条。

当前版本使用昵称与浏览器 Cookie 区分发布者，身份 Cookie 持续有效期为 365 天，照片保留期仍为 7 天。清除 Cookie、换浏览器或换设备后无法管理此前发布的作品；正式账号登录和跨设备同步尚未接入。

- `GET /hall`：公开大厅页面，支持 `?topic=话题` 与 `?post=帖子ID` 分享链接。
- `GET /api/hall/posts`：公开作品分页，支持 `topic`、`q`、`mine=1`、`page`、`page_size`。
- `GET /api/hall/topics`：当前公开作品的话题及数量。
- `POST /api/hall/posts`：确认公开后提交作品快照及分享信息。
- `GET /api/hall/posts/<id>`：作品详情。
- `GET /api/hall/posts/<id>/image`、`/thumbnail`：公开成品与缩略图。
- `POST /api/hall/posts/<id>/withdraw`：仅发布者可撤回公开展示。

大厅数据与任务同存于 `instance/journal.sqlite3`，公开图片保存于 `instance/hall-media`。部署和备份时应一并保留数据库、公开图片目录与会话签名密钥。当前仍默认仅在本机运行；其他设备访问需要部署到可访问的服务器。

## 生成任务

前端使用后台任务并显示实际阶段：准备照片、分析照片、整理地点、撰写手帐。识图或写作失败会返回明确错误，已有作品继续保留。重试会复用成功的识图和地点结果；服务重启后，中断任务可重试恢复。

- `POST /api/jobs`：创建任务，接收 multipart 照片和补充信息。
- `GET /api/jobs/<id>`：查询任务阶段和结果。
- `POST /api/jobs/<id>/retry`：重试失败任务。
- `POST /api/regenerate`：调整文案语气。
- `POST /api/export-image`：按当前作品快照生成 PNG，支持 750px / 1500px 宽度。
- `GET /api/sample/<style>`：使用同一渲染器生成的内置示例，示例配图为内置插画。

原同步生成接口和表单入口继续保留。任务由当前服务进程的线程池执行，状态存入 SQLite。当前实现适合本机或单服务进程；多进程、多实例部署应使用共享任务队列，并统一照片存储与会话密钥。

## 验证

```bash
python -m pytest -q
node --check static/app.js
node tests/frontend_state_check.cjs
node tests/publish_state_check.cjs
node tests/hall_state_check.cjs
```

默认测试全部离线，覆盖生成重试、图片校验、跨会话权限、路径越界、照片清理、EXIF、长图裁切、文案真实性规则和异常响应；大厅测试还覆盖公开快照持久化、话题检索、发布幂等与并发、每日限额、权限撤回及前端请求竞争。真实模型与地图测试单独标记，不会默认执行；需要实际凭据且可能产生费用时，可主动运行 `python -m pytest -m live -v`。
