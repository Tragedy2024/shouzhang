---
version: alpha
name: "智旅纪"
description: "以旅行相册为线索的中文手帐工作台与公开作品大厅。"
colors:
  bgLight: "#f3f5f6"
  surfaceLight: "#ffffff"
  surfaceSoftLight: "#eef1f3"
  paperLight: "#ffffff"
  inkLight: "#253038"
  mutedLight: "#5e6c76"
  faintLight: "#64717c"
  lineLight: "#dde3e7"
  controlLineLight: "#8596a2"
  accentLight: "#b83f46"
  accentHoverLight: "#a2363d"
  accentSoftLight: "#fbebed"
  accentLineLight: "#e9bfc3"
  primary: "#b83f46"
  buttonHoverLight: "#a2363d"
  onButtonLight: "#ffffff"
  focusLight: "#b83f46"
  warningBgLight: "#fff7e7"
  warningInkLight: "#735019"
  warningLineLight: "#e1c78f"
  backdropLight: "rgb(20 28 35 / .58)"
  bgDark: "#171e23"
  surfaceDark: "#20292f"
  surfaceSoftDark: "#29343c"
  inkDark: "#f1f4f6"
  mutedDark: "#b6c1c9"
  faintDark: "#a4b2bd"
  lineDark: "#3b4852"
  controlLineDark: "#6d7d89"
  accentDark: "#f1a5ab"
  accentHoverDark: "#ffc0c5"
  accentSoftDark: "#3e2d34"
  accentLineDark: "#79535b"
  buttonDark: "#ad3b43"
  buttonHoverDark: "#992e36"
  focusDark: "#f1a5ab"
  warningBgDark: "#3a3222"
  warningInkDark: "#f0d6a2"
  warningLineDark: "#79633e"
typography:
  sans:
    fontFamily: "\"PingFang SC\", \"Noto Sans SC\", \"Microsoft YaHei\", sans-serif"
  display:
    fontFamily: "ui-serif, \"Songti SC\", \"Noto Serif SC\", serif"
rounded:
  control: "10px"
  card: "20px"
omitted:
  - section: spacing
    reason: "页面使用现有响应式几何；共享源未定义 spacing 令牌，不虚构统一间距刻度。"
