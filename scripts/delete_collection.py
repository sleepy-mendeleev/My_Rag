from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530"
)

client.drop_collection(
    collection_name="agent_rag"
)

print("agent_rag 已删除")