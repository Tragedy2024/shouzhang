# 智旅纪手账项目 UML 设计说明

设计依据：当前工作区源码与实际已实现功能。文档日期：2026 年 10 月 11 日。

本说明提供 1 张系统用例图、3 张类图、3 张时序图、3 张对象状态图和 3 张活动图，共 13 段可独立渲染的 PlantUML 代码，以及 actor-goal lists 和 3 个核心用例的完整规约。

原要求第 4 项同时出现“状态图”和“3 个类图”，本说明按章节含义提供三个对象状态图，并在类图章节另外提供三张类图，覆盖两种理解。第 5 项的“互动图”按其描述的“活动图”处理；第 3 项的交互图采用 UML 时序图。

## 一、系统范围与用例设计

### 1.1 系统边界

智旅纪把用户的旅行照片与补充记录整理为可编辑的手账，提供本机草稿、成品预览、PNG 下载，以及自愿公开到大厅的功能。

系统边界包含浏览器前端、Flask 后台、SQLite 私有任务与大厅存储、图片渲染器、本机草稿与服务器媒体文件。图像理解、文字生成和地图地理编码属于外部协作系统。当前图像理解使用华为云 Qwen；文字生成配置为 DeepSeek 官方；地理编码使用百度地图。

当前没有正式账号注册、登录、评论、点赞、关注、收藏、管理员审核或帖子恢复功能。因此不把这些功能画入现有系统模型。用户身份来自浏览器 Cookie 中的 `owner_id`，作者昵称仅是展示信息。

三个核心用例统一编号如下：

| 编号 | 核心目标 | 主要成果 |
|---|---|---|
| UC01 | 生成旅行手账 | 结构化的手账初稿与可恢复的任务结果 |
| UC02 | 编辑并导出手账 | 与当前预览一致的 PNG 成品 |
| UC03 | 发布成品到大厅 | 独立公开作品快照、话题与详情链接 |

### 1.2 Actor-goal lists

#### A1：大厅访客

| 目标编号 | 参与者目标 | 对应用例 |
|---|---|---|
| A1-G1 | 浏览最新公开作品与分页加载 | UC11 浏览大厅作品 |
| A1-G2 | 按关键字或话题找到作品 | UC12 搜索／按话题筛选 |
| A1-G3 | 查看作品详情与完整长图 | UC13 查看作品详情与长图 |

#### A2：创作者

创作者具有大厅访客的浏览能力。以下为新增的创作目标。

| 目标编号 | 参与者目标 | 对应用例 |
|---|---|---|
| A2-G1 | 将有序照片和记录整理为手账 | UC01 生成旅行手账 |
| A2-G2 | 修改内容、照片排版并下载成品 | UC02 编辑并导出手账 |
| A2-G3 | 自愿公开当前成品 | UC03 发布成品到大厅 |
| A2-G4 | 调整正文语气，保留原有事实 | UC04 调整文案语气 |
| A2-G5 | 撤销或恢复一次编辑 | UC05 撤销／重做编辑 |
| A2-G6 | 继续上次本机保存的创作 | UC06 恢复本机草稿 |
| A2-G7 | 清除当前设备的创作记录 | UC07 清空本机草稿 |
| A2-G8 | 复制当前手账文案 | UC08 复制手账文案 |
| A2-G9 | 继续查看任务或重试失败步骤 | UC09 查看／重试生成任务 |
| A2-G10 | 了解五种风格的排版效果 | UC10 查看风格样张 |

#### A3：发布者

发布者是创作者在管理已发布作品时的角色，不是另一种账户。

| 目标编号 | 参与者目标 | 对应用例 |
|---|---|---|
| A3-G1 | 查看本浏览器身份发布的作品 | UC14 查看我的发布 |
| A3-G2 | 撤回自己的公开作品 | UC15 撤回自己的发布 |

#### 外部协作参与者

| 参与者 | 协作职责 | 对应用例 |
|---|---|---|
| A4 图像理解服务 | 批量描述用户提供的照片 | UC01 的照片分析 |
| A5 文字生成服务 | 按风格生成正文；按语气改写原稿 | UC01、UC04 |
| A6 地理编码服务 | 有 GPS 且未手填地点时提供地址参考 | UC01 的条件性自动定位 |

外部服务是辅助参与者，不发起创作目标。浏览器、数据库与后台线程属于系统内部组成，不作为业务 actor。

### 1.3 用例关系说明

- 创作者泛化到大厅访客，发布者泛化到创作者；空心三角指向较一般的角色。
- `include` 从基本用例指向必需的子用例。例如生成包含素材处理、照片分析和正文撰写；发布包含明确公开确认和保存独立公开成品。
- `extend` 从可选行为指向被扩展用例，并标明守卫。自动定位的守卫为“有 GPS 且未填写地点”；搜索筛选是浏览大厅时的可选行为。
- UC01、UC02、UC03 是独立用户目标，结果可以衔接，但不使用 `include` 表示执行先后。生成并不必然要求编辑或公开发布。
- 语气调整、撤销重做、恢复草稿、失败重试、撤回发布保留为独立目标，并在核心规约中描述其关联场景。

### 1.4 系统用例图代码

源文件：[01_use_cases.puml](/Users/lujiahao/Documents/手帐/docs/uml/01_use_cases.puml)。

<!-- diagram: 01_use_cases.puml -->

```plantuml
@startuml
!pragma layout smetana
left to right direction
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam packageStyle rectangle
skinparam ArrowColor #34495E
skinparam usecaseBackgroundColor #F5F8FC
title 智旅纪：系统用例图

actor "大厅访客" as Visitor
actor "创作者" as Creator
actor "发布者" as Publisher
Creator --|> Visitor
Publisher --|> Creator

rectangle "智旅纪系统（网站、后台与本机草稿）" {
  usecase "UC01\n生成旅行手账" as Generate
  usecase "校验并保存素材" as Prepare
  usecase "分析旅行照片" as Analyze
  usecase "撰写手账正文" as Write
  usecase "自动补充拍摄地点" as Locate
  usecase "UC02\n编辑并导出手账" as EditExport
  usecase "生成或复用当前 PNG 成品" as Render
  usecase "UC04 调整文案语气" as Rewrite
  usecase "UC05 撤销／重做编辑" as History
  usecase "UC06 恢复本机草稿" as Restore
  usecase "UC07 清空本机草稿" as Clear
  usecase "UC08 复制手账文案" as Copy
  usecase "UC09 查看／重试生成任务" as Retry
  usecase "UC10 查看风格样张" as Sample
  usecase "UC03\n发布成品到大厅" as Publish
  usecase "明确确认公开" as Consent
  usecase "保存独立的公开成品" as PublicSnapshot
  usecase "UC11 浏览大厅作品" as Browse
  usecase "UC12 搜索／按话题筛选" as Search
  usecase "UC13 查看作品详情与长图" as Detail
  usecase "UC14 查看我的发布" as Mine
  usecase "UC15 撤回自己的发布" as Withdraw
}

actor "图像理解服务\n华为云 Qwen" as Vision
actor "文字生成服务\nDeepSeek 官方" as Text
actor "地理编码服务\n百度地图" as Map

Visitor -right- Browse
Visitor -right- Search
Visitor -right- Detail
Creator -right- Generate
Creator -right- EditExport
Creator -right- Rewrite
Creator -right- History
Creator -right- Restore
Creator -right- Clear
Creator -right- Copy
Creator -right- Retry
Creator -right- Sample
Creator -right- Publish
Publisher -right- Mine
Publisher -right- Withdraw

Generate .right.> Prepare : <<include>>
Generate .right.> Analyze : <<include>>
Generate .right.> Write : <<include>>
Locate ..> Generate : <<extend>>\n[有 GPS 且未手填地点]
EditExport .right.> Render : <<include>>
Publish .right.> Consent : <<include>>
Publish .right.> PublicSnapshot : <<include>>
Search ..> Browse : <<extend>>\n[用户设置搜索或话题条件]
Analyze -right- Vision
Write -right- Text
Rewrite -right- Text
Locate -right- Map

note bottom of Publisher
  参与者表示角色；同一个人可切换角色。
  发布管理依据浏览器 owner_id，未实现账号登录。
end note
note bottom of EditExport
  UC01、UC02、UC03 是独立用户目标。
  成功结果可衔接下一目标，不能用 include 表示先后。
end note
@enduml
```

## 二、三个核心用例规约

### 2.1 UC01：生成旅行手账