components:
  page-light:
    backgroundColor: "{colors.bgLight}"
    textColor: "{colors.inkLight}"
    typography: "{typography.sans}"
  panel-light:
    backgroundColor: "{colors.surfaceLight}"
    textColor: "{colors.inkLight}"
    rounded: "{rounded.card}"
  field-light:
    backgroundColor: "{colors.surfaceLight}"
    textColor: "{colors.inkLight}"
    rounded: "{rounded.control}"
    typography: "{typography.sans}"
  helper-text-light:
    textColor: "{colors.mutedLight}"
  field-placeholder-light:
    textColor: "{colors.faintLight}"
  divider-paint-light:
    backgroundColor: "{colors.lineLight}"
  scrollbar-thumb-light:
    backgroundColor: "{colors.controlLineLight}"
  secondary-button-hover-light:
    backgroundColor: "{colors.surfaceSoftLight}"
    textColor: "{colors.inkLight}"
    rounded: "{rounded.control}"
  primary-button-light:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.onButtonLight}"
    rounded: "{rounded.control}"
  primary-button-hover-light:
    backgroundColor: "{colors.buttonHoverLight}"
    textColor: "{colors.onButtonLight}"
    rounded: "{rounded.control}"
  accent-link-light:
    textColor: "{colors.accentLight}"
  accent-link-hover-light:
    textColor: "{colors.accentHoverLight}"
  accent-status-light:
    backgroundColor: "{colors.accentSoftLight}"
    textColor: "{colors.accentLight}"
    rounded: "{rounded.control}"
  accent-border-paint-light:
    backgroundColor: "{colors.accentLineLight}"
  focus-indicator-paint-light:
    backgroundColor: "{colors.focusLight}"
  warning-status-light:
    backgroundColor: "{colors.warningBgLight}"
    textColor: "{colors.warningInkLight}"
    rounded: "{rounded.control}"
  warning-border-paint-light:
    backgroundColor: "{colors.warningLineLight}"
  page-dark:
    backgroundColor: "{colors.bgDark}"
    textColor: "{colors.inkDark}"
    typography: "{typography.sans}"
  panel-dark:
    backgroundColor: "{colors.surfaceDark}"
    textColor: "{colors.inkDark}"
    rounded: "{rounded.card}"
  field-dark:
    backgroundColor: "{colors.surfaceDark}"
    textColor: "{colors.inkDark}"
    rounded: "{rounded.control}"
    typography: "{typography.sans}"
  helper-text-dark:
    textColor: "{colors.mutedDark}"
  field-placeholder-dark:
    textColor: "{colors.faintDark}"
  divider-paint-dark:
    backgroundColor: "{colors.lineDark}"
  scrollbar-thumb-dark:
    backgroundColor: "{colors.controlLineDark}"
  secondary-button-hover-dark:
    backgroundColor: "{colors.surfaceSoftDark}"
    textColor: "{colors.inkDark}"
    rounded: "{rounded.control}"
  primary-button-dark:
    backgroundColor: "{colors.buttonDark}"
    textColor: "{colors.onButtonLight}"
    rounded: "{rounded.control}"
  primary-button-hover-dark:
    backgroundColor: "{colors.buttonHoverDark}"
    textColor: "{colors.onButtonLight}"
    rounded: "{rounded.control}"
  accent-link-dark:
    textColor: "{colors.accentDark}"
  accent-link-hover-dark:
    textColor: "{colors.accentHoverDark}"
  accent-status-dark:
    backgroundColor: "{colors.accentSoftDark}"
    textColor: "{colors.accentDark}"
    rounded: "{rounded.control}"
  accent-border-paint-dark:
    backgroundColor: "{colors.accentLineDark}"
  focus-indicator-paint-dark:
    backgroundColor: "{colors.focusDark}"
  warning-status-dark:
    backgroundColor: "{colors.warningBgDark}"
    textColor: "{colors.warningInkDark}"
    rounded: "{rounded.control}"
  warning-border-paint-dark:
    backgroundColor: "{colors.warningLineDark}"
  paper-preview:
    backgroundColor: "{colors.paperLight}"
  dialog-backdrop:
    backgroundColor: "{colors.backdropLight}"
  display-heading:
    typography: "{typography.display}"
---

# 智旅纪 Design System

## Overview

### Creative North Star

界面像把旅行照片、便笺和一页已经排好的手帐放在同一张工作桌上：素材可整理，文案可修改，成品可查看。大厅延续相册与纸页的层次，让作品摄影成为视觉重点。外观服务于真实的编辑、保存与分享，不用装饰假数据制造热闹。

### Product context and register

- **Audience and primary job:** 中文使用者整理旅行照片、编辑手帐、下载 PNG，并自行选择公开分享。
- **Target market(s) and evidence:** 当前任务明确面向中文、中国用户；页面及 README 使用中文，公开发布时间格式采用 `zh-CN` 与 `Asia/Shanghai`。没有日本市场或日本业务要求。
- **Locale and language policy:** 产品文案为简体中文，模型名和 PNG 等必要格式名称保留；错误从用户能够采取的下一步描述，不展示技术响应、密钥或路径。
- **Usage scene:** 手机选照与浏览，电脑整理多图及编辑较长正文；离开页面后返回仍能继续已建立的后台任务。
- **Register:** `/` 与 `/hall` 均为产品界面，操作可靠性和清晰度优先；只在标题、样张和作品摄影中保留表达。
- **Memorable signature:** 实际照片与实际成品长图构成内容中心，纸页与背景形成安静的前后层次。
- **Restraint:** 表单、进度、确认及失败恢复使用熟悉的控件和一致的中文动词。
- **Anti-references:** 不做以营销口号占据工作台的落地页；不使用虚构帖子、统计、人物身份或旅游经历；不靠无意义序号、玻璃模糊和持续动画表现层次。
- **Token ownership/runtime mapping:** **Model B**。`static/app-shell.css` 是共享视觉令牌的唯一运行时源，`static/app-ui.js` 是跨页交互基础。此文档解释并镜像实际接受的值，不生成或覆盖 CSS。[令牌映射](docs/frontend/token-mapping.md)与 [drift gate](docs/frontend/check_token_drift.py)记录检查路径。

