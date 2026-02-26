import requests
import torch
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient
import os

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
chroma_path = os.path.join(BASE_DIR, "chroma_db")

client = PersistentClient(path=chroma_path)
collection = client.get_collection(name="rag_otc_pdf")

embedding_model = None
rerank_model = None

def load_models():
    global embedding_model, rerank_model

    if embedding_model is None:
        embedding_model = SentenceTransformer(
            "sentence-transformers/all-mpnet-base-v2",
            device=device,
            local_files_only=True
        )

    if rerank_model is None:
        rerank_model = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            device=device,
            local_files_only=True,
            max_length=512
        )

conversation_memory = {}

def get_ollama_response(system_prompt: str, user_prompt: str):
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "llama3.2",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": 0.0,   # deterministic
                    "top_p": 0.9,
                    "num_predict": 120
                }
            }
        )
        return response.json()["message"]["content"]
    except:
        return "⚠️ Ollama not running."


def ask_question_rag(question: str, username: str):

    global conversation_memory

    # ---------------- FIRST ROUND ----------------
    if username not in conversation_memory:

        conversation_memory[username] = {
            "initial_question": question
        }

        system_prompt = """
You are a health chatbot.

The user has described a symptom.

Ask exactly TWO short clarifying questions.

Ask about:
- Duration of symptoms
- Severity level
- Other associated symptoms

Each question under 12 words.
Do NOT give advice yet.
Output only the two questions.
No extra text.
"""

        return get_ollama_response(system_prompt, question)

    # ---------------- SECOND ROUND ----------------
    else:

        initial_question = conversation_memory[username]["initial_question"]

        load_models()

        expanded_query = f"minor symptom question: {initial_question}"
        query_embedding = embedding_model.encode(expanded_query).tolist()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=3
        )

        retrieved_docs = results["documents"][0]
        context = "\n\n".join(retrieved_docs[:1])

        system_prompt = """
You already asked follow-up questions.

Now provide short suggestions.

STRICT RULES:
- Maximum 3 bullet points.
- Each bullet under 15 words.
- Simple pharmacy options or home remedies only.
- No questions.
- Do NOT ask anything.
- No warnings.
- No disclaimers.
- If you ask a question, output is invalid.
"""

        user_prompt = f"""
Original symptom:
{initial_question}

User reply:
{question}

Provide suggestions now.
"""

        response = get_ollama_response(system_prompt, user_prompt)

        # Hard guard: if model still asks a question, override
        if "?" in response:
            response = """- Take paracetamol for fever relief.
- Drink plenty of fluids.
- Rest and monitor symptoms."""

        # Clear state to prevent looping
        del conversation_memory[username]

        return response