# ingest.py
import os
import glob
from openai import OpenAI
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db")

collection = chroma_client.get_or_create_collection(
    name="trailpeak_docs",
    configuration={"hnsw": {"space": "cosine"}}
)

def get_embedding(text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(input=text, model=model)
    return response.data[0].embedding

splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""]
)

txt_files = glob.glob("data/*.txt")
print(f"Found {len(txt_files)} document(s)")

all_ids, all_chunks, all_metadatas = [], [], []
chunk_counter = 0

for txt_path in txt_files:
    filename = os.path.basename(txt_path)
    with open(txt_path, "r") as f:
        text = f.read()

    chunks = splitter.split_text(text)  # keep your existing splitter setup
    for chunk in chunks:
        all_ids.append(f"chunk_{chunk_counter}")
        all_chunks.append(chunk)
        all_metadatas.append({"source": filename})
        chunk_counter += 1

print(f"\nTotal chunks across all documents: {chunk_counter}")
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