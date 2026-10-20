from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
import json
import asyncio
import os
from tqdm import tqdm
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables at the very beginning
load_dotenv()
if os.getenv("GOOGLE_API_KEY"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- Model configuration (single source of truth, see ADR-003) ---
# Both are Gemini models. Ollama was dropped (ADR-016).
CHAT_MODEL = os.getenv("CHAT_MODEL", "models/gemini-2.5-flash")
CLASSIFY_MODEL = os.getenv("CLASSIFY_MODEL", "models/gemini-2.5-flash")

# Longest query we accept on /chat. Stops an open endpoint being used as an
# unmetered relay to the upstream model.
MAX_QUERY_CHARS = 2000

from src.vault import Vault
from src.scout import NewsScraper
from src.jurist import Jurist

app = FastAPI(title="Vigilance-PK Intel API")

# --- CORS ---
# Comma-separated list, e.g. ALLOWED_ORIGINS="https://vigilance.vercel.app"
# Credentials stay off: the spec forbids "*" together with credentials, and
# nothing here authenticates via cookies.
allowed_origins = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# --- Singleton Models ---
# Loaded once at startup so the embedding model is not re-read per request.
vault = Vault()

@app.get("/feed")
async def get_feed(limit: int = 15):
    """Returns the LATEST 'Ground Truth' documents."""
    try:
        # Chroma cannot sort inside get(), so we pull and sort in Python.
        # Embeddings are excluded to keep the payload small.
        news = vault.collection.get(include=["documents", "metadatas"])
        ids = news.get("ids") or []
        documents = news.get("documents") or []
        metadatas = news.get("metadatas") or []

        results = []
        for i in range(len(ids)):
            results.append({
                "id": ids[i],
                "document": documents[i] if i < len(documents) else "",
                "metadatas": metadatas[i] if i < len(metadatas) else {},
            })

        # Sort by published date (Descending)
        results.sort(key=lambda x: (x["metadatas"] or {}).get("published", ""), reverse=True)
        return results[:limit]
    except Exception as e:
        print(f"ERROR: /feed failed: {e}")
        raise HTTPException(status_code=500, detail="Could not read the intelligence repository.")

@app.get("/sync")
async def sync_intel(background_tasks: BackgroundTasks, wipe: bool = False):
    """Triggers the full Scout-Jurist-Vault pipeline."""
    def run_pipeline():
        import concurrent.futures
        if wipe:
            print("WIPING_VAULT: Purging old records for fresh sync...")
            vault.reset_collection()

        scraper = NewsScraper()
        jurist = Jurist(model=CLASSIFY_MODEL)

        # 1. Scout
        raw_news = scraper.scrape_all()

        # 2. Incremental Filter: Skip what we already have in the Vault.
        # include=[] means ids only - documents and metadata are not needed here.
        existing_ids = set(vault.collection.get(include=[])['ids'])
        import uuid
        new_articles = []
        for art in raw_news:
            doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, art.get('link', '')))
            if doc_id not in existing_ids:
                new_articles.append(art)
        
        print(f"Incremental Sync: {len(new_articles)} new articles identified (Skipped {len(raw_news) - len(new_articles)} existing).")

        # 3. Jurist (Triage)
        analyzed_news = []
        def classify(article):
            return jurist.categorize_article(article)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(classify, art) for art in new_articles]
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(new_articles), desc="Analyzing News"):
                article = future.result()
                # Flatten classification for ChromaDB metadata
                if 'jurist_classification' in article:
                    jc = article['jurist_classification']
                    article['category'] = jc['major_categories'][0] if jc['major_categories'] else "GENERAL"
                    article['tags'] = ",".join(jc['specific_tags'])
                    # Enhanced Severity Logic: Catching high-priority violations
                    cats_str = str(jc['major_categories']).lower()
                    tags_str = str(jc['specific_tags']).lower()
                    high_priority = ['terrorism', 'crime', 'armed forces', 'extrajudicial', 'disappearances', 'blasphemy', 'death penalty', 'killing', 'remand', 'arrest', 'custody']
                    
                    if any(x in cats_str or x in tags_str for x in high_priority):
                        article['severity'] = 'high'
                    elif any(x in cats_str for x in ['vulnerable groups', 'accountability']):
                        article['severity'] = 'medium'
                    else:
                        article['severity'] = 'low'
                
                analyzed_news.append(article)
        
        # 4. Vault (Ingest)
        vault.ingest_news(analyzed_news)
        print("PIPELINE_COMPLETE: Repository Updated.")

    background_tasks.add_task(run_pipeline)
    return {"status": "SYNC_STARTED"}

