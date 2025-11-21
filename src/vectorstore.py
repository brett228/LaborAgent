import os
import faiss

def load_or_create_index(dimension, path):
    if os.path.exists(path):
        print("[FAISS] Loading existing index")
        return faiss.read_index(path)
    print("[FAISS] Creating new index")
    return faiss.IndexFlatL2(dimension)

def save_index(index, path):
    faiss.write_index(index, path)

def add_embeddings(index, embeddings):
    index.add(embeddings)
