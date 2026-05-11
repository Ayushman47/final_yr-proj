import requests
import torch
import re
import PyPDF2
import io
from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient
import os
import sys

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Ensure ChromaDB is in a writable location
if hasattr(sys, '_MEIPASS'):
    # Running as bundled EXE
    app_data_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), "HealthAssist")
    os.makedirs(app_data_dir, exist_ok=True)
    chroma_path = os.path.join(app_data_dir, "chroma_db")
else:
    # Running as normal script
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    chroma_path = os.path.join(BASE_DIR, "chroma_db")

client = PersistentClient(path=chroma_path)
collection = client.get_or_create_collection(name="rag_otc_pdf")

# Lazy-loaded — only occupies RAM when the first request arrives
embedding_model = None

# How many past messages to include in the Ollama prompt (keeps RAM low)
MAX_HISTORY = 20  # ~10 full exchanges


def load_models():
    global embedding_model
    if embedding_model is None:
        embedding_model = SentenceTransformer(
            "sentence-transformers/all-MiniLM-L6-v2",
            device=device,
            local_files_only=True,
        )


# ---------------------------------------------------------------------------
# Core Ollama caller — accepts a pre-built messages list (multi-turn)
# ---------------------------------------------------------------------------

def _call_ollama(messages: list[dict], num_predict: int = 400) -> str:
    """Send a messages array directly to Ollama /api/chat.

    messages must be fully formed: [{"role": "system"|"user"|"assistant",
                                     "content": "..."}]
    This is the single choke-point for all LLM calls in this module.
    """
    try:
        from app.model_manager import get_active_model
        active_model = get_active_model()
        if not active_model:
            return "No AI model is currently active. Please select or download one from the settings."

        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": active_model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "num_predict": 400,
                },
            },
            timeout=90,
        )
        data = resp.json()
        print("Ollama raw response:", data)

        if "error" in data:
            print("Ollama error detail:", data["error"])
            return "Server error. Please try again."
        if "message" not in data:
            print("Ollama unexpected structure:", data)
            return "Server error. Please try again."
        return data["message"]["content"]

    except requests.exceptions.ConnectionError:
        print("Ollama error: Could not connect. Is Ollama running?")
        return "Service unavailable. Please ensure Ollama is running on port 11434."
    except requests.exceptions.Timeout:
        print("Ollama error: Request timed out.")
        return "Request timed out. Please try again."
    except Exception as exc:
        print("Ollama error:", exc)
        return "Server error. Please try again."


# Convenience wrapper kept for any callers that pass (system, user) strings
def get_ollama_response(system_prompt: str, user_prompt: str) -> str:
    return _call_ollama([
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_prompt},
    ])


# ---------------------------------------------------------------------------
# Intent helpers
# ---------------------------------------------------------------------------

SYMPTOM_KEYWORDS = [
    "fever", "pain", "headache", "cough", "cold",
    "nausea", "vomit", "diarrhea", "rash", "itch",
    "sore throat", "fatigue", "tired", "dizzy", "dizziness",
    "breathless", "breathing", "swelling", "swollen", "bleeding",
    "stomach", "chest", "back", "runny nose", "congestion",
    "sneez", "weak", "weakness", "burn", "blister", "infection",
    "allerg", "anxious", "anxiety", "depress", "insomnia",
    "constipat", "bloat", "cramp", "muscle", "joint",
    "hurt", "ache", "sick", "sickness", "discharge", "vomiting",
    "symptom", "medicine", "medication", "drug", "dose",
    "tablet", "pill", "treatment", "remedy", "cure", "heal",
    "otc", "over the counter", "pharmacy", "prescription",
    "unconscious", "seizure", "choking", "poison", "emergency",
    "collapsed", "heart attack", "stroke", "bleeding profusely",
    "can't breathe", "difficulty breathing", "chest pain",
]

EMERGENCY_KEYWORDS = [
    "collapsed", "not waking up", "unconscious", "chest pain", "can't breathe",
    "difficulty breathing", "heart attack", "stroke", "seizure", "choking",
    "poison", "severe bleeding", "bleeding profusely", "suicide", "kill myself",
]

