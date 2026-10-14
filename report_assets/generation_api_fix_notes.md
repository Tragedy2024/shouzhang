# 文字生成接口修复记录

## 已确认的原因

2026-10-10 检查了本机任务状态：失败发生在 writing 阶段，照片分析与地点结果均已保留。

旧配置调用华为云 `deepseek-v4-pro`，实际最小测试返回 HTTP 404、`ModelArts.81009`、`Invalid model`。华为云[模型下线公告](https://support.huaweicloud.com/bulletin-maas/bulletin-maas-0002.html)说明该服务于 2026-09-30 下线。

官方建议的新模型在当前华为云账号返回 HTTP 403、`ModelArts.81004`，表示尚未开通。已开通的 Qwen 模型能够生成文字，但用户随后提供了 DeepSeek 官方密钥，并要求先改官方接入；最终没有采用 Qwen 写作方案。

## 当前改动

- 文字生成与语气改写默认调用 `https://api.deepseek.com/chat/completions`，模型 `deepseek-flash`，关闭思考模式。参数与 [DeepSeek 官方文档](https://api-docs.deepseek.com/)一致。
- `TEXT_MODEL`、`TEXT_API_URL` 支持环境变量及本机私有配置覆盖，环境变量优先。
- 用户提供的文字密钥只保存在 `instance/provider-secrets.json`，文件权限为 0600；未写入前端、源码说明或日志。原有照片分析和地图凭据保持不变。
- HTTP 401、402、403、404、429 与服务端错误显示具体、安全的中文提示；异常日志只记录状态码或异常类型，不显示密钥、请求内容或上游响应。
- 配置修复后，原失败任务仍可重试撰写步骤并复用照片分析。JSON 解码失败单独识别为结果异常。

## 验证与待办

- 全部离线 Python 检查：194 项通过，24 项真实接口检查未运行。
- 新增回归涵盖生成/改写的 HTTP 分类、连接异常、JSON 解码、思考模式、空密钥与配置优先级。
- 本地网站已重启并确认原地址可访问。
- 用户表示稍后提供接口信息。当前使用官方标准地址；新 DeepSeek 密钥尚未发起真实推理请求，待接口信息核对后验证生成。
