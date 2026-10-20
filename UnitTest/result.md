# 「智旅纪手帐」单元测试报告

> 测试对象：`app.py`、`services/`、`utils/` 中的**实体类**与**核心函数**
> 测试代码：`UnitTest/`（与本文件同目录）
> 覆盖率报告：`UnitTest/htmlcov/index.html`（用浏览器直接打开）
> 记录时间：2026-10-14

---

## 一、总体结果

| 指标 | 结果 |
| --- | --- |
| 收集用例数 | 530 |
| 通过 | **527** |
| 失败 | 0 |
| 跳过 | 3（Windows 符号链接权限，见 §6.3） |
| **测试通过率** | **527 / 530 = 99.4%**（按实际执行计：527 / 527 = **100%**） |
| 语句总数 | 1360 |
| 未覆盖语句 | 4 |
| **代码覆盖率** | **1356 / 1360 = 99%**（`coverage.py` 7.16.2） |
| 测试代码规模 | 10 个测试模块 + 2 个支撑文件，3948 行，73 个测试类 |

模块级覆盖率：

```
Name                               Stmts   Miss  Cover   Missing
----------------------------------------------------------------
app.py                               501      1    99%   629
services\__init__.py                   0      0   100%
services\errors.py                    12      0   100%
services\hall_service.py             173      2    99%   125, 242
services\image_render_service.py     301      0   100%
services\map_service.py               32      0   100%
services\sample_service.py            27      0   100%
services\storage_service.py          105      1    99%   88
services\text_service.py              93      0   100%
services\vision_service.py            63      0   100%
utils\__init__.py                      0      0   100%
utils\image_utils.py                  53      0   100%
----------------------------------------------------------------
TOTAL                               1360      4    99%
```

---

## 二、环境与工具链

| 项目 | 值 |
| --- | --- |
| 操作系统 | Windows 11 (10.0.26200) |
| Python | 3.12.15（conda 环境 `shouzhang`） |
| 解释器绝对路径 | `D:\anaconda\envs\shouzhang\python.exe` |
| 测试框架 | pytest 9.1.1 |
| **打桩工具** | 标准库 `unittest.mock`（`Mock` / `patch` / `side_effect`） |
| **覆盖率工具** | `coverage.py` 7.16.2（**未使用 pytest-cov**） |
| 图像处理 | Pillow 12.3.0 |
| HTTP | requests 2.34.2 |

环境准备（本次实际执行过一次）：

```bash
conda run -n shouzhang python -m pip install coverage
# Successfully installed coverage-7.16.2
```

> 注：本机存在 `conda run -n <env> python -c "<多行代码>"` 不可用的问题
> （`NotImplementedError: Support for scripts where arguments contain newlines`），
> 因此下文所有命令都直接调用环境内的 `python.exe`，效果等价且没有这个限制。

---

## 三、目录结构

```
手帐/
├── app.py                     ← 被测：Flask 应用与 Web 校验层
├── services/                  ← 被测：业务服务
│   ├── errors.py                    GenerationError / read_generated_text
│   ├── storage_service.py           JournalStore（私有照片 + 任务持久化）
│   ├── hall_service.py              HallService（公共大厅）+ HallError
│   ├── vision_service.py            视觉理解
│   ├── text_service.py              文本生成与改写
│   ├── map_service.py               百度地图逆地理编码 / 附近景点
│   ├── image_render_service.py      长图渲染
│   └── sample_service.py            示例手帐
├── utils/image_utils.py       ← 被测：EXIF GPS / 拍摄时间解析
├── tests/                     ← 既有：面向接口的回归测试（192 passed / 2 skipped）
└── UnitTest/                  ← 本次新增：面向实现单元的单元测试
    ├── __init__.py            套件说明与模块划分
    ├── conftest.py            共用夹具：临时目录、离线护栏、样例图片
    ├── test_entity_errors.py              18 例  异常实体
    ├── test_entity_journal_store.py       41 例  JournalStore 实体
    ├── test_entity_hall_service.py        62 例  HallService 实体
    ├── test_core_image_utils.py           37 例  EXIF 解析
    ├── test_core_map_service.py           19 例  地图服务
    ├── test_core_text_service.py          52 例  文本生成 / 改写
    ├── test_core_vision_service.py        23 例  视觉理解
    ├── test_core_render_service.py        72 例  长图渲染
    ├── test_core_sample_service.py        12 例  示例服务
    ├── test_core_web_layer.py            194 例  Web 校验层与路由
    ├── htmlcov/               coverage html 生成的 HTML 报告（20 个文件）
    └── result.md              本文件
```

