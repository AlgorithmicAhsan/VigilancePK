# 🛡️ Vigilance-PK Pro: Elite Multilingual Human Rights Triage

**Vigilance-PK Pro** is an OSINT (Open Source Intelligence) platform designed for the automated triage and analysis of human rights violations in Pakistan. It leverages a decoupled architecture to process multilingual news feeds (Urdu and English), categorize them using LLMs, and provide a real-time RAG (Retrieval-Augmented Generation) dashboard.

---

## 🛰️ System Architecture

The platform follows a modular **Scout-Jurist-Vault** pipeline, ensuring high precision and low-latency intelligence synthesis.

```mermaid
graph TD
    subgraph Ingestion_Phase [1. Scout Phase: OSINT Ingestion]
        A[RSS Feeds: Dawn, Express, Jang, BBC Urdu] --> B[Scout Scraper]
        B --> C[Stanza NLP Engine: CPU-Optimized]
        C --> D[Filtered News JSON]
    end

    subgraph Intelligence_Phase [2. Jurist Phase: AI Triage]
        D --> E[Jurist Classifier]
        E --> F[Google Gemini Flash API]
        F --> G[Categorized & Tagged Intel]
    end

    subgraph Storage_Phase [3. Vault Phase: Knowledge Base]
        G --> H[Vault Ingestor]
        H --> I[ChromaDB: Vector Store]
        I --> J[paraphrase-multilingual-MiniLM-L12-v2]
    end

    subgraph Presentation_Phase [4. Nexus Phase: RAG & UI]
        J --> K[FastAPI Backend]
        K --> L[Next.js Elite Dashboard]
        L --> M[Bilingual RAG Chat]
    end
```

---

## 💎 Key Features

### 🌍 Bilingual Intelligence Engine
*   **Cross-Lingual Retrieval**: Query in English to retrieve Urdu news sources.
*   **Stanza Urdu NLP**: High-precision normalization and lemmatization of Urdu text on CPU to save VRAM.
*   **Universal Translator**: Automated pre-processing of Urdu context for the LLM judge during evaluations.

### 🧠 Advanced AI Triage (The Jurist)
*   **Gemini Flash API**: High-speed, high-token-count cloud inference for complex reasoning and synthesis.
*   **Two-Tier Taxonomy**: Automated mapping of reports to HRCP (Human Rights Commission of Pakistan) categories.
*   **Grounded Analyst Prompting**: Hardened system prompts and zero-temperature configurations to eliminate hallucinations and ensure evidence-based reporting.

### 📊 Elite Analytical Dashboard
*   **Real-time Streaming**: RAG responses delivered via Server-Sent Events (SSE).
*   **Source Citation**: Every claim is linked back to the original verified news source (BBC, Dawn, Jang, etc.).
*   **Fixed Dashboard Layout**: Independent scrolling for the Intel Feed and Command Hub to ensure maximum accessibility.

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Backend** | Python 3.11, FastAPI, Uvicorn |
| **Frontend** | Next.js 15 (App Router), Tailwind CSS, Framer Motion |
| **NLP** | Stanza (Urdu/English), Sentence-Transformers |
| **LLM** | Google Gemini (Flash 1.5/2.0) |
| **Database** | ChromaDB (Vector Database) |
| **Evaluation** | DeepEval (RAG Faithfulness & Relevancy) |

---

## 🚀 Installation & Setup

### 1. Prerequisites
- Python 3.11+
- Node.js 18+
- Google Gemini API Key (obtain from [Google AI Studio](https://aistudio.google.com/))

### 2. Backend Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure Environment
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# Start the Intelligence API
uvicorn src.api:app --reload --port 8000
```

### 3. Frontend Setup
```bash
cd web
npm install
npm run dev
```

### 4. Intelligence Audit
To verify the system's analytical accuracy:
```bash
deepeval test run tests/test_eval_rag.py
```

---

## 🛡️ Ethics & Compliance
Vigilance-PK is built to support human rights defenders. The system operates entirely locally (No data sent to external APIs), ensuring the highest level of security for sensitive intelligence logs.

---