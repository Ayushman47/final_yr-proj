from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel
import os
import sqlite3

from app.database import get_db

# Load from environment variable — fallback only for local development
SECRET_KEY = os.getenv("SECRET_KEY", "DEVELOPMENT_SECRET_KEY_CHANGE_ME_IN_PRODUCTION")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 24 hours for a desktop app

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter()


# ---------------- MODELS ----------------

class User(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_super_admin: bool = False

class AuthRequest(BaseModel):
    username: str
    password: str
    admin_code: str | None = None


# ---------------- PASSWORD ----------------

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


# ---------------- TOKEN ----------------

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ---------------- SIGNUP ----------------

@router.post("/signup")
def signup(body: AuthRequest, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()

    cursor.execute("SELECT id FROM users WHERE username = ?", (body.username,))
    if cursor.fetchone():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already exists"
        )

    try:
        is_admin_flag = 0
        if body.admin_code:
            admin_signup_code = os.getenv("ADMIN_SIGNUP_CODE")
            if not admin_signup_code or body.admin_code != admin_signup_code:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid admin code"
                )
            is_admin_flag = 1

        cursor.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
            (body.username, hash_password(body.password), is_admin_flag)
        )
        db.commit()
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user"
        )

    return {"message": "User created successfully"}


# ---------------- LOGIN ----------------

@router.post("/login")
def login(body: AuthRequest, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()

    cursor.execute("SELECT * FROM users WHERE username = ?", (body.username,))
    user = cursor.fetchone()

    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": user["username"]})

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# ---------------- AUTH DEPENDENCY ----------------

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: sqlite3.Connection = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, username, is_admin, is_super_admin FROM users WHERE username = ?", (username,))
    except sqlite3.OperationalError:
        # Fallback if migration hasn't run during this exact request
        cursor.execute("SELECT id, username, is_admin FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row is None:
            raise credentials_exception
        return User(
            id=row["id"],
            username=row["username"],
            is_admin=bool(row["is_admin"]),
            is_super_admin=False
        )

    row = cursor.fetchone()
    
    if row is None:
        raise credentials_exception
        
    return User(
        id=row["id"],
        username=row["username"],
        is_admin=bool(row["is_admin"]),
        is_super_admin=bool(row.get("is_super_admin", 0))
    )


# ---------------- ADMIN DEPENDENCY ----------------

def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def get_current_super_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access required"
        )
    return current_user
