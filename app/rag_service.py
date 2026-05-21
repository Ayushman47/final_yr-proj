import requests
import re
from app.model_profile_service import get_tier_for_model, get_tier_settings
from app.prompt_service import build_system_prompt, build_general_prompt
from app.retrieval_service import retrieve_and_rerank

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

def _call_ollama(messages: list[dict], tier_settings: dict) -> str:
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
                    "temperature": tier_settings.get("temperature", 0.3),
                    "top_p": 0.9,
                    "num_predict": 400,
                },
            },
            timeout=90,
        )
        data = resp.json()
        if "error" in data or "message" not in data:
            return "Server error. Please try again."
        return data["message"]["content"]
    except requests.exceptions.ConnectionError:
        return "Service unavailable. Please ensure Ollama is running on port 11434."
    except requests.exceptions.Timeout:
        return "Request timed out. Please try again."
    except Exception:
        return "Server error. Please try again."

def ask_question_rag(question: str, conversation_id: int, chat_history: list[dict] | None = None) -> str:
    if chat_history is None:
        chat_history = []

    from app.model_manager import get_active_model
    active_model = get_active_model()
    tier = get_tier_for_model(active_model) if active_model else "Balanced"
    tier_settings = get_tier_settings(tier)

    # Split medical profile context if present
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

    # Get conversation history
    max_history = tier_settings["max_history"]
    tail = chat_history[-max_history:] if chat_history else []
    history_messages = [{"role": "user" if m.get("sender") == "user" else "assistant", "content": m["content"]} for m in tail]

    if not chat_history and is_greeting(clean_question):
        return (
            "Hello! I'm Health Assist — your AI medical assistant. 👋\n\n"
            "I can help you with:\n"
            "• Symptom assessment and safe OTC medication advice\n"
            "• General health questions\n"
            "• Anything else you'd like to chat about\n\n"
            "How can I help you today?"
        )

    recent_user_msgs = [m["content"] for m in chat_history if m.get("sender") == "user"]
    is_medical = is_symptom(clean_question) or any(is_symptom(m) for m in recent_user_msgs)

    if is_medical:
        rag_query = clean_question
        for msg in reversed(chat_history):
            if msg.get("sender") == "user" and is_symptom(msg["content"]):
                rag_query = msg["content"]
                break

        context, metas, confidence = retrieve_and_rerank(rag_query, tier)
        system_prompt = build_system_prompt(tier, profile_context, context)
        
        ollama_messages = [{"role": "system", "content": system_prompt}] + history_messages + [{"role": "user", "content": clean_question}]
        response = _call_ollama(ollama_messages, tier_settings)
        
        # Add warning for low confidence matches
        if confidence < 0.2 and context:
            response = "⚠️ I am not very confident in this response as my medical references are weak. Please consult a doctor.\n\n" + response
            
        if is_emergency(clean_question):
            warning = "⚠️ EMERGENCY: PLEASE CALL 112 OR 102 IMMEDIATELY.\n\n"
            if not response.strip().startswith("⚠️"):
                response = warning + response

        # Add reference sources
        seen_sources = set()
        citations = []
        for m in metas:
            name = m.get("source", "unknown")
            page = m.get("page", "?")
            key = f"{name} (Page {page})"
            if key not in seen_sources:
                seen_sources.add(key)
                citations.append(f"📄 {key}")
                
        if citations:
            source_text = " | ".join(citations)
            response += f"\n\n─────────────────\n📚 Sources: {source_text}"
            
        return response

    # Handle general queries
    system_prompt = build_general_prompt(tier, profile_context)
    ollama_messages = [{"role": "system", "content": system_prompt}] + history_messages + [{"role": "user", "content": clean_question}]
    return _call_ollama(ollama_messages, tier_settings)
