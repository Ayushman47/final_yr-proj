from datetime import datetime
import os
import sys
import sqlite3
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.rag import ask_question_rag, ingest_pdf, delete_pdf
from app.nearby import is_doctor_search_intent, find_nearby_doctors
from app.auth import router as auth_router, get_current_user, get_current_admin_user, User
from app.database import init_db, get_db


def get_bundle_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# -------------------------
# Initialize DB
# -------------------------
app = FastAPI(title="Health Assist API", version="2.0.0")
app.include_router(auth_router)

# Restrict CORS to local development or specified origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, this should be specific origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["*"],
)

# -------------------------
# Initialize DB & Sync
# -------------------------
@app.on_event("startup")
async def startup_event():
    init_db()
    
    # Sync existing PDFs from ChromaDB to SQLite if they are missing
    from app.rag import collection
    from app.database import get_connection
    
    try:
        results = collection.get(include=["metadatas"])
        metas = results.get("metadatas", [])
        sources = set()
        for m in metas:
            if m and "source" in m:
                sources.add(m["source"])
        
        if sources:
            conn = get_connection()
            cursor = conn.cursor()
            # Get admin user ID (first admin)
            cursor.execute("SELECT id FROM users WHERE is_admin = 1 LIMIT 1")
            admin = cursor.fetchone()
            admin_id = admin["id"] if admin else 1
            
            for src in sources:
                cursor.execute("SELECT id FROM documents WHERE filename = ?", (src,))
                if not cursor.fetchone():
                    # Count chunks for this source
                    count = sum(1 for m in metas if m.get("source") == src)
                    cursor.execute("""
                        INSERT INTO documents (filename, uploaded_by, chunk_count)
                        VALUES (?, ?, ?)
                    """, (src, admin_id, count))
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Startup sync error: {e}")


templates = Jinja2Templates(directory=os.path.join(get_bundle_dir(), "app", "templates"))


@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"request": request})


@app.get("/index", response_class=HTMLResponse)
async def index_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request})


@app.get("/notes", response_class=HTMLResponse)
async def notes_page(request: Request):
    return templates.TemplateResponse(request=request, name="notes.html", context={"request": request})


# -------------------------
# Models
# -------------------------
class QuestionRequest(BaseModel):
    question: str
    conversation_id: int
    lat: float | None = None
    lon: float | None = None


class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str


class HealthProfile(BaseModel):
    allergies: str = ""
    conditions: str = ""
    age: int | None = None


class DoctorSearchRequest(BaseModel):
    lat: float
    lon: float


@app.get("/me")
def get_me(user: User = Depends(get_current_user)):
    """Returns basic user info, including admin status."""
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}


# -------------------------
# Admin Features
# -------------------------