## Colors

共享颜色、字体、控件边界、焦点和外观状态只由 `app-shell.css` 定义；`creator.css`、`hall.css` 使用 `--app-*` 或只指向它们的兼容别名。不得在两个页面重新定义浅色或深色调色板。

语义角色包括页面背景、主表面、辅助表面、正文、辅助文字、普通分隔线、可交互边框、强调文字、强调背景、实心按钮及按钮前景、焦点、警告、滚动条。实心 CTA 的文字对比度与强调链接的文字对比度分别验收，不能因为当前值近似就合并语义角色。frontmatter 的 primary 镜像浅色实心CTA，Light/Dark 后缀镜像其余实际主题声明；深色主题继承未覆盖的 root 值。当前共享源共 49 项主题令牌声明，颜色、字体和圆角有 43 项精确文档映射，其余阴影／层级由映射清单记录。迁移记录未验证的部分不作为已通过结论。

支持 system、light、dark，同一个外观选择贯穿创作与大厅；兼容既有 `zhilvji-hall-appearance` 存储键。深色主题变更语义令牌，保留操作层级。强制颜色模式使用系统色，让焦点、输入和滚动条继续可见。

## Typography

使用共享 `--app-font-*` 字体栈，覆盖简体中文、中文标点和英文格式名；不下载外部字体作为恢复任务的前置条件。标题使用 `typography.display` 的书页字体栈，正文、字段和状态使用 `typography.sans` 的中文无衬线字体。编辑正文与表单输入采用 16px，辅助说明按角色使用较小字号；长文案保留自然换行和足够行高。

标题、正文、辅助文字与控件拥有明确层级。作者、话题和说明允许长中文及英文，不能撑出容器；用户原文用文本节点呈现。文案字数不当作模型 token 数。该项目不声明日本本土排版、日历或姓名规则。

## Layout

现有创作工作台在宽屏分为素材与作品两区；大厅使用作品网格。页面几何保留在 `creator.css`、`hall.css`，共享控件尺寸、圆角、表面和层级在 `app-shell.css`。

页面现有断点为 1100px、760px，窄屏另有 340px 处理。手机创作使用素材／作品切换，导航、主题切换与草稿操作保持可达；横向不产生页面溢出。照片顺序和删除同时提供按钮与拖动，不依赖触屏拖拽。

图片预留尺寸。空态样张完整显示，成品长图在自己的预览区域滚动；大厅缩略图可以裁切封面，详情展示完整长图。按钮待处理时保持尺寸；错误与状态不覆盖输入。sticky 动作考虑 safe-area 与短屏，键盘焦点不得被遮挡。

## Elevation & Depth

优先使用表面色、留白和边框表达层次。照片／成品纸页与弹窗可以使用共享阴影；普通内容容器不叠加不同页面的临时阴影。深色主题由共享阴影令牌适配，不改变控件边界和焦点。

原生 `<dialog>` 进入浏览器 top layer；页面 sticky 控件不通过更大的任意 z-index 抢占弹窗。共享层级为 sticky 100、dialog 600。阴影、遮罩的精确主题声明由 `token-mapping.json` 镜像。背景遮罩、弹窗内容和焦点规则由共享基础拥有。

