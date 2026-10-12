# 问答现场排查

从项目根目录启动：`python -m backend.app.server`。修改后需重启后端。

检索采用 L2 距离，默认保留 `distance <= 14000` 的候选。
启动前的环境变量 `L2_MAX_DISTANCE` 可以覆盖默认值；终端与现场文件均显示实际阈值。
14000 是当前项目的实验参数，不是通用相关性标准。

每次通过 `/api/vector/query` 的问答返回 `request_id` 和 `status`，
并写入项目根目录的 `logs/rag_traces/<request_id>.json`（UTF-8）。
终端输出该路径。日志目录已被 .gitignore 忽略，文件包含问题与文档全文，不记录 API Key。
此功能不能补回改动前未记录的请求。

字段说明：

- `question`、`collection_name`、`k`：本次问题、集合、候选数量。
- `max_distance`：实际距离阈值。
- `candidates`：过滤前候选全文、元数据、距离、排名及 `kept` 标记。
- `context`：过滤后拼装的参考资料。
- `messages`：实际准备提交给模型的 system 和 user 消息。
- `model`、`generation_params`：请求模型和温度；`model_returned` 是服务返回的模型名。
- `answer`：最终回答。
- `error`：发生异常的阶段和异常类型，结合终端错误排查。

`status=no_context` 表示没有通过过滤的资料，不调用大模型；此时 `messages=null` 是预期行为。
`status=error` 表示异常，不能当作知识库无答案。
`status=answered` 仅表示调用和返回完成，不代表答案经过事实校验。
现场在开始、检索完成、调用前和结束阶段保存；若进程意外中止，可以检查最后保存的阶段。

排查顺序：确认入库全文包含目标条款 → 查看候选是否命中 → 检查 `kept` → 检查 `messages` → 对照回答。
返回候选但全部被过滤时，先检查阈值；资料不支持问题时，不应通过扩大阈值强行制造答案。

测试：`python -m unittest backend.tests.test_rag_traces backend.tests.test_vector_management -v`。
测试使用模拟数据库和模型，不调用线上服务，不修改实际集合。
