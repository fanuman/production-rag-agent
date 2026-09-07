import chromadb

CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "trailpeak_docs"


def get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
    )
