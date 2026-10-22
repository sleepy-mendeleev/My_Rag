"""
向量数据库管理模块
基于LangChain和Milvus实现文档切分、向量化存储和检索功能
- 1.
MinIO (对象存储服务) : Milvus 使用 MinIO 来存储数据。它提供了一个网页管理界面。

- 登录页面 : http://localhost:9001
- 账号 (Access Key) : minioadmin
- 密码 (Secret Key) : minioadmin
- 2.
Milvus (向量数据库) : 在我们当前的配置中，Milvus 本身 没有 提供一个用于登录的网页界面。您可以通过代码（例如使用 pymilvus 库）连接到 Milvus 服务来进行操作。

- 连接地址 : localhost:19530
"""

import os
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dotenv import load_dotenv

# Load env vars from explicit path
env_path = Path(__file__).resolve().parents[2] / '.env'
load_dotenv(dotenv_path=env_path)

# LangChain and Milvus imports
from langchain_community.embeddings import HuggingFaceEmbeddings, DashScopeEmbeddings
from langchain_milvus import Milvus
from langchain_core.documents import Document
from .document_loader import DocumentLoader
from .document_splitter import StructuredDocumentSplitter
from pymilvus import utility, connections, Collection, DataType

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorDatabaseManager:
    """向量数据库管理器 (Milvus后端)"""
    
    def __init__(self, 
                 milvus_host: str = None,
                 milvus_port: int = None,
                 collection_name: str = None,
                 embedding_model: str = None,
                 dashscope_api_key: str = None,
                 chunk_size: int = 500,
                 chunk_overlap: int = 50):
        """
        初始化向量数据库管理器
        
        Args:
            milvus_host: Milvus 服务主机
            milvus_port: Milvus 服务端口
            collection_name: Milvus 集合名称
            embedding_model: DashScope嵌入模型名称
            dashscope_api_key: DashScope API密钥
            chunk_size: 文档切分块大小
            chunk_overlap: 文档切分重叠大小
        """
        self.milvus_host = milvus_host or os.getenv("MILVUS_HOST", "127.0.0.1")
        # Ensure port is a string as pymilvus might expect it, or handle int gracefully
        self.milvus_port = str(milvus_port or os.getenv("MILVUS_PORT", "19530"))
        self.collection_name = collection_name or os.getenv("COLLECTION_NAME", "agent_rag")
        self.embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "text-embedding-v1")
        self.dashscope_api_key = dashscope_api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # 初始化嵌入模型
        self._init_embeddings()
        
        # 文件解析和结构切分各自只有一个入口。
        self.document_loader = DocumentLoader()
        self._init_text_splitter()

        # 连接到Milvus
        self._connect_to_milvus()
        
        # 向量数据库实例
        self.vectorstore = None
        # 延迟加载：不要在 __init__ 中调用 _load_existing_db，避免启动时连接未就绪或报错
        # self._load_existing_db() 


    def _init_text_splitter(self):
        """读取切分配置，复用已经初始化的 Embedding 模型。"""
        flag = os.getenv(
            "SEMANTIC_SPLIT_ENABLED", "false"
        ).strip().lower()

        if flag not in ("true", "false"):
            raise ValueError(
                "SEMANTIC_SPLIT_ENABLED 必须为 true 或 false"
            )

        enabled = flag == "true"
        threshold = None

        if enabled:
            raw_threshold = os.getenv(
                "SEMANTIC_SIMILARITY_THRESHOLD", ""
            ).strip()

            if not raw_threshold:
                raise ValueError(
                    "启用语义切分时，请设置 "
                    "SEMANTIC_SIMILARITY_THRESHOLD"
                )

            try:
                threshold = float(raw_threshold)
            except ValueError as error:
                raise ValueError(
                    "SEMANTIC_SIMILARITY_THRESHOLD 必须为数字"
                ) from error

        self.text_splitter = StructuredDocumentSplitter(
            self.chunk_size,
            self.chunk_overlap,
            embeddings=self.embeddings if enabled else None,
            semantic_threshold=threshold,
        )

        logger.info(
            "正文语义切分：%s，阈值：%s",
            "启用" if enabled else "关闭",
            threshold,
        )

    def _init_embeddings(self):
        """初始化嵌入模型"""
        try:
            # 确保 API Key 存在
            if not self.dashscope_api_key:
                 logger.warning("未提供 DashScope API Key，将尝试从环境变量获取")
                 self.dashscope_api_key = os.environ.get("DASHSCOPE_API_KEY", "")

            self.embeddings = DashScopeEmbeddings(
                model=self.embedding_model,
                dashscope_api_key=self.dashscope_api_key
            )
            # 简单测试 embedding 是否工作
            try:
                self.embeddings.embed_query("test")
                logger.info(f"成功加载并验证 DashScope嵌入模型: {self.embedding_model}")
            except Exception as e:
                 logger.error(f"DashScope 模型验证失败: {e}")
                 raise e

        except Exception as e:
            logger.error(f"加载DashScope模型失败: {e}")
            logger.warning("使用备用HuggingFace模型")
            self.embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'}
            )

    def _connect_to_milvus(self):
        """连接到Milvus服务"""
        try:
            logger.info(f"Connecting to Milvus: host={self.milvus_host}, port={self.milvus_port}")
            connections.connect("default", host=self.milvus_host, port=self.milvus_port)
            logger.info(f"成功连接到Milvus: {self.milvus_host}:{self.milvus_port}")
        except Exception as e:
            logger.error(f"连接Milvus失败: {e}")
            raise

    def _load_existing_db(self):
        """加载已存在的Milvus集合"""
        try:
            if utility.has_collection(self.collection_name):
                try:
                    self.vectorstore = self._open_vectorstore(self.collection_name)
                    logger.info(f"成功加载现有Milvus集合: {self.collection_name}")
                except Exception as e:
                    logger.error(f"加载现有集合失败: {e}")
                    # 不再自动删除，防止误删数据。
                    # 如果 Schema 不兼容，将在写入时处理。
                    self.vectorstore = None
            else:
                logger.info(f"未找到集合 {self.collection_name}，将在添加文档时创建")
        except Exception as e:
            logger.error(f"加载Milvus集合失败: {e}")

    def load_document(self, file_path: str) -> List[Document]:
        """所有文件通过统一加载器解析。"""
        documents = self.document_loader.load_single_file(file_path)
        logger.info("成功解析文件 %s，共 %s 个原始文档", file_path, len(documents))
        return documents

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """先按章节/条款分段，再对长段落切分并继承元数据。"""
        chunks = self.text_splitter.split_documents(documents)
        logger.info("结构切分完成：%s -> %s 个片段", len(documents), len(chunks))
        return chunks

    def _milvus_options(self, collection_name: str) -> Dict[str, Any]:
        if not utility.has_collection(collection_name):
            return {'enable_dynamic_field': True,
                    'index_params': {'index_type': 'AUTOINDEX', 'metric_type': 'L2', 'params': {}}}
        schema = Collection(collection_name).schema
        if schema.enable_dynamic_field:
            return {'enable_dynamic_field': True}
        if any(field.name == 'metadata' and field.dtype == DataType.JSON for field in schema.fields):
            return {'metadata_field': 'metadata'}
        return {}

    def _open_vectorstore(self, collection_name: str):
        return Milvus(embedding_function=self.embeddings, collection_name=collection_name,
                      connection_args={'host': self.milvus_host, 'port': self.milvus_port},
                      **self._milvus_options(collection_name))

    def add_documents_to_db(self, documents: List[Document], collection_name: str = None):
        """保存完整元数据；不兼容时拒绝写入，绝不自动删除旧集合。"""
        if not documents:
            return
        target_collection = collection_name or self.collection_name
        options = self._milvus_options(target_collection)
        if utility.has_collection(target_collection) and not options:
            fields = {field.name for field in Collection(target_collection).schema.fields}
            missing = set().union(*(doc.metadata.keys() for doc in documents)) - fields
            if missing:
                raise ValueError(f"集合 '{target_collection}' 无法保存新增元数据 {sorted(missing)}。"
                                 "请在页面填写新的集合名称（例如 bank_rag_v2）后重新上传；旧集合保留。")
        if self.vectorstore is None or self.collection_name != target_collection:
            self.vectorstore = self._open_vectorstore(target_collection)
            self.collection_name = target_collection
        self.vectorstore.add_documents(documents)
        logger.info("集合 %s 写入 %s 个片段", target_collection, len(documents))

    def process_file(self, file_path: str, collection_name: str = None, file_name: str = None) -> bool:
        """
        处理单个文件：加载、切分、存储
        
        Args:
            file_path: 文件路径
            collection_name: 集合名称
            
        Returns:
            处理是否成功
        """
        try:
            logger.info(f"开始处理文件: {file_path}")
            documents = self.load_document(file_path)
            if file_name:
                for document in documents:
                    document.metadata.update({
                        "file_name": file_name,
                        "source": file_name,
                    })
            if not documents:
                return False
            
            split_docs = self.split_documents(documents)

            if not split_docs:
                raise ValueError(
                    "文件未生成有效片段，请检查是否为空白或仅包含标题"
                )

            self.add_documents_to_db(split_docs, collection_name)
            
            logger.info(f"文件处理完成: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"处理文件失败 {file_path}: {e}")
            raise

    def process_csv_data(self, csv_path: str,
                         text_columns: List[str] = None,
                         metadata_columns: List[str] = None) -> bool:
        """
        处理CSV数据文件
        
        Args:
            csv_path: CSV文件路径
            text_columns: 需要向量化的文本列名列表
            
        Returns:
            处理是否成功
        """
        try:
            import pandas as pd
            df = pd.read_csv(csv_path, encoding='utf-8')
            logger.info(f"读取CSV文件: {csv_path}, 共 {len(df)} 行数据")
            if text_columns is None or not text_columns:
                object_cols = [c for c in df.columns if df[c].dtype == 'object']
                text_columns = [c for c in object_cols if not str(c).startswith('Unnamed')]

            if metadata_columns is None:
                metadata_columns = [c for c in df.columns if c not in text_columns]

            documents = []
            for idx, row in df.iterrows():
                content_parts = []
                metadata = {"source": csv_path, "row_index": idx}
                
                for col in text_columns:
                    if pd.notna(row[col]):
                        text = str(row[col]).strip()
                        if text:
                            content_parts.append(f"{col}: {text}")

                for col in metadata_columns:
                    val = row.get(col)
                    if pd.notna(val):
                        metadata[str(col)] = str(val)
                
                if content_parts:
                    content = "\n".join(content_parts)
                    doc = Document(page_content=content, metadata=metadata)
                    documents.append(doc)
            
            logger.info(f"构建了 {len(documents)} 个文档")
            split_docs = self.split_documents(documents)
            self.add_documents_to_db(split_docs)
            
            return True
            
        except Exception as e:
            logger.error(f"处理CSV数据失败: {e}")
            return False

    def get_embedding(self, texts: List[str]) -> List[List[float]]:
        """使用嵌入模型为一组文本生成嵌入向量"""
        try:
            return self.embeddings.embed_documents(texts)
        except Exception as e:
            logger.error(f"生成嵌入向量失败: {e}")
            return []

    def search(self, query: str, k: int = 5, filter_dict: Dict = None, collection_name: Optional[str] = None,
               raise_errors: bool = False) -> List[Tuple[Document, float]]:
        """
        相似性搜索
        
        Args:
            query: 查询文本
            k: 返回结果数量
            filter_dict: Milvus目前不支持直接的元数据过滤，此参数保留但暂不使用
            collection_name: 指定要搜索的集合名称（可选）
        
        Returns:
            (文档, 相似度分数) 列表
        """
        target_collection = collection_name or self.collection_name

        if self.vectorstore is None or (target_collection and self.collection_name != target_collection):
            try:
                if target_collection and utility.has_collection(target_collection):
                    self.vectorstore = self._open_vectorstore(target_collection)
                    self.collection_name = target_collection
                    logger.info(f"加载集合用于搜索: {target_collection}")
                else:
                    logger.warning("向量数据库未初始化")
                    return []
            except Exception as e:
                logger.error(f"加载Milvus集合失败: {e}")
                if raise_errors:
                    raise
                return []
        
        try:
            if filter_dict:
                logger.warning("Milvus集成当前不支持直接的元数据过滤，该过滤器将被忽略。")
            
            results = self.vectorstore.similarity_search_with_score(
                query=query, k=k, consistency_level="Strong"
            )
            logger.info(f"搜索查询: '{query}', 返回 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            if raise_errors:
                raise
            return []

    def get_database_info(self, collection_name: str = None) -> Dict[str, Any]:
        """
        获取数据库信息
        """
        target_collection = collection_name or self.collection_name
        
        info = {
            "milvus_host": self.milvus_host,
            "milvus_port": self.milvus_port,
            "collection_name": target_collection,
            "is_initialized": self.vectorstore is not None
        }
        
        try:
            # 如果 vectorstore 未初始化，尝试临时连接检查
            if utility.has_collection(target_collection):
                # 使用 Collection 对象获取统计信息
                col = Collection(target_collection)
                # 刷新以确保获取最新数据量（刚插入的数据可能还在内存中）
                col.flush()
                info["document_count"] = col.num_entities
                
                # 如果 self.vectorstore 为空但集合存在，尝试初始化它（如果还没做过）
                if self.vectorstore is None:
                     try:
                        self.vectorstore = self._open_vectorstore(target_collection)
                        self.collection_name = target_collection
                        info["is_initialized"] = True
                     except:
                        pass # 忽略加载错误，只返回统计
            else:
                info["document_count"] = 0
        except Exception as e:
            logger.error(f"获取Milvus集合信息失败: {e}")
            info["error"] = str(e)
        
        return info

    @staticmethod
    def _validate_collection_name(collection_name: str):
        if not isinstance(collection_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,254}", collection_name):
            raise ValueError("集合名称只能包含英文字母、数字和下划线，且不能以数字开头")

    @staticmethod
    def _primary_key_expression(primary_field, vector_id: str) -> str:
        # INT64 IDs must remain strings in the browser to avoid JavaScript rounding.
        if primary_field.dtype == DataType.INT64:
            if not isinstance(vector_id, str) or not re.fullmatch(r"-?[0-9]{1,20}", vector_id):
                raise ValueError("无效的整数向量 ID")
            value = int(vector_id)
            if not -(2 ** 63) <= value < 2 ** 63:
                raise ValueError("向量 ID 超出 INT64 范围")
            literal = str(value)
        elif primary_field.dtype == DataType.VARCHAR:
            if not isinstance(vector_id, str) or not vector_id:
                raise ValueError("向量 ID 不能为空")
            literal = json.dumps(vector_id, ensure_ascii=False)
        else:
            raise ValueError("不支持的主键类型")
        return f"{primary_field.name} == {literal}"

    def list_vectors(self, collection_name: str, offset: int = 0, limit: int = 10) -> Dict[str, Any]:
        """Browse stored chunks and dense vectors without invoking embedding or LLM."""
        self._validate_collection_name(collection_name)
        if offset < 0 or not 1 <= limit <= 50 or offset + limit + 1 >= 16384:
            raise ValueError("每页需为 1～50 条，分页窗口必须小于 16384 条")
        if not utility.has_collection(collection_name):
            return {"items": [], "has_more": False, "collection_exists": False}
        col = Collection(collection_name)
        fields = col.schema.fields
        primary = next(f for f in fields if f.is_primary)
        vector_fields = [f for f in fields if f.dtype == DataType.FLOAT_VECTOR]
        if len(vector_fields) != 1:
            raise ValueError("当前浏览器只支持具有一个 FLOAT_VECTOR 字段的集合")
        vector_name = vector_fields[0].name
        scalar_types = (DataType.VARCHAR, DataType.INT64, DataType.INT32, DataType.INT16,
                        DataType.INT8, DataType.BOOL, DataType.FLOAT, DataType.DOUBLE, DataType.JSON)
        output_fields = [f.name for f in fields if f.dtype in scalar_types or f.name == vector_name]
        if getattr(col.schema, 'enable_dynamic_field', False) is True:
            output_fields = ['*']
        col.load(timeout=15)
        rows = col.query(expr="", output_fields=output_fields, offset=offset, limit=limit + 1,
                         consistency_level="Strong", timeout=15)
        items = []
        for row in rows[:limit]:
            vector = [float(value) for value in row.get(vector_name, [])]
            metadata = dict(row.get('metadata') or {})
            metadata.update({key: value for key, value in row.items()
                             if key not in (primary.name, vector_name, 'text', 'page_content', 'metadata')})
            items.append({
                "id": str(row[primary.name]),
                "content": row.get("text") or row.get("page_content") or "",
                "source": metadata.get("source") or metadata.get("name") or "未知",
                "dimension": len(vector),
                "vector": vector,
                "metadata": metadata
            })
        return {"items": items, "has_more": len(rows) > limit, "collection_exists": True}

    def list_collections(self) -> List[str]:
        """List collections on the current Milvus connection without changing them."""
        return sorted(utility.list_collections(timeout=15))

    def delete_vectors(self, collection_name: str, vector_ids: List[str]) -> Dict[str, Any]:
        """Validate the entire batch before issuing a single exact-ID deletion."""
        self._validate_collection_name(collection_name)
        if not isinstance(vector_ids, list) or not 1 <= len(vector_ids) <= 100:
            raise ValueError('请选择 1～100 条向量，ID 必须以字符串列表提交')
        if any(not isinstance(value, str) or not value for value in vector_ids):
            raise ValueError('每个向量 ID 都必须是非空字符串')
        if not utility.has_collection(collection_name):
            return {'deleted_ids': [], 'missing_ids': list(dict.fromkeys(vector_ids))}
        col = Collection(collection_name)
        primary = next(field for field in col.schema.fields if field.is_primary)
        literals = {}
        for vector_id in vector_ids:
            literal = self._primary_key_expression(primary, vector_id).split(' == ', 1)[1]
            canonical_id = str(int(vector_id)) if primary.dtype == DataType.INT64 else vector_id
            literals[canonical_id] = literal
        expr = f"{primary.name} in [{', '.join(literals.values())}]"
        col.load(timeout=15)
        rows = col.query(expr=expr, output_fields=[primary.name], limit=len(literals),
                         consistency_level='Strong', timeout=15)
        found = {str(row[primary.name]) for row in rows}
        deleted_ids = [value for value in literals if value in found]
        if deleted_ids:
            delete_expr = f"{primary.name} in [{', '.join(literals[value] for value in deleted_ids)}]"
            col.delete(expr=delete_expr, timeout=15)
            logger.info('批量删除集合 %s 中 %s 条向量', collection_name, len(deleted_ids))
        return {'deleted_ids': deleted_ids, 'missing_ids': [value for value in literals if value not in found]}

    def delete_vector(self, collection_name: str, vector_id: str) -> bool:
        """Delete one exact primary key; never drop or rebuild the collection."""
        self._validate_collection_name(collection_name)
        if not utility.has_collection(collection_name):
            return False
        col = Collection(collection_name)
        primary = next(f for f in col.schema.fields if f.is_primary)
        expr = self._primary_key_expression(primary, vector_id)
        col.load(timeout=15)
        rows = col.query(expr=expr, output_fields=[primary.name], limit=1,
                         consistency_level="Strong", timeout=15)
        if not rows:
            return False
        col.delete(expr=expr, timeout=15)
        logger.info("删除集合 %s 中的向量 ID=%s", collection_name, vector_id)
        return True

    def clear_database(self):
        """清空Milvus集合"""
        try:
            if utility.has_collection(self.collection_name):
                utility.drop_collection(self.collection_name)
                self.vectorstore = None
                logger.info(f"Milvus集合 '{self.collection_name}' 已被删除")
        except Exception as e:
            logger.error(f"清空Milvus集合失败: {e}")

def main():
    """测试函数"""
    # 确保Milvus服务正在运行
    try:
        connections.connect("default", host="127.0.0.1", port=19530)
        utility.get_collection_stats("agent_rag")
        connections.disconnect("default")
    except Exception as e:
        logger.error("无法连接到Milvus服务，请确保您已通过 docker-compose up -d 启动了Milvus。")
        logger.error(f"错误: {e}")
        return

    # 创建向量数据库管理器
    db_manager = VectorDatabaseManager()
    
    # 清空现有数据
    print("清空现有数据库...")
    db_manager.clear_database()

    # 处理学科数据CSV文件
    csv_path = "../data.csv"
    if os.path.exists(csv_path):
        print("处理CSV数据...")
        success = db_manager.process_csv_data(csv_path)
        if success:
            print("CSV数据处理成功！")
            
            # 测试搜索
            print("\n测试搜索功能:")
            results = db_manager.search("示例查询", k=3)
            for i, (doc, score) in enumerate(results):
                print(f"\n结果 {i+1} (相似度: {score:.4f}):")
                print(f"内容: {doc.page_content[:200]}...")
                print(f"元数据: {doc.metadata}")
        else:
            print("CSV数据处理失败！")
    else:
        print(f"未找到数据文件: {csv_path}")
    
    # 显示数据库信息
    print("\n数据库信息:")
    info = db_manager.get_database_info()
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