def is_emergency(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in EMERGENCY_KEYWORDS)

GREETING_WORDS = {
    "hi", "hello", "hey", "good morning", "good evening",
    "howdy", "greetings", "good afternoon", "good day",
}


def is_symptom(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in SYMPTOM_KEYWORDS)


def is_greeting(text: str) -> bool:
    stripped = re.sub(r"[^\w\s]", "", text.lower()).strip()
    return stripped in GREETING_WORDS


# ---------------------------------------------------------------------------
# RAG retrieval
# ---------------------------------------------------------------------------

def _get_rag_context(query: str) -> tuple[str, list[str]]:
    """Embed query, retrieve top-3 chunks, return (context, source_names)."""
    load_models()
    embedding = embedding_model.encode(f"symptom treatment: {query}").tolist()
    results = collection.query(query_embeddings=[embedding], n_results=3)

    docs = results["documents"][0]
    metas = results.get("metadatas", [[]])[0] or []
    context = "\n\n".join(docs[:3])

    seen: set[str] = set()
    source_names: list[str] = []
    for m in metas:
        if isinstance(m, dict):
            name = m.get("source", "unknown")
            if name not in seen:
                seen.add(name)
                source_names.append(name)
    if not source_names:
        source_names = ["unknown"]

    return context, source_names


# ---------------------------------------------------------------------------
# History conversion: DB rows → Ollama message dicts
# ---------------------------------------------------------------------------

