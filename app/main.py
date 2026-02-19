import json
import os
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from app.rag import ask_question_rag


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Notes File Path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
notes_path = os.path.join(BASE_DIR, "user_notes.json")

# Create file if it doesn't exist
if not os.path.exists(notes_path):
    with open(notes_path, "w") as f:
        json.dump({"medications": []}, f)

#models
class QuestionRequest(BaseModel):
    question: str

class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str

#RAG Endpoint
@app.post("/ask")
def ask_question(request: QuestionRequest):
    answer = ask_question_rag(request.question)
    return {"answer": answer}


#Add Medication

@app.post("/add-medication")
def add_medication(med: Medication):
    with open(notes_path, "r") as f:
        data = json.load(f)

    data["medications"].append(med.dict())

    with open(notes_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"message": "Medication added successfully"}

#Get Medications

@app.get("/medications")
def get_medications():
    with open(notes_path, "r") as f:
        data = json.load(f)

    return data


#Delete Medication
@app.delete("/medication/{name}")
def delete_medication(name: str):
    with open(notes_path, "r") as f:
        data = json.load(f)

    data["medications"] = [
        med for med in data["medications"] if med["name"] != name
    ]

    with open(notes_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"message": "Medication removed"}