@app.get("/stats")
async def get_stats():
    """Returns intelligence repository statistics."""
    try:
        count = vault.collection.count()
        return {
            "total_logs": count,
            "status": "OPERATIONAL",
            "engine": CHAT_MODEL,
            "gemini_key_configured": bool(os.getenv("GOOGLE_API_KEY")),
        }
    except Exception as e:
        print(f"ERROR: /stats failed: {e}")
        raise HTTPException(status_code=500, detail="Could not read repository statistics.")

def translate_to_urdu_keywords(query: str):
    """Uses Gemini to generate Urdu search terms for better RAG retrieval.

    Blocking network call: callers on the event loop must wrap this in
    run_in_threadpool().
    """
    if not os.getenv("GOOGLE_API_KEY"):
        return ""
    try:
        model = genai.GenerativeModel(CHAT_MODEL)
        prompt = f"Translate the following English search query into 3-4 specific Urdu keywords for news searching. Return ONLY the Urdu words separated by spaces. Query: {query}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        # Translation is an enhancement, not a requirement: fall back to
        # searching with the original query alone.
        print(f"DEBUG: Urdu keyword translation failed: {e}")
        return ""

@app.post("/chat")
async def chat_endpoint(request: Request):
    """RAG Chat with Streaming Response & Multilingual Search."""
    data = await request.json()
    user_query = (data.get("query") or "").strip()

    if not user_query:
        raise HTTPException(status_code=400, detail="A query is required.")
    if len(user_query) > MAX_QUERY_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"Query too long (max {MAX_QUERY_CHARS} characters).",
        )

    # 4. Stream Generator
    async def generate():
        # Immediately notify the UI that we are working
        yield json.dumps({"type": "status", "data": "Initializing Analytical Engine..."}) + "\n"
        await asyncio.sleep(0.1) # Force flush
        
        # 1. Bilingual Search (English + Urdu Keywords) - Done inside the stream
        yield json.dumps({"type": "status", "data": "Translating for Multilingual Search..."}) + "\n"
        urdu_keywords = await run_in_threadpool(translate_to_urdu_keywords, user_query)
        search_query = f"{user_query} {urdu_keywords}".strip()

        yield json.dumps({"type": "status", "data": "Searching Intelligence Repository..."}) + "\n"
        # 2. RAG Search (search_news returns a normalized list[dict])
        try:
            search_results = await run_in_threadpool(vault.search_news, search_query, 5)

            context_parts = []
            sources = []

            for r in search_results:
                if not isinstance(r, dict):
                    continue

                doc = r.get('document', '')
                meta = r.get('metadata') or {}

                if doc:
                    context_parts.append(doc)
                    sources.append({
                        "source": meta.get('source', 'Unknown'),
                        "title": str(doc).splitlines()[0][:50] + "...",
                        "link": meta.get('link', '')
                    })

            context = "\n---\n".join(context_parts) if context_parts else "No relevant documents found."
        except Exception as e:
            print(f"DEBUG: Search failed: {e}")
            context = "System busy. Limited context."
            sources = []

        yield json.dumps({"type": "sources", "data": sources}) + "\n"
        yield json.dumps({"type": "status", "data": "Generating Inference..."}) + "\n"

        system_prompt = (
            "### IDENTITY ###\n"
            "You are an Elite Intelligence Analyst for Vigilance-PK. Your purpose is to provide objective, grounded reports based ONLY on the provided Research Notes.\n\n"
            "### STRICT GROUNDING RULES ###\n"
            "1. USE ONLY the provided Research Notes. If the information is not present, state: 'I do not have specific data on this topic in the current intelligence repository.'\n"
            "2. NEVER invent details, dates, or names not found in the notes.\n"
            "3. CITE YOUR SOURCES. Every factual claim must be attributed (e.g., 'Per Jang...', 'Express Urdu reports...').\n"
            "4. SYNTHESIZE MULTILINGUAL DATA. Incorporate details from Urdu reports into your English response accurately.\n"
            "5. NO EXTERNAL KNOWLEDGE. Do not use your internal training data to supplement the report unless it is for general context (e.g., explaining what an FIR is).\n\n"
            f"### RESEARCH NOTES ###\n{context}"
        )
        # Safety filters are relaxed because the corpus is, by design, reports
        # of violence and abuse: the defaults block legitimate analysis.
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        model = genai.GenerativeModel(
            model_name=CHAT_MODEL,
            system_instruction=system_prompt,
            safety_settings=safety_settings
        )
        response = await model.generate_content_async(
            user_query,
            stream=True,
            generation_config={"temperature": 0.3}
        )
        async for chunk in response:
            try:
                if chunk.candidates and chunk.candidates[0].content.parts:
                    text = chunk.text
                    yield json.dumps({"type": "content", "data": text}) + "\n"
            except Exception as e:
                print(f"DEBUG: Chunk error (Safety?): {e}")

    # This is newline-delimited JSON, not SSE (no "data:" prefixes), so it is
    # labelled as such. The no-cache / no-buffering headers stop reverse proxies
    # holding the stream back and delivering it as one lump.
    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