| 规约项 | 描述 |
|---|---|
| 用例编号与名称 | UC01，生成旅行手账 |
| 范围与级别 | 智旅纪系统；用户目标级 |
| 主参与者 | 创作者 |
| 协作参与者 | 图像理解服务、文字生成服务；地理编码服务为条件性协作 |
| 触发事件 | 点击“生成旅行手帐”或“用素材重新生成” |
| 前置条件 | 已选择至少一张可读取的支持格式照片；风格与选填记录合法；当前页面允许开始生成 |
| 输入 | 1～9 张有序照片、风格、可选地点／日期／天气／心情／感受 |
| 输出 | 任务状态、正文、title/body/tags 结构、照片引用及日期地点提示 |
| 成功后置条件 | 任务成为 completed，保存有效结果；前端复制结果为可编辑快照，尝试保存本机草稿并开始排版预览 |
| 最低失败保障 | 已有作品不被错误覆盖；成功阶段已持久化；错误不暴露密钥或上游响应；本机保存失败会提示用户 |

**主成功流程**

1. 创作者添加、移除或调整照片顺序，选择五种风格之一，并填写可选记录。
2. 浏览器校验输入并保留已有作品，提交创建任务请求。
3. 后端检查图片格式、大小、像素及表单，提取元信息，纠正方向，把上传副本规范化为去除 EXIF 的 JPEG，登记所有者。
4. 后端在并发额度允许时创建 queued 任务并返回 202；后台线程执行，前端观察实际进度。
5. 图像理解服务批量分析照片，后台立即保存有效描述。
6. 后台整理日期与地点。有 GPS 且用户未手填地点时调用地理编码；手填记录优先，多日期／多地点或未知地点产生提示。
7. 文字生成服务依据照片线索、风格与用户记录撰写正文，执行真实性约束。
8. 后端检查正文并解析 title/body/tags，保存 result，设为 completed/done。
9. 浏览器展示结果，尝试保存本机草稿，触发后续成品排版。

**备选与异常流程**

| 编号 | 发生位置 | 处理 |
|---|---|---|
| UC01-A1 | 第 2～3 步，输入不合法 | 提示具体问题；本批次部分已保存的上传副本回滚，用户修正后重新提交 |
| UC01-A2 | 第 4 步，并发额度不足 | 返回 429，回收本批照片；提示等待，不创建新任务 |
| UC01-A3 | 第 6 步，无 GPS、无日期或地图失败 | 使用用户记录与已知内容继续，提示手动确认，不把地图失败当作写作失败 |
| UC01-A4 | 第 5／7 步，识图或文字 API 失败 | 记录 failed、失败阶段、retryable；失败不替换已有作品 |
| UC01-A5 | 失败后，允许且选择重试 | 校验 owner、failed、retryable 与额度，重新排队；复用已保存的描述和地点结果 |
| UC01-A6 | 观察任务时浏览器超时或离开页面 | 后台任务可能继续；可继续查看或从草稿恢复任务引用，不认定后台已取消 |
| UC01-A7 | 服务重启发现未完成任务 | 设为可重试失败，保留已完成阶段 |
| UC01-A8 | 任务或照片已不可访问 | 提示重新选择素材；照片访问错误不可直接重试，浏览器已有文案继续保留 |

**业务规则**

- 支持 JPG/JPEG、PNG、WebP；最多 9 张，单张最多 16 MiB，请求总大小最多 50 MiB；单图最多 3000 万像素。
- 每个 owner 最多 2 个 queued/running 任务，全系统最多 12 个；执行线程池当前为 3 个 worker。
- 五种风格为小红书风、INS 风、日杂风、胶片风、Muji 极简风。
- 用户确认信息优先；不把不确定识别或附近景点写成到访经历。当前主生成流程未调用附近景点检索。
- 私有照片保留 7 天；创建超过 7 天且非 queued/running 的任务可清理。清理由请求触发的周期检查完成，非后台定时精确到秒执行。

### 2.2 UC02：编辑并导出手账

| 规约项 | 描述 |
|---|---|
| 用例编号与名称 | UC02，编辑并导出手账 |
| 范围与级别 | 智旅纪系统；用户目标级 |
| 主参与者 | 创作者 |
| 协作参与者 | 调整语气时使用文字生成服务；常规排版由本系统完成 |
| 触发事件 | 修改已有作品并点击下载；也可保留原稿直接下载 |
| 前置条件 | 存在已生成或恢复的结果；当前内容可编辑；用于本次排版的私图属于当前 owner 且有效，允许 0 张照片的纯文字成品 |
| 输入 | 结构化标题、正文、标签、成品风格、有序照片引用与日期地点天气等元信息 |
| 输出 | 对应当前内容的 PNG 预览与下载文件 |
| 成功后置条件 | 浏览器下载与当前匹配预览相同的 PNG；尝试保存作品与编辑历史 |
| 最低失败保障 | 当前正文和历史保留；不允许把内容不匹配的旧缓存下载为当前成品 |

**主成功流程**

1. 系统展示已有手账，或恢复本机保存的较新草稿。
2. 创作者修改标题、正文、作品标签、成品风格、日期、天气、地点及照片顺序；也可保留原稿。
3. 浏览器将编辑分组记录到历史，新编辑清空重做栈，并安排自动保存。
4. 浏览器递增预览版本号、中止旧请求、计算当前内容 key；匹配缓存存在时直接复用。
5. 若无匹配缓存，浏览器冻结本次作品快照，提交排版请求；后端检查内容、风格、scale 与私图所有权。
6. 系统渲染结构化内容并返回 PNG。浏览器只接受版本号与内容 key 均匹配的响应，更新预览与缓存。
7. 创作者点击下载，浏览器保存当前预览使用的同一个 PNG Blob。

**备选与异常流程**

| 编号 | 场景 | 处理 |
|---|---|---|
| UC02-A1 | 选择语气调整 | 发送原稿、语气与风格；成功产生可撤销新版本；失败保留原稿 |
| UC02-A2 | 撤销／重做 | 恢复完整结果快照，包括照片顺序与元信息，并重新检查预览匹配 |
| UC02-A3 | 文案为空或超过 12000 字 | 不生成有效预览，提示编辑；空标题本身合法 |
| UC02-A4 | 排版失败或超时 | 保留文字及旧预览，允许重试；旧图 key 不匹配时下载保持禁用 |
| UC02-A5 | 排版期间继续修改 | 使旧请求失效；即便旧响应随后到达也不覆盖新版本 |
| UC02-A6 | 私有照片过期 | 恢复时移除失效引用并保留文字与本地素材；可以排版纯文字版本，重新使用照片需重新生成上传 |
| UC02-A7 | 本机完整保存失败 | 尝试 localStorage 文字后备，提示照片未完整保存；两者都失败则明确提醒 |
| UC02-A8 | 选择复制文案 | 复制当前正文；剪贴板不可用时提示手动选择复制，不改变作品 |

**业务规则**

- 当前页面排版 scale=2，即 1500 像素宽；后台也支持 scale=1，即 750 像素宽。
- 文案总量最多 12000 字；结构化标题可以为空，正文段落与标签由明确字段表达。
- 撤销与重做栈分别限制为 50 项；一次文本编辑按防抖或失焦分组。
- 素材区设置用于下一次生成，成品区设置作用于当前作品。
- 自动排版防抖为 700ms，草稿保存防抖为 450ms；下载不重新请求导出接口。
- 改写只调整表达，保留原稿事实，不补写未知经历。

### 2.3 UC03：发布成品到大厅

| 规约项 | 描述 |
|---|---|
| 用例编号与名称 | UC03，发布成品到大厅 |
| 范围与级别 | 智旅纪系统；用户目标级 |
| 主参与者 | 创作者；成功后可作为该帖子的发布者 |
| 触发事件 | 成品有效时点击“发布到大厅”，填写信息并明确确认公开 |
| 前置条件 | 当前内容与 PNG 预览一致；未在生成或改写；新发布所用私图属于当前 owner 且仍有效，允许纯文字作品 |
| 输入 | 冻结的成品快照、分享标题、说明、昵称、话题、公开确认、幂等 UUID |
| 输出 | 新帖子或已存在的相同帖子、公开媒体 URL 与详情链接 |
| 成功后置条件 | 帖子为 active，公开 PNG 与缩略图独立保存，话题关联完整；大厅可见，本机草稿保留 |
| 最低失败保障 | 表单与作品保留；写入错误回滚本次未提交的数据与文件；超时表示结果未确认，不等于确定未发布 |

**主成功流程**

1. 浏览器确认当前作品与预览匹配，冻结作品的内容、风格、元信息和照片引用。
2. 发布窗口展示当前成品，公开确认默认不勾选；创作者填写分享标题、说明、昵称和可选话题。
3. 系统说明成品中的图片、文字及地点等会公开，创作者明确勾选并提交。
4. 浏览器校验输入、固定本次 payload 与幂等 key，防止提交中的重复点击。
5. 后端校验公开确认与字段，计算规范 payload 指纹，先检查同 owner + key 的幂等结果和发布配额。
6. 新发布继续校验私图归属及有效期，按冻结快照渲染 1500px PNG，生成 JPEG 缩略图。
7. HallService 开启事务，再次校验幂等和额度，排他写入独立媒体、保存帖子、复用话题并保存关联顺序。
8. 事务提交，返回 201 与帖子；浏览器显示详情链接及查看大厅入口。

