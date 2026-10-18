# Abenzo AI — Local Sales Assistant MVP

A minimal, local-first AI sales assistant for **Abenzo**, a web development agency serving businesses across India.

Built with:
- **Frontend**: Next.js App Router (JavaScript + Tailwind CSS)
- **Backend**: Python + FastAPI
- **Local AI**: Ollama with `qwen2.5:3b`
- **Database**: SQLite (WAL mode)
- **Zero Paid APIs**: Runs completely local with ₹0 cost

---

## 1. Prerequisites Check

- **Node.js**: v20+ (`node -v`)
- **npm**: v10+ (`npm -v`)
- **Python**: 3.10+ (`python3 --version`)
- **Git**: (`git --version`)
- **Ollama**: Installed and running locally with `qwen2.5:3b` (`ollama list`)

If Ollama is not installed:
```bash
brew install ollama
ollama serve
ollama pull qwen2.5:3b
```

---

## 2. Setup and Installation

### Backend Setup
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Frontend Setup
```bash
cd frontend
npm install
cp .env.example .env.local
```

---

## 3. Running the Application

### Start the FastAPI Backend
```bash
# In the backend directory (or root with venv activated)
backend/venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
API Documentation is available at: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Start the Next.js Frontend
```bash
# In the frontend directory
npm run dev
```
Open the Dashboard at: [http://localhost:3000](http://localhost:3000)

---

## 4. Running Automated Tests

Run the test suite verifying deduplication, website evidence verification, Ollama schema validation, and human-approval rules:
```bash
PYTHONPATH=. backend/venv/bin/pytest backend/tests/test_all.py -v
```

---

## 5. Honesty and Platform Safety Rules

1. **No Automated Cold DMs**: All cold outreach drafts are generated for human review. The operator must review, copy, and send manually.
2. **Evidence-Based Qualification**: Website statuses are marked as `found`, `not_found`, or `uncertain` based on real HTTP checks. The AI never claims certainty without evidence.
3. **Official Meta APIs Only**: No password scraping or unofficial automation. Webhooks enforce idempotency on `external_event_id`.
4. **Human In The Loop**: Inbound replies require operator approval before delivery.
