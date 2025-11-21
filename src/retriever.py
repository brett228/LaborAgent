import numpy as np
from .vectorstore import load_or_create_index
from .metadata_store import load_metadata
from .embeddings import get_embedding

def load_index_and_metadata(index_path="rag_store/faiss.index", metadata_path="rag_store/metadata.jsonl"):
    metadata = load_metadata(metadata_path)
    if metadata:
        dim = len(metadata[0]["chunk"])  # placeholder; adjust if using real embeddings
        index = load_or_create_index(dim, index_path)
    else:
        index = load_or_create_index(768, index_path)  # default
    return index, metadata

def query_index(query, index, metadata, top_k=5):
    emb = get_embedding(query)
    emb = np.array([emb], dtype="float32")

    distances, ids = index.search(emb, top_k)
    results = [metadata[i]["chunk"] for i in ids[0]]
    return results
