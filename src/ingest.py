# src/ingest.py
import os
import glob
import hashlib
from dotenv import load_dotenv

load_dotenv()

import chromadb
from src.core.embeddings import get_embedding
from src.core.vectorstore import get_collection, CHROMA_PATH, COLLECTION_NAME
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Delete any existing collection first - re-running ingestion should always
# produce a clean, correctly-derived index from whatever's currently in
# data/, not silently build on top of a collection whose chunk IDs may
# have been assigned under a different (buggy) scheme.
_client = chromadb.PersistentClient(path=CHROMA_PATH)
try:
    _client.delete_collection(name=COLLECTION_NAME)
    print(f"Deleted existing '{COLLECTION_NAME}' collection - starting fresh")
except Exception:
    print(f"No existing '{COLLECTION_NAME}' collection found - creating new")

collection = get_collection()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""]
)

txt_files = glob.glob("data/*.txt")
print(f"Found {len(txt_files)} document(s)")

all_ids, all_chunks, all_metadatas = [], [], []

for txt_path in txt_files:
    filename = os.path.basename(txt_path)
    with open(txt_path, "r") as f:
        text = f.read()

    chunks = splitter.split_text(text)
    for i, chunk in enumerate(chunks):
        # Stable ID derived from filename + position within that file -
        # independent of glob's file ordering and independent of how many
        # other files exist alongside it. Fixes a real bug: the old
        # chunk_{counter} scheme let adding a new file silently shift every
        chunk_id = hashlib.md5(f"{filename}-{i}".encode()).hexdigest()
        all_ids.append(chunk_id)
        all_chunks.append(chunk)
        all_metadatas.append({"source": filename})

print(f"\nTotal chunks across all documents: {len(all_chunks)}")
print("Generating embeddings...")

all_embeddings = []
for i, chunk in enumerate(all_chunks):
    all_embeddings.append(get_embedding(chunk))
    if (i + 1) % 20 == 0:
        print(f"  Embedded {i + 1}/{len(all_chunks)} chunks...")

print("Storing in Chroma...")
collection.add(
    ids=all_ids,
    documents=all_chunks,
    embeddings=all_embeddings,
    metadatas=all_metadatas
)

print(f"Done. Collection now has {collection.count()} chunks.")