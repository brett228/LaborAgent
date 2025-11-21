from src.auto_ingest import auto_ingest

if __name__ == "__main__":
    auto_ingest(
        pdf_dir="data/pdfs",
        index_path="rag_store/faiss.index",
        metadata_path="rag_store/metadata.jsonl"
    )
