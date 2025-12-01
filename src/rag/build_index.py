# rag/build_chroma_index.py

import json
from pathlib import Path
from chromadb import PersistentClient


DEFAULT_COLLECTION = "chunks"

def initialize_collection(save_dir="db/chroma_index", collection_name=DEFAULT_COLLECTION):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    client = PersistentClient(path=str(save_dir))
    if collection_name in [c.name for c in client.list_collections()]:
        collection = client.get_collection(name=collection_name)
    else:
        collection = client.create_collection(name=collection_name)

    return collection, client


def add_documents(chunks, get_embedding_fn, save_dir="db/chroma_index",
                  collection_name=DEFAULT_COLLECTION, auto_init=True):
    """
    Append documents to a Chroma collection.
    If collection/DB doesn't exist and auto_init=True, initialize automatically.
    """

    client = PersistentClient(path=str(save_dir))

    # auto_init: 컬렉션/파일 없으면 초기화
    if collection_name in [c.name for c in client.list_collections()]:
        collection = client.get_collection(name=collection_name)
    else:
        if auto_init:
            collection, client = initialize_collection(save_dir, collection_name)
        else:
            raise FileNotFoundError(f"Collection '{collection_name}' not found in {save_dir}")

    # 임베딩 추가
    new_embeddings = [get_embedding_fn(chunk) for chunk in chunks]
    collection.add(
        documents=chunks,
        embeddings=new_embeddings,
        ids=[str(i) for i in range(collection.count(), collection.count() + len(chunks))]
    )

    return collection, client
