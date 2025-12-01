# rag/load_chroma_index.py

import json
from pathlib import Path
from chromadb import Client
from chromadb.config import Settings


def load_chroma_collection(load_dir="chroma_index", collection_name="chunks"):
    """
    Load a persisted Chroma DB collection and the chunk metadata.
    """
    load_dir = Path(load_dir)

    # Load text chunks (same as your FAISS version)
    with open(load_dir / "chunks.json", "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # Create Chroma client from persisted directory
    client = Client(
        Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=str(load_dir),
        )
    )

    # Load existing collection
    collection = client.get_collection(name=collection_name)

    return collection, chunks



def search(collection, chunks, query, get_embedding_fn, k=5):
    """
    Vector search using ChromaDB.
    """
    query_emb = get_embedding_fn(query)

    # Chroma expects list of embeddings
    result = collection.query(
        query_embeddings=[query_emb],
        n_results=k
    )

    # result["ids"] is like: [["3", "10", "8"]]
    ids = result["ids"][0]

    # Convert string IDs to int
    ids = list(map(int, ids))
    return [chunks[i] for i in ids]



def search_vector_store(collection, chunks, query, get_embedding_fn, top_k=5):
    print("#MCP: Search Vector API")
    query_emb = get_embedding_fn(query)

    result = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k
    )

    ids = list(map(int, result["ids"][0]))
    print("Search:", str([chunks[i] for i in ids]))

    return [chunks[i] for i in ids]


def search_multiple_collections(client: Client, collection_names, query, get_embedding_fn, top_k=5, chunks_map=None):
    """
    Search multiple Chroma collections and merge results.
    
    Args:
        client: ChromaDB client
        collection_names: list of collection names to search
        query: string query
        get_embedding_fn: function to get embedding from text
        top_k: number of results to return
        chunks_map: dict {collection_name: list_of_chunks} to map ids to original chunks
    
    Returns:
        merged top_k results as list of dicts:
            {"collection": collection_name, "id": id, "document": doc, "distance": distance}
    """
    query_emb = get_embedding_fn(query)
    all_results = []

    for name in collection_names:
        col = client.get_collection(name)
        res = col.query(
            query_embeddings=[query_emb],
            n_results=top_k
        )

        # res["ids"], res["documents"], res["distances"] are lists of lists
        ids = res["ids"][0]
        docs = res["documents"][0] if chunks_map is None else [chunks_map[name][int(i)] for i in ids]
        distances = res["distances"][0]

        for i, doc, dist in zip(ids, docs, distances):
            all_results.append({
                "collection": name,
                "id": i,
                "document": doc,
                "distance": dist
            })

    # 거리 기준으로 정렬 (작을수록 유사)
    all_results.sort(key=lambda x: x["distance"])

    return all_results[:top_k]
