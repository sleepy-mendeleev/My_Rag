# 第一步：统一加载与结构切分

## 数据流

网页上传 → `VectorDatabaseManager.process_file()` → `DocumentLoader.load_single_file()`
→ `StructuredDocumentSplitter.split_documents()` → Milvus → 检索器拼装参考资料。

加载器负责读取，不负责生成向量。切分器负责标题归属与片段边界。
Manager 负责把整个处理流程串起来。后续 OCR 应接在加载器的 PDF 处理步骤中。

## 离线练习

在项目根目录的虚拟环境中执行：

```powershell
python -m scripts.preview_document docs/examples/bank_structure_demo.txt
```

打开 `logs/document_preview.json`，找到 `article` 为 `第七条` 的片段。
其 `heading_path` 应为 `["第二章 客户身份核验", "第一节 柜面业务"]`。
第八条的正文不会混入第七条；第三章不会继承第二章的第一节。

关键字段：`document_id` 是文件内容的 SHA-256；`heading_path` 是标题列表；
`article` 是条款号；`section_id` 标识本次结构分段；`chunk_id` 标识子片段。
同一文件使用同一解析和切分配置重跑时标识稳定，不代表系统已实现上传去重。
修改文件或切分规则后标识可能变化。

长条款按大小继续切分，各子片段继承同一条款与标题，并加标题路径前缀用于向量化。
`chunk_size` 限制正文部分长度，最终用于向量化的内容还包含标题前缀。
PDF `page_start` / `page_end` 是所属结构分段的页码范围，不是精确定位每个子片段。

## 页面验证

重启 `python -m backend.app.server`。
集合名称填写一个尚不存在的新名称，例如 `bank_rag_v2`，上传练习文件。
查看入库向量 → 详情 → 来源信息，确认标题和条款元数据保存成功。
然后提问“哪些情况下应暂停办理相关业务并提交人工复核？”
在问答现场文件中检查候选内容和 `messages` 的来源信息。

新集合启用 Milvus 动态字段并明确采用 AUTOINDEX/L2。
旧集合仍可查询；字段不兼容的上传会明确报错，不会自动删库重建。
已有片段不会自动获得新元数据，需要重新解析后上传到新集合。
本次未向真实数据库创建集合或插入记录，在线写入需按上面的步骤验证。

## 当前支持与边界

支持文字版 PDF/TXT 中的“第×章、第×节、第×条”显式编号，以及 Markdown 的 `#` 标题。
PDF 仍使用 PyPDFium2 的原生文本提取；章节状态可以跨页面延续。
没有编号、仅靠字号表现的标题，暂未识别；Word 暂未读取标题样式。
暂未处理重复页眉、多栏阅读顺序、PDF 表格还原、流程图和扫描件 OCR。
提取到空白页面时会中止 PDF 入库并提示 OCR 需求；合法空白页也可能触发此检查。
该检查不能发现所有混合 PDF 中的图片文字遗漏或乱码。
CSV 已通过 pandas 保留表头与二维数据，交给 `TableSplitter` 按完整数据行组成 Markdown 片段。
每块重复表头，字符预算默认 500；单行超过预算时完整保留并标记 `oversized=true`。
`row_start` / `row_end` 是从 1 开始的数据记录范围，不计表头，不等于文件物理行号。
表格片段保留 `table_id` 与 `splitter_version=table-v1`，中间字段 `table_data` 不进入最终元数据。
表格不做章节识别，也不使用普通文本的字符重叠窗口。
Excel 仍使用 `UnstructuredExcelLoader`，尚未接入上述 CSV 表格链路；相关依赖也未纳入核心安装清单。

离线测试：

```powershell
python -m unittest backend.tests.test_document_structure -v
```
