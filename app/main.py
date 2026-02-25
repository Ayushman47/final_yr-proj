import json
import os
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from app.rag import ask_question_rag, conversation_memory
from app.auth import router as auth_router, get_current_user

# -------------------------
# App Setup
# -------------------------
app = FastAPI()

app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Notes File Path
# -------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
notes_path = os.path.join(BASE_DIR, "user_notes.json")

if not os.path.exists(notes_path):
    with open(notes_path, "w") as f:
        json.dump({"medications": []}, f)

# -------------------------
# Request Models
# -------------------------
class QuestionRequest(BaseModel):
    question: str

class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str

# -------------------------
# RAG Endpoint (Protected)
# -------------------------
@app.post("/ask")
def ask_question(
    request: QuestionRequest,
    user: str = Depends(get_current_user)
):
    answer = ask_question_rag(request.question, user)
    return {"answer": answer}

# -------------------------
# Clear Conversation Memory
# -------------------------
@app.post("/clear-memory")
def clear_memory(user: str = Depends(get_current_user)):
    if user in conversation_memory:
        conversation_memory[user] = []
    return {"message": "Memory cleared"}

# -------------------------
# Add Medication (Protected)
# -------------------------
@app.post("/add-medication")
def add_medication(
    med: Medication,
    user: str = Depends(get_current_user)
):
    with open(notes_path, "r") as f:
        data = json.load(f)

    data["medications"].append(med.dict())

    with open(notes_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"message": "Medication added successfully"}

# -------------------------
# Get Medications (Protected)
# -------------------------
@app.get("/medications")
def get_medications(user: str = Depends(get_current_user)):
    with open(notes_path, "r") as f:
        data = json.load(f)

    return data

# -------------------------
# Delete Medication (Protected)
# -------------------------
@app.delete("/medication/{name}")
def delete_medication(
    name: str,
    user: str = Depends(get_current_user)
):
    with open(notes_path, "r") as f:
        data = json.load(f)

    data["medications"] = [
        med for med in data["medications"] if med["name"] != name
    ]

    with open(notes_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"message": "Medication removed"}