from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
import asyncio
import os
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables at the very beginning
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

from src.vault import Vault
from src.scout import NewsScraper
from src.jurist import Jurist

app = FastAPI(title="Vigilance-PK Intel API")

# --- Enable CORS for Next.js ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Singleton Models ---
# We load these once at startup to prevent Streamlit's "Lag on Reload"
vault = Vault()

@app.get("/feed")
async def get_feed(limit: int = 15):
    """Returns the latest 'Ground Truth' documents."""
    try:
        news = vault.collection.get(limit=limit)
        results = []
        for i in range(len(news['documents'])):
            results.append({
                "id": news['ids'][i],
                "document": news['documents'][i],
                "metadata": news['metadatas'][i]
            })
        return results
    except Exception as e:
        return {"error": str(e)}

def translate_to_urdu_keywords(query: str):
    """Uses the LLM to generate Urdu keywords for a query to improve retrieval."""
    try:
        model = genai.GenerativeModel("gemini-flash-latest")
        resp = model.generate_content(f"Translate the core human rights keywords of this request to Urdu. Only output the Urdu keywords separated by commas: {query}")
        return resp.text
    except Exception as e:
        print(f"Translation Error: {e}")
        return ""

@app.post("/chat")
async def chat_endpoint(request: Request):
    """RAG Chat with Streaming Response & Multilingual Search."""
    data = await request.json()
    user_query = data.get("query", "")
    
    # 1. Bilingual Search (English + Urdu Keywords)
    urdu_keywords = translate_to_urdu_keywords(user_query)
    search_query = f"{user_query} {urdu_keywords}"
    
    search = vault.search_news(search_query, top_k=10)
    
    # 2. Retrieval & Context Formatting
    context = "\n\n".join([f"SOURCE [{search['metadatas'][0][i]['source']}]: {d}" for i, d in enumerate(search['documents'][0])])
    
    # 3. Format Context for UI
    sources = []
    for i, meta in enumerate(search['metadatas'][0]):
        sources.append({
            "source": meta['source'], 
            "title": search['documents'][0][i].splitlines()[0], 
            "link": meta['link']
        })

    # 4. Stream Generator
    async def generate():
        # First send the context info as a special JSON chunk
        yield json.dumps({"type": "sources", "data": sources}) + "\n"
        
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
        model = genai.GenerativeModel(
            model_name="gemini-flash-latest",
            system_instruction=system_prompt
        )
        response = model.generate_content(
            user_query, 
            stream=True,
            generation_config={"temperature": 0.0} # Maximum grounding
        )
        
        for chunk in response:
            if chunk.text:
                yield json.dumps({"type": "content", "data": chunk.text}) + "\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/sync")
async def sync_pipeline():
    """Triggers the full Scout -> Jurist -> Vault cycle."""
    # Note: In a real app, this should be BackgroundTasks. 
    # For now, we run it synchronously to show log-style progress if needed.
    scraper = NewsScraper()
    scraper.fetch_feeds()
    scraper.filter_articles()
    scraper.save_to_file("data/filtered_news.json")
    
    jurist = Jurist(model="gemini-flash-latest")
    jurist.process_all(input_file="data/filtered_news.json", output_file="data/categorized_news.json", max_workers=2)
    
    vault.ingest_json("data/categorized_news.json")
    return {"status": "success", "message": "Pipeline synchronized."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