**备选与异常流程**

| 编号 | 场景 | 处理 |
|---|---|---|
| UC03-A1 | 未确认公开、取消窗口或字段不合法 | 不提交或返回 400；保留私有草稿与表单 |
| UC03-A2 | 同 owner、key、内容相同且原帖 active | 返回原帖子 200；不重复渲染，不消耗第二次发布额度；原私图即使已过期也可确认既有发布结果 |
| UC03-A3 | 同 key 内容改变或帖子已撤回 | 返回 409；客户端变更内容后使用新 key，并按公开确认流程再次提交 |
| UC03-A4 | 达到日发布限额 | 返回 429，不创建新帖子 |
| UC03-A5 | 私图过期或不属于当前 owner | 返回 403，保留作品并提示处理照片 |
| UC03-A6 | 渲染、文件或事务写入失败 | 返回安全错误；回滚未提交的数据库变更，删除本次已创建文件，允许修复后重试 |
| UC03-A7 | 网络超时或响应丢失 | 提示结果尚未确认；相同 payload 重试使用原 key，防止已经提交的作品被重复发布 |
| UC03-A8 | 需要回到编辑区改图 | 关闭窗口后重新编辑，再打开时冻结新快照并再次确认公开 |
| UC03-A9 | 发布后想撤回 | 进入独立 UC15；仅 owner 可软撤回，公开访问立即停止，不修改本机草稿 |

**业务规则**

- 分享标题 1～100 字，说明最多 2000 字，昵称 1～30 字；分享标题与成品图内标题是不同字段。
- 最多 5 个大厅话题，每个 1～20 字；NFKC 规范化、去掉前导井号并按大小写折叠去重。
- 每个 owner 在北京时间每日最多发布 20 篇；撤回不返还当日额度。
- 幂等约束为 `unique(owner, idempotency_key)`；话题关联约束为 `unique(post_id, topic_id)`。
- 公开 PNG 和缩略图独立保存，不随私照的 7 天策略清理。发布后继续编辑草稿不改变已发布图片。
- 昵称不是身份凭据；清除 Cookie、换浏览器或设备后无法凭昵称管理此前发布。

## 三、类图设计

### 3.1 从实现抽象的实体与值对象

本项目以模块函数、SQLite 行、dict/JSON 和浏览器状态实现业务。下列类是软件分析模型，不声称源码存在同名 Python 实体类。`JournalStore`、`HallService` 是实际服务类；控制器、执行器和适配器表示现有模块函数承担的职责。

| 类 | 类型与存放位置 | 核心职责 |
|---|---|---|
| SessionOwner | 概念实体；Cookie 中的 owner_id，无账户表 | 私有照片、任务及帖子所有权 |
| PrivatePhoto | 持久实体；photos 行与私有 JPEG 文件 | 私图登记、访问校验和过期清理 |
| GenerationJob | 持久实体；jobs 行及 record JSON | 四种任务状态、处理阶段、成功缓存与结果 |
| PhotoReference | 任务内嵌值对象 | 有序照片名与拍摄时间／GPS／地址线索 |
| JournalResult | 任务内嵌值对象 | 服务器生成的正文及结构化初稿 |
| LocalDraft | 浏览器聚合；IndexedDB 与文字后备 | 本机素材、作品版本、待处理任务和缓存 |
| JournalSnapshot | 草稿内值对象 | 当前作品、撤销和重做的独立内容快照 |
| RenderedPreview | 浏览器值对象 | 与内容 key 对应的 PNG Blob |
| HallPost | 持久实体；hall_posts | 公开分享信息、幂等性及展示状态 |
| PublicMedia | 文件值对象；公开媒体目录 | 独立 PNG 和 JPEG 缩略图 |
| Topic | 持久实体；hall_topics | 可被多篇帖子复用的话题 |
| PostTopic | 关联实体；hall_post_topics | 帖子与话题的多对多关联及顺序 |
| TravelInput、Sections | 内嵌值类型 | 旅行记录；标题、正文与作品标签结构 |

### 3.2 关联类型与多重性

| 关系 | UML 类型 | 多重性与原因 |
|---|---|---|
| SessionOwner—PrivatePhoto／GenerationJob／HallPost | 普通关联 | 每条记录属于 1 个 owner；一个 owner 可对应 0..* 条记录。没有账户表外键 |
| GenerationJob—PhotoReference | 组合 `*--` | 一个任务组合 1..9 个内嵌照片引用；随任务 JSON 一同存取 |
| PhotoReference—PrivatePhoto | 普通可选关联 | 当前创建路径每个私图至多属于一个任务引用；每个引用指向 0..1 个仍可访问私图，过期后可以不存在 |
| GenerationJob—JournalResult | 组合 | 一个任务最多 1 个生成结果；初始与失败阶段可为 0 |
| LocalDraft—JournalSnapshot／RenderedPreview | 组合 | 版本及预览属于本机草稿；清空草稿会删除这些本机记录，不删除服务器帖子 |
| LocalDraft—GenerationJob | 普通关联 | pendingJobId 是可选引用；清空本机草稿不代表销毁服务器任务 |
| JournalSnapshot—PrivatePhoto | 普通关联 | 一个快照选用 0..9 张私图；多个版本可引用同一私图，访问仍需有效期与 owner 校验 |
| HallPost—PublicMedia | 组合 | 每个帖子拥有 2 份独立公开媒体：1 PNG 与 1 JPEG 缩略图 |
| HallPost—PostTopic—Topic | 组合与普通关联 | 每帖有 0..5 条话题关联，每关联指向 1 个共享 Topic，每 Topic 可对应 0..* 条关联；帖子与话题整体为多对多 |
| 生成结果→编辑快照、发布帖子→发布时快照 | 依赖 `..>` | 数据在生成或发布时被读取并复制／固化；不新增不存在的 job_id 或内容快照外键 |
| 控制器／执行器→服务 | 调用依赖或普通服务关联 | 使用服务不意味着拥有其生命周期；HallService 注入 JournalStore 不是组合 |

未强行引入空心菱形聚合：共享照片／话题可以用普通关联清楚表达；并非所有“使用”关系都是聚合。领域实体之间没有必要的 is-a 关系，因此不虚构继承。参与者的角色泛化已在用例图表达。

`PhotoReference.position` 是从有序列表推导的属性，非现有单独持久列；`PostTopic.position` 则是数据库实际列。`Sections.tags` 是成品文案标签，`Topic` 是大厅检索话题，二者不能混为同一实体。

### 3.3 全局实体类图

<!-- diagram: 02_class_domain.puml -->

```plantuml
@startuml
!pragma layout smetana
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam classAttributeIconSize 0
skinparam classBackgroundColor #F5F8FC
title 智旅纪：全局实体类图（分析模型）
hide empty methods

class "会话所有者\nSessionOwner" as SessionOwner <<概念实体>> {
  ownerId: UUID
  cookieLifetimeDays: Integer = 365
}
class "私有照片\nPrivatePhoto" as PrivatePhoto <<持久实体>> {
  filename: String {PK}
  owner: UUID
  createdAt: Timestamp
  metadata: JSON
  retentionDays: Integer = 7
}
class "生成任务\nGenerationJob" as GenerationJob <<持久实体>> {
  jobId: UUID {PK}
  status: JobStatus
  stage: String
  fields: JSON
  imageDescription: String [0..1]
  locationData: JSON [0..1]
  error: String [0..1]
  retryable: Boolean
}
class "照片引用\nPhotoReference" as PhotoReference <<内嵌值对象>> {
  filename: String
  datetime: String [0..1]
  gps: Coordinates [0..1]
  address: String [0..1]
  /position: Integer
}
class "生成结果\nJournalResult" as JournalResult <<内嵌值对象>> {
  journal: String
  sections: Sections
  style: String
  date: String
  weather: String
  imageFilenames: String[]
}
class "本机草稿\nLocalDraft" as LocalDraft <<浏览器聚合>> {
  storageKey: String = active
  form: JSON
  files: File[]
  pendingJobId: UUID [0..1]
  updatedAt: Timestamp
  /saveState: String
  /previewState: String
  +undo()
  +redo()
  +clear()
}
class "编辑快照\nJournalSnapshot" as JournalSnapshot <<值对象>> {
  sections: Sections
  style: String
  date: String
  weather: String
  address: String
  imageFilenames: String[]
}
class "成品缓存\nRenderedPreview" as RenderedPreview <<浏览器值对象>> {
  key: String
  blob: PNG
  objectUrl: String
}
class "大厅帖子\nHallPost" as HallPost <<持久实体>> {
  postId: UUID {PK}
  owner: UUID
  title: String
  caption: String
  authorName: String
  idempotencyKey: UUID
  payloadHash: String
  status: PostStatus
  createdAt: Timestamp
}
class "公开媒体\nPublicMedia" as PublicMedia <<文件值对象>> {
  filename: String
  kind: PNG_OR_THUMBNAIL
  width: Integer
  height: Integer
}
class "大厅话题\nTopic" as Topic <<持久实体>> {
  topicId: Integer {PK}
  name: String
  topicKey: String {unique}
}
class "帖子话题关联\nPostTopic" as PostTopic <<关联实体>> {
  postId: UUID {PK part}
  topicId: Integer {PK part}
  position: Integer
}
enum JobStatus {
  queued
  running
  completed
  failed
}
enum PostStatus {
  active
  withdrawn
}

SessionOwner "1" -- "0..*" PrivatePhoto : owner 所有权
SessionOwner "1" -- "0..*" GenerationJob : owner 所有权
SessionOwner "1" -- "0..*" HallPost : owner 所有权
GenerationJob "1" *-- "1..9" PhotoReference : 内嵌、按序
PhotoReference "0..1" --> "0..1" PrivatePhoto : 文件名引用、可过期
GenerationJob "1" *-- "0..1" JournalResult : 完成时产生
GenerationJob ..> JobStatus
GenerationJob ..> JournalSnapshot : 成功结果复制为初稿
LocalDraft "1" *-- "0..*" JournalSnapshot : 当前／撤销／重做版本
LocalDraft "1" *-- "0..1" RenderedPreview : 当前缓存
LocalDraft "0..1" --> "0..1" GenerationJob : 通过 pendingJobId 查询
JournalSnapshot "0..*" --> "0..9" PrivatePhoto : 选用照片、读取时验权
HallPost "1" *-- "2" PublicMedia : 1 PNG + 1 JPEG 缩略图
HallPost "1" *-- "0..5" PostTopic
PostTopic "0..*" --> "1" Topic
HallPost ..> PostStatus
HallPost ..> JournalSnapshot : 发布时读取并固化成图片

note bottom of LocalDraft
  每个浏览器存储空间仅有一份 active 草稿。
  当前快照最多 1 份；撤销与重做栈分别受 50 项限制。
  草稿无 owner 外键，清除 Cookie 不等于删除本机草稿。
end note
note bottom of HallPost
  没有 job_id 或完整 sections 持久列。
  公开图片独立保存，不依赖私有照片的 7 天生命周期。
  图中类为领域分析抽象，不表示已有同名 Python 类。
end note
@enduml
```