@app.post("/admin/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    """Secure endpoint for admins to ingest medical reference PDFs."""
    # Security: File validation
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    
    # Check file size (max 10MB)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # Basic PDF magic number check
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF file format")

    try:
        chunk_count = ingest_pdf(content, file.filename)
        
        # Record in database
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO documents (filename, uploaded_by, chunk_count)
            VALUES (?, ?, ?)
        """, (file.filename, admin.id, chunk_count))
        db.commit()
        
        return {"message": f"Ingested {file.filename} ({chunk_count} chunks)"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Admin Routes
# -------------------------

@app.get("/admin/stats")
async def get_admin_stats(
    admin: User = Depends(get_current_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count, SUM(chunk_count) as chunks FROM documents")
    doc_data = cursor.fetchone()
    
    # Simple storage estimate
    from app.database import DB_PATH
    storage_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
    
    return {
        "users": user_count,
        "documents": doc_data["count"] or 0,
        "total_chunks": doc_data["chunks"] or 0,
        "db_size_mb": round(storage_mb, 2)
    }

@app.get("/admin/users")
async def list_users(
    admin: User = Depends(get_current_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT id, username, is_admin, created_at FROM users")
    return {"users": [dict(row) for row in cursor.fetchall()]}

@app.post("/admin/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    body: dict, # {"new_password": "..."}
    admin: User = Depends(get_current_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    from app.auth import hash_password
    new_pwd = body.get("new_password")
    if not new_pwd:
        raise HTTPException(status_code=400, detail="New password required")
        
    cursor = db.cursor()
    cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hash_password(new_pwd), user_id))
    db.commit()
    return {"message": "Password reset successfully"}

@app.get("/admin/documents")
async def list_documents(
    admin: User = Depends(get_current_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    """List all uploaded PDF documents."""
    cursor = db.cursor()
    cursor.execute("""
        SELECT d.id, d.filename, d.chunk_count, d.created_at, u.username as uploader
        FROM documents d
        JOIN users u ON d.uploaded_by = u.id
        ORDER BY d.created_at DESC
    """)
    rows = cursor.fetchall()
    return {"documents": [dict(row) for row in rows]}


@app.delete("/admin/documents/{doc_id}")
def delete_document(
    doc_id: int,
    admin: User = Depends(get_current_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    """Delete a document from both SQLite and ChromaDB."""
    cursor = db.cursor()
    
    # Get filename first
    cursor.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    
    filename = row["filename"]
    
    try:
        # Delete from ChromaDB
        delete_pdf(filename)
        
        # Delete from SQLite
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        db.commit()
        return {"message": f"Deleted {filename}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# Conversations
# -------------------------

@app.post("/conversations")
def create_conversation(
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO conversations (user_id, created_at) VALUES (?, ?)",
            (user.id, datetime.utcnow().isoformat())
        )
        db.commit()
        conversation_id = cursor.lastrowid
        return {"conversation_id": conversation_id}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create conversation")


@app.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("""
        SELECT id, title, created_at
        FROM conversations
        WHERE user_id = ?
        ORDER BY id DESC
    """, (user.id,))
    rows = cursor.fetchall()
    return {"conversations": [dict(r) for r in rows]}


@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    
    # Ownership check
    cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user.id))
    if not cursor.fetchone():
        raise HTTPException(status_code=403, detail="Not authorized to delete this conversation")

    try:
        # Cascading deletes are handled by SQLite foreign keys (if configured)
        # or we do them manually for safety.
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        db.commit()
        return {"message": "Conversation deleted"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not delete conversation")


# -------------------------
# Ask
# -------------------------

@app.post("/ask")
def ask_question(
    request: QuestionRequest,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()

    # Ownership check
    cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (request.conversation_id, user.id))
    if not cursor.fetchone():
        raise HTTPException(status_code=403, detail="Unauthorized access to this conversation")

    # Sanitize input (basic)
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    cursor.execute("""
        INSERT INTO messages (conversation_id, sender, content, timestamp)
        VALUES (?, ?, ?, ?)
    """, (
        request.conversation_id,
        "user",
        question,
        datetime.utcnow().isoformat()
    ))

    cursor.execute("""
        SELECT allergies, conditions, age
        FROM health_profiles
        WHERE user_id = ?
    """, (user.id,))
    profile = cursor.fetchone()

    profile_context = ""
    if profile:
        profile_context = f"""
User Health Profile:
Allergies: {profile['allergies']}
Medical Conditions: {profile['conditions']}
Age: {profile['age']}
"""

    if is_doctor_search_intent(question):
        answer = "You can find nearby doctors using the 'Find Doctors' option in your Health Dashboard."
    else:
        cursor.execute("""
            SELECT sender, content FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
        """, (request.conversation_id,))
        rows = cursor.fetchall()
        # Exclude the current message we just added
        history = [dict(r) for r in rows[:-1]]

        enhanced_question = profile_context + "\nUser Question:\n" + question
        answer = ask_question_rag(enhanced_question, request.conversation_id, history)

    # Update conversation title if it's the first message
    cursor.execute("SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?", (request.conversation_id,))
    msg_count = cursor.fetchone()["count"]
    if msg_count <= 2:
        short_title = question[:40] + ("..." if len(question) > 40 else "")
        cursor.execute("UPDATE conversations SET title = ? WHERE id = ?", (short_title, request.conversation_id))
    
    cursor.execute("""
        INSERT INTO messages (conversation_id, sender, content, timestamp)
        VALUES (?, ?, ?, ?)
    """, (
        request.conversation_id,
        "bot",
        answer,
        datetime.utcnow().isoformat()
    ))

    db.commit()
    return {"answer": answer, "type": "chat"}


# -------------------------
# Messages
# -------------------------

@app.get("/messages/{conversation_id}")
def get_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()

    # Ownership check
    cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user.id))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Conversation not found")

    cursor.execute("""
        SELECT sender, content, timestamp
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))

    messages = [dict(row) for row in cursor.fetchall()]
    return {"messages": messages}


# -------------------------
# Medications
# -------------------------

@app.post("/add-medication")
def add_medication(
    med: Medication,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO medications (user_id, name, dosage, frequency)
            VALUES (?, ?, ?, ?)
        """, (user.id, med.name, med.dosage, med.frequency))
        db.commit()
        return {"message": "Medication added successfully"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not add medication")


@app.get("/medications")
def get_medications(
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("""
        SELECT name, dosage, frequency
        FROM medications
        WHERE user_id = ?
    """, (user.id,))
    meds = [dict(row) for row in cursor.fetchall()]
    return {"medications": meds}


@app.delete("/medication/{name}")
def delete_medication(
    name: str,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    # Check if exists and belongs to user
    cursor.execute("SELECT id FROM medications WHERE user_id = ? AND name = ?", (user.id, name))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Medication not found")

    try:
        cursor.execute("DELETE FROM medications WHERE user_id = ? AND name = ?", (user.id, name))
        db.commit()
        return {"message": "Medication removed"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not remove medication")


# -------------------------
# Health Profile
# -------------------------

@app.post("/update-profile")
def update_profile(
    profile: HealthProfile,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()

    cursor.execute("SELECT id FROM health_profiles WHERE user_id = ?", (user.id,))
    existing = cursor.fetchone()

    try:
        if existing:
            cursor.execute("""
                UPDATE health_profiles
                SET allergies = ?, conditions = ?, age = ?
                WHERE user_id = ?
            """, (profile.allergies, profile.conditions, profile.age, user.id))
        else:
            cursor.execute("""
                INSERT INTO health_profiles (user_id, allergies, conditions, age)
                VALUES (?, ?, ?, ?)
            """, (user.id, profile.allergies, profile.conditions, profile.age))
        db.commit()
        return {"message": "Profile updated successfully"}
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not update profile")


@app.get("/profile")
def get_profile(
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("""
        SELECT allergies, conditions, age
        FROM health_profiles
        WHERE user_id = ?
    """, (user.id,))
    profile = cursor.fetchone()

    if profile:
        return dict(profile)
    return {"allergies": "", "conditions": "", "age": None}


# -------------------------
# Doctor Finder
# -------------------------

@app.post("/find-doctors")
def find_doctors(
    request: DoctorSearchRequest,
    user: User = Depends(get_current_user)
):
    # This feature relies on external API (Nominatim), so it's less critical for ownership
    # but still protected by auth.
    results = find_nearby_doctors(request.lat, request.lon, "doctor hospital clinic")

    if not results:
        return {
            "type": "doctor_results",
            "results": [],
            "message": "No results found or internet connection missing."
        }

    normalized = []
    for item in results:
        normalized.append({
            "name": item.get("name", "Unknown"),
            "address": item.get("address", "Address unavailable"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "maps_url": item.get("maps_url"),
        })

    return {"type": "doctor_results", "results": normalized[:5]}

# -------------------------
# Models Management
# -------------------------
from app.model_manager import (
    get_installed_models, delete_model, get_active_model, set_active_model,
    start_pull_model, get_pull_progress, cancel_pull_model
)

class PullModelRequest(BaseModel):
    model: str

class SelectModelRequest(BaseModel):
    model: str

@app.get("/api/models")
def api_get_models(user: User = Depends(get_current_user)):
    models = get_installed_models()
    active = get_active_model()
    return {"models": models, "active": active}

@app.post("/api/models/pull")
def api_pull_model(req: PullModelRequest, user: User = Depends(get_current_user)):
    success = start_pull_model(req.model)
    if not success:
        raise HTTPException(status_code=400, detail="A model is already downloading.")
    return {"message": "Download started"}

@app.get("/api/models/progress")
def api_pull_progress(user: User = Depends(get_current_user)):
    return get_pull_progress()

@app.post("/api/models/cancel")
def api_cancel_pull(user: User = Depends(get_current_user)):
    cancel_pull_model()
    return {"message": "Download cancelled"}

@app.delete("/api/models/{model_name}")
def api_delete_model(model_name: str, user: User = Depends(get_current_user)):
    success = delete_model(model_name)
    if success:
        return {"message": "Model deleted"}
    raise HTTPException(status_code=500, detail="Failed to delete model")

@app.post("/api/models/active")
def api_set_active_model(req: SelectModelRequest, user: User = Depends(get_current_user)):
    set_active_model(req.model)
    return {"message": "Active model updated", "active": req.model}
