# 前端修复验收记录

日期：2026-10-14。范围为创作页、大厅和共享UI；app.py及services/*.py开工／完工SHA-256一致。未更改供应商接口、权限、数据保留期或后端任务状态。

## 诊断与修复

- IndexedDB open/get原先没有时限，restoring一直为true会禁用选图。连接／读取现在1800ms内完成或降级；迟到读取不能覆盖新选择。
- POST建立任务后原先await完整草稿put才启动GET；照片存储卡住会让后端已完成、页面仍busy。任务编号立即写入文字后备，完整保存后台进行，立即查询结果。
- 页面隐藏／返回取消旧轮询和预览，通过pageshow与visibility恢复已有任务的GET；不会重发生成POST。后台恢复完成不抢编辑焦点，手机素材／作品区域也随草稿恢复。
- JSON和PNG正文与响应头共享请求总期限，超时有重试入口；旧结果不能回写新页面。
- 选照立即保存；离开时已有数据库连接同步发起最新照片快照，完成或超时后关闭，回到新页面可恢复顺序和文件。
- 清空确认改为应用自己的dialog，默认取消，取消／Escape保留草稿；清理期间禁用冲突操作，旧保存不能让已清空草稿复活。
- 过期照片HEAD请求先捕获文件名，重排成品后仍移除原来的过期照片。
- 共享主题、控件、滚动条、字体和色值集中在app-shell.css/app-ui.js。五种风格完整展示、选填资料默认展开，素材表单按文档自然滚动；长图在预览区可滚动。
- 大厅搜索提供300ms防IME输入、立即提交与清除；外观偏好在往返、系统变更和多页间重新读取。

## 实际运行

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 五套Node前端检查 | 全部PASS | frontend-checks.txt |
| creator_resilience_check | 11项故障回归PASS，包括挂起存储、迟到回写、两次往返、全新页面照片恢复、JSON/PNG正文超时、HEAD重排 | tests/creator_resilience_check.cjs |
| Python离线测试 | 194 passed，24 live deselected，7.30s | 实际pytest输出；未调用付费API |
| JS语法检查 | app.js、app-ui.js、hall.js通过 | node --check |
| 令牌镜像gate | 49声明／43镜像PASS | token-mapping.json、check_token_drift.py |
| 外部动作绑定gate | 45/45 PASS | semantic-binding-report.json |
| 官方Premium strict静态审计 | 原始38项均为actionless-button | premium-audit.json；规则只识别inline onclick，外部ID／代理事件证据见补充gate，不宣称原始审计零错误 |
| 官方designmd lint | 0 errors、0 warnings | designmd-lint.json；官方npm包 @google/design.md v0.4.0 |

## 浏览器验收

使用真实Flask路由的隔离5002测试环境：临时SQLite、uploads、hall-media，合成旅行图片和固定延时6秒的模型返回；requests外连被拒绝。真实生成任务、PNG排版、发布与详情均使用项目后端，供应商回答仅替换为离线样本。未把测试帖子写入5001项目数据。

- 桌面1366×900与1280布局：双栏、照片、成品预览、标题和动作正常；无横向溢出。
- 手机390×844与320×640：导航与外观／草稿操作可达，五风格按窄屏换行，照片箭头／删除保持按钮，长表单可滚动至旅行感受和生成按钮，无横向溢出。320时照片操作换行而非裁掉。
- 从创作选图、填资料→大厅→返回，再选图和拖入→生成→大厅→返回：不用刷新即可看到完成内容和PNG。随后选入第三张后立即往返，照片数量始终3/9；新的页面也能恢复照片。
- light/dark/system主题：深色字段背景rgb(32,41,47)、正文rgb(241,244,246)；root scrollbar颜色由共享令牌生效。两页主题沿用同一偏好键。
- 天气原生选项与日期日历实际打开；Escape关闭日历，焦点回日期入口。native popup的字体、语言和几何由平台拥有，不声称自制弹层。
- 手机发布dialog：标题、长表单与关闭按钮可达；勾选明确公开同意后在测试环境完成发布，详情展示完整手帐和真实测试作者。大厅搜索提交／清除后URL移除q，焦点回搜索框。
- 清空dialog默认焦点在取消；Escape保留3张照片和作品，焦点回触发按钮。

照片／表单和业务故障路径还有离线状态回归。未运行真实收费模型、Lighthouse、独立屏幕阅读器或OS软键盘测试；不据此宣称性能分数或完整WCAG认证。浏览器往返实测与pagehide/pageshow事件回归分别记录，不声称已证明所有浏览器都使用BFCache。

截图：screenshots/creator-sample-desktop.jpg（正式网站完整样张，750×1199且object-fit:contain，选填默认展开），screenshots/creator-desktop.jpg与screenshots/hall-desktop.jpg为合成测试内容。真实项目服务保留在5001；隔离测试服务在验收后停止。
