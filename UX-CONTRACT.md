# UX Contract

本文件记录跨页面的 UI 后果与本轮已确定的恢复契约。后端权限、生命周期及 API 规则由下表中的维护源拥有；不以视觉迁移改变业务。验证状态单独记录在 [迁移记录](docs/frontend/migration-ledger.md)。

## Product context

- Audience / primary jobs: 简体中文用户选照、生成与编辑旅行手帐、下载 PNG、自行选择公开分享、浏览及撤回自己的分享。
- Target market(s): 当前产品任务明确面向中国、中文使用者；无日本市场或日本专用数据要求。
- Active locale: `zh-CN`；页面与可访问名称使用中文，必要的文件格式或模型名保留。
- Timezone/calendar: 公开时间显示 `Asia/Shanghai`；旅行日期是无时区 ISO 日期，日期控件由平台拥有。没有年号日历。
- Register / review: 产品界面，采用简洁操作文案；中文人工文案核对与浏览器验收由本次交付负责人执行，不自动声称已完成。
- Accessibility target: WCAG 2.2 AA；原生控件、可见焦点、中文可访问名称、拖动的按钮替代、文字错误。

## Business-context sources

| Domain / scope | Authoritative source | Source type | Reviewed date |
|---|---|---|---|
| Permission model | [README 使用与保存／大厅](README.md)，[app.py 的 _owner、私图及发布路由](app.py)，[JournalStore.photo](services/storage_service.py) | 维护产品说明与已验证服务器 API；无正式账号登录 | 2026-10-14 |
| Data lifecycle | [生成任务 API](README.md)，[任务状态与阶段](app.py)，[JournalStore](services/storage_service.py) | 维护 API 说明／服务器生命周期 | 2026-10-14 |
| Deletion / retention | [README 使用与保存／大厅](README.md)，[cleanup](services/storage_service.py)，[withdraw](services/hall_service.py) | 维护产品说明／服务器 API；不扩展为法律意见 | 2026-10-14 |
| Public confirmation / idempotency | [_hall_publication_fields 与 hall_publish](app.py)，[HallService.preflight/publish](services/hall_service.py) | 服务器公开发布与幂等契约 | 2026-10-14 |
| Billing / payment | [README 配置与离线验证](README.md) | 无产品支付 UI；真实供应商调用不可由恢复逻辑重复提交 | 2026-10-14 |
| Legal / regulatory copy | [现有公开确认与隐私提示](templates/index.html)，用户授权的前端修复范围 | 现有产品文案；保留语义，不虚构法律审核 | 2026-10-14 |
| Market / content conventions | [README](README.md)、[中文页面](templates/index.html)、当前中国用户产品任务 | 产品范围与现有内容证据，不宣称用户研究 | 2026-10-14 |

## Visual contract

- Taste context: [DESIGN.md](DESIGN.md)。
- Token ownership: **Model B, existing runtime canonical**。
- Runtime source: [static/app-shell.css](static/app-shell.css)；行为基础：[static/app-ui.js](static/app-ui.js)。
- Page adapters: `static/creator.css`、`static/hall.css` 仅将页面角色映射到 `--app-*`；不定义另一套颜色或字体值。
- Mapping / drift: [token-mapping.md](docs/frontend/token-mapping.md)、[check_token_drift.py](docs/frontend/check_token_drift.py)。
- Themes: system/light/dark；沿用既有外观存储键，并在两个页面同步。
- Owner / review: 共享基础修改由项目交付负责人维护，必须同时验收创作与大厅。

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Select/Listbox | Native HTML select，浏览器／操作系统拥有打开的选项 | 本契约的平台 owner 决策；app-shell 可见字段样式 | native；接受平台 popup 几何与键盘行为 | 桌面与手机打开真实 select，键盘选择和焦点回归 |
| Date | Native input[type=date]，浏览器／操作系统拥有日历 | 本契约的平台 owner 决策；服务器 ISO 日期校验 | native；系统日历与键盘，应用保持旅行日期语义 | 真实日期弹层、中文标签、窄屏及键盘验证 |
| Form | app-shell 字段／按钮样式，app-ui Textarea／确认基础，页面各自校验适配 | 本契约 Validation；服务器 API 校验 | 素材、编辑、搜索、公开发布 | frontend_state_check、publish_state_check、hall_state_check 及浏览器首错焦点 |
| Scrollbar | app-shell 全局 standards 与 WebKit fallback | DESIGN.md；app-shell scrollbar 令牌 | 成品／详情区域仅改变几何与 scrollbar-gutter | computed style、键盘滚动、深浅色与 forced-colors |
| Toast | 本产品不使用独立toast；具名native role=status/alert 区域由各页控制器拥有，视觉由app-shell拥有 | 本契约 Overlays and feedback | inline／页面status；关键反馈持续可见，不创建另一套toast | 页面中文 status、重复反馈与读屏语义核对 |
| CRUD | 既有 Flask API + 页面控制器，app-ui 提供跨页公共行为 | 维护 README/API；本契约 Flow ledger | 生成与编辑留在作品区；发布给大厅链接；撤回刷新当前列表 | 四组 Node 状态检查；真实发布／撤回离线服务与浏览器 |