### 3.4 创作子域类图

此图细化任务、初稿、编辑快照与渲染协作职责；TravelInput 与 Sections 是被复制的值类型，使用类型依赖，避免把不同对象中的复制值画成共享实体。

<!-- diagram: 03_class_creation.puml -->

```plantuml
@startuml
!pragma layout smetana
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam classAttributeIconSize 0
skinparam classBackgroundColor #F5F8FC
title 智旅纪：创作子域类图（实体与协作职责）

class GenerationJob <<分析实体>> {
  jobId: UUID
  status: JobStatus
  stage: String
  fields: TravelInput
  imageDescription: String [0..1]
  locationData: JSON [0..1]
  retryable: Boolean
  +canRetry(): Boolean
}
class TravelInput <<值类型>> {
  location: String
  mood: String
  feelings: String
  style: String
  date: String
  weather: String
}
class PhotoReference <<内嵌值对象>> {
  filename: String
  /position: Integer
  gps: Coordinates [0..1]
  datetime: String [0..1]
  address: String [0..1]
}
class PrivatePhoto <<分析实体>> {
  filename: String
  owner: UUID
  createdAt: Timestamp
}
class JournalResult <<内嵌值对象>> {
  journal: String
  sections: Sections
  style: String
  imageFilenames: String[]
}
class Sections <<值类型>> {
  title: String
  body: String
  tags: String[]
}
class LocalDraft <<浏览器聚合>> {
  form: TravelInput
  files: File[]
  pendingJobId: UUID [0..1]
  /saveState: String
  /previewState: String
  +applyEdit()
  +undo()
  +redo()
}
class JournalSnapshot <<值对象>> {
  sections: Sections
  style: String
  imageFilenames: String[]
  +contentKey(): String
}
class RenderedPreview <<值对象>> {
  key: String
  blob: PNG
  objectUrl: String
}
class "生成与导出控制器" as Controller <<控制职责>> {
  +createJob(form, files)
  +queryJob(jobId)
  +retryJob(jobId)
  +exportImage(snapshot)
}
class "任务执行器" as Worker <<控制职责>> {
  +run(jobId, owner)
}
class JournalStore <<已有服务类>> {
  +create_job(record)
  +job(jobId, owner)
  +save_job(record)
  +claim_retry(jobId, owner)
  +photo(filename, owner)
}
class "图像理解适配器" as Vision <<服务职责>>
class "文字生成适配器" as Text <<服务职责>>
class "地理编码适配器" as Map <<服务职责>>
class "长图渲染器" as Renderer <<服务职责>>

GenerationJob "1" *-- "1..9" PhotoReference
PhotoReference "0..1" --> "0..1" PrivatePhoto : 访问时校验
GenerationJob "1" *-- "0..1" JournalResult
GenerationJob ..> TravelInput : fields 的值类型
JournalResult ..> Sections : 内嵌内容的值类型
LocalDraft ..> TravelInput : 表单的值类型
LocalDraft "1" *-- "0..*" JournalSnapshot : 当前／历史／重做
JournalSnapshot ..> Sections : 独立复制的内容值
LocalDraft "1" *-- "0..1" RenderedPreview
LocalDraft "0..1" --> "0..1" GenerationJob : 可选的待处理引用
JournalResult ..> JournalSnapshot : 传输后复制，后续独立编辑
Controller ..> Worker : 调度
Controller --> JournalStore : 查询与校验
Worker --> JournalStore : 持久化步骤
Worker ..> Vision
Worker ..> Text
Worker ..> Map : 仅满足 GPS 条件时
Controller ..> Renderer
Renderer ..> JournalSnapshot : 渲染参数

note bottom of Controller
  Controller、Worker、适配器是职责抽象。
  实现分别为 Flask 路由、_run_job 与服务模块函数。
  JournalStore 是实际 Python 类。
end note
note bottom of Sections
  tags 为成品文案标签，不是大厅 Topic。
  值类型会被复制，虚线表示类型／调用依赖。
end note
@enduml
```

### 3.5 大厅子域类图

此图细化公开媒体、话题关联、发布幂等及服务协作。公开帖子没有对原生成任务的必需关联，也没有对私有照片的持续生命周期依赖。

<!-- diagram: 04_class_hall.puml -->

```plantuml
@startuml
!pragma layout smetana
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam classAttributeIconSize 0
skinparam classBackgroundColor #F5F8FC
title 智旅纪：大厅子域类图

class SessionOwner <<概念实体>> {
  ownerId: UUID
}
class HallPost <<持久实体>> {
  postId: UUID {PK}
  owner: UUID
  title: String
  caption: String
  authorName: String
  style: String
  createdAt: Timestamp
  status: active_or_withdrawn
  idempotencyKey: UUID
  payloadHash: String
}
class PublicMedia <<文件值对象>> {
  filename: String
  kind: PNG_OR_THUMBNAIL
  width: Integer
  height: Integer
}
class Topic <<持久实体>> {
  topicId: Integer {PK}
  name: String
  topicKey: String {unique}
}
class PostTopic <<关联实体>> {
  postId: UUID {PK part}
  topicId: Integer {PK part}
  position: Integer
}
class "发布请求快照" as PublicationPayload <<临时值对象>> {
  title: String
  caption: String
  authorName: String
  topics: String[]
  sections: Sections
  style: String
  imageFilenames: String[]
  publicConfirm: Boolean
}
class "大厅控制器" as Controller <<控制职责>> {
  +publish(form)
  +listPosts(filters)
  +getPost(postId)
  +withdraw(postId)
}
class HallService <<已有服务类>> {
  +preflight(owner, key, fingerprint)
  +publish(owner, key, fingerprint, payload, png)
  +list_posts(owner, page, page_size, topic, query, mine)
  +post(postId)
  +topics()
  +media(postId, thumbnail)
  +withdraw(postId, owner)
}
class JournalStore <<已有服务类>> {
  +connect()
  +photo(filename, owner)
}
class "长图渲染器" as Renderer <<服务职责>>

SessionOwner "1" -- "0..*" HallPost : 所有者，昵称仅展示
HallPost "1" *-- "2" PublicMedia : PNG + JPEG 缩略图
HallPost "1" *-- "0..5" PostTopic
PostTopic "0..*" --> "1" Topic
Controller ..> PublicationPayload : 校验公开确认与字段
Controller --> HallService
Controller --> JournalStore : 新发布时校验私图归属
Controller ..> Renderer : 新发布时生成公开 PNG
HallService --> JournalStore : 注入存储服务，非组合
HallService ..> HallPost : 创建／读取／软撤回
HallService ..> Topic : 规范化复用
HallService ..> PublicMedia : 保存独立文件
HallPost ..> PublicationPayload : 创建时读取，不持久关联

note bottom of HallPost
  unique(owner, idempotencyKey)
  同键同内容返回原帖子；同键异内容返回 409。
  北京时间每日最多 20 篇；撤回不返还额度。
end note
note bottom of PostTopic
  unique(postId, topicId)，position 表示话题顺序。
  HallPost 与 Topic 是多对多关联；Topic 不属于某一帖子。
end note
@enduml
```

