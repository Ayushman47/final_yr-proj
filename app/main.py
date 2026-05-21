from datetime import datetime
import os
import sys
import sqlite3
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.rag_service import ask_question_rag
from app.retrieval_service import ingest_pdf_pymupdf as ingest_pdf, delete_pdf
from app.nearby import is_doctor_search_intent, find_nearby_doctors
from app.auth import router as auth_router, get_current_user, get_current_admin_user, get_current_super_admin_user, User
from app.database import init_db, get_db
from app.updater import updater

def get_bundle_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="Health Assist API", version="2.0.0")
app.include_router(auth_router)

# Mount static files folder
app.mount("/static", StaticFiles(directory=os.path.join(get_bundle_dir(), "app", "static")), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PUT"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    init_db()
    
    # Generate default otc-il.pdf if it doesn't exist
    static_dir = os.path.join(get_bundle_dir(), "app", "static")
    os.makedirs(static_dir, exist_ok=True)
    default_pdf_path = os.path.join(static_dir, "otc-il.pdf")
    
    if not os.path.exists(default_pdf_path):
        try:
            import fitz
            doc = fitz.open()
            page = doc.new_page()
            
            otc_text = """OTC Medication Reference Guide (otc-il.pdf)
==============================================
This document contains standard Over-The-Counter (OTC) medication reference guidelines for common health conditions.

1. FEVER & PAIN RELIEF (Analgesics & Antipyretics)
- Acetaminophen (Tylenol/Paracetamol): Used for mild to moderate pain relief and reducing fever. Typical adult dosage is 325mg to 650mg every 4 to 6 hours as needed. Do not exceed 3,000mg in 24 hours. High doses can cause severe liver damage.
- Ibuprofen (Advil/Motrin): Non-steroidal anti-inflammatory drug (NSAID) used for pain, fever, and inflammation. Typical adult dosage is 200mg to 400mg every 4 to 6 hours. Do not exceed 1,200mg in 24 hours. Take with food to avoid stomach irritation.

2. COUGH, COLD & DECONGESTANTS
- Dextromethorphan: Cough suppressant used for temporary relief of dry, non-productive coughs. Typical dosage is 10mg to 20mg every 4 hours.
- Guaifenesin (Mucinex): Expectorant used to help thin and loosen mucus in the chest. Typical dosage is 200mg to 400mg every 4 hours. Drink plenty of water.
- Pseudoephedrine (Sudafed): Nasal decongestant. Reduces swelling in nasal passages. May cause alertness or insomnia.

3. ALLERGIES & ANTIHISTAMINES
- Cetirizine (Zyrtec): Second-generation antihistamine used for seasonal allergies, hives, and runny nose. Adult dosage is 10mg once daily. Non-drowsy for most people.
- Diphenhydramine (Benadryl): First-generation antihistamine used for allergic reactions and sleep aid. Dosage is 25mg to 50mg every 6 hours. May cause significant drowsiness.

4. DIGESTIVE AID
- Loperamide (Imodium): Used to treat acute diarrhea. Initial dose is 4mg, followed by 2mg after each loose stool. Do not exceed 8mg per day for OTC use.
- Famotidine (Pepcid): H2 blocker used to prevent and relieve heartburn or acid indigestion. Dosage is 10mg to 20mg once or twice daily.
"""
            page.insert_text((50, 50), otc_text, fontsize=10)
            doc.save(default_pdf_path)
            doc.close()
            print("Generated default otc-il.pdf successfully.")
        except Exception as e:
            print(f"Error generating default PDF: {e}")

    # Ingest default PDF if database is empty
    from app.database import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM documents")
    doc_count = cursor.fetchone()["count"]
    if doc_count == 0 and os.path.exists(default_pdf_path):
        try:
            with open(default_pdf_path, "rb") as f:
                pdf_bytes = f.read()
            
            # Find an admin user to assign as uploader
            cursor.execute("SELECT id FROM users WHERE is_admin = 1 LIMIT 1")
            admin = cursor.fetchone()
            admin_id = admin["id"] if admin else 1
            
            from app.retrieval_service import ingest_pdf_pymupdf
            chunk_count = ingest_pdf_pymupdf(pdf_bytes, "otc-il.pdf")
            
            cursor.execute("""
                INSERT INTO documents (filename, uploaded_by, chunk_count)
                VALUES (?, ?, ?)
            """, ("otc-il.pdf", admin_id, chunk_count))
            conn.commit()
            print("Successfully ingested default otc-il.pdf on startup.")
        except Exception as e:
            print(f"Error ingesting default PDF on startup: {e}")
            
    # Sync database documents with vector store on start
    from app.retrieval_service import collection
    try:
        results = collection.get(include=["metadatas"])
        metas = results.get("metadatas", [])
        sources = set()
        for m in metas:
            if m and "source" in m:
                sources.add(m["source"])
        
        if sources:
            cursor.execute("SELECT id FROM users WHERE is_admin = 1 LIMIT 1")
            admin = cursor.fetchone()
            admin_id = admin["id"] if admin else 1
            
            for src in sources:
                cursor.execute("SELECT id FROM documents WHERE filename = ?", (src,))
                if not cursor.fetchone():
                    count = sum(1 for m in metas if m.get("source") == src)
                    cursor.execute("""
                        INSERT INTO documents (filename, uploaded_by, chunk_count)
                        VALUES (?, ?, ?)
                    """, (src, admin_id, count))
            conn.commit()
    except Exception as e:
        print(f"Startup sync error: {e}")
    finally:
        conn.close()

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
    return {"id": user.id, "username": user.username, "is_admin": user.is_admin}

@app.post("/admin/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    
    # Check max file size (10MB)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")

    # Strict MIME type check using PDF header signature
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="Invalid file format. Only genuine PDF files are allowed.")

    try:
        chunk_count = ingest_pdf(content, file.filename)
        
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
    body: dict,
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
    cursor = db.cursor()
    cursor.execute("SELECT filename FROM documents WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    
    filename = row["filename"]
    
    try:
        delete_pdf(filename)
        cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        db.commit()
        return {"message": f"Deleted {filename}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/superadmin/users")
async def sa_list_users(
    sadmin: User = Depends(get_current_super_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT id, username, is_admin, is_super_admin, created_at FROM users")
    return {"users": [dict(row) for row in cursor.fetchall()]}

class RoleUpdateRequest(BaseModel):
    is_admin: bool

@app.post("/superadmin/users/{user_id}/role")
async def sa_update_user_role(
    user_id: int,
    body: RoleUpdateRequest,
    sadmin: User = Depends(get_current_super_admin_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT is_super_admin FROM users WHERE id = ?", (user_id,))
    target_user = cursor.fetchone()
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if target_user["is_super_admin"] and sadmin.id == user_id and not body.is_admin:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    
    cursor.execute("UPDATE users SET is_admin = ? WHERE id = ?", (int(body.is_admin), user_id))
    db.commit()
    return {"message": "Role updated successfully"}

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
    cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user.id))
    if not cursor.fetchone():
        raise HTTPException(status_code=403, detail="Not authorized to delete this conversation")

    try:
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        db.commit()
        return {"message": "Conversation deleted"}
    except Exception as e:
        db.rollback()
        print(f"Error deleting conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not delete conversation")

@app.post("/ask")
def ask_question(
    request: QuestionRequest,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM conversations WHERE id = ? AND user_id = ?", (request.conversation_id, user.id))
    if not cursor.fetchone():
        raise HTTPException(status_code=403, detail="Unauthorized access to this conversation")

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
        history = [dict(r) for r in rows[:-1]]

        enhanced_question = profile_context + "\nUser Question:\n" + question
        answer = ask_question_rag(enhanced_question, request.conversation_id, history)

    # Update title on first interaction
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

@app.get("/messages/{conversation_id}")
def get_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
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

@app.post("/find-doctors")
def find_doctors(
    request: DoctorSearchRequest,
    user: User = Depends(get_current_user)
):
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

@app.get("/api/setup-info")
def api_setup_info(user: User = Depends(get_current_user)):
    from app.model_profile_service import get_recommended_tier
    import psutil
    ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    recommended = get_recommended_tier()
    return {"ram_gb": ram_gb, "recommended_tier": recommended}

@app.get("/api/update/check")
async def check_update(user: User = Depends(get_current_user)):
    return updater.check_for_update()

@app.post("/api/update/download")
async def download_update(user: User = Depends(get_current_user)):
    if not updater.update_info or not updater.update_info.get("download_url"):
        updater.check_for_update()
    
    if updater.update_info and updater.update_info.get("download_url"):
        success = updater.start_download(updater.update_info["download_url"])
        return {"success": success, "message": "Download started" if success else "Already downloading"}
    
    raise HTTPException(status_code=404, detail="No update available to download")

@app.get("/api/update/progress")
async def get_update_progress(user: User = Depends(get_current_user)):
    return {
        "progress": updater.download_progress,
        "is_downloading": updater.is_downloading,
        "status": "error" if updater.download_progress == -1 else "success"
    }

@app.post("/api/update/apply")
async def apply_update(user: User = Depends(get_current_user)):
    success = updater.apply_update()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to launch update installer")
    return {"message": "Update started"}