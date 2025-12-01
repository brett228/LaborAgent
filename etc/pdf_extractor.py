import requests
import base64
import json
import os
import glob
import numpy as np
from PIL import Image
from io import BytesIO
from datetime import datetime, timedelta
from openai import OpenAI
import json


# RAG 구성
import faiss
import PyPDF2
import pdfplumber
import pytesseract
from pdf2image import convert_from_path

data_folder = './'
OPENAI_API_KEY = "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"
client = OpenAI(api_key=OPENAI_API_KEY)

def extract_text_from_pdf(file_path):
    text_list = []
    pages = convert_from_path(file_path, dpi=50)
    for i, page in enumerate(pages):
        file_name = "pdf_img_temp/page_"+str(i+1)+".png"
        page.save(data_folder + file_name, "PNG")

        with open(data_folder + file_name, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")
        data_url = f"data:image/png;base64,{image_base64}"

        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "이미지 내 정보를 텍스트로 상세히 정리해줘. 표는 표 형태로 정리해줘."},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ]
        )
        text_list.append(response.choices[0].message.content)
    return text_list

def extract_text_from_img(file_path):
    f = open(file_path, "rb")
    image_base64 = base64.b64encode(f.read()).decode("utf-8")
    f.close()

    data_url = f"data:image/png;base64,{image_base64}"
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "이미지 내 정보를 텍스트로 상세히 정리해줘. 표는 표 형태로 정리해줘."},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]
            }
        ]
    )
    img_text = response.choices[0].message.content
    return img_text

def chunk_text(text, max_tokens=500):
    lines = text.split('\n')
    chunk = []
    tokens_count = 0
    chunks = []   # 최종 청크들을 담을 리스트
    in_table = False

    for line in lines:
        # 테이블 시작 감지
        if '|' in line:
            in_table = True

        if in_table:
            chunk.append(line)
            if not line.strip():  # 테이블 끝
                chunks.append("\n".join(chunk))
                chunk = []
                in_table = False
                tokens_count = 0
            continue

        line_tokens = len(line.split())
        if tokens_count + line_tokens > max_tokens and chunk:
            chunks.append("\n".join(chunk))
            chunk = []
            tokens_count = 0
        chunk.append(line)
        tokens_count += line_tokens

    if chunk:
        chunks.append("\n".join(chunk))

    return chunks


def get_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

def build_faiss_index(chunks):
    embeddings = []
    for chunk in chunks:
        emb = get_embedding(chunk)
        embeddings.append(emb)

    embeddings = np.array(embeddings).astype("float32")
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)
    return index, chunks


# PDF와 이미지 파일 확장자를 모두 포함
file_list = []
for ext in ["*.pdf", "*.jpg", "*.jpeg", "*.png"]:
    file_list.extend(glob.glob(os.path.join(data_folder, ext)))

# 파일 리스트 확인
for path in file_list:
    print(path)


# 1. 문서인식

text_list = []

for path in file_list:
    print("*임베딩 진행중 :", path)
    if path.split(".")[-1] in ["pdf"]:
        pdf_text_list = extract_text_from_pdf(path)
        text_list += pdf_text_list
    elif path.split(".")[-1] in ["jpg", "jpeg", "png"]:
        img_text = extract_text_from_img(path)
        text_list += [img_text]
    else:
        continue    



# 2. 청킹

chunks = []

for text in text_list:
    chunks += list(chunk_text(text))


# 3~4. 임베딩, 임베딩 벡터 저장

index, chunks = build_faiss_index(chunks)

faiss.write_index(index, "faiss_index/index.faiss")
with open("faiss_index/chunks.json", "w", encoding="utf-8") as f:
    json.dump(chunks, f, ensure_ascii=False, indent=2)
index = faiss.read_index("faiss_index/index.faiss")
with open("faiss_index/chunks.json", "r", encoding="utf-8") as f:
    chunks = json.load(f)


def search_vector_store(query, top_k=5):
    print("#MCP: Search Vector API")
    query_emb = np.array([get_embedding(query)]).astype("float32")
    distances, indices = index.search(query_emb, top_k)
    print("Search : ", str([chunks[i] for i in indices[0]]))
    return [chunks[i] for i in indices[0]]



# rag/build_index.py
import faiss
import json
import numpy as np
from pathlib import Path

def build_faiss_index(chunks, get_embedding_fn, save_dir="faiss_index"):
    """
    chunks: list of raw text chunks
    get_embedding_fn: function that takes text -> embedding list/np array
    save_dir: path to store index.faiss and chunks.json
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: create embeddings
    embeddings = []
    for chunk in chunks:
        emb = get_embedding_fn(chunk)
        embeddings.append(emb)

    embeddings = np.array(embeddings).astype("float32")

    # Step 2: build FAISS index
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    # Step 3: save index
    faiss.write_index(index, str(save_dir / "index.faiss"))

    # Step 4: save chunks (metadata store)
    with open(save_dir / "chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    return index
