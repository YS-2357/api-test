from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from langgraph_service import run_graph


class AskRequest(BaseModel):
    question: str


app = FastAPI(title="API LangGraph Test", version="0.1.0")

# CORS 설정: Streamlit과의 통신을 위해 필요
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 로컬 개발 환경에서는 모든 origin 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/ask")
async def ask_question(payload: AskRequest):
    try:
        result = run_graph(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - FastAPI handles logging
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