## 四、三个用例的交互图：时序图

生命线采用“参与者—边界—控制—实体／服务”的分析结构。实线消息表示请求或调用，虚线消息表示返回，异步箭头表示后台派发；`alt`、`opt`、`loop`、`par` 分别表达分支、可选、循环和并发交互。

### 4.1 UC01 生成旅行手账

展示创建异步任务、后台与轮询的并行协作、阶段缓存、失败与重试。三种外部处理服务不是被同时并发调用，后台仍按照片分析、地点整理、正文撰写顺序执行。

<!-- diagram: 05_sequence_generate.puml -->

```plantuml
@startuml
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam sequenceMessageAlign center
autonumber
title UC01：生成旅行手账时序图
actor "创作者" as User
boundary "创作页面" as UI
control "Flask 生成控制器" as API
entity "JournalStore" as Store
control "后台任务执行器" as Worker
participant "图像理解服务" as Vision
participant "百度地图" as Map
participant "文字生成服务" as Text

User -> UI : 选择照片、排序、风格及选填记录
UI -> UI : 校验输入并保留已有作品
UI -> API : POST /api/jobs（照片与表单）
API -> API : 校验格式／容量／像素\n提取元信息、转正、移除副本 EXIF
API -> Store : 登记私图、create_job(queued, upload)
alt 素材无效或并发额度不足
  API -> Store : 回收本批已保存的私图
  API --> UI : 400／413／429 与明确错误
  UI --> User : 保留素材和已有作品，提示调整
else 创建成功
  API ->> Worker : dispatch(jobId, owner)
  API --> UI : 202，jobId 与 queued
  par 后台处理
    Worker -> Store : 读取任务、检查私图仍有效且属 owner
    alt 私图无效
      Worker -> Store : failed，retryable=false
    else 私图有效
      opt 尚无 image_description
        Worker -> Store : running，stage=vision
        Worker -> Vision : 批量分析有序照片
        Vision --> Worker : 描述或 GenerationError
        alt 分析成功
          Worker -> Store : 保存 image_description
        else 分析失败
          Worker -> Store : failed，保留失败阶段和 retryable
        end
      end
      opt 描述有效且尚无 location_data
        Worker -> Store : running，stage=location
        opt 有 GPS 且用户未填写地点
          Worker -> Map : 逆地理编码（重复坐标复用）
          Map --> Worker : 地址或空值
        end
        Worker -> Worker : 整理日期、地点和提示\n手填信息优先，地图失败继续
        Worker -> Store : 保存 location_data
      end
      opt 分析和地点整理已完成
        Worker -> Store : running，stage=writing
        Worker -> Text : 照片线索 + 用户记录 + 风格 + 真实性约束
        Text --> Worker : 正文或 GenerationError
        alt 有效正文
          Worker -> Worker : 解析 title／body／tags
          Worker -> Store : 保存 result，completed／done
        else 写作失败
          Worker -> Store : failed，保留前序成功数据
        end
      end
    end
  else 前端观察
    loop 直到终态或前端暂时停止等待
      UI -> API : GET /api/jobs/{jobId}
      API -> Store : 按 jobId + owner 查询
      Store --> API : 当前状态、阶段、结果或错误
      API --> UI : 任务 DTO
      UI -> UI : 更新实际进度
    end
  end
  alt completed
    UI -> UI : 将结果复制为可编辑快照\n保存本机草稿、触发成品预览
    UI --> User : 展示手账正文与成品区
  else failed
    UI --> User : 显示失败阶段，已有作品保持
    opt retryable=true 且用户选择重试
      User -> UI : 点击重试失败步骤
      UI -> API : POST /api/jobs/{jobId}/retry
      API -> Store : claim_retry（所有权、状态、配额）
      alt 允许重试
        Store --> API : queued，成功缓存保留
        API ->> Worker : 再次调度，跳过已有成功步骤
        API --> UI : 202，继续观察同一任务
      else 不允许
        API --> UI : 409
      end
    end
  else 前端等待中断
    UI --> User : 可继续查看生成状态
    note over UI,Worker : 停止轮询不会取消后台任务。
  end
end
@enduml
```

### 4.2 UC02 编辑并导出手账

展示编辑历史、可选改写、预览版本检查及缓存下载。下载行为直接使用与当前作品匹配的 PNG，避免把“点击下载”错误画成新一轮模型生成或服务器排版。

<!-- diagram: 06_sequence_edit_export.puml -->

```plantuml
@startuml
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam sequenceMessageAlign center
autonumber
title UC02：编辑并导出手账时序图
actor "创作者" as User
boundary "创作页面" as UI
entity "LocalDraft／编辑历史" as Draft
control "Flask 导出控制器" as API
entity "JournalStore" as Store
participant "文字生成服务" as Text
control "长图渲染器" as Renderer
entity "当前 PNG 缓存" as Cache

User -> UI : 修改标题、正文、标签或成品设置
UI -> Draft : 提交编辑组，记录快照\n清空重做栈，安排本机保存
opt 用户选择调整语气
  UI -> API : POST /api/regenerate（原稿、语气、风格）
  API -> Text : 改写请求 + 保留原稿事实的约束
  Text --> API : 改写结果或错误
  alt 成功
    API --> UI : 新正文与 sections
    UI -> Draft : 保存可撤销的新版本
  else 失败
    API --> UI : 安全错误提示
    UI -> UI : 保留原稿与编辑历史
  end
end
opt 用户撤销／重做
  User -> UI : 选择撤销／重做
  UI -> Draft : 在当前、history、future 间交换快照
  Draft --> UI : 恢复内容、照片顺序与元信息
end
UI -> UI : revision++，取消旧排版请求\n计算内容 key，防抖 700ms
UI -> Cache : 查找与当前 key 一致的缓存
alt 当前缓存匹配
  Cache --> UI : 当前 PNG Blob
else 需要重新排版
  UI -> UI : 冻结本次 snapshot 与 revision
  UI -> API : POST /api/export-image\nsections、照片名、风格、元信息、scale=2
  API -> API : 校验结构、内容长度、风格与 scale
  API -> Store : 检查每张照片的 owner 与保留期
  alt 参数或照片无效
    API --> UI : 400（保留文字，可移除失效照片）
  else 校验通过
    API -> Renderer : render_journal_to_bytes(snapshot, paths)
    Renderer --> API : PNG 或渲染错误
    alt 渲染成功
      API --> UI : image/png
      alt 本次请求捕获的 revision 与 key 仍匹配当前内容
        UI -> Cache : 替换 Blob／URL／key
        UI -> UI : 显示匹配预览，启用下载
      else 内容已变化，响应过期
        UI -> UI : 丢弃旧响应，保留最新排版流程
      end
    else 渲染失败
      API --> UI : 500，安全错误提示
    end
  end
end
alt 存在与当前作品一致的 PNG
  User -> UI : 点击下载长图
  UI -> Cache : 读取已显示的同一个 PNG Blob
  Cache --> UI : Object URL
  UI --> User : 浏览器保存 PNG
  note over UI,API : 点击下载直接使用缓存，不再次请求导出接口。
else 当前预览未就绪
  UI --> User : 下载禁用；可以编辑或重试排版
end
note over Draft : IndexedDB 保存完整草稿与 Blob；失败时尝试文字后备。
@enduml
```

### 4.3 UC03 发布成品到大厅

展示冻结快照、公开确认、两次幂等与配额检查、媒体及数据库事务、响应丢失后的安全确认。

<!-- diagram: 07_sequence_publish.puml -->

