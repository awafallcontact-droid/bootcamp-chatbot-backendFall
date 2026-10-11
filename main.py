import os
import json
from datetime import datetime

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.db import get_db
from database.models import Conversation, Message

load_dotenv(override=True)

RODIUMAI_URL = "https://api.rodiumai.io/v1/chat/completions"
RODIUMAI_API_KEY = os.environ.get("RODIUMAI_API_KEY", "")
MODEL = os.getenv("RODIUMAI_MODEL", "openai/gpt-4o")
PREVIEW_LENGTH = 60

LLM_ROLES = {"user", "assistant"}
NOTIFICATION_ROLE = "system-notification"
NOTIFICATION_EVERY = 10
NOTIFICATION_TEXT = "Notification système : Une dizaine de messages écrits."

prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "system.md")
try:
    with open(prompt_path, "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = (
        "Tu es Study Buddy, un tuteur bienveillant pour les étudiants. "
        "Réponds aux questions de manière claire et concise."
    )

app = FastAPI(title="Study Buddy Chatbot")

# Liste stricte des modèles autorisés
ALLOWED_MODELS = [
    {"id": "anthropic/claude-sonnet-4-5-20250929", "name": "Claude 3.5 Sonnet"},
    {"id": "openai/gpt-4o", "name": "GPT-4o"}
]

@app.get("/models")
def get_models():
    """Retourne la liste des modèles disponibles au frontend."""
    return {"models": ALLOWED_MODELS}

class ConversationResponse(BaseModel):
    conversation_id: int

class ConversationSummary(BaseModel):
    id: int
    created_at: datetime
    preview: str | None

class ChatRequest(BaseModel):
    conversation_id: int
    message: str
    role: str = "user"
    model: str = "openai/gpt-4o"

class ChatResponse(BaseModel):
    reply: str
    notification: str | None = None

class MessageResponse(BaseModel):
    seq: int
    role: str
    content: str
    created_at: datetime

def load_messages(db: Session, conversation_id: int) -> list[Message]:
    if db.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq)
    ).all()

def build_llm_history(rows: list[Message]) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in rows if m.role in LLM_ROLES]

@app.post("/conversations", status_code=201)
def create_conversation(db: Session = Depends(get_db)) -> ConversationResponse:
    conversation = Conversation()
    db.add(conversation)
    db.commit()
    return ConversationResponse(conversation_id=conversation.id)

@app.get("/conversations")
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationSummary]:
    rows = db.execute(
        select(Conversation, Message.content)
        .outerjoin(Message, and_(Message.conversation_id == Conversation.id, Message.seq == 1))
        .order_by(Conversation.id.desc())
    ).all()
    
    results = []
    for r in rows:
        preview = r.content[:PREVIEW_LENGTH] + "..." if r.content and len(r.content) > PREVIEW_LENGTH else r.content
        results.append(ConversationSummary(id=r.Conversation.id, created_at=r.Conversation.created_at, preview=preview))
    return results

@app.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: int, db: Session = Depends(get_db)) -> list[MessageResponse]:
    rows = load_messages(db, conversation_id)
    return [
        MessageResponse(seq=m.seq, role=m.role, content=m.content, created_at=m.created_at)
        for m in rows
    ]

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    # 1. Vérification du modèle
    allowed_model_ids = [m["id"] for m in ALLOWED_MODELS]
    if req.model not in allowed_model_ids:
        raise HTTPException(status_code=400, detail="Modèle non autorisé.")

    messages_in_db = load_messages(db, req.conversation_id)
    next_seq = len(messages_in_db) + 1

    # 2. Sauvegarde du message utilisateur (ou de la note)
    user_msg = Message(
        conversation_id=req.conversation_id,
        seq=next_seq,
        role=req.role,
        content=req.message
    )
    db.add(user_msg)
    db.commit()

    # Gestion du rôle 'note'
    if req.role == "note":
        async def note_stream():
            yield f"data: {json.dumps({'chunk': '📝 Note personnelle sauvegardée.'})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(note_stream(), media_type="text/event-stream")

    # 3. Préparation pour le LLM
    messages_in_db.append(user_msg)
    llm_history = build_llm_history(messages_in_db)
    
    payload = {
        "model": req.model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + llm_history,
        "stream": True
    }
    
    headers = {
        "Authorization": f"Bearer {RODIUMAI_API_KEY}",
        "Content-Type": "application/json"
    }

    # 4. Générateur pour le flux SSE
    async def generate():
        full_content = ""
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream("POST", RODIUMAI_URL, headers=headers, json=payload, timeout=60.0) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                # SÉCURITÉ : On vérifie que la liste "choices" n'est pas vide
                                if data.get("choices") and len(data["choices"]) > 0:
                                    chunk = data["choices"][0]["delta"].get("content", "")
                                    if chunk:
                                        full_content += chunk
                                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                            except json.JSONDecodeError:
                                continue
            except httpx.HTTPError as exc:
                print(f"Erreur LLM : {exc}")
                yield f"data: {json.dumps({'error': 'Erreur API LLM'})}\n\n"

        # 5. Sauvegarde de la réponse complète en base
        if full_content:
            bot_msg = Message(
                conversation_id=req.conversation_id,
                seq=next_seq + 1,
                role="assistant",
                content=full_content
            )
            db.add(bot_msg)
            db.commit()
            
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")