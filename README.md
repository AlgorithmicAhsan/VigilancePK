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
        K --> L[Featherweight Lite Dashboard]
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
*   **Gemini Flash API**: Cloud inference for both classification and chat, so the backend fits a free-tier host.
*   **Two-Tier Taxonomy**: Automated mapping of reports to HRCP (Human Rights Commission of Pakistan) categories.
*   **Grounded Analyst Prompting**: Hardened system prompts and zero-temperature configurations to eliminate hallucinations.

### 📊 Featherweight Analytical Dashboard
*   **No-Build UI**: A single-file dashboard in vanilla HTML/JS with Tailwind CSS. No `node_modules` and no build step. Note that Tailwind, Lucide and the web fonts load from public CDNs at runtime — self-host them if your threat model rules out third-party requests from an analyst's browser.
*   **Real-time Streaming**: RAG responses delivered via Server-Sent Events (SSE) with live internal status updates.
*   **Source Citation**: Every claim is linked back to the original verified news source (BBC, Dawn, Jang, etc.).

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Backend** | Python 3.11, FastAPI, Uvicorn |
| **Frontend** | Vanilla HTML5, Tailwind CSS (CDN), Lucide Icons |
| **NLP** | Stanza (Urdu/English), Sentence-Transformers |
| **LLM** | Google Gemini (Flash) |
| **Database** | ChromaDB (Vector Database) |
| **Evaluation** | DeepEval (RAG Faithfulness & Relevancy) |

---

## 🚀 Installation & Setup

### 1. Prerequisites
- Python 3.11+
- Google Gemini API Key (Optional, for cloud-based inference)

### 2. Environment Setup
```bash
# Install runtime dependencies
pip install -r requirements.txt

# Or, for development (adds pytest + deepeval)
pip install -r requirements-dev.txt

# Configure Environment
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY, CHAT_MODEL and CLASSIFY_MODEL
```

### 3. Execution
```bash
# Start the Intelligence API
uvicorn src.api:app --reload --port 8000

# Open the Dashboard
# Simply open 'lite-web/index.html' in any modern web browser.
```

If you serve the dashboard from anywhere other than your own machine, set
`API_BASE` at the top of the `<script>` block in `lite-web/index.html` to your
deployed API URL, and set `ALLOWED_ORIGINS` in `.env` to match.

### 4. Intelligence Audit
RAG quality is scored with DeepEval. The test suite is not yet in the
repository (see ADR-009); once added it runs with:
```bash
deepeval test run tests/test_eval_rag.py
```

---

## 🛡️ Ethics & Compliance
Vigilance-PK is built to support human rights defenders. The system prioritizes local processing and data sovereignty to ensure the highest level of security for sensitive intelligence logs.

---