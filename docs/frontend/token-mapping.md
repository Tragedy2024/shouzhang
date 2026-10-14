# 共享令牌映射

采用 **Model B**：`static/app-shell.css` 是唯一运行时作者源；DESIGN.md镜像已接受的精确值并解释用途。不要从DESIGN生成另一份CSS，不把文档、页面别名和共享CSS作为三个独立系统维护。

```text
static/app-shell.css 的 --app-* 语义令牌与 theme override
  → 共享body、控件、dialog、scrollbar与外观
  → creator.css / hall.css 的角色别名与页面几何
  → 实际创作／大厅DOM
  ↘ DESIGN.md frontmatter 与 token-mapping.json 的精确镜像
```

| Semantic role | Runtime owner | Adapters / consumers | Documentation |
|---|---|---|---|
| 页面、主／辅助表面、正文／辅助文字 | app-shell 的 --app-bg、--app-surface、--app-surface-soft、--app-ink、--app-muted | creator/hall表面和文字别名，公共shell | DESIGN Colors |
| 普通分隔线、交互边框、焦点 | app-shell 的 --app-line、--app-control-line、--app-focus | form、搜索、button、链接、dialog | DESIGN Colors / Components |
| 强调、主按钮、警告与反馈 | app-shell 的 --app-accent*、--app-button*、--app-warning* | 状态、主CTA、公开确认／撤回 | DESIGN Colors / Components |
| 中文字体、控件／卡片圆角 | app-shell 的 --app-font-*、--app-radius-* | body、标题、字段、卡片、弹窗 | DESIGN Typography / Shapes |
| 阴影、纸页、top-layer、scrollbar | app-shell 对应语义令牌 | 长图、详情、共享dialog、所有overflow区域 | DESIGN Elevation / Layout |

确切selector、值和frontmatter路径见 [token-mapping.json](token-mapping.json)。它记录共享源落地后的提取结果，不是新运行时源。CSS中有新令牌而清单未更新、清单与CSS值变化、DESIGN镜像偏离、页面重新定义app令牌或出现裸颜色，drift gate必须报错；不能用不存在的令牌掩盖遗漏。

执行：

```bash
python3 docs/frontend/check_token_drift.py
```

检查只读项目的共享CSS、页面CSS、清单和DESIGN.md，不访问私有配置或用户存储，不产生网络请求。它检查静态所有权和镜像，不能代替浏览器computed style、对比度、焦点或原生popup验收。

当前提取的共享源有2个主题selector、49项声明、43项DESIGN颜色／字体／圆角镜像。未在深色块重复的值继承root；映射清单保留selector级真实声明，不能把继承值误写成新的深色override。Python脚本仅解析项目实际使用的简单frontmatter标量子集；完整YAML格式、组件与对比度由官方designmd lint拥有。

另有应用动作绑定补充检查：

```bash
node docs/frontend/semantic_binding_check.cjs --output docs/frontend/semantic-binding-report.json
```

它扫描所有templates中的literal button，限定证据来自该模板真正载入的脚本，支持ID click、form submit、共享主题installTheme、祖先容器中data-style/data-tone/data-topic代理。找不到owner时退出非零；报告保存具体源文件／行号。官方Premium strict原始报告仍保留：此检查解释external-binding误报，不篡改其errors，也不声称已证明生成按钮、键盘或事件处理正确。

修改流程：先在canonical CSS改一次→同步更新本清单与DESIGN镜像→运行drift gate与designmd lint→运行四组状态检查→验收两页深浅色和窄屏。既有creator/hall别名只是兼容层，不得在其定义里放另一套实际颜色。