---

## 四、执行命令与过程日志

以下命令均在项目根目录 `E:\大学课堂\软工基础实验\智旅纪\手帐\手帐` 下执行。

### 步骤 1 · 安装覆盖率工具

```bash
conda run -n shouzhang python -m pip install coverage
```

```
Successfully installed coverage-7.16.2
```

### 步骤 2 · 首次运行，收集失败

```bash
/d/anaconda/envs/shouzhang/python.exe -m pytest UnitTest/ -q --no-header -p no:cacheprovider
```

```
17 failed, 455 passed, 3 skipped in 17.47s
```

首轮暴露了三类问题，全部在测试代码侧修正（被测代码未做任何修改，见 §5.4）：

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| `ImportError: cannot import name 'HallError' from 'services.errors'` | `HallError` 定义在 `services/hall_service.py`，不在 `errors.py` | 修正 import |
| `SyntaxWarning: invalid escape sequence '\.'` | 文档字符串里的正则示例 `^[a-f0-9]{32}\.jpg$` 未加 `r` 前缀 | 改为 `r"""..."""` |
| `TypeError: object of type 'NoneType' has no len()`（9 例） | Pillow 12 里**显式传 `save(exif=None)` 与不传不等价**，会被当成"用户指定了空 EXIF 块" | 造图助手改成仅在非 None 时才传 `exif=` |
| 渲染用图片构造失败（3 例） | 同上，`conftest.make_jpeg` 默认 `exif=None` | 同上 |
| `TypeError: expected string or bytes-like object, got 'NoneType'` | `JournalStore.photo()` 对非字符串入参不做防御（调用方已用 `PHOTO_NAME` 过滤） | 该参数化分支收窄为字符串用例 |
| `'NoneType' object is not subscriptable` | `create_job` 限制同一 owner 最多 2 个进行中任务，第 3 条 `completed` 记录被并发闸门挡掉 | 调整建单顺序 |
| 发布未登记照片返回 403 而非 400 | 名字合法但从未登记属于**权限**问题，路由确实返回 403 | 修正期望值，并补充"名字格式非法 → 400"的用例 |

### 步骤 3 · 修正后复跑

```bash
/d/anaconda/envs/shouzhang/python.exe -m pytest UnitTest/ -q --no-header -p no:cacheprovider
```

```
474 passed, 3 skipped in 17.79s
```

### 步骤 4 · 补齐覆盖率缺口

针对首轮覆盖率报告里被标红的语句逐条补充用例（示例服务插画生成、字体降级链、
多照片宫格、标签换行、任务失败各分支、并发闸门三入口、旧版 `POST /upload`、
GPS 去重与冲突提醒、后台线程池分发等）：

```bash
/d/anaconda/envs/shouzhang/python.exe -m pytest UnitTest/ -q --no-header -p no:cacheprovider
```

```
527 passed, 3 skipped in 31.79s
```

### 步骤 5 · 用 coverage.py 统计覆盖率

```bash
rm -f .coverage
/d/anaconda/envs/shouzhang/python.exe -m coverage run --source=app,services,utils -m pytest UnitTest/ -q --no-header -p no:cacheprovider -rs
```

```
SKIPPED [2] UnitTest\test_entity_hall_service.py:444: 创建符号链接需要管理员权限或开发者模式
SKIPPED [1] UnitTest\test_entity_journal_store.py:184: 创建符号链接需要管理员权限或开发者模式
527 passed, 3 skipped in 21.47s
```

```bash
/d/anaconda/envs/shouzhang/python.exe -m coverage report -m
```

```
Name                               Stmts   Miss  Cover   Missing
----------------------------------------------------------------
app.py                               501      1    99%   629
services\__init__.py                   0      0   100%
services\errors.py                    12      0   100%
services\hall_service.py             173      2    99%   125, 242
services\image_render_service.py     301      0   100%
services\map_service.py               32      0   100%
services\sample_service.py            27      0   100%
services\storage_service.py          105      1    99%   88
services\text_service.py              93      0   100%
services\vision_service.py            63      0   100%
utils\__init__.py                      0      0   100%
utils\image_utils.py                  53      0   100%
----------------------------------------------------------------
TOTAL                               1360      4    99%
```

