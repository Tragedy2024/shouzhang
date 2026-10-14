# 手帐大厅前端改版

使用 design-taste-frontend 技能，按保留品牌的视觉改版处理。面向旅行记录者，以手帐成品和照片为主，采用轻杂志式排版。

- DESIGN_VARIANCE: 6，变化集中在图片比例、留白和详情布局。
- MOTION_INTENSITY: 3，仅使用反馈性质的 hover、active 与 focus。
- VISUAL_DENSITY: 4，保证筛选与作品浏览的效率。
- 使用已有 Flask 模板与原生 CSS / JavaScript，保留品牌、导航名称、URL、表单字段和后端接口。
- 后端源文件在修改前后逐一比较 SHA-256，验证保持不变。

## 页面配图

使用内置 image_gen 工具生成，未使用 CLI/API fallback。配图用于品牌引导与空状态，不作为用户发布作品。

项目文件：[hall-travel-banner.webp](/Users/lujiahao/Documents/手帐/static/images/hall-travel-banner.webp)。从生成原图转换为 WebP，保留原有像素与构图，只做网页格式压缩。

生成提示词：

```text
Use case: photorealistic-natural. Asset type: a compact editorial travel photograph for a Chinese travel-journal community website, used as an introductory image and empty-state image, not a user post. Generate a photorealistic horizontal 3:2 photograph: a quiet coastal road curving gently above a blue-green sea, distant softly layered cliffs, Mediterranean-like natural shoreline without identifiable famous landmarks, one tiny white sailboat offshore, lush sparse roadside foliage, clear pale sky. Editorial travel magazine photography, real fine texture, calm morning daylight, understated natural cyan sea and sage foliage, warm sunlight on limestone, convincing depth, restrained film-like color, crisp yet soft, no dramatic HDR. Composition should work when cropped into a wide 2.4:1 banner as well as a small landscape image, keep the horizon and coastline within the middle 60% of the frame. No people, no vehicles, no buildings, no lettering, no logos, no frames, no scrapbook decorations, no watermark. The image should feel like a real invitation to travel, not a website mockup or an illustration.
```

## 验证记录

验证桌面与手机布局、明暗主题、空状态与真实接口格式的示例作品、筛选与详情操作，检查前端状态回归测试、资源体积、CTA 与输入框对比度。真实作品与发布数据没有新增或改写。

- 1280px 桌面为四列，390px 手机为双列；两个尺寸均无横向溢出。手机搜索字号 16px，详情关闭按钮 44px。
- 空状态只保留一个创作入口，桌面与手机首屏均可见；没有分页内容时收起分页留白。空状态配图延迟到可见时加载。
- 主按钮文字对比度 5.18:1，浅色正文 14.09:1，深色正文 14.20:1，控件边界最小 3.08:1；修复深色键盘跳转链接。
- 159 项离线测试通过，24 项需要真实外部服务的测试未运行；大厅、创作、发布三组前端状态检查通过。
- 14 个后端文件 SHA-256 与修改前一致，后端接口与业务逻辑未改。
- 页面配图 323,658 字节，无外部字体或新增依赖；浏览器检查未发现页面错误。
- 示例作品仅存放于独立临时测试环境，正式数据未添加作品。

本机没有预装 Lighthouse，检查记录不包含 Lighthouse 分数。