```plantuml
@startuml
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam sequenceMessageAlign center
autonumber
title UC03：发布成品到大厅时序图
actor "创作者／发布者" as User
boundary "创作页与发布窗口" as UI
control "Flask 大厅控制器" as API
control "HallService" as Hall
entity "JournalStore／SQLite" as Store
control "长图渲染器" as Renderer
entity "公开媒体目录" as Media

User -> UI : 点击发布到大厅
UI -> UI : 确认当前预览匹配\n冻结作品快照，公开确认默认未勾选
User -> UI : 填写分享标题、说明、昵称与话题\n勾选公开确认，提交
UI -> UI : 校验字段、生成／复用 UUID\n锁定提交按钮，固定本次 payload
UI -> API : POST /api/hall/posts\npublic_confirm=true + key + 作品快照
API -> API : 校验字段并计算规范 payload 的 fingerprint
alt 公开确认或字段不合法
  API --> UI : 400，保留发布表单
else 字段合法
  API -> Hall : preflight(owner, key, fingerprint)
  Hall -> Store : 查询同 owner + key；检查当日配额
  alt 同键同内容且原帖子 active
    Store --> Hall : 原帖子
    Hall --> API : existing
    API --> UI : 200，原帖子与详情链接
    note over API,Media : 重放不重读私图、不重渲染、不重复占用额度。
  else 同键异内容或原帖子已撤回
    Hall --> API : HallError(409)
    API --> UI : 要求重新确认发布
  else 当日额度不足
    Hall --> API : HallError(429)
    API --> UI : 每日发布上限提示
  else 可创建新帖子
    API -> Store : 检查私图仍存在、未过期且属于 owner
    alt 私图不可访问
      API --> UI : 403，保留作品与发布信息
    else 私图有效或纯文字作品
      API -> Renderer : 按冻结快照生成 1500px PNG
      Renderer --> API : PNG 或渲染错误
      alt 渲染成功
        API -> Hall : publish(owner, key, fingerprint, payload, png)
        Hall -> Hall : 从 PNG 生成 JPEG 缩略图
        alt 缩略图有效
          Hall -> Store : BEGIN IMMEDIATE\n再次检查幂等与配额（防并发）
          alt 并发请求已创建同键同内容帖子
            Store --> Hall : 原帖子
            Hall --> API : existing, created=false
            API --> UI : 200
          else 并发检查冲突或额度不足
            Hall -> Store : ROLLBACK
            Hall --> API : HallError(409／429)
            API --> UI : 对应错误，不写入媒体
          else 本次创建
            Hall -> Media : 排他写入独立 PNG 与缩略图
            Hall -> Store : INSERT HallPost(active)\n复用 Topic，保存 PostTopic 顺序
            alt 全部成功
              Hall -> Store : COMMIT
              Hall --> API : post, created=true
              API --> UI : 201，详情链接
            else 写文件或存储失败
              Hall -> Store : ROLLBACK
              Hall -> Media : 移除本次已创建的媒体文件
              Hall --> API : 发布错误
              API --> UI : 500，安全错误提示
            end
          end
        else 缩略图失败
          Hall --> API : 渲染结果错误
          API --> UI : 500，不开始发布事务
        end
      else 渲染失败
        API --> UI : 500，不创建公开媒体或帖子
      end
    end
  end
end
alt 收到成功结果
  UI --> User : 显示已发布与查看大厅作品入口
else 明确失败
  UI --> User : 保留表单，可修正或重试
else 超时／响应丢失，结果尚未确认
  UI --> User : 提示再次确认结果
  User -> UI : 重试相同发布
  UI -> API : 相同 payload + 相同 key
  note over API,Hall : 走同一幂等校验流程；不会创建重复帖子。
end
@enduml
```

## 五、三个类对象的状态描述与状态图

### 5.1 GenerationJob 任务对象

| 对象状态 | 含义 | 进入条件／动作 | 主要后续事件 |
|---|---|---|---|
| queued | 任务已创建或已重新排队 | 首次创建的 stage=upload；重试保留原阶段与成功缓存 | 执行器启动、照片无效、服务恢复 |
| running | 后台处理正在执行 | stage 可为 vision、location、writing；按缓存选择起始子阶段 | 阶段成功、GenerationError、未知异常、服务恢复 |
| completed | 有效初稿已生成 | 保存 result；stage=done；retryable=false | 创建超过 7 天后的清理 |
| failed | 处理未完成 | 保存安全错误、失败阶段、retryable 与成功缓存 | 满足守卫后重试，或超期清理 |

关键守卫：重试要求 owner 匹配、status=failed、retryable=true，并满足会话与全局并发额度。重试复用成功描述与地点结果，不重新执行这些已完成步骤。照片访问错误的 retryable=false。

`upload/vision/location/writing/done` 是阶段而不是五种顶层状态。任务清理表示对象记录销毁，不建立不存在的 expired 枚举；queued/running 不按任务超期条件删除。

<!-- diagram: 08_state_job.puml -->

```plantuml
@startuml
!pragma layout smetana
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam stateBackgroundColor #F5F8FC
title GenerationJob：生成任务对象状态图

state "排队\nstatus=queued" as Queued
state "运行\nstatus=running" as Running {
  state Entry <<choice>>
  state "分析照片\nstage=vision" as Vision
  state "整理地点\nstage=location" as Location
  state "撰写手账\nstage=writing" as Writing
  [*] --> Entry
  Entry --> Vision : [无 image_description]
  Entry --> Location : [有描述且无 location_data]
  Entry --> Writing : [描述与地点结果均存在]
  Vision --> Location : 分析成功 / 保存描述
  Location --> Writing : 整理成功 / 保存地点与提示
}
state "已完成\nstatus=completed\nstage=done" as Completed
state "失败\nstatus=failed" as Failed

[*] --> Queued : 素材有效且并发额度允许\n/ 创建任务，stage=upload
Queued --> Running : 执行器启动 [照片可访问]
Queued --> Failed : 照片无效 / retryable=false
Vision --> Failed : 识图错误 / 保存 stage 与 retryable
Location --> Failed : 未预期异常 / 保存成功数据
Writing --> Failed : 写作错误 / 保存 stage 与 retryable
Writing --> Completed : 有效正文 / 保存 result，retryable=false
Queued --> Failed : 服务恢复发现中断 / retryable=true
Running --> Failed : 服务恢复发现中断 / retryable=true
Failed --> Queued : 重试 [owner 匹配且可重试且配额允许]\n/ 清除 error，保留阶段缓存
Failed --> Failed : 重试 [守卫不满足] / 拒绝请求
Completed --> [*] : cleanup [创建超过 7 天] / 删除任务记录
Failed --> [*] : cleanup [创建超过 7 天] / 删除任务记录

note bottom of Running
  内部节点是 stage；四个外层状态才是持久 status。
  无 GPS、已手填地点或定位失败不会中止任务。
  停止前端轮询不会取消正在运行的任务。
end note
note bottom of Failed
  retryable=false 的任务不能直接重试。
  超期清理是对象销毁，不增加不存在的 expired 状态。
end note
@enduml
```

### 5.2 LocalDraft 草稿对象

草稿没有一个现成的统一状态枚举。这里分析的是同一聚合的两组可同时成立的推导状态：保存状态与成品预览状态。它们由计时器、保存结果、作品存在性、预览版本与 key 推导，因此使用复合状态的正交区域。

| 保存状态 | 含义 |
|---|---|
| 恢复中 | 读取 IndexedDB 与 localStorage，选择较新版本并校验照片清单 |
| 恢复完成／空草稿 | 已建立可编辑的本机状态 |
| 待保存 | 变化已发生，等待保存防抖 |
| 保存中 | 完整保存按 Promise 链串行执行，后续修改排队 |
| 完整保存 | IndexedDB 中保存内容、素材 Blob 与可用缓存 |
| 仅文字保存 | 完整保存不可用，但文字后备成功 |
| 保存失败 | 完整记录与文字后备均未成功，向用户提示 |

| 预览状态 | 含义 |
|---|---|
| 无作品 | 没有当前可排版结果，可仍拥有素材 |
| 等待排版／预览已过期 | 已有作品，但当前缓存不匹配，或等待防抖 |
| 排版中 | 已发送当前版本请求 |
| 预览匹配当前作品 | Blob 对应当前 key，可下载 |
| 排版失败或内容无效 | 当前请求失败，或内容未满足排版条件 |

清空经过用户确认，并受“未在生成或改写”守卫约束；会等待已排队保存结束、删除本机草稿与缓存。运行对象随后回到空草稿／无作品状态，仍可继续编辑，因此不把清空画成对象终止。

发布成功不把 LocalDraft 变成“已发布状态”；公开作品的状态属于独立 HallPost。关闭页面也不等于销毁已保存草稿。

<!-- diagram: 09_state_draft.puml -->

