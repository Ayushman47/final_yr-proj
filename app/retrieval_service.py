import re
import fitz  # PyMuPDF
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient
import os
import sys
import torch

from app.model_profile_service import get_tier_settings

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if hasattr(sys, '_MEIPASS'):
    app_data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "HealthAssist")
    os.makedirs(app_data_dir, exist_ok=True)
    chroma_path = os.path.join(app_data_dir, "chroma_db")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(BASE_DIR, "chroma_db")

client = PersistentClient(path=chroma_path)
collection = client.get_or_create_collection(name="rag_otc_pdf")

embedding_models = {}
reranker_model = None

def get_embedding_model(model_name: str):
    if model_name not in embedding_models:
        embedding_models[model_name] = SentenceTransformer(model_name, device=device)
    return embedding_models[model_name]

def get_reranker():
    global reranker_model
    if reranker_model is None:
        reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", device=device)
    return reranker_model

def clean_text(text: str) -> str:
    text = re.sub(r'\[\d+(,\s*\d+)*\]', '', text)
    text = re.sub(r'http\S+|www\.\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def semantic_chunking(text: str, chunk_size: int = 500, overlap: int = 100):
    """Basic implementation of semantic chunking preserving paragraphs/sentences."""
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        tokens = len(sentence.split()) # Rough token estimate
        if current_length + tokens > chunk_size and current_chunk:
            chunks.append(" ".join(current_chunk))
            
            # Keep overlap
            overlap_length = 0
            overlap_chunk = []
            for s in reversed(current_chunk):
                s_tokens = len(s.split())
                if overlap_length + s_tokens <= overlap:
                    overlap_chunk.insert(0, s)
                    overlap_length += s_tokens
                else:
                    break
            
            current_chunk = list(overlap_chunk)
            current_length = overlap_length
            
        current_chunk.append(sentence)
        current_length += tokens
        
    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

def ingest_pdf_pymupdf(pdf_bytes: bytes, source_name: str, tier: str = "Balanced") -> int:
    settings = get_tier_settings(tier)
    chunk_size = settings["chunk_size"]
    chunk_overlap = settings["chunk_overlap"]
    model_name = settings["embedding_model"]
    
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_chunks = []
    all_metadatas = []
    
    for page_num, page in enumerate(doc):
        text = page.get_text()
        cleaned = clean_text(text)
        if not cleaned:
            continue
            
        chunks = semantic_chunking(cleaned, chunk_size=chunk_size, overlap=chunk_overlap)
        all_chunks.extend(chunks)
        
        for _ in chunks:
            all_metadatas.append({
                "source": source_name,
                "page": page_num + 1,
                "medical_topic": "General", # Could be refined with NLP
                "symptom_category": "Unknown",
                "severity": "Unknown"
            })
            
    if not all_chunks:
        raise ValueError("PDF contained no extractable text.")
        
    model = get_embedding_model(model_name)
    embeddings = model.encode(all_chunks).tolist()
    
    ids = [f"{source_name}_chunk_{i}" for i in range(len(all_chunks))]
    collection.upsert(
        documents=all_chunks,
        embeddings=embeddings,
        ids=ids,
        metadatas=all_metadatas,
    )
    return len(all_chunks)

def delete_pdf(source_name: str):
    collection.delete(where={"source": source_name})

def retrieve_and_rerank(query: str, tier: str) -> tuple[str, list[dict], float]:
    settings = get_tier_settings(tier)
    model_name = settings["embedding_model"]
    top_k = settings["top_k"]
    use_rerank = settings["rerank"]
    
    model = get_embedding_model(model_name)
    embedding = model.encode(f"symptom treatment: {query}").tolist()
    
    # Retrieve more if reranking
    fetch_k = 10 if use_rerank else top_k
    
    results = collection.query(query_embeddings=[embedding], n_results=fetch_k)
    
    docs = results["documents"][0] if results["documents"] else []
    metas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
    
    if not docs:
        return "", [], 0.0
        
    confidence = 1.0 # default
        
    if use_rerank and len(docs) > 1:
        reranker = get_reranker()
        pairs = [[query, doc] for doc in docs]
        scores = reranker.predict(pairs)
        
        # Sort by scores descending
        scored_docs = sorted(zip(scores, docs, metas), key=lambda x: x[0], reverse=True)
        top_scored = scored_docs[:top_k]
        
        docs = [x[1] for x in top_scored]
        metas = [x[2] for x in top_scored]
        
        # Confidence logic based on reranker scores
        avg_score = sum(x[0] for x in top_scored) / len(top_scored)
        confidence = avg_score
    else:
        # If no reranking, we just use the raw chunks up to top_k
        docs = docs[:top_k]
        metas = metas[:top_k]
    
    context = "\n\n".join(docs)
    return context, metas, confidence
