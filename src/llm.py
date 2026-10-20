"""Every Gemini call goes through this module (ADR-016, ADR-023).

Keeping the client, model names, retries and safety settings in one place
means swapping provider or model later is a change to this file only.
"""
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "models/gemini-2.5-flash")
# Flash-Lite: classification is a constrained labelling task, and Lite has
# the most generous free-tier limits.
CLASSIFY_MODEL = os.getenv("CLASSIFY_MODEL", "models/gemini-3.1-flash-lite")

# Retries are handled by the SDK: exponential backoff with jitter on rate
# limits (429) and transient server errors. 5 attempts waits up to ~30 s in
# total before giving up, which rides out a per-minute quota window.
RETRY = types.HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=30.0,
    exp_base=2.0,
    jitter=1.0,
    http_status_codes=[408, 429, 500, 502, 503, 504],
)

# The corpus is, by design, reports of violence and abuse. Default filters
# block legitimate analysis and classification, so they are switched off.
SAFETY_OFF = [
    types.SafetySetting(category=category, threshold=types.HarmBlockThreshold.BLOCK_NONE)
    for category in (
        types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
    )
]

_client = None


def key_configured() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY"))


def client() -> genai.Client:
    """Created on first use, so importing this module never needs a key."""
    global _client
    if _client is None:
        if not key_configured():
            raise RuntimeError("GOOGLE_API_KEY is not set.")
        _client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY"),
            http_options=types.HttpOptions(retry_options=RETRY),
        )
    return _client


def generate_json(prompt: str, system: str, model: str = CLASSIFY_MODEL, schema=None) -> str:
    """One blocking call that must return JSON. Returns the raw text."""
    response = client().models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=schema,
            safety_settings=SAFETY_OFF,
        ),
    )
    return response.text or ""


async def stream_chat(query: str, system: str, model: str = CHAT_MODEL):
    """Yields the answer as text chunks."""
    stream = await client().aio.models.generate_content_stream(
        model=model,
        contents=query,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.3,
            safety_settings=SAFETY_OFF,
        ),
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text
