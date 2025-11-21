from dotenv import load_dotenv
import numpy as np
from openai import OpenAI

load_dotenv()  # reads .env file
client = OpenAI(api_key=OPENAI_API_KEY)

def get_embedding(text: str):
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding