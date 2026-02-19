import os
import requests
import torch
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient

# ------------------------
# Device
# ------------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ------------------------
# Load Embedding Model
# ------------------------
embedding_model = SentenceTransformer(
    "sentence-transformers/all-mpnet-base-v2",
    device=device
)

# ------------------------
# Load Persistent Chroma DB
# ------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
chroma_path = os.path.join(BASE_DIR, "chroma_db")

client = PersistentClient(path=chroma_path)

collection = client.get_collection(name="rag_otc_pdf")

# ------------------------
# Re-ranker
# ------------------------
rerank_model = CrossEncoder(
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
    max_length=512,
    device=device
)

# ------------------------
# Retrieval
# ------------------------
def retrieve_vector_db(query, n_results=10):
    query_embedding = embedding_model.encode([query])
    results = collection.query(
        query_embeddings=query_embedding.tolist(),
        n_results=n_results
    )
    return results["documents"][0]

# ------------------------
# Reranking
# ------------------------
def rerank_documents(query, documents, top_k=5):
    pairs = [(query, doc) for doc in documents]
    scores = rerank_model.predict(pairs)
    ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in ranked[:top_k]]

# ------------------------
# Ollama
# ------------------------
def get_ollama_response(prompt, model="llama3.2:latest", max_tokens=500):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": max_tokens
            }
        }
    )

    if response.status_code == 200:
        return response.json().get("response", "")
    else:
        return "Error generating response from Ollama."

# ------------------------
# MAIN RAG FUNCTION
# ------------------------
def ask_question_rag(question, retrieve_n=10, rerank_top_k=5):
    retrieved_docs = retrieve_vector_db(question, n_results=retrieve_n)

    reranked_docs = rerank_documents(
        question,
        retrieved_docs,
        top_k=rerank_top_k
    )

    context = "\n\n".join(reranked_docs)

    prompt = f"""
You are a helpful medical assistant.
Use ONLY the context below.

Context:
{context}

Question:
{question}

Answer:
"""

    return get_ollama_response(prompt)