### 步骤 6 · 生成 HTML 覆盖率报告

```bash
/d/anaconda/envs/shouzhang/python.exe -m coverage html -d UnitTest/htmlcov --title "智旅纪手帐 · UnitTest 单元测试覆盖率"
```

```
Wrote HTML report to UnitTest/htmlcov\index.html
```

报告内容：`index.html`（总览，可逐层下钻）、`app_py.html`、`z_*_<模块>.html`
（逐行高亮：绿色=已执行、红色=未执行、黄色=未覆盖分支）、`function_index.html`
（按函数维度的覆盖率）、`class_index.html`（按类维度）、`status.json`。

### 步骤 7 · 确认既有回归套件未被影响

```bash
/d/anaconda/envs/shouzhang/python.exe -m pytest tests/ -q --no-header -p no:cacheprovider
```

```
192 passed, 2 skipped, 24 deselected in 20.98s
```

两个套件合并跑一次时：

```bash
/d/anaconda/envs/shouzhang/python.exe -m coverage run --source=app,services,utils -m pytest UnitTest/ tests/ -q
```

```
719 passed, 5 skipped, 24 deselected in 36.58s
TOTAL   1360      4    99%
```

---

## 五、测试设计与写法说明

### 5.1 测试函数如何定义

每个测试都是一个**方法名即断言说明**的独立函数，统一遵循
`test_<被测对象>_<场景>` 命名，一条用例只验证一个行为，失败时看名字就能定位：

```python
class TestNormalizeTopic:
    """话题规范化：NFKC 折叠 + 去空白 + 去前导 #。"""

    def test_normalize_topic_strips_whitespace_and_leading_hash(self):
        assert normalize_topic('  # 旅行 ') == '旅行'

    def test_normalize_topic_folds_full_width_characters(self):
        # 用户从中文输入法打出的全角 # 和全角字母都要折成半角。
        assert normalize_topic('＃ＦＯＯＤ') == 'FOOD'
```

参数化用例（把同一逻辑的多组数据摆在一起，避免复制粘贴）：

```python
@pytest.mark.parametrize('status,expected', [
    (401, '文字生成服务认证失败，请检查服务配置后重试。'),
    (429, '文字生成请求过于频繁，请稍后重试。'),
    (500, '文字生成服务暂时不可用，请稍后重试。'),
])
def test_writing_http_message_maps_status_codes(self, status, expected):
    assert _writing_http_message(http_error(status)) == expected
```

异常路径用 `pytest.raises` 断言类型，再读 `error.value` 断言字段：

```python
def test_image_content_reports_an_unreadable_photo_as_permanent(self, tmp_path):
    with pytest.raises(GenerationError) as error:
        _image_content(str(broken))

    # 照片本身坏了，重试多少次都一样，必须标成不可重试。
    assert (error.value.stage, error.value.retryable) == ('vision', False)
```

每个测试模块的文档字符串都写明了**被测单元清单**与**打桩策略**，读者可以只看
文件头就判断这个模块在测什么、哪些依赖被替换掉了。

### 5.2 Mock 工具包的使用方式

全部使用标准库 `unittest.mock`，按"依赖的**边界**"打桩，而不是按"方便"打桩：

**(a) 替换 `requests` 的出口。** `services/*` 都通过 `requests.get/post` 发请求，
测试把这两个函数换成 `Mock`，再用 `side_effect` 模拟超时、断连、HTTP 错误：

```python
@pytest.fixture
def http_post(monkeypatch):
    response = Mock()
    response.status_code = 200
    response.raise_for_status.return_value = None
    poster = Mock(return_value=response)
    monkeypatch.setattr(requests, 'post', poster)
    return SimpleNamespace(post=poster, response=response)
```

```python
def test_request_text_times_out_as_a_retryable_error(self, http_post):
    http_post.post.side_effect = requests.Timeout('太慢了')
    ...
```

**(b) 替换 `app.py` 命名空间里的服务函数。** `app.py` 用的是
`from services.vision_service import analyze_images_batch`，所以必须打在 `app`
上——打在源模块里不会生效，这是个很容易踩的坑，测试里专门写了注释：

```python
@pytest.fixture
def providers(monkeypatch):
    stubs = SimpleNamespace(vision=Mock(return_value='海面和一条船。'), ...)
    monkeypatch.setattr(project, 'analyze_images_batch', stubs.vision)
    ...
```

