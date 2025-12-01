# rag/load_chroma_index.py

import json
from pathlib import Path
from chromadb import PersistentClient


def load_chroma_collection(load_dir="db/chroma_index", collection_name="default"):
    """
    Load a persisted Chroma DB collection.
    """
    load_dir = Path(load_dir)
    load_dir.mkdir(parents=True, exist_ok=True)

    # Persistent Chroma client
    client = PersistentClient(path=str(load_dir))

    # 컬렉션 존재 여부 확인
    if collection_name in [c.name for c in client.list_collections()]:
        collection = client.get_collection(name=collection_name)
    else:
        raise FileNotFoundError(f"Collection '{collection_name}' not found in {load_dir}")

    return collection, client


def search_vector_store(collection, query, get_embedding_fn, top_k=5):
    """
    Chroma collection에서 검색 후 원문 반환
    """
    query_emb = get_embedding_fn(query)

    result = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k
    )

    # Chroma query 결과에서 바로 documents 가져오기
    docs = result["documents"][0]
    print("Search:", docs)
    return docs


def search_multiple_collections(client, collection_names, query, get_embedding_fn, top_k=5):
    """
    Search multiple Chroma collections and merge results.
    
    Returns top_k results sorted by distance.
    """
    print("#MCP: search_multiple_collections")
    query_emb = get_embedding_fn(query)
    all_results = []

    for name in collection_names:
        collection = client.get_collection(name)
        print(name)
        res = collection.query(
            query_embeddings=[query_emb],
            n_results=top_k
        )

        docs = res["documents"][0]
        distances = res["distances"][0]

        for doc, dist in zip(docs, distances):
            all_results.append({
                "collection": name,
                "document": doc,
                "distance": dist
            })

    # 거리 기준 정렬 (작을수록 유사)
    all_results.sort(key=lambda x: x["distance"])
    return all_results[:top_k]
