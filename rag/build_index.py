# rag/build_index.py
import faiss
import json
import numpy as np
from pathlib import Path


def initialize_index(dim, save_dir="faiss_index"):
    """
    Create a new empty FAISS index + empty chunks.json
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    index = faiss.IndexFlatL2(dim)
    faiss.write_index(index, str(save_dir / "index.faiss"))

    # initialize empty metadata store
    with open(save_dir / "chunks.json", "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

    return index


def add_documents(chunks, get_embedding_fn, save_dir="faiss_index"):
    """
    Append new documents to an existing FAISS index.
    chunks: list of raw text chunks from new documents
    """
    save_dir = Path(save_dir)

    # --- Load existing index ---
    index = faiss.read_index(str(save_dir / "index.faiss"))

    # --- Load existing chunks (metadata) ---
    with open(save_dir / "chunks.json", "r", encoding="utf-8") as f:
        existing_chunks = json.load(f)

    # Compute embeddings for new chunks
    new_embeddings = []
    for chunk in chunks:
        emb = get_embedding_fn(chunk)
        new_embeddings.append(emb)

    new_embeddings = np.array(new_embeddings).astype("float32")

    # --- Append vectors to FAISS index ---
    index.add(new_embeddings)

    # --- Append metadata (keep ordering aligned with FAISS IDs) ---
    updated_chunks = existing_chunks + chunks

    # --- SAVE BACK ---
    faiss.write_index(index, str(save_dir / "index.faiss"))

    with open(save_dir / "chunks.json", "w", encoding="utf-8") as f:
        json.dump(updated_chunks, f, ensure_ascii=False, indent=2)

    return index, updated_chunks
