import os
import re
import torch
import PyPDF2
from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient

# ------------------------
# Device
# ------------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
pdf_path = os.path.join(BASE_DIR, "data", "oct.pdf")
chroma_path = os.path.join(BASE_DIR, "chroma_db")

# ------------------------
# Load PDF
# ------------------------
reader = PyPDF2.PdfReader(pdf_path)
pages = [page.extract_text() for page in reader.pages]
document = "\n".join(pages)

# ------------------------
# Cleaning
# ------------------------
def clean_text(text):
    text = re.sub(r'\[\d+(,\s*\d+)*\]', '', text)
    text = re.sub(r'http\S+|www\.\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ------------------------
# Chunking
# ------------------------
def get_overlapped_chunks(text, chunksize=1000, overlapsize=100):
    return [
        text[i:i + chunksize]
        for i in range(0, len(text), chunksize - overlapsize)
    ]

cleaned_document = clean_text(document)
chunks = get_overlapped_chunks(cleaned_document)
chunks = [chunk for chunk in chunks if len(chunk.split()) > 10]

# ------------------------
# Embedding Model
# ------------------------
embedding_model = SentenceTransformer(
    "sentence-transformers/all-mpnet-base-v2",
    device=device
)

chunk_embeddings = embedding_model.encode(
    chunks,
    show_progress_bar=True
)

# ------------------------
# Persistent Chroma Client
# ------------------------
client = PersistentClient(path=chroma_path)

collection_name = "rag_otc_pdf"

# Delete old collection if exists
try:
    client.delete_collection(name=collection_name)
except:
    pass

collection = client.create_collection(name=collection_name)

collection.add(
    documents=chunks,
    embeddings=chunk_embeddings.tolist(),
    ids=[str(i) for i in range(len(chunks))]
)

print("Indexing complete. Database saved at:", chroma_path)