# rag/build_chroma_index.py

import json
from pathlib import Path
from chromadb import Client
from chromadb.config import Settings


DEFAULT_COLLECTION = "chunks"


def initialize_index(dim, save_dir="chroma_index", collection_name=DEFAULT_COLLECTION):
    """
    Create an empty Chroma DB collection and empty chunks.json.
    This replaces FAISS initialize_index().
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    # initialize empty chunk metadata
    with open(save_dir / "chunks.json", "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

    # Create chroma client
    client = Client(
        Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=str(save_dir),
        )
    )

    # If collection already exists, remove and recreate
    if collection_name in [c.name for c in client.list_collections()]:
        client.delete_collection(collection_name)

    collection = client.create_collection(name=collection_name)

    return collection



def add_documents(chunks, get_embedding_fn, save_dir="chroma_index", collection_name=DEFAULT_COLLECTION):
    """
    Append new documents to an existing ChromaDB collection.
    Replicates FAISS add_documents() behavior.
    """
    save_dir = Path(save_dir)

    # --- Load existing chunks.json ---
    with open(save_dir / "chunks.json", "r", encoding="utf-8") as f:
        existing_chunks = json.load(f)

    # Connect to persisted Chroma DB
    client = Client(
        Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=str(save_dir),
        )
    )

    # Load collection
    collection = client.get_collection(collection_name)

    # Compute embeddings for new chunks
    new_embeddings = []
    for chunk in chunks:
        emb = get_embedding_fn(chunk)
        new_embeddings.append(emb)

    # New IDs start after existing count
    start_id = len(existing_chunks)
    new_ids = [str(start_id + i) for i in range(len(chunks))]

    # Append new vectors to Chroma
    collection.add(
        ids=new_ids,
        embeddings=new_embeddings,
        metadatas=[{"chunk_index": int(i)} for i in new_ids],
        documents=chunks,
    )

    # Update local metadata
    updated_chunks = existing_chunks + chunks

    # Write back chunks.json
    with open(save_dir / "chunks.json", "w", encoding="utf-8") as f:
        json.dump(updated_chunks, f, ensure_ascii=False, indent=2)

    return collection, updated_chunks
