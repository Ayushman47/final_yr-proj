import requests
import torch
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient
import os

# -------------------------
# Device Setup
# -------------------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# -------------------------
# Chroma DB Setup
# -------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
chroma_path = os.path.join(BASE_DIR, "chroma_db")

client = PersistentClient(path=chroma_path)
collection = client.get_collection(name="rag_otc_pdf")

# -------------------------
# Lazy Model Loading
# -------------------------
embedding_model = None
rerank_model = None

def load_models():
    global embedding_model, rerank_model

    if embedding_model is None:
        print("🔄 Loading embedding model...")
        embedding_model = SentenceTransformer(
            "sentence-transformers/all-mpnet-base-v2",
            device=device,
            local_files_only=True
        )

    if rerank_model is None:
        print("🔄 Loading reranker model...")
        rerank_model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            device=device,
            local_files_only=True,
            max_length=512
        )

# -------------------------
# Conversation Memory (Per User)
# -------------------------
conversation_memory = {}   # { username: [q1, q2] }

# -------------------------
# Ollama LLM Call
# -------------------------
def get_ollama_response(prompt: str):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 120
                }
            }
        )

        return response.json()["response"]

    except requests.exceptions.ConnectionError:
        return "⚠️ Ollama is not running. Please start Ollama."

# -------------------------
# Main RAG Function
# -------------------------
def ask_question_rag(question: str, username: str):

    global conversation_memory

    # Initialize memory for user if not exists
    if username not in conversation_memory:
        conversation_memory[username] = []

    # Store question
    conversation_memory[username].append(question)

    # Keep only last 2 questions
    conversation_memory[username] = conversation_memory[username][-2:]

    # Previous question (if exists)
    memory_text = "\n".join(conversation_memory[username][:-1])

    # Load models if needed
    load_models()

    # Expand query
    expanded_query = f"Medical treatment question: {question}"
    query_embedding = embedding_model.encode(expanded_query).tolist()

    # Retrieve
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=8
    )

    retrieved_docs = results["documents"][0]

    # Rerank
    pairs = [[question, doc] for doc in retrieved_docs]
    scores = rerank_model.predict(pairs)

    ranked_docs = [
        doc for _, doc in sorted(zip(scores, retrieved_docs), reverse=True)
    ]

    # Build context
    context = "\n\n".join(ranked_docs[:3])

    # Prompt
    prompt = f"""
You are a medical information assistant.

Previous conversation context:
{memory_text}

Current question:
{question}

Provide a short and direct answer based strictly on the given context.
Limit the response to a maximum of 3 short points.
Do not introduce the answer.
Do not add explanations about formatting.
Respond directly with the information only.
If listing medicines, just list them concisely.

Context:
{context}

Answer:
"""

    return get_ollama_response(prompt)