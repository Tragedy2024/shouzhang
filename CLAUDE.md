# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指引。

## 常用命令

```bash
# 创建虚拟环境并安装依赖
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 启动开发服务器
python3 app.py
# 运行在 http://127.0.0.1:5001，关闭 debug 模式；修改代码后需重启

# 运行所有测试
python3 -m pytest tests/ -v

# 运行单个测试文件
python3 -m pytest tests/test_text.py -v

# 运行单个测试用例
python3 -m pytest tests/test_text.py::TestTextGeneration::test_generate_journal_with_all_info -v
```

## 架构

> 本项目已增加私有照片存储、后台任务、结构化编辑和设备草稿。
> 当前接口、配置、隐私与测试说明以 `README.md` 为准。
> 前端逻辑现位于 `static/app.js`；生成入口为 `/api/jobs`，预览和下载共用 `/api/export-image`。
> 大厅入口为 `/hall`，接口位于 `/api/hall/`；发布弹窗由 `static/publish.js` 管理，大厅列表和详情由 `static/hall.js` 管理。
> 真实服务测试标记为 `live`，默认测试离线；不要在普通验证中调用付费 API。

基于 Flask 的 Web 应用，根据用户上传的旅行照片生成小红书风格的手帐。

**处理流水线**（`app.py` 中的 `_process_upload`）：
1. 保存上传的图片到 `uploads/` 目录
2. 提取 EXIF 数据：GPS 坐标 + 拍摄时间（`utils/image_utils.py`）
3. 视觉分析：将图片发送给 qwen2.5-vl-72b 模型，获取内容描述（`services/vision_service.py`）
4. 如果有 GPS 信息：通过百度地图 API 逆地理编码获取地址 + 搜索附近景点（`services/map_service.py`）
5. 通过 deepseek-v4-pro 模型生成手帐文本，综合视觉分析结果 + 地理位置 + 用户可选提示词（`services/text_service.py`）

**路由：**
- `GET /` — 单页 UI（左侧输入面板，右侧输出面板）
- `POST /upload` — HTML 表单提交的兜底方案（渲染 `result.html`）
- `POST /api/generate` — 供 AJAX 前端调用的 JSON 接口（接受 multipart 表单，包含 `image` + 可选的 `location`、`mood`、`feelings` 字段）
- `GET /uploads/<filename>` — 通过 `send_from_directory` 提供上传图片的访问

**核心文件：**
- `app.py` — 路由 + `_process_upload` 共享处理函数
- `templates/index.html` — 主界面（左右分栏布局，AJAX 提交）
- `templates/result.html` — 服务端渲染的兜底结果页
- `static/style.css` — CSS Grid 布局（1fr 1fr），768px 断点响应式
- `services/text_service.py` — `generate_journal()`，支持可选的 `location`、`mood`、`feelings` 参数
- `config.py` — 视觉模型、文本模型、百度地图的 API 密钥和端点

**设计决策：**
- `_process_upload` 被提取为共享处理函数，避免 `/upload` 和 `/api/generate` 重复 5 步流水线逻辑。流水线的任何修改只需改一处。
- 三个可选参数（`location`、`mood`、`feelings`）默认值均为空字符串，保证现有调用和测试向后兼容。
- AJAX 流程在提交后保留左侧面板的状态（图片预览、文本输入），无需页面刷新。
- AJAX 响应中所有用户可控的字符串在插入 DOM 前均经过 `escapeHtml()` 转义处理。
