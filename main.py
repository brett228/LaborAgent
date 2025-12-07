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
import streamlit as st

# RAG 구성
from chromadb import PersistentClient
from src.embeddings import get_embedding
from src.rag.load_index import load_chroma_collection, search_vector_store, search_multiple_collections
from src.consult.legal_report_builder import LegalAgent
from src.newsletter.newsletter_builder import NewsletterAgent

# Explicitly load .env from project root (parent of src)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Create Agent instance
create_newsletter = NewsletterAgent()
create_legalreport = LegalAgent()

tool_implementations = {
    "create_legalreport": lambda query=None: create_legalreport.run(query=query),
    "create_newsletter": lambda user_input=None: create_newsletter.run_steps(user_input=user_input),
}

tools = [
    {
        "type": "function",
        "function": {
            "name": "create_newsletter",
            "description": "create newsletter on recent issues on labor market",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_input": {
                        "type": "string",
                        "description": "사용자 응답"
                    }
                },
                "required": ["user_input"],
            },
        },
    },

    {
        "type": "function",
        "function": {
            "name": "create_legalreport",
            "description": "create legal report according to customer's query on labor issue",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "사용자 질문"
                    }
                },
                "required": ["query"],
            },
        }
    },

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
    },

    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "Generate a structured text report from given sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "heading": {"type": "string"},
                                "content": {"type": "string"}
                            },
                            "required": ["heading", "content"]
                        }
                    },
                    "format": {
                        "type": "string",
                        "enum": ["text", "markdown"],
                        "default": "markdown"
                    }
                },
                "required": ["title", "sections"]
            }
        }
    }
]

global session
session = []

DEFAULT_COLLECTIONS = ["moel_iqrs", "moel_fastcounsel"]

def get_response(query, collection_names=None, directive="", continuous=False):
    global session

    # 세션 초기화
    if "session" not in st.session_state:
        st.session_state["session"] = []
    session = st.session_state["session"]

    # 대화 초기화 옵션
    if not continuous:
        session = []

    # 기본 컬렉션 지정
    if collection_names is None:
        collection_names = DEFAULT_COLLECTIONS

    # Tools 호출한 assistant/tool 메시지는 session에서 제거
    session = [m for m in session if m["role"] not in ["tool", "assistant"]]

    # system 메시지 설정
    if not directive:
        directive = """
        당신은 RAG 기반 정보 검색 / 리포트 작성 보조 AI입니다.
        다음 규칙에 따라 사용자가 요청한 작업을 수행합니다.

        0. 공통 규칙
          - 항상 한글로만 대답합니다.
          - 욕설과 비속어는 사용하지 않습니다.
          - 당신의 답변 영역은 인사/노무 분야로 한정되며, 그 외의 일반적인 질문에 대해서는 답을 피합니다.
        
        1. 사용자가 인사/노무 관련 질문을 하면 관련 문서를 검색하기 위해 반드시 search_multiple_collections 함수를 호출합니다.
          - 검색되지 않은 사항에 대해서는 답변하지 않습니다.
          - 답변에는 검색된 문서의 출처와 링크를 포함합니다.
          - 답변 근거를 찾은 collecion 이름과 문서 ID를 명시합니다.
          - 문장을 단락으로 구분하고 이해하기 쉽게 작성합니다. 

        2. 사용자가 노무 보고서, 의견서 등을 요청하면 create_legalreport 함수를 호출합니다.
           create_legalreport 함수를 호출할 경우에는 다른 답변은 절대 제공하지 않습니다.

        3. 사용자가 "뉴스레터 생성"을 요청하면  create_newsletter 함수를 호출합니다.
           뉴스레터 생 흐름은 멀티턴으로 진행됩니다.
           (1) 
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
                
            # elif func_name in tool_implementations:
            #     result = tool_implementations[func_name](**args)

            elif func_name == "create_legalreport":
                result = create_legalreport.run(**args)

            elif func_name == "create_newsletter":
                result = create_newsletter.run_steps(args.get("user_input", ""))
                if create_newsletter._phase == "ready_to_generate":
                    html = create_newsletter.run()
                    result = {"newsletter": html}

            else:
                result = {"error": f"Unknown tool: {func_name}"}

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "name": func_name,
                "content": json.dumps(result, ensure_ascii=False)
            })
            # print(result)
            # print("tool_messages:", tool_messages)

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
    st.session_state["session"] = session
    return output_text, tool_messages
