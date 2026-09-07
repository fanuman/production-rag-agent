import os
import glob
from dotenv import load_dotenv

load_dotenv()

from src.core.embeddings import get_embedding
from src.core.vectorstore import get_collection
from langchain_text_splitters import RecursiveCharacterTextSplitter

collection = get_collection()

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

    chunks = splitter.split_text(text)
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