Table Selection 不适用：大厅是作品 feed，无表格批量勾选、批量删除或 all-results 操作。

## Component behavior

| Component | Default | Hover | Focus | Active | Disabled | Busy | Error |
|---|---|---|---|---|---|---|---|
| Button | 真实 button / 导航用 a | 共享令牌反馈与 pointer | 可见 outline | 不改按钮尺寸 | 不触发，原因在状态文字 | 防重复激活，稳定尺寸 | 保留动作和可重试说明 |
| Icon button | 至少 44px 手机目标、具体中文名称 | 共享反馈 | 同按钮 | 同按钮 | 正确 disabled | 不重复执行 | 不仅用颜色 |
| Input / select / date | label、平台语义、共享边框 | 共享表面反馈 | 同共享焦点 | 平台交互 | 原生禁用 | 仅锁本次操作必需字段 | 文本提示、aria-invalid、aria-describedby |
| Search | 非空有清除动作、300ms debounce | 同字段 | 清除后回输入 | Enter立即提交 | 请求中允许继续修改条件 | 稳定feed加载区域 | 已加载结果保留与重试 |
| Textarea | resize none、足够高度、长文滚动 | 同字段 | 同字段 | 正常选择输入 | 改写时禁用，旧正文保留 | 不依赖保存状态锁死 | 保留全文并指出修正方法 |
| Feed / preview | 真实作品／预留媒体几何 | 卡片有限反馈 | 链接／按钮可达 | 当前条件清晰 | 无数据有空态 | 显示真实任务阶段或稳定区域 | 缩略图、详情、排版各自回退 |

没有客户端密钥输入；供应商密钥不进入前端、草稿、URL、日志或用户提示。

## Dataset navigation

- 大厅为探索式 feed，采用显式“加载更多”，默认 12 篇；服务器页大小与校验见维护 API。
- URL 持久化已提交的 `q`、`topic`、`mine` 和打开的 `post`。页码不作为分享语义：重新进入从第一页核对，加载更多是本次视图增量，不制造与现有客户端不符的页码恢复承诺。
- 搜索／话题改变重置 feed 的加载页；清空搜索立刻执行，清空筛选保留“我的发布”。
- Loading、空大厅、无搜索结果、部分失败、图片失败都有独立反馈；失败不清掉已经读取的卡片。
- 浏览器管理原生后退滚动；列表恢复与详情关闭保留可识别上下文，异步完成不强制把输入焦点跳走。无批量选择。

## Flow ledger

