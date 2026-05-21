# Health Assist

Health Assist is a desktop application designed for local medical document retrieval and offline symptom analysis. It is developed as a final year project to provide a private, offline alternative to online AI health assistants.

The project uses a local RAG (Retrieval-Augmented Generation) pipeline so that patient records and documents remain completely private on the user's computer.

---


---

## Features
* **Offline Medical Chat:** Ask health questions and get responses offline using local language models (TinyLlama/Phi-3) through Ollama.
* **Document Upload & Retrieval:** Ingest medical reports or prescription PDFs, which are chunked and stored in a local vector database (ChromaDB) to provide context for user queries.
* **Model Downloader:** Manage and pull models directly from the settings panel inside the application.
* **Medication Planner & Notes:** Add and track medication schedules and general medical notes saved in a local SQLite database.
* **Admin Controls:** Upload medical reference texts and manage user permissions.

---

## How it Works
1. **PDF Ingestion:** Text is extracted from uploaded PDF reports using PyMuPDF and split into chunks.
2. **Embedding:** Chunks are converted into vector embeddings using the `all-MiniLM-L6-v2` Sentence Transformer.
3. **Storage:** The vectors are stored in a ChromaDB database.
4. **Retrieval & Query:** When you ask a question, the app finds the most relevant chunks in ChromaDB, matches them, and feeds them as reference context to the local Ollama LLM to generate a response.

---

## How to Set Up and Run

### Requirements
* Python 3.11
* Ollama (installed on your Windows system)

### Setup Steps
1. Clone the project and navigate into the folder:
   ```bash
   git clone https://github.com/Ayushman47/final_yr-proj.git
   cd final_yr-proj
   ```

2. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

4. Initialize the SQLite database:
   ```bash
   python -m app.database
   ```

5. Promoted an Admin user (Sign up a user in the UI first, then run this in terminal):
   ```bash
   python seed_admin.py <username>
   ```

6. Run the application:
   * **To run in development mode (access via browser at localhost:8000)**:
     ```bash
     $env:SECRET_KEY="test-secret-key"
     uvicorn app.main:app --reload
     ```
   * **To run as a native desktop application**:
     ```bash
     python run_app.py
     ```

---

## How to Build the Installer

The project is configured to build a single installer executable using PyInstaller and Inno Setup.

### Local Build:
1. Run PyInstaller to bundle the application files:
   ```bash
   pyinstaller run_app.spec --clean
   ```
2. Open Inno Setup Compiler and compile `installer.iss` to generate the `HealthAssist_Setup.exe` file in the `dist` directory.

### GitHub Actions (CI/CD):
Pushing commits to the `main` branch triggers the build workflow automatically on GitHub. You can download the compiled installer directly from the "Actions" tab under the latest run artifacts.
