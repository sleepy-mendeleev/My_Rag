# GitHub 整理说明

这份说明针对当前版本，区分已经完成的仓库整理和仍需调整的代码；不把规划中的功能写成已实现。

## 已整理的内容

- `.gitignore`：忽略 Python 环境与缓存、前端依赖与构建结果、真实环境配置、运行日志、业务文档工作目录和数据库数据卷。
- 保留源码、有效测试、配置模板、虚构样例、前端 `package-lock.json` 和依赖清单。
- README：写清已有功能、PowerShell 运行方法、实际配置位置、离线预览、测试和当前限制。
- `.editorconfig` / `.gitattributes`：约定编码、缩进和换行，便于不同编辑器与操作系统协作。
- 后端清单固定当前本机的直接依赖版本；已验证真实 Milvus 3.0.2 的集合加载与向量列表，间接依赖尚未完全锁定。干净环境安装和真实模型的完整问答链路仍需另行验证。
- 旧 `milvus_create.py` 中的 API Key 字面量和外部数据库地址已改为读取环境变量。

## 本轮验证

验证日期：2026-10-12。环境：Windows、Python 3.12.5、Node.js 24.15.0。

| 检查 | 结果 |
| --- | --- |
| 后端 `test_*.py` | 33 项通过，使用模拟数据库与模型 |
| 前端上传队列测试 | 3 项通过 |
| 前端生产构建 | 通过，仍有单个 JS 包体积偏大的提示 |
| Python 依赖一致性 | `pip check` 通过 |
| Git 忽略规则 | 17 个应忽略路径与 14 个应保留路径验证通过 |
| 本地 Markdown 链接、配置模板与固定版本 | 验证通过 |
| 真实 Milvus 3.0.2 集合加载与查询 | `agent_rag` 25 条、`bank_rag_2` 23 条记录可读取 |
| 向量列表接口与网页 | 两个集合的分页接口均返回 HTTP 200；已确认网页恢复正常 |

已对忽略规则之外的源文件检查常见 API Key 字面量格式，移除旧脚本中的匹配项后未再发现匹配；没有读取实际 `.env` 的值。
若旧脚本中的 Key 仍有效，建议更换并更新本地配置；删除源码字面量不会撤销 Key，可参照 [百炼 API Key 管理说明](https://help.aliyun.com/zh/model-studio/get-api-key)。

## 当前需要注意的代码

| 位置 | 当前情况 | 建议 |
| --- | --- | --- |
| `backend/app/server.py` 等模块 | 读取根目录 `.env`，不是 `configs/.env` | 当前按 README 复制到根目录即可；以后统一为一个配置加载入口 |
| `frontend/rag_front/src/components/RagChat.vue` | `API_BASE` 写死本机 5000 端口 | 换端口或部署时改为前端环境变量，或使用 Vite 代理 |
| `backend/app/api_integration.py` | 上传目录写死 `/tmp/vector_uploads` | 改用 `tempfile.gettempdir()` 或统一配置路径 |
| `backend/app/document_loader.py` | Excel 路径仍依赖 Unstructured，核心清单未包含其依赖 | 完善 Excel 处理时补齐并验证，当前不承诺安装核心清单就能解析 Excel |
| `backend/app/api_integration.py` 的 `/clear_collection` | 向无参 `clear_database()` 传入集合名，接口当前不能正常工作 | 后续统一方法签名；当前使用已测试的单条 / 批量删除入口 |
| `backend/app/__init__.py` | 旧 `create_vector_system()` 仍传入已不支持的 `db_path` 参数 | 更新或移除旧工厂，当前从 `python -m backend.app.server` 启动 |
| `backend/app/vector_retriever.py` | 过滤参数未接入实际查询，`confidence` 使用旧分数公式处理 L2 | 接通元数据过滤；将 L2 距离与答案可信度分开定义 |
| `scripts/upload_document.py`、`query_system.py` | 独立旧链路，含本机路径或旧切分 / schema | 后续改为调用统一 manager 的命令行入口，避免维护两套入库逻辑 |
| `scripts/delete_collection.py` | 执行即删除硬编码集合 | 后续改为显式传参的工具，当前不列入快速开始 |
| `backend/tests/milvus_*.py` | 历史手工实验，有仓库外模块与额外依赖 | 后续移到明确的实验目录；自动测试仅运行 `test_*.py` |

## 进一步改善展示与复现

1. 加两张当前版本截图：问答页、向量管理页。使用虚构样例，放在 `docs/images/`，再从 README 引用。
2. 已记录 Milvus 3.0.2 镜像版本；后续补充并验证对应 Compose 文件。
3. 在干净环境里按 README 完整运行一次，再考虑锁定间接依赖和添加 GitHub Actions。当前没有添加未经验证的 CI 成功徽章。
4. 选择适合自己的开源许可证后再添加 `LICENSE`；当前没有替项目作者决定授权方式。

## 提交前检查

本次检查时，项目目录尚未初始化 Git 仓库。整理没有替你创建远程仓库、提交或推送。

初始化仓库后，先检查待提交文件：

```powershell
git status --short --untracked-files=all
git check-ignore -v .env configs/.env .venv/Scripts/python.exe frontend/rag_front/node_modules/example.js frontend/rag_front/dist/index.html logs/document_preview.json
```

`.gitignore` 只影响未跟踪文件；已经纳入 Git 的文件不会因为增加规则而自动移除，详见 [Git 官方说明](https://git-scm.com/docs/gitignore)。之后如需取消跟踪，应针对确认过的具体路径使用 `git rm --cached`，保留本地文件。

GitHub 上的源码仓库用于展示和协作；它不等于已经部署了可访问的 Flask、Milvus 和模型服务。
