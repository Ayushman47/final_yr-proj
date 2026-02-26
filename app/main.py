print("NOTES ROUTE SHOULD EXIST")

import json
import os
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.rag import ask_question_rag
from app.auth import router as auth_router, get_current_user
from app.database import init_db, get_connection

# -------------------------
# Initialize DB
# -------------------------
init_db()

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
# Templates
# -------------------------
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/index", response_class=HTMLResponse)
async def index_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request):
    return templates.TemplateResponse("notes.html", {"request": request})

# -------------------------
# Models
# -------------------------
class QuestionRequest(BaseModel):
    question: str
    conversation_id: int

class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str

# -------------------------
# Create New Conversation
# -------------------------
@app.post("/conversations")
def create_conversation(user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM users WHERE username = ?",
        (user,)
    )
    user_row = cursor.fetchone()

    if not user_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")

    cursor.execute(
        "INSERT INTO conversations (user_id, created_at) VALUES (?, ?)",
        (user_row["id"], datetime.utcnow().isoformat())
    )

    conn.commit()
    conversation_id = cursor.lastrowid
    conn.close()

    return {"conversation_id": conversation_id}

# -------------------------
# Ask
# -------------------------
@app.post("/ask")
def ask_question(request: QuestionRequest, user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO messages (conversation_id, sender, content, timestamp)
        VALUES (?, ?, ?, ?)
    """, (
        request.conversation_id,
        "user",
        request.question,
        datetime.utcnow().isoformat()
    ))

    answer = ask_question_rag(request.question, user)

    cursor.execute("""
        INSERT INTO messages (conversation_id, sender, content, timestamp)
        VALUES (?, ?, ?, ?)
    """, (
        request.conversation_id,
        "bot",
        answer,
        datetime.utcnow().isoformat()
    ))

    conn.commit()
    conn.close()

    return {"answer": answer}

# -------------------------
# Medications
# -------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
notes_path = os.path.join(BASE_DIR, "user_notes.json")

if not os.path.exists(notes_path):
    with open(notes_path, "w") as f:
        json.dump({"medications": []}, f)

@app.post("/add-medication")
def add_medication(med: Medication, user: str = Depends(get_current_user)):
    with open(notes_path, "r") as f:
        data = json.load(f)

    data["medications"].append(med.dict())

    with open(notes_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"message": "Medication added successfully"}

@app.get("/medications")
def get_medications(user: str = Depends(get_current_user)):
    with open(notes_path, "r") as f:
        data = json.load(f)

    return data

@app.delete("/medication/{name}")
def delete_medication(name: str, user: str = Depends(get_current_user)):
    with open(notes_path, "r") as f:
        data = json.load(f)

    data["medications"] = [
        med for med in data["medications"] if med["name"] != name
    ]

    with open(notes_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"message": "Medication removed"}