```plantuml
@startuml
!pragma layout smetana
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam stateBackgroundColor #F5F8FC
title LocalDraft：本机草稿对象状态图（两组正交状态）

state "LocalDraft 存在" as Draft {
  state "草稿保存状态" as Persistence {
    state "恢复中" as Restoring
    state "恢复完成／空草稿" as Loaded
    state "待保存（防抖）" as PendingSave
    state "保存中（串行队列）" as Saving
    state "完整保存" as FullSaved
    state "仅文字保存" as TextOnly
    state "保存失败" as SaveFailed
    [*] --> Restoring
    Restoring --> Loaded : 恢复较新记录／没有旧记录
    Loaded --> PendingSave : 修改素材、作品或任务状态
    FullSaved --> PendingSave : 内容变化
    TextOnly --> PendingSave : 内容变化／重试保存
    SaveFailed --> PendingSave : 内容变化／重试保存
    PendingSave --> Saving : after(450ms)／离开页面前保存
    Saving --> FullSaved : IndexedDB 完整写入成功
    Saving --> TextOnly : 完整保存失败 [文字后备成功]
    Saving --> SaveFailed : 完整保存与文字后备均失败
    FullSaved --> Saving : [串行队列仍有下一次保存]
    TextOnly --> Saving : [串行队列仍有下一次保存]
    SaveFailed --> Saving : [串行队列仍有下一次保存]
    PendingSave --> PendingSave : 继续修改 / 重置防抖计时
    Saving : 修改 / 在串行队列中追加后续保存
  }
  --
  state "成品预览状态" as Preview {
    state "无作品" as NoResult
    state "等待排版／预览已过期" as Waiting
    state "排版中" as Rendering
    state "预览匹配当前作品" as Matched
    state "排版失败或内容无效" as PreviewFailed
    [*] --> NoResult
    NoResult --> Waiting : 生成成功／恢复已有作品
    Waiting --> Matched : [缓存 key 匹配当前作品]
    Waiting --> Rendering : after(700ms) 或立即重试\n[内容有效且无匹配缓存]
    Waiting --> PreviewFailed : [空内容或超过 12000 字]
    Rendering --> Matched : PNG 返回 [请求版本与快照 key 仍匹配]
    Rendering --> Waiting : 当前内容变化 / version++，中止旧请求
    Rendering --> PreviewFailed : 当前请求失败或超时
    Matched --> Waiting : 编辑、撤销、重做或成品设置变化
    PreviewFailed --> Waiting : 修改内容／点击重试预览
    Matched --> Matched : 下载 / 保存同一 PNG Blob
    Rendering : 旧响应到达 / 忽略，不覆盖新状态
  }
}
[*] --> Draft : 打开创作页，创建／恢复草稿对象
state "清空中" as Clearing
Draft --> Clearing : 用户确认清空 [未在生成或改写]\n/ 取消计时器，使旧预览失效，等待保存队列
Clearing --> Loaded : 删除本机记录与缓存，重置数据\n/ 保存区回到空草稿，预览区进入 NoResult

note bottom of Draft
  保存与预览状态可以同时成立，不能串成单一发布链。
  状态由字段、计时器、缓存 key 与操作结果推导，非数据库枚举。
  保存失败不删除正文；预览不匹配时禁止下载。
  关闭页面后已存草稿保留；发布状态属于 HallPost。
  清空重置同一运行对象，仍可继续选择素材和创作。
end note
@enduml
```

### 5.3 HallPost 大厅帖子对象

| 状态 | 含义 | 状态转移 |
|---|---|---|
| active | 公开展示；可在列表、详情及媒体接口返回 | 发布事务提交后进入；同内容幂等重放和浏览不改变状态 |
| withdrawn | 软撤回；记录、媒体和话题关联仍保留 | 只有匹配 owner 的撤回事件可从 active 进入；重复撤回仍成功 |

非 owner 撤回返回 403，状态不变。撤回后列表排除该帖，详情与图片返回 404。同旧 key 再发布返回 409；使用新 key 重新确认发布会创建另一对象，不是把旧对象恢复为 active。

当前没有恢复、审核中、永久删除状态。withdrawn 不是对象销毁，因此没有从撤回状态连到 UML 终止伪状态。

<!-- diagram: 10_state_post.puml -->

```plantuml
@startuml
!pragma layout smetana
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam stateBackgroundColor #F5F8FC
title HallPost：大厅帖子对象状态图

state "公开展示\nstatus=active" as Active
state "已撤回\nstatus=withdrawn" as Withdrawn
[*] --> Active : 发布事务提交成功\n[公开确认、字段、私图、配额校验通过]
Active --> Active : 同 owner + key + 同内容重放\n/ 返回原帖子，不重复创建
Active --> Active : 浏览、查看详情或加载媒体\n/ 返回公开快照
Active --> Withdrawn : 撤回 [请求 owner=帖子 owner]\n/ 更新 status，保留记录、媒体和话题关系
Active --> Active : 撤回 [owner 不匹配] / 返回 403
Withdrawn --> Withdrawn : 所有者重复撤回 / 返回成功
Withdrawn --> Withdrawn : 同旧 key 重新发布 / 返回 409
Withdrawn --> Withdrawn : 请求列表、详情或图片\n/ 列表排除，详情与媒体返回 404

note bottom of Withdrawn
  撤回不是对象销毁，因此不连接终止伪状态。
  当前没有恢复／永久删除／审核中的状态。
  再发布需重新确认并使用新 key，产生另一个 HallPost。
end note
@enduml
```

## 六、三个用例事件的活动图

活动图使用 `start` 初始节点、`stop` 活动终止节点、圆角活动节点、带“是／否”守卫的决策及合并节点、`repeat` 循环与泳道。泳道区分用户、浏览器、网站后端及外部服务的责任。

这些业务中的照片分析、地点整理和正文撰写有先后依赖，故不为了展示符号而强行并行。异步派发与前端观察的并发关系在 UC01 时序图中明确表达。状态图关注某个对象如何响应事件，活动图关注整个用例如何从输入走到成果，二者不互相替代。

### 6.1 UC01：一次生成及失败步骤重试

覆盖输入拒绝、素材规范化、并发配额、已有阶段复用、自动定位的条件分支、识图与写作失败、成功结果以及重试循环。定位返回空值是可继续分支。

<!-- diagram: 11_activity_generate.puml -->

```plantuml
@startuml
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam activityBackgroundColor #F5F8FC
title UC01：生成旅行手账活动图

|创作者|
start
:选择 1～9 张照片并排序;
:选择风格，填写可选旅行记录;
:点击生成;
|浏览器|
:校验素材并保留已有作品;
if (前端输入有效？) then (是)
  :提交 /api/jobs;
else (否)
  :显示输入问题，保留素材;
  stop
endif
|网站后端|
:校验格式、大小、像素与补充字段;
if (服务端校验通过？) then (是)
  :提取元信息，转正并去除上传副本 EXIF;
  :登记私有照片;
else (否)
  :回收本批已保存的照片，返回错误;
  stop
endif
if (会话活跃任务 < 2 且全局 < 12？) then (是)
  :创建 queued 任务并异步派发;
  :返回 202 与任务标识;
else (否)
  :回收本批照片，提示等待;
  stop
endif
note right
  浏览器从此定期查询阶段。
  下列处理在后台线程中执行。
end note

repeat
  |网站后端|
  :检查照片仍有效且属于当前 owner;
  if (照片有效？) then (是)
    if (已有照片描述？) then (是)
      :复用 image_description;
    else (否)
      :标记 running / vision;
      |外部服务|
      :批量分析有序照片;
      |网站后端|
      if (描述有效？) then (是)
        :保存 image_description;
      else (否)
        :记录识图失败与可重试标志;
      endif
    endif
    if (照片描述已完成？) then (是)
      if (已有地点结果？) then (是)
        :复用 location_data;
      else (否)
        :标记 running / location;
        if (有 GPS 且未手填地点？) then (是)
          |外部服务|
          :百度地图逆地理编码;
          |网站后端|
          :整理地址，失败时记录提示并继续;
        else (否)
          :采用手填地点或已知照片信息;
        endif
        :整理日期与冲突提示，保存 location_data;
      endif
      :标记 running / writing;
      |外部服务|
      :依据照片线索、用户记录与真实性规则撰写;
      |网站后端|
      if (正文有效？) then (是)
        :解析标题／正文／标签，保存 result;
        :标记 completed / done;
      else (否)
        :标记 failed，保存写作错误;
      endif
    else (否)
      :标记 failed，保留失败阶段;
    endif
  else (否)
    :标记 failed，retryable=false;
  endif
  :持久化终态与成功缓存;
  |浏览器|
  :查询并显示任务终态;
  if (任务 completed？) then (是)
    :复制结果到编辑区;
    :保存本机草稿并安排成品预览;
    stop
  else (否)
    :显示失败阶段，保留素材和已有作品;
  endif
  |创作者|
  if (任务可重试且选择重试？) then (是)
    |网站后端|
    :原子校验 owner、failed、retryable 与配额;
    if (允许重试？) then (是)
      :转 queued，保留成功阶段，重新派发;
    else (否)
      :返回 409，提示无法重试;
      stop
    endif
  else (否)
    stop
  endif
repeat while (已重新派发同一任务？) is (是)
stop
@enduml
```

### 6.2 UC02：编辑、更新预览并下载

覆盖可选改写、撤销重做、缓存命中、服务端排版、旧响应丢弃、失败后修正／重试，以及一致性守卫下的 Blob 下载。

<!-- diagram: 12_activity_edit_export.puml -->