**(c) 只替换外部依赖，不替换被测对象本身。** `JournalStore`、`HallService`、
图像渲染流水线都是**真跑**的（真实 sqlite、真实 Pillow、真实字体），
因为 SQL 约束、文件句柄、EXIF 往返、像素布局正是风险所在，mock 掉就测不到了。
唯一的例外是需要"拨动时间"的地方：

```python
with patch('services.storage_service.time.time', return_value=just_inside):
    assert store.photo(filename, 'owner-1') is not None
```

**(d) 断言"没有发生什么"和断言"发生了什么"同样重要：**

```python
def test_regenerate_journal_returns_the_original_for_an_unknown_tone(self, http_post):
    assert regenerate_journal('原标题\n\n正文', '不存在的语气') == '原标题\n\n正文'
    http_post.post.assert_not_called()      # 未知语气不该浪费一次付费调用
```

**(e) 全局离线护栏。** `conftest.py` 的 autouse 夹具把 `requests` 唯一的出口
`Session.request` 换成会抛 `AssertionError` 的桩。任何"忘了 mock"的真实调用
都会立刻失败，而不是静默联网：

```python
@pytest.fixture(autouse=True)
def block_unplanned_network(request, monkeypatch):
    if request.node.get_closest_marker('live'):
        return
    def blocked(*args, **kwargs):
        raise AssertionError('单元测试必须用 unittest.mock 打桩外部请求，不得真实联网')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)
```

### 5.3 隔离与可移植

* 一切落盘路径都指向 pytest 的 `tmp_path`；字体缓存（`_get_font` 带 `lru_cache`）
  与示例缓存（`sample_journal` 带 `lru_cache`）在每个用例前后清空，避免顺序耦合。
* 只读路由 `/api/sample` 会用到应用自带的示例插画；测试把 `__file__` 指到
  临时目录，既覆盖了"插画不存在 → 现画"这条只在全新机器上才会走到的分支，
  又不污染项目真实的 `instance/`。
* 平台差异（Windows 的 `%WINDIR%` 字体目录、符号链接权限）都有兜底：
  能测就断言，测不了就 `pytest.skip` 并说明原因。

### 5.4 被测代码的改动

**未改动任何被测代码。** 测试过程中发现的 3 处行为差异，经核对都是**测试期望写错**，
已按被测代码的真实行为修正断言（见 §4 表格）。唯一记录在案的代码缺陷见 §8。

---

## 六、未覆盖语句清单

1360 条语句中仅 4 条未被执行：

| 文件:行 | 代码 | 未覆盖原因 |
| --- | --- | --- |
| `app.py:629` | `app.run(host=..., port=5001, debug=False)` | 位于 `if __name__ == '__main__':` 之内，是开发服务器入口。测试通过 `test_client()` 调用应用，不会走到这里；强行覆盖需要真的起一个监听端口，属于集成测试范畴。 |
| `hall_service.py:125` | `raise ValueError('The server renderer returned an empty image')` | 防御性检查。`Image.open()` 能成功打开的 PNG 不可能宽或高小于 1 像素，构造不出能触发它的输入。 |
| `hall_service.py:242` | `return None`（拒绝符号链接） | 对应的两条用例在本机被 `pytest.skip`：Windows 需要管理员权限或开发者模式才能创建符号链接。 |
| `storage_service.py:88` | `return None`（拒绝符号链接） | 同上。 |

也就是说，**在本机可执行的所有代码路径中，单元测试已 100% 覆盖**；
剩余 4 条分别是"进程入口""不可构造输入"和"环境权限不支持"三类。

---

## 七、测试覆盖了什么

按被测单元分组（括号内为用例数）：

**实体类**

* `GenerationError` / `HallError`（18）——字段默认值、`str()` 行为、互不兼容的异常层级。
* `JournalStore`（41）——建表与索引、连接生命周期（**含 Windows 上必须关闭连接、
  不残留 WAL 边车文件的回归用例**）、照片 owner 隔离与文件名白名单、保留期边界、
  任务并发闸门（单人 2 / 全局 12）、重试资格矩阵、进程重启恢复、7 天清理。
* `HallService`（62）——话题规范化、载荷指纹、公开字段白名单、缩略图裁剪、
  中国时区零点配额重置、幂等发布、发布失败回滚、LIKE 通配符转义搜索、
  话题统计、媒体文件解析、撤回权限。

**核心函数**

