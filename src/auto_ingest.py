import os
import json
from .ingest import ingest_pdf

def auto_ingest(pdf_dir="data/pdfs", index_path="rag_store/faiss.index", metadata_path="rag_store/metadata.jsonl"):
    processed_file = "rag_store/processed.json"
    os.makedirs("rag_store", exist_ok=True)

    if os.path.exists(processed_file):
        processed = set(json.load(open(processed_file)))
    else:
        processed = set()

    new_pdfs = [f for f in os.listdir(pdf_dir)
                if f.endswith(".pdf") and f not in processed]

    if not new_pdfs:
        print("No new PDFs to process.")
        return

    for pdf in new_pdfs:
        pdf_path = os.path.join(pdf_dir, pdf)
        ingest_pdf(pdf_path, index_path, metadata_path)
        processed.add(pdf)

    json.dump(list(processed), open(processed_file, "w"), indent=2)
    print("[Auto-Ingest] All new PDFs processed.")
