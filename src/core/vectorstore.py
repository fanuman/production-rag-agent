import chromadb
import os

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8001"))
COLLECTION_NAME = "trailpeak_docs"

def get_chroma_client():
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

def get_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}}
    )

def delete_collection():
    client = get_chroma_client()
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"Deleted existing '{COLLECTION_NAME}' collection - starting fresh")
    except Exception:
        print(f"No existing '{COLLECTION_NAME}' collection found - creating new")