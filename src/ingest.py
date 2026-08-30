# ingest.py
import os
import glob
from pypdf import PdfReader
from openai import OpenAI
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI()
chroma_client = chromadb.PersistentClient(path="./chroma_db")

collection = chroma_client.get_or_create_collection(
    name="ai_governance_docs",
    configuration={"hnsw": {"space": "cosine"}}
)

def get_embedding(text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(input=text, model=model)
    return response.data[0].embedding

def extract_text_from_pdf(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text

splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=150,
    separators=["\n\n", "\n", ". ", " ", ""]
)

pdf_files = glob.glob("data/*.pdf")
print(f"Found {len(pdf_files)} PDF(s): {pdf_files}")

all_ids, all_chunks, all_metadatas = [], [], []
chunk_counter = 0

for pdf_path in pdf_files:
    filename = os.path.basename(pdf_path)
    print(f"Processing {filename}...")

    text = extract_text_from_pdf(pdf_path)
    print(f"  Extracted {len(text):,} characters")

    chunks = splitter.split_text(text)
    print(f"  Split into {len(chunks)} chunks")

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