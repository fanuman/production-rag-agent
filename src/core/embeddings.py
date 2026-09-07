from openai import OpenAI

from src.core.config import EMBEDDING_MODEL

_client = OpenAI()


def get_embedding(text, model=EMBEDDING_MODEL):
    response = _client.embeddings.create(input=text, model=model)
    return response.data[0].embedding