## Shapes

圆角通过共享控件和卡片令牌统一；页面仅保留用途明确的图片几何。不要为创作按钮、大厅按钮、确认按钮分别创建形状。品牌字标和真实作者首字不是功能图标，不应改变其含义。

## Components

### Foundational visual states

Frontmatter使用官方schema支持的属性；hover、placeholder与辅助文字作为实际状态变体单列。`*-paint-*`是已有分隔线、边框和焦点轮廓的绘制颜色角色，backgroundColor表示无文本paint色，不要求新增DOM层或更改CSS属性。实际CSS消费路径见token映射清单；所有值仍由canonical CSS拥有。

按钮、链接、字段和可操作卡片覆盖默认、hover、focus-visible、active、selected、disabled 和 busy。成功、警告、错误同时提供文字；状态不可只由颜色表达。`[hidden]` 始终隐藏，不能被页面 display 规则抵消。加载显示真实阶段或稳定的状态区域，不展示假百分比。

### Buttons and actions

主动作使用实心强调；辅助动作使用边框或安静文字；清空草稿、撤回展示等危险意图与安全动作分开。所有主要手机目标至少 44px，图标按钮有中文可访问名称。禁用原因应能从旁边的状态理解，禁用按钮不再触发同一请求。

### Navigation and data display

创作／大厅导航使用真实链接，当前页有 `aria-current`。大厅最新分享／我的发布、话题与搜索状态使用稳定标签；显式“加载更多”，保留已加载作品直到新的结果可用。缩略图失败有可读回退。清空筛选保留“我的发布”范围。

### Forms and overlays

应用拥有校验和错误展示，产品 form 使用 `novalidate`。所有字段有 label；必要时通过 `aria-invalid`、`aria-describedby` 关联错误并聚焦首个需修正字段。Textarea 不允许自由拖动改变布局，提供足够高度或滚动。

Select 和日期输入明确采用 **native 平台 owner**：接受操作系统打开的选项、日历、键盘及弹出几何；不声称它们是自制统一弹层。可见输入外观仍消费共享令牌。发布、详情与清空确认使用原生 `<dialog>` 的浏览器焦点与 top-layer 能力，内部内容、名称、动作、错误和确认后果由应用拥有；不用 `window.confirm()`。共享接口为 `ZhilvjiUI.confirm({title,message,confirmLabel,destructive})`、`installTheme(scope,button)`、`resizeTextarea(element)`；网络与页面具名状态区仍由各页控制器适配同一契约。

### Iconography

保留已有轻量文字／符号与 CSS 图形；移动、移除、关闭、返回等符号必须有具体可访问名称。装饰性的摄影和字标不替代按钮文本，不为简单控件引入额外图标运行时。

### Motion

沿用短、可中断的控件颜色／摄影反馈；过渡不成为保存、生成或恢复的条件。`prefers-reduced-motion` 下取消非必要动画和滚动过渡。后台完成与返回页恢复不会突然抢走正在编辑字段的焦点。

### Content and data visualization

使用“生成手帐”“下载长图”“发布到大厅”“撤回公开展示”等实际操作名称；按钮与反馈保持同一词汇。错误保留作品并给出重试或重新选照的下一步。时间显示使用 `zh-CN`、`Asia/Shanghai`；不添加没有业务依据的图表、指标和示例帖子。

## Do's and Don'ts

- **Do:** 让真实照片、可编辑正文与同一份 PNG 预览承担主要内容。
- **Do:** 改共享样式时同时更新令牌镜像、跨页验收与迁移记录。
- **Do:** 让草稿保存降级、任务恢复和离线错误保持可操作。
- **Don't:** 在 feature CSS 再维护一份调色板或独立主题逻辑。
- **Don't:** 为视觉统一牺牲平台控件可用性、焦点、正文或现有草稿。
- **Don't:** 把待执行的浏览器检查或测试命令写成通过结果。
