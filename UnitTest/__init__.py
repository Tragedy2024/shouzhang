"""「智旅纪手帐」独立单元测试套件。

本目录与项目根目录的 ``tests/`` 平行存在，两者定位不同：

==================  ==========================================================
``tests/``          面向接口的回归测试：端到端 HTTP 流程、长图布局快照、并发与持久化。
``UnitTest/``       面向实现单元的单元测试：每个**实体类**、每个**核心函数**单独隔离
                    验证；一切外部依赖（HTTP、当前时间、模型服务）用
                    ``unittest.mock`` 打桩，不联网、不写真实 ``instance/`` 目录。
==================  ==========================================================

模块划分
--------
``test_entity_*.py``  实体类：``JournalStore``、``HallService``、``GenerationError``、``HallError``
``test_core_*.py``    核心函数：EXIF 解析、文本生成、视觉理解、地图检索、示例服务、
                      长图渲染、Web 校验层与路由
``conftest.py``       共用夹具（临时目录、离线网络护栏、样例图片）
``result.md``         测试命令、执行过程、通过率与覆盖率的实测记录
``htmlcov/``          ``coverage html`` 生成的 HTML 覆盖率报告（``index.html`` 为入口）

运行方式（项目根目录，已激活 conda 环境 ``shouzhang``）::

    python -m pytest UnitTest/ -v
    coverage run --source=app,services,utils -m pytest UnitTest/
    coverage report -m
    coverage html -d UnitTest/htmlcov
"""
