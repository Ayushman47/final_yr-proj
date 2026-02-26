print("NOTES ROUTE SHOULD EXIST")

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

class HealthProfile(BaseModel):
    allergies: str = ""
    conditions: str = ""
    age: int | None = None

# -------------------------
# Conversations
# -------------------------
@app.post("/conversations")
def create_conversation(user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    user_row = cursor.fetchone()

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

    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    user_row = cursor.fetchone()

    cursor.execute("""
        SELECT allergies, conditions, age
        FROM health_profiles
        WHERE user_id = ?
    """, (user_row["id"],))

    profile = cursor.fetchone()

    profile_context = ""
    if profile:
        profile_context = f"""
User Health Profile:
Allergies: {profile['allergies']}
Medical Conditions: {profile['conditions']}
Age: {profile['age']}
"""

    enhanced_question = profile_context + "\nUser Question:\n" + request.question
    answer = ask_question_rag(enhanced_question, user)

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
# Messages
# -------------------------
@app.get("/messages/{conversation_id}")
def get_messages(conversation_id: int, user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT conversations.id
        FROM conversations
        JOIN users ON conversations.user_id = users.id
        WHERE conversations.id = ? AND users.username = ?
    """, (conversation_id, user))

    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Conversation not found")

    cursor.execute("""
        SELECT sender, content, timestamp
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))

    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {"messages": messages}

# -------------------------
# Medications
# -------------------------
@app.post("/add-medication")
def add_medication(med: Medication, user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    user_row = cursor.fetchone()

    cursor.execute("""
        INSERT INTO medications (user_id, name, dosage, frequency)
        VALUES (?, ?, ?, ?)
    """, (
        user_row["id"],
        med.name,
        med.dosage,
        med.frequency
    ))

    conn.commit()
    conn.close()

    return {"message": "Medication added successfully"}

@app.get("/medications")
def get_medications(user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    user_row = cursor.fetchone()

    cursor.execute("""
        SELECT name, dosage, frequency
        FROM medications
        WHERE user_id = ?
    """, (user_row["id"],))

    meds = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return {"medications": meds}

@app.delete("/medication/{name}")
def delete_medication(name: str, user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    user_row = cursor.fetchone()

    cursor.execute("""
        DELETE FROM medications
        WHERE user_id = ? AND name = ?
    """, (user_row["id"], name))

    conn.commit()
    conn.close()

    return {"message": "Medication removed"}

# -------------------------
# Health Profile
# -------------------------
@app.post("/update-profile")
def update_profile(profile: HealthProfile, user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    user_row = cursor.fetchone()

    cursor.execute("SELECT id FROM health_profiles WHERE user_id = ?", (user_row["id"],))
    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE health_profiles
            SET allergies = ?, conditions = ?, age = ?
            WHERE user_id = ?
        """, (
            profile.allergies,
            profile.conditions,
            profile.age,
            user_row["id"]
        ))
    else:
        cursor.execute("""
            INSERT INTO health_profiles (user_id, allergies, conditions, age)
            VALUES (?, ?, ?, ?)
        """, (
            user_row["id"],
            profile.allergies,
            profile.conditions,
            profile.age
        ))

    conn.commit()
    conn.close()

    return {"message": "Profile updated successfully"}

@app.get("/profile")
def get_profile(user: str = Depends(get_current_user)):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (user,))
    user_row = cursor.fetchone()

    cursor.execute("""
        SELECT allergies, conditions, age
        FROM health_profiles
        WHERE user_id = ?
    """, (user_row["id"],))

    profile = cursor.fetchone()
    conn.close()

    if profile:
        return dict(profile)

    return {"allergies": "", "conditions": "", "age": None}