| Operation | Trigger | Pending | Success destination | Success feedback | Failure recovery | Focus outcome | Source ref |
|---|---|---|---|---|---|---|---|
| 选照／排序 | 选择或拖入、前移／后移／移除 | 本地校验，不等持久化才允许操作 | 素材区 | 照片数量与顺序 | 保留旧有效素材，显示格式／大小／数量说明 | 删除后邻近照片操作或上传按钮 | app.js addPhotos/renderPhotos/movePhoto；服务器 _save_uploaded_images |
| 后台生成 | 生成旅行手帐 | 上传→真实阶段；防重复POST | 作品区 | 展示本次完整 result 并更新预览 | 旧作品保留；已有 job 用GET核对，失败按retryable提供重试 | 显式生成可聚焦作品标题；返回页恢复不抢输入 | app.py /api/jobs；app.js generate/runPolling |
| 编辑与改写 | 字段修改／语气按钮 | 当前快照变更；改写保留旧文本 | 原作品区 | 同一份正文与成品设置 | 保留全文，预览可单独重试 | 继续在编辑字段；显式改写完成按现有作品流程 | app.js editResult/regenerate；/api/regenerate |
| 导出 | 下载长图 | 仅匹配当前key的缓存可下载 | 留在作品区 | 下载预览同一PNG Blob | 预览过期则先重排，不把旧PNG当新作品下载 | 保留下载按钮上下文 | app.js previewKey/download；/api/export-image |
| 公开发布 | 发布到大厅、明确公开确认 | 保留表单、固定作品快照与幂等键 | 成功面板和大厅作品链接；本地草稿保留 | 已发布 | 未确定完成时重用同payload/key查询式重放，不重复生成帖子 | 成功作品链接；关闭返回发布按钮 | app.py hall_publish；HallService.preflight；publish.js |
| 搜索／筛选 | 输入、Enter、话题、我的发布 | 300ms防IME；取消旧GET，版本保护 | 当前大厅 | 数量与条件 | inline错误与重试，已有卡片保留 | 输入或当前筛选按钮 | hall.js；GET /api/hall/posts |
| 公开撤回 | 自己作品详情中的撤回确认 | 防重复执行，保留确认内容 | 关闭详情并刷新原大厅范围 | 已撤回公开展示 | 不声明永久删除；未确定时刷新核对并重试 | 邻近卡片或列表范围按钮 | HallService.withdraw；hall.js withdraw |
| 清空草稿 | 清空草稿→应用异步确认 | 等待确认、取消计时器与过期响应、等待有界保存队列 | 空素材区，页面仍可继续创作 | 草稿已清空 | 取消不变更；存储失败给出真实降级反馈 | 初始取消动作；完成后上传入口 | app.js clearDraft；app-ui确认dialog |
| 返回创作页 | pageshow / 可见性恢复 | 去重恢复；取消旧GET和旧预览 | 现有素材／作品上下文 | 已有job最新状态 | 不重发创建POST；读取失败提供继续查看 | 不自动跳走正在编辑的焦点 | app.js suspendPage/resumePage |

正式账号、跨设备同步、评论、点赞、收藏、审核、帖子编辑、恢复帖子、永久删除均未实现，不加入新入口。

## Navigation and responsive behavior

- 真实路由为 `/` 与 `/hall`；两页 document title 表示创作或大厅，当前导航用 aria-current。
- 原生 select/date 保留平台 popup owner；不以 CSS appearance 设置宣称应用拥有 popup。
- 手机素材／作品切换保留状态，44px动作与可见焦点；sticky动作、dialog 和输入避开 safe-area 与虚拟键盘。
- 成品长图、详情与dialog自己的内容可以滚动，不能把整个页面锁成不完整的 fixed-height 表单。
- 私有照片／任务过期或无权限时保留当前文字与素材说明；大厅不存在／已撤回详情给出返回列表路径。403不能通过UI绕过。

## Overlays and feedback

- Canonical primitive: 应用内容的 native `<dialog>`，由 app-ui 统一确认与焦点恢复；公开发布和作品详情使用业务具名dialog。
- 清空草稿先焦点取消按钮；说明会清空本设备素材、作品与编辑历史，已下载作品保留。撤回说明只停止公开展示，保留记录；公开发布每次新打开都重新确认。
- 关键错误、恢复提示与任务进度使用页面具名 live/status 区域；不自动消失，不只放在toast。app-shell统一状态视觉，页面控制器维护具名区域和文案；不存在未实现的全局toast服务。
- dialog top layer 高于sticky内容，Escape与关闭按钮行为一致，忙于外部写入时防止重复确认；关闭后回到触发按钮或有效列表位置。
- 本地持久化失败不谎报完整保存；导航时尽力同步保存文字后备，不靠卸载时等待IndexedDB完成。

## Async and resilience

