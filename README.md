# Vigilance-PK: Multilingual Human Rights Triage System

Vigilance-PK is a multilingual human rights triage system designed for Pakistan. It monitors local news and social media to find, categorize, and summarize violations—handling both English and Urdu/Roman Urdu.

## Project Structure
- `src/`: Core logic and scrapers.
- `data/`: Local storage for raw and filtered news (ignored by Git).
- `.venv/`: Python virtual environment.
- `requirements.txt`: Dependencies.

## Current Milestones
- [x] **Milestone 1**: Ingestion & Filtering (Phase 1).
- [ ] **Phase 2**: Multilingual NLP (Translation & Normalization).
- [ ] **Phase 3**: Zero-Shot Classification (The Jurist).
- [ ] **Phase 4**: Vector Database (The Vault).
- [ ] **Phase 5**: FastAPI & Frontend Interface.

## Getting Started
1. Activate the environment: `.\.venv\Scripts\activate`
2. Install dependencies: `pip install -r requirements.txt`
3. Run the scout: `python src/scout_v1.py`