```plantuml
@startuml
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam activityBackgroundColor #F5F8FC
title UC02：编辑并导出手账活动图

|创作者|
start
:打开已生成作品或恢复本机草稿;
repeat
  :编辑标题、正文、标签、成品风格或照片顺序，\n也可保留原稿;
  |浏览器|
  :按编辑组记录历史，安排本机保存;
  |创作者|
  if (选择调整语气？) then (是)
    |网站后端|
    :校验原稿、语气与风格;
    |文字生成服务|
    :按事实保留约束改写;
    |浏览器|
    if (改写成功？) then (是)
      :保存可撤销的新版本;
    else (否)
      :显示错误，保留原稿;
    endif
  endif
  |创作者|
  if (选择撤销或重做？) then (是)
    |浏览器|
    :恢复对应完整作品快照;
  endif
  |浏览器|
  :保存草稿；必要时采用仅文字后备;
  :版本号递增，中止旧请求，计算当前内容 key;
  if (当前内容有效且不超过 12000 字？) then (是)
    if (已有匹配 key 的 PNG？) then (是)
      :直接展示缓存成品;
    else (否)
      :等待 700ms 防抖或立即重试;
      :冻结 snapshot、version、key，提交排版;
      |网站后端|
      :校验 sections、风格、scale 和私图所有权;
      if (参数与私图有效？) then (是)
        :依据结构化内容渲染 PNG;
        |浏览器|
        if (返回有效 PNG？) then (是)
          if (本次请求版本与快照 key 仍匹配当前作品？) then (是)
            :替换缓存与成品预览;
          else (否)
            :丢弃过期响应，等待当前版本;
          endif
        else (否)
          :保留文字与旧图，显示重试提示;
        endif
      else (否)
        |浏览器|
        :显示校验错误；过期照片可移除，正文保留;
      endif
    endif
  else (否)
    :显示空内容或长度问题，禁用下载;
  endif
  |创作者|
repeat while (继续修改或重试排版？) is (是)

|浏览器|
if (当前预览 key 匹配作品且用户点击下载？) then (是)
  :读取预览缓存的同一个 PNG Blob;
  :浏览器保存长图，不再调用导出 API;
else (否)
  :保留本机草稿；未匹配时不可下载旧成品;
endif
stop
@enduml
```

### 6.3 UC03：公开确认、发布及未确认结果重试

覆盖取消公开、字段错误、已有发布重放、额度、照片归属、渲染与事务失败，以及相同 payload 复用 key／修改 payload 换新 key 的循环。

<!-- diagram: 13_activity_publish.puml -->

```plantuml
@startuml
skinparam defaultFontName "PingFang SC"
skinparam shadowing false
skinparam activityBackgroundColor #F5F8FC
title UC03：发布成品到大厅活动图

|创作者|
start
:点击发布到大厅;
|浏览器|
if (作品有效、预览匹配且未在生成或改写？) then (是)
  :冻结当前成品快照，打开发布窗口;
  :公开确认默认不勾选;
else (否)
  :提示先完成编辑与成品预览;
  stop
endif
|创作者|
:填写分享标题、说明、昵称与 0～5 个话题;
:阅读公开范围并勾选确认;
if (决定提交并明确确认公开？) then (是)
else (否)
  :取消窗口，继续保留私有草稿;
  stop
endif
|浏览器|
:准备发布快照与幂等 UUID;
repeat
  :校验本次发布字段与公开确认;
  if (前端字段有效且公开确认已勾选？) then (是)
    :固定本次 payload 与幂等 UUID;
  else (否)
    :定位输入问题，保留发布表单;
    stop
  endif
  :锁定提交按钮，发送 /api/hall/posts;
  |网站后端|
  :校验公开确认、字段、内容、风格与话题;
  if (字段合法？) then (是)
    :计算规范 payload 指纹;
    :查询 owner + key 的已有帖子;
    if (同键已有帖子？) then (是)
      if (指纹一致且帖子 active？) then (是)
        :返回原帖子 200，不重读私图或重复扣额度;
      else (否)
        :返回 409，要求重新确认发布;
      endif
    else (否)
      if (北京时间当日发布数 < 20？) then (是)
        :校验 0～9 张私图归属与有效期;
        if (全部可访问？) then (是)
          :尝试从冻结快照渲染 PNG 与生成缩略图;
          if (渲染及缩略图生成成功？) then (是)
            :开启事务，再次检查幂等与配额;
            if (并发检查允许新建？) then (是)
              :排他写入独立公开媒体;
              :保存 active 帖子、复用话题与顺序关联;
              if (全部写入成功？) then (是)
                :提交事务，返回新帖子 201;
              else (否)
                :回滚事务与本次创建媒体，返回错误;
              endif
            else (否)
              :并发同内容则返回原帖子；\n冲突或额度不足则返回相应错误;
            endif
          else (否)
            :返回渲染错误，保留作品与发布表单;
          endif
        else (否)
          :返回 403，保留私有作品与发布信息;
        endif
      else (否)
        :返回 429，当日额度用尽;
      endif
    endif
  else (否)
    :返回 400，字段不合法;
  endif
  |浏览器|
  if (收到 200／201 成功结果？) then (是)
    :显示详情链接与查看大厅入口;
    :保持本机草稿，防止成功后重复提交;
    stop
  else (否)
    if (网络超时或响应丢失？) then (是)
      :提示发布结果尚未确认，保留同一个 key;
    else (否)
      :显示明确错误，保留发布表单;
    endif
  endif
  |创作者|
  if (选择重试或修正后提交？) then (是)
    |浏览器|
    if (规范 payload 已改变？) then (是)
      :分配新的幂等 key;
    else (否)
      :复用原 payload 与 key，避免重复帖子;
    endif
  else (否)
    stop
  endif
repeat while (继续提交？) is (是)
stop
@enduml
```

## 七、用例—结构—行为可追踪性

| 用例 | 关键类对象 | 交互图 | 对象状态图 | 活动图 |
|---|---|---|---|---|
| UC01 生成 | GenerationJob、PhotoReference、PrivatePhoto、JournalResult | 05_sequence_generate | 08_state_job | 11_activity_generate |
| UC02 编辑导出 | LocalDraft、JournalSnapshot、RenderedPreview | 06_sequence_edit_export | 09_state_draft | 12_activity_edit_export |
| UC03 发布 | HallPost、PublicMedia、Topic、PostTopic | 07_sequence_publish | 10_state_post | 13_activity_publish |

全局用例图统一 actor 与目标，类图统一对象名称，三个核心用例规约定义成功和失败保障，对应时序图／活动图实现行为追踪，状态图核对对象生命周期。

## 八、源码依据与渲染方式

### 8.1 主要源码依据

| 建模内容 | 当前实现 |
|---|---|
| owner 与会话 | [app.py:72](/Users/lujiahao/Documents/手帐/app.py:72) |
| 上传校验与规范化 | [app.py:238](/Users/lujiahao/Documents/手帐/app.py:238) |
| 分阶段生成与结果 | [app.py:308](/Users/lujiahao/Documents/手帐/app.py:308) |
| 任务持久化、并发、重试、清理 | [storage_service.py:90](/Users/lujiahao/Documents/手帐/services/storage_service.py:90) |
| 发布字段与公开确认 | [app.py:112](/Users/lujiahao/Documents/手帐/app.py:112) |
| 发布幂等与事务媒体 | [hall_service.py:87](/Users/lujiahao/Documents/手帐/services/hall_service.py:87) |
| 软撤回 | [hall_service.py:249](/Users/lujiahao/Documents/手帐/services/hall_service.py:249) |
| 成品预览与缓存一致性 | [app.js:401](/Users/lujiahao/Documents/手帐/static/app.js:401) |
| 草稿序列化与保存 | [app.js:692](/Users/lujiahao/Documents/手帐/static/app.js:692) |
| 发布窗口与固定快照 | [publish.js:120](/Users/lujiahao/Documents/手帐/static/publish.js:120) |
| 导出服务端校验 | [app.py:558](/Users/lujiahao/Documents/手帐/app.py:558) |

### 8.2 如何使用代码

每个 `.puml` 文件均包含完整 `@startuml` 与 `@enduml`，不依赖其他源文件。可单独复制到 PlantUML 编辑器或 VS Code 的 PlantUML 插件中。中文字体使用 PingFang SC；其他系统可替换为 Noto Sans CJK SC 或已安装的中文字体。

用例、类图和状态图采用 Smetana 布局，避免本机必须安装 Graphviz。[PlantUML 官方布局说明](https://plantuml.com/layout-engines)介绍了该选项；时序图与活动图采用其对应原生语法。[状态图语法](https://plantuml.com/state-diagram)、[活动图语法](https://plantuml.com/activity-diagram-beta)。

本机渲染命令示例（在 `docs/uml` 目录中执行，jar 路径按实际安装位置调整）：

```bash
java -Djava.awt.headless=true -jar /path/to/plantuml.jar -charset UTF-8 -tsvg -o images *.puml
java -Djava.awt.headless=true -jar /path/to/plantuml.jar -charset UTF-8 -tpng -o images *.puml
```

交付包含全部 UML 源文件、合并说明、SVG／PNG 图像及 `index.html` 图示预览。此任务只新增设计资料，不改变网站业务代码或用户数据。
