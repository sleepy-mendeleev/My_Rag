# Milvus 启动说明

当前项目连接独立运行的 Milvus，默认地址为 `127.0.0.1:19530`。本目录尚未包含经过验证的 Docker Compose 文件。

已验证的服务镜像为 `milvusdb/milvus:v3.0.2`，Python 客户端为 `pymilvus==3.0.2`；已验证已有集合的加载、记录查询及网页向量列表。

如果已经有 Milvus 容器，打开 Docker Desktop 并启动该容器；如果原先通过 Compose 创建，应按原配置启动对应服务组。Python 虚拟环境负责项目依赖，Docker 容器需要单独运行。

在 PowerShell 中检查运行状态与映射端口：

```powershell
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
Test-NetConnection 127.0.0.1 -Port 19530
```

首次安装可参照 [Milvus 官方 Windows Docker 指南](https://milvus.io/docs/install_standalone-windows.md)。记录实际使用的 Milvus 镜像版本和启动配置，后续再将经过本项目验证的配置放入此目录。

Docker 映射端口写作“宿主机端口:容器端口”。例如 `19531:19530` 表示 Python 应连接 `127.0.0.1:19531`；根目录 `.env` 的 `MILVUS_PORT` 和检查命令的 `-Port` 都应使用 19531。常规单实例可以继续使用 `19530:19530`，端口配置保存后无需每次启动重复指定。

复用使用内嵌 etcd 的旧 standalone 数据时，需要保留原有配置、数据挂载和 `ETCD_DATA_DIR=/var/lib/milvus/etcd`。遗漏该设置可能连接到新建的空元数据目录，表现为服务能连接但旧集合不存在。升级先使用停机备份的副本验证，保留原数据。

数据库持久化目录 `infra/volumes/` 和根目录 `volumes/` 已被忽略；不把实际向量库数据提交到 GitHub。
