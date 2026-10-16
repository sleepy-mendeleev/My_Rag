# 项目文档

| 文档 | 内容 |
| --- | --- |
| [项目首页](../README.md) | 已实现功能、运行步骤、接口与当前边界 |
| [新版功能需求报告](rag_upgrade_requirements_v2.md) | 文档解析、清洗、切分、混合检索与简化评测需求 |
| [文档结构与切分](document_structure_learning.md) | Loader / Splitter 分工、标题元数据和 CSV 表格切分 |
| [问答现场排查](rag_debugging.md) | L2 阈值、候选过滤与请求现场字段 |
| [GitHub 整理说明](github_readiness.md) | 提交范围、当前复现问题和后续整理建议 |
| [结构化条款样例](examples/bank_structure_demo.txt) | 虚构测试制度，适合演示标题与条款切分 |
| [Milvus 启动说明](../infra/README.md) | 数据库准备与端口检查 |

根目录的 `04_rag_vector_database_learning_doc.md` 是原项目的历史学习资料，其中的旧路径、旧加载器与启动指令不作为本版本运行依据。当前启动步骤以项目首页为准。
