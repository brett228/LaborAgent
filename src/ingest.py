import os
import numpy as np
from .chunking import load_pdf_text, chunk_text
from .embeddings import get_embedding
from .vectorstore import load_or_create_index, save_index
from .metadata_store import append_metadata

def ingest_pdf(pdf_path, index_path="rag_store/faiss.index", metadata_path="rag_store/metadata.jsonl"):
    os.makedirs(os.path.dirname(index_path), exist_ok=True)

    text = load_pdf_text(pdf_path)
    chunks = chunk_text(text)
    embeddings = np.array([get_embedding(c) for c in chunks], dtype="float32")
    
    index = load_or_create_index(embeddings.shape[1], index_path)
    start_id = index.ntotal

    index.add(embeddings)
    save_index(index, index_path)

    metadata = [{
        "vector_id": start_id + i,
        "chunk": c,
        "pdf": os.path.basename(pdf_path)
    } for i, c in enumerate(chunks)]

    append_metadata(metadata_path, metadata)

    print(f"[Ingest] {len(chunks)} chunks added for {pdf_path}")
    return len(chunks)
