# 필요한 라이브러리 불러오기

# Python 기본함수
import requests
import base64
import json
import os
import glob
import numpy as np
from PIL import Image
from io import BytesIO
from datetime import datetime, timedelta
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path

# RAG 구성
from chromadb import PersistentClient
from src.embeddings import get_embedding
from src.rag.load_index import load_chroma_collection, search_vector_store, search_multiple_collections

# Explicitly load .env from project root (parent of src)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_multiple_collections",
            "description": "Search across multiple Chroma collections and return merged top-k vector results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "검색할 chromadb collection 리스트"
                    },
                    "query": {
                        "type": "string",
                        "description": "사용자 질문"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "검색할 개수",
                        "default": 5
                    }
                },
                "required": ["collection_names", "query"]
            }
        }
    }
]

global session
session = []

DEFAULT_COLLECTIONS = ["moel_iqrs", "moel_fastcounsel"]

def get_response(query, collection_names=None, directive="", continuous=False):
    global session

    # 기본 컬렉션 지정
    if collection_names is None:
        collection_names = DEFAULT_COLLECTIONS

    # Tools 호출한 assistant/tool 메시지는 session에서 제거
    session = [m for m in session if m["role"] not in ["tool", "assistant"]]

    # continuous 모드가 아니면 session 초기화
    if not continuous:
        session = []

    # system 메시지 설정
    if not directive:
        directive = """
        너는 RAG 기반 정보 검색 보조 AI야.
        사용자가 질문하면 관련 문서를 검색하기 위해 반드시 search_multiple_collections 함수를 호출해야 해.
        - 검색되지 않은 사항에 대해서는 답변하지 말 것.
        - 답변에는 검색된 문서의 출처와 링크를 포함할 것.
        - 컬렉션 이름과 문서 ID를 명시할 것.
        - 문장을 단락으로 구분하고 이해하기 쉽게 작성할 것.
        """
    session.append({"role": "system", "content": directive})

    # user 메시지 삽입
    session.append({"role": "user", "content": query})

    # GPT 호출
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=session,
        tools=tools,
        tool_choice="auto"
    )

    choice = response.choices[0]
    tool_messages = []

    # Tool Calls 처리
    if choice.finish_reason == "tool_calls":
        for tool_call in choice.message.tool_calls:
            func_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            tool_call_id = tool_call.id

            if func_name == "search_multiple_collections":
                global chroma_client
                try:
                    chroma_client
                except NameError:
                    load_dir = Path("db/chroma_index")
                    chroma_client = PersistentClient(path=str(load_dir))

                # 존재하는 컬렉션만 사용
                existing_collections = [col.name for col in chroma_client.list_collections()]
                safe_collections = [name for name in args.get("collection_names", collection_names)
                                    if name in existing_collections]
                print("참조 정보: ", collection_names)

                if not existing_collections:
                    result = {"error": "검색 가능한 컬렉션이 없습니다."}
                else:
                    result = search_multiple_collections(
                        client=chroma_client,
                        collection_names=existing_collections,
                        query=args["query"],
                        get_embedding_fn=get_embedding,
                        top_k=args.get("top_k", 5),
                    )
            else:
                result = {"error": f"Unknown tool: {func_name}"}

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": func_name,
                "content": json.dumps(result, ensure_ascii=False)
            })

    # Tool 실행 결과 session에 추가
    if choice.message.tool_calls is not None:
        session.append({"role": "assistant", "tool_calls": choice.message.tool_calls})

    for tool_msg in tool_messages:
        session.append(tool_msg)

    # 최종 응답 생성
    final_response = client.chat.completions.create(
        model="gpt-4o",
        messages=session
    )

    output_text = final_response.choices[0].message.content
    session.append({"role": "system", "content": output_text})
    return output_text