def _db_history_to_ollama(chat_history: list[dict]) -> list[dict]:
    """Convert [{sender, content}] from the DB to [{role, content}] for Ollama.

    Trims to MAX_HISTORY messages so the prompt stays small.
    """
    tail = chat_history[-MAX_HISTORY:]
    messages = []
    for msg in tail:
        role = "user" if msg.get("sender") == "user" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    return messages


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def ask_question_rag(
    question: str,
    conversation_id: int,
    chat_history: list[dict] | None = None,
) -> str:
    """History-aware unified conversation handler.

    Parameters
    ----------
    question      : raw question from the /ask endpoint (may contain profile
                    preamble injected by main.py).
    conversation_id : not used for routing anymore — kept for API compat.
    chat_history  : list of {sender: 'user'|'bot', content: str} rows from the
                    DB, ordered oldest-first, NOT including the current message.
    """
    if chat_history is None:
        chat_history = []

    # ── Strip the health-profile preamble that main.py prepends ────────────
    profile_context = ""
    clean_question = question
    if "User Question:" in question:
        parts = question.split("User Question:", 1)
        profile_context = parts[0].strip()
        clean_question = parts[1].strip()
    elif "user question:" in question.lower():
        idx = question.lower().index("user question:")
        profile_context = question[:idx].strip()
        clean_question = question[idx + len("user question:"):].strip()

    # ── Build Ollama history from DB rows ───────────────────────────────────
    history_messages = _db_history_to_ollama(chat_history)

    # ── Greeting with no prior context → static welcome ─────────────────────
    if not chat_history and is_greeting(clean_question):
        return (
            "Hello! I'm Health Assist — your AI medical assistant. 👋\n\n"
            "I can help you with:\n"
            "• Symptom assessment and safe OTC medication advice\n"
            "• General health questions\n"
            "• Anything else you'd like to chat about\n\n"
            "How can I help you today?"
        )

    # ── Decide whether this conversation is medical ──────────────────────────
    # A follow-up like "what should I take?" is medical if any recent user
    # message contained a symptom — checking history handles this correctly.
    recent_user_msgs = [m["content"] for m in chat_history if m.get("sender") == "user"]
    is_medical = is_symptom(clean_question) or any(is_symptom(m) for m in recent_user_msgs)

    if is_medical:
        # Pick the best RAG query: the most recent symptom-containing user
        # message (likely where the actual symptom was first described).
        rag_query = clean_question
        for msg in reversed(chat_history):
            if msg.get("sender") == "user" and is_symptom(msg["content"]):
                rag_query = msg["content"]
                break

        context, source_names = _get_rag_context(rag_query)

        profile_section = (
            f"\nUser Health Profile (use when relevant):\n{profile_context}\n"
            if profile_context else ""
        )

        system_prompt = (
            "You are Health Assist, an OTC health assistant with memory of the full conversation.\n"
            "Use the Medical Reference below to ground your answers.\n"
            "RULES:\n"
            "- Recommended safe OTC medications and self-care only (no prescriptions, no diagnoses)\n"
            "- If the user asks a follow-up ('what should I take?', 'is that safe?'), "
            "look at the conversation history and answer in full context\n"
            "- If the symptom is still unclear, ask 1-2 short clarifying questions\n"
            "- Keep responses concise: max 4 bullet points or ~100 words\n"
            "- EMERGENCY PROTOCOL: If the user describes life-threatening symptoms (chest pain, difficulty breathing, severe bleeding, unconsciousness, etc.), "
            "you MUST start your response with: '⚠️ EMERGENCY: PLEASE CALL 112 OR 102 IMMEDIATELY.' before saying anything else.\n"
            f"{profile_section}\n"
            f"Medical Reference:\n{context}"
        )

        # Full prompt = [system] + [history] + [current user message]
        ollama_messages = (
            [{"role": "system", "content": system_prompt}]
            + history_messages
            + [{"role": "user", "content": clean_question}]
        )

        response = _call_ollama(ollama_messages)
        
        # ── Force Emergency Warning if detected ────────────────────────────
        if is_emergency(clean_question):
            warning = "⚠️ EMERGENCY: PLEASE CALL 112 OR 102 IMMEDIATELY.\n\n"
            if not response.strip().startswith("⚠️"):
                response = warning + response

        source_text = " | ".join(f"📄 {n}" for n in source_names)
        return f"{response}\n\n─────────────────\n📚 Sources: {source_text}"

    # ── General / conversational ─────────────────────────────────────────────
    profile_section = (
        f"\nUser context:\n{profile_context}\n" if profile_context else ""
    )
    system_prompt = (
        "You are Health Assist, a highly capable and friendly AI assistant.\n"
        "While your specialty is health, you are also a versatile AI like GPT. You can help with writing, coding, math, general knowledge, or just casual chat.\n"
        "You remember the entire conversation history to provide natural, context-aware responses.\n"
        "RULES:\n"
        "- Be helpful, professional, and friendly.\n"
        "- Do not mention health or symptoms unless the user brings it up first.\n"
        "- Keep responses natural and well-structured.\n"
        f"{profile_section}"
    )

    ollama_messages = (
        [{"role": "system", "content": system_prompt}]
        + history_messages
        + [{"role": "user", "content": clean_question}]
    )

    return _call_ollama(ollama_messages)


# ---------------------------------------------------------------------------
# PDF ingestion (admin upload)
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    text = re.sub(r'\[\d+(,\s*\d+)*\]', '', text)
    text = re.sub(r'http\S+|www\.\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _get_overlapped_chunks(text: str, chunksize: int = 1000, overlapsize: int = 100) -> list[str]:
    return [
        text[i:i + chunksize]
        for i in range(0, len(text), chunksize - overlapsize)
    ]


def ingest_pdf(pdf_bytes: bytes, source_name: str) -> int:
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]

    cleaned = _clean_text("\n".join(pages))
    chunks = _get_overlapped_chunks(cleaned)

    if not chunks:
        raise ValueError("PDF contained no extractable text.")

    load_models()
    embeddings = embedding_model.encode(chunks)

    ids = [f"{source_name}_chunk_{i}" for i in range(len(chunks))]
    collection.upsert(
        documents=chunks,
        embeddings=embeddings.tolist(),
        ids=ids,
        metadatas=[{"source": source_name}] * len(chunks),
    )
    return len(chunks)


def delete_pdf(source_name: str):
    """Delete all chunks belonging to a specific source from ChromaDB."""
    collection.delete(where={"source": source_name})