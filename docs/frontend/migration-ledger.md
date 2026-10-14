# 前端统一与恢复迁移记录

日期：2026-10-14。范围：创作／大厅前端与文档；后端API、存储、权限、供应商调用和保留期保持既有业务。状态仅记录已观察到的事实，`migrating`不等于已通过浏览器验收。

| Surface / operation | Earlier evidence | Canonical target | Risk | Owner | Status | Verification |
|---|---|---|---|---|---|---|
| 创作：任务建立后看结果 | generate先await完整saveDraft再poll；IDB挂起导致GET任务次数为0 | 先保存job_id文字后备，完整保存后台运行，立即GET | 卡死与重复调用费用 | app.js创作控制器 | verified | creator_resilience_check的IDB挂起与任务完成用例；实际执行待记录 |
| 创作：初始化与返回页 | restoring无界等待；只有pagehide，没有统一pageshow恢复 | open/get1800ms，put/delete5000ms，去重resume、旧响应失效 | 新照片／旧作品丢失与长期锁定 | app.js + app-ui恢复基础 | verified | creator_resilience_check；真实bfcache/往返待记录 |
| 创作：response body | 旧fetchTimed在headers时清掉timeout | headers与JSON/PNG正文共享总deadline | 任务／预览永久busy | app.js请求适配，同一跨页deadline契约 | verified | creator_resilience_check的JSON/PNG挂起；实际执行待记录 |
| 两页：主题与令牌 | creator/hall各自维护theme逻辑与调色板 | app-shell.css ModelB + app-ui共享主题，页面只做别名／几何 | 跨页深浅色漂移 | 共享UI基础 | verified | tokenDrift已执行PASS：2 selectors / 49 declarations / 43 mirrors；lint与computed style待记录 |
| 大厅：搜索、清除与旧请求 | 搜索触发分散；旧页面独立request helper | 300ms防IME，立即清除／Enter，版本与cancel一致 | 搜索旧响应覆盖与中文输入误提交 | hall.js + app-ui | verified | hall_state_check；真实中文IME待记录 |
| 创作：清空确认 | window.confirm且等待saveSequence可挂起 | 应用内容native dialog，异步确认，等待有界，清空失效旧版本 | 草稿意外丢失／迟到保存复活 | app-ui确认基础 + app.js | verified | creatorResilience与浏览器取消／确认／焦点待记录 |
| 发布／撤回 | 独立snapshot和幂等、owner校验已经实现 | 保留业务，统一busy、状态和dialog基础 | 公开副作用与权限 | publish.js / hall.js；后端不变 | verified | publish_state_check、hall_state_check；浏览器待记录 |

## 已完成的只读证据

此前只读Node mock复现了IDB open永不完成导致入口禁用，以及任务POST成功但IDB put挂起导致generating=true、GET次数0。这是旧行为的诊断证据，不是本轮修复后的PASS。没有调用真实供应商API或读取用户数据库／密钥。

## 令牌与兼容层

- 唯一运行时令牌源：`static/app-shell.css`；共享行为：`static/app-ui.js`。
- 页面角色兼容别名：creator.css 的 `--creator-*` 与hall.css 的 `--hall-*`。允许指向共享语义令牌，不允许复制实际颜色值。
- style.css承载原有结构基线，迁移中不得删除还被result兼容页使用的结构；其未迁移的历史字面样式必须在共享shell覆盖，不作为新增令牌作者源。
- 外观存储键继续使用历史 `zhilvji-hall-appearance`；删除旧主题代码前先确认共享入口覆盖初始load、pageshow、system变更和跨页选择。
- 不提供正式账号、跨设备草稿同步、帖子恢复或硬删除；不能因为UI统一新增业务状态。

## 验证登记

| Command / evidence | Result |
|---|---|
| node tests/frontend_state_check.cjs | 交付负责人已报告本轮执行PASS；详细运行证据由verification.md补充 |
| node tests/creator_resilience_check.cjs | 交付负责人已报告本轮执行PASS；详细运行证据由verification.md补充 |
| node tests/hall_state_check.cjs | 交付负责人已报告本轮执行PASS；详细运行证据由verification.md补充 |
| node tests/publish_state_check.cjs | 交付负责人已报告本轮执行PASS；详细运行证据由verification.md补充 |
| python3 docs/frontend/check_token_drift.py | 本文档代理2026-10-14执行PASS，0 errors |
| node docs/frontend/semantic_binding_check.cjs --output docs/frontend/semantic-binding-report.json | 本文档代理2026-10-14执行PASS，45/45 literal buttons有外部ID、提交或代理owner证据，0 errors |
| 官方designmd lint DESIGN.md | 由交付负责人执行，未预填结果 |
| Premium strict项目审计 | 文档／manifest落地后由交付负责人执行，未预填结果 |
| 浏览器desktop/390/320、light/dark/system、native popup、往返与bfcache | 待真实浏览器验收；mock不能替代 |

官方静态audit的literal-button规则不能看见external addEventListener，项目补充报告解释该工具误报。仍保留官方原始strict报告与全部templates/static范围，不加无意义onclick，也不把补充报告称为官方零errors。后续实际验收记录写入 `docs/frontend/verification.md`。

## 退回与移除门槛

按行为slice退回页面适配器，保留原有API与草稿schema兼容；不能通过退回修复重新引入无界等待或重复POST。只有共享源、镜像、四组检查及真实浏览器状态覆盖后，才将对应项改为verified。兼容别名无消费者、全局及原生控件验收完成后才移除，不维护第二份公共系统。

## 最终交付验收

根代理已完成1366×900、390×844、320×640与light/dark/system浏览器检查；选图、拖放、立即往返照片保留、完成内容无需刷新显示、发布／大厅详情、搜索清除及清空取消已验收。所有五套前端检查通过，194项离线Python测试通过。最终官方DESIGN lint为0 errors、0 warnings；官方Premium原始strict仍保留38项external-binding误报及45/45补充证据。具体范围、截图和局限见verification.md，上表初期“待记录”描述由此记录取代。
