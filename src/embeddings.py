import os
from pathlib import Path
from dotenv import load_dotenv
import numpy as np
from openai import OpenAI

# Explicitly load .env from project root (parent of src)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding