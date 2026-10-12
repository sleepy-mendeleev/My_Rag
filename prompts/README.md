# Prompt 位置说明

当前问答 Prompt 定义在 `backend/app/vector_retriever.py` 的 `_generate_answer_with_llm()` 中：只根据参考资料回答，依据不足时明确说明，不用通用知识补充银行规定。

本目录尚未被运行代码读取。修改此目录中的文件不会改变系统实际发送给模型的 Prompt；实际消息可在 `logs/rag_traces/` 中核对。

以后将 Prompt 从代码提取成文件时，再补充加载方式和版本约定。
