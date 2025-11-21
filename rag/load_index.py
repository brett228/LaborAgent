# rag/load_index.py
import faiss
import json
import numpy as np
from pathlib import Path

def load_faiss_index(load_dir="faiss_index"):
    load_dir = Path(load_dir)

    index = faiss.read_index(str(load_dir / "index.faiss"))

    with open(load_dir / "chunks.json", "r", encoding="utf-8") as f:
        chunks = json.load(f)

    return index, chunks


def search(index, chunks, query, get_embedding_fn, k=5):
    emb = get_embedding_fn(query)
    emb = np.array([emb]).astype("float32")

    distances, ids = index.search(emb, k)
    results = [chunks[i] for i in ids[0]]
    return results

def search_vector_store(query, top_k=5):
    print("#MCP: Search Vector API")
    query_emb = np.array([get_embedding(query)]).astype("float32")
    distances, indices = index.search(query_emb, top_k)
    print("Search : ", str([chunks[i] for i in indices[0]]))
    return [chunks[i] for i in indices[0]]