* `utils/image_utils.py`（37）——度分秒→十进制度、非法分量拒绝、GPS 半球参考、
  拍摄时间三级回退与格式归一，全部失败路径返回 `None`。
* `services/map_service.py`（19）——`coordtype=wgs84ll` 参数、超时、前 5 条截断、
  限流/断网/返回体变动一律降级。
* `services/text_service.py`（52）——HTTP 状态码→中文文案映射（**并断言不泄漏
  供应商原文与密钥**）、缺密钥时不发请求、用户输入优先于自动识别、
  附近景点必须标注"未证明用户到访"、未知语气原样返回。
* `services/vision_service.py`（23）——EXIF 方向校正、长边限幅、去隐私元数据、
  透明通道铺白底、N 张照片**只发 1 次**请求、编号清晰。
* `services/image_render_service.py`（72）——排版单元切分（组合符 / ZWJ / 肤色）、
  像素级换行、正文切分、等比缩放不裁剪、胶片颗粒确定性、字体降级链、
  倍率校验、多照片宫格、标签换行。
* `services/sample_service.py`（12）——首次现画插画、之后复用、按风格缓存。
* `app.py` Web 层（194）——上传校验（张数/扩展名/体积/像素/真实格式/透明通道/
  批次原子回滚）、Web 层参数校验、任务状态白名单、HTTP 异常→文案、
  全部路由的正常与异常出口、大厅发布→浏览→撤回闭环、并发闸门 429。

---

## 八、测试过程中发现的问题

**(1) `POST /upload` 的错误提示不会显示给用户（未修复，仅记录）**

`app.py` 的三处兜底分支调用了 `render_template('index.html', error=...)`：

```python
except ValueError as error:
    return render_template('index.html', error=str(error)), 400
```

但 `templates/index.html` 里只有 `<div class="error-message" id="errorMsg" hidden>`
这个由 JavaScript 填充的节点，**模板本身不渲染 `error` 变量**。因此在禁用
JavaScript 的浏览器里，用户只会看到回到首页，看不到"请上传 JPG、PNG 或 WebP
格式的照片"这类原因。对应的测试只能断言状态码，无法断言文案：

```python
def test_upload_renders_the_error_on_the_index_page(self, client):
    # 注意：``index.html`` 目前只暴露一个由脚本填充的 #errorMsg 节点，
    # 模板并不渲染 error 变量，所以这里只能断言"回到首页并给出 400"。
    response = client.post('/upload', data={'image': (io.BytesIO(jpeg()), 'notes.txt')})
    assert response.status_code == 400 and response.mimetype == 'text/html'
```

修复方式是在 `index.html` 里补一段 `{% if error %}` 输出，但这超出"只写测试"
的范围，故未改动，留待确认。

**(2) 两处已知的 Pillow 12 行为差异（测试侧已规避）**

* `Image.save(path, 'JPEG', exif=None)` 与不传 `exif=` 不等价，前者会在保存时对
  `None` 求长度而抛 `TypeError`。
* 写 GPS EXIF 必须用 `PIL.TiffImagePlugin.IFDRational`，直接传元组会抛
  `TypeError: bad operand type for abs(): 'tuple'`。

**(3) 渲染层与路由层对"空标签"的口径不同（符合设计，已用测试固定）**

`image_render_service` 只丢弃**纯空白**标签，而 `app.py` 的发布路径会额外丢弃
`#`/`＃` 之外没有内容的标签。两处都有用例把这层差异钉死，避免日后被误"统一"
而导致渲染出的标签胶囊数量变化。

---

## 九、如何复现

```bash
# 0. 进入项目根目录
cd "E:/大学课堂/软工基础实验/智旅纪/手帐/手帐"

# 1. 只跑单元测试（约 20–30 秒）
/d/anaconda/envs/shouzhang/python.exe -m pytest UnitTest/ -v

# 2. 统计覆盖率
rm -f .coverage
/d/anaconda/envs/shouzhang/python.exe -m coverage run --source=app,services,utils -m pytest UnitTest/
/d/anaconda/envs/shouzhang/python.exe -m coverage report -m

# 3. 生成 HTML 报告，然后浏览器打开 UnitTest/htmlcov/index.html
/d/anaconda/envs/shouzhang/python.exe -m coverage html -d UnitTest/htmlcov
```

已激活 conda 环境时可简写为 `python -m pytest UnitTest/ -v`。
Windows 下若控制台中文乱码，先执行 `set PYTHONUTF8=1`。
