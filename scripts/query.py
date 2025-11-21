from src.retriever import load_index_and_metadata, query_index

index, metadata = load_index_and_metadata()

query = "Explain risk weight in corporate lending."
results = query_index(query, index, metadata, top_k=5)

for i, r in enumerate(results, 1):
    print(f"{i}. {r}\n")
