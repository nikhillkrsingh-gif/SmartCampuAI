import os
import time
import itertools
from groq import Groq
from config import Config

raw_keys = Config.GROQ_API_KEYS.split(",")
VALID_KEYS = [k.strip() for k in raw_keys if k.strip() and not k.strip().startswith("PASTE") and not k.strip().startswith("gsk_key1_example")]

if not VALID_KEYS:
    print("\n[CRITICAL ERROR] No valid Groq API Key found in .env!\n")

CLIENT_POOL = [Groq(api_key=k) for k in VALID_KEYS]
client_cycle = itertools.cycle(CLIENT_POOL) if CLIENT_POOL else None

# Discover active chat models at startup to avoid 404 or 400 decommissioned model errors
ACTIVE_MODELS = []
if CLIENT_POOL:
    try:
        data = CLIENT_POOL[0].models.list().data
        all_ids = [m.id for m in data]
        
        priority = [
            "openai/gpt-oss-120b",
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-20b",
            "allam-2-7b",
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama3-70b-8192"
        ]
        
        ACTIVE_MODELS = [m for m in priority if m in all_ids]
        if not ACTIVE_MODELS:
            ACTIVE_MODELS = [m for m in all_ids if not any(x in m.lower() for x in ["whisper", "guard", "safeguard", "embed", "orpheus", "tts", "audio", "vision"])]
            
        print(f"\n>>> [Groq Engine] Active models connected: {ACTIVE_MODELS}\n")
    except Exception as e:
        print(f"[Model Discovery Error]: {e}")
        ACTIVE_MODELS = ["openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]

ANSWER_CACHE = {}

def get_cached_answer(query_text):
    return ANSWER_CACHE.get(query_text.lower().strip())

def set_cached_answer(query_text, answer):
    if len(ANSWER_CACHE) > 500:
        ANSWER_CACHE.clear()
    ANSWER_CACHE[query_text.lower().strip()] = answer

def generate_ai_response(system_instruction, chat_history, user_query):
    cached = get_cached_answer(user_query)
    if cached:
        return cached

    if not client_cycle:
        return "Configuration Error: No valid Groq API key found in .env."

    messages = [{"role": "system", "content": system_instruction}]
    for turn in chat_history:
        role = "user" if turn["sender"] == "user" else "assistant"
        messages.append({"role": role, "content": turn["content"]})
    messages.append({"role": "user", "content": user_query})

    total_clients = len(CLIENT_POOL)
    for _ in range(max(1, total_clients)):
        client = next(client_cycle)
        for model_id in ACTIVE_MODELS:
            try:
                completion = client.chat.completions.create(
                    messages=messages,
                    model=model_id,
                    temperature=0.0,
                    max_tokens=650
                )
                answer = completion.choices[0].message.content.strip()
                if answer:
                    set_cached_answer(user_query, answer)
                    return answer
            except Exception as err:
                err_msg = str(err).lower()
                print(f"[Groq Attempt] Model '{model_id}' failed: {err}")
                if "429" in err_msg or "rate limit" in err_msg:
                    print("[Groq Pool] Rotating to next API key...")
                    break
                time.sleep(0.1)
                continue

    return ""