- 外部mutation按服务器确认提交：创建任务、改写、公开发布、撤回。浏览器编辑与预览为本地可恢复状态，不新增离线API写入队列。
- IndexedDB open/get **1800ms**，put/delete **5000ms**。超时结束等待并处理迟到连接／事务；不能让 saveSequence、restoreDraft、clearDraft 永久占用UI。
- 上传POST成功后先保留job_id到同步文字后备；完整草稿后台保存，不能阻挡第一次任务GET。
- 恢复不得用迟到的旧记录覆盖用户新选照片、新编辑或已经核对的任务结果。清空使所有旧版本失效，防止迟到写入复活草稿。
- 网络响应头和JSON/PNG正文使用**同一总deadline**；正文挂起也触发恢复。按既有操作保持任务GET25秒、上传／预览90秒、语气改写120秒；app.js的fetchTimed及大厅／发布请求适配负责本操作deadline与取消，不虚构app-ui内的网络helper。
- pagehide只挂起浏览器工作、保留文字后备；pageshow、visibility visible与连接恢复去重地重新GET已知job。只恢复GET轮询，不重复POST创建任务、不修改后端任务状态。
- 有pendingJob就核对服务器真实状态，不依赖草稿保存的旧status；completed立即应用result，failed按服务器retryable展示动作，过期清理pending引用但保留作品。
- 旧poll／旧preview版本无效时禁止覆写新状态；仅当前版本负责释放busy。mutation尚未返回job_id时不得假装取消了服务器，也不得自动重发。
- 大厅搜索300ms debounce，composition期间不提交，compositionend再安排，Enter和清空立即执行；旧搜索、详情与话题响应都受版本保护。
- 浏览器online事件只是重新核对的提示，不作为服务器可达证明。重试次数有界，未知完成保持中性文字。
- 多标签页不声明跨设备同步或内容合并能力；共享外观可同步，同一已有job可以核对；旧草稿不得静默覆盖本页新编辑。
- 清除cookie可能失去私图和发布管理身份；展示现有API的访问错误，不新增虚构登录流程。

## Validation

- 应用校验拥有 form novalidate、首错焦点、保留值与中文反馈；服务器仍是格式、长度、owner权限和日期的最终校验来源。
- 选照、公开字段、话题和文案字数在明确触发时校验；不要在IME输入途中把半成品当错误或提交。
- 表单错误摘要与字段关联，API错误使用短中文，不含端点、headers、密钥、GPS或私有路径。
- 发布失败保留同作品快照与表单；payload变化换key，相同payload失败重试复用key。不能把网络重放变成未经再次确认的新公开发布。

## Permission and clipboard

- “我的发布”与撤回按is_owner呈现，但服务器owner校验不能由UI代替；错误后重新核对，保留安全输入。
- 复制手帐正文采用Clipboard API，失败提供文本选择回退；反馈不重复显示整段内容，不触及供应商密钥。
- 不可下载／发布时说明需要当前有效成品预览；生成／改写busy仅暂时锁定相关操作，存储失败不能长期禁用照片入口。

## Migration status

- Ledger: [docs/frontend/migration-ledger.md](docs/frontend/migration-ledger.md)。
- Shared owners: `app-shell.css` + `app-ui.js`；创作、大厅页面适配器与原生平台选择保留。
- 优先顺序：恢复卡死／任务显示→公共主题与反馈→搜索IME／dialog→视觉收口。
- 没有引用、状态与浏览器证据之前，不删除兼容别名或切换共享令牌所有权。不通过修改文档合理化权限／业务变化。

## Verification

- Required static/runtime commands 由 [premium-ui.json](premium-ui.json)登记；四组页面Node状态检查、app_ui_check共享主题／确认／Textarea检查、令牌drift gate与semantic binding补充检查需分别运行，命令存在不等于执行通过。
- 浏览器矩阵：创作↔大厅真实往返与bfcache、desktop/390px/320px、浅色／深色／跟随系统、键盘选照与dialog、native select/date真实popup、搜索IME、慢IDB、超时正文、离线与旧响应。
- 功能边界：已知任务恢复不得新增POST；已完成任务返回立即显示；草稿、旧作品与发布确认完整保留；拒绝假百分比或假完成。
- 当前无Storybook或独立visual regression系统；mock状态测试不替代真实键盘、popup几何、焦点、对比度与滚动验证。
- 官方designmd lint、Premium strict审计与浏览器结果由交付负责人运行记录；本契约不预填PASS。
- 官方Premium静态审计只识别literal button的inline onclick/@click，不识别项目外部ID及data代理绑定。保留官方原始报告，并用 [semantic_binding_check.cjs](docs/frontend/semantic_binding_check.cjs)补充实际载入脚本的绑定证据，不能加空onclick或缩小审计范围制造零errors。补充检查不代替运行时动作、键盘或焦点验证。
