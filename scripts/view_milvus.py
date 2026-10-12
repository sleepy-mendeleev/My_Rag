from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530"
)

results = client.query(
    collection_name="agent_rag",
    filter="id >= 0",
    output_fields=["id", "name", "text"],
    limit=5
)

for i, row in enumerate(results, 1):
    print("=" * 80)
    print(f"第 {i} 条")
    print("ID:", row["id"])
    print("文件名:", row["name"])
    print("文本:")
    print(row["text"])