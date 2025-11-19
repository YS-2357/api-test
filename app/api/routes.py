"""API 라우터와 엔드포인트 정의."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import stream_graph

router = APIRouter()


class AskRequest(BaseModel):
    """질문을 포함하는 요청 스키마."""

    question: str


@router.get("/health")
async def health():
    """서비스 가용성을 확인하는 헬스 체크 응답을 반환한다.

    Returns:
        dict: `{"status": "ok"}` 구조의 간단한 상태 객체.
    """

    return {"status": "ok"}


@router.post("/api/ask")
async def ask_question(payload: AskRequest):
    """LangGraph 워크플로우를 스트림 형태로 실행한다.

    Args:
        payload: 질문 문자열을 담은 요청 본문.

    Returns:
        StreamingResponse: partial/summary 이벤트가 줄 단위 JSON으로 전달되는 스트림 응답.
    """

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="질문을 입력해주세요.")

    def response_stream():
        answers = {}
        api_status = {}
        messages = [{"role": "user", "content": question}]
        seen_messages = {("user", question)}

        def extend_messages(new_messages: list[dict[str, str]] | None):
            for message in new_messages or []:
                role = str(message.get("role"))
                content = str(message.get("content"))
                key = (role, content)
                if key in seen_messages:
                    continue
                seen_messages.add(key)
                messages.append({"role": role, "content": content})

        try:
            for event in stream_graph(question):
                model = event.get("model")
                if model:
                    answers[model] = event.get("answer")
                    status = event.get("status")
                    if status:
                        api_status[model] = status
                extend_messages(event.get("messages"))
                yield json.dumps(event, ensure_ascii=False) + "\n"

            summary = {
                "type": "summary",
                "result": {
                    "question": question,
                    "answers": answers,
                    "api_status": api_status,
                    "messages": messages,
                },
            }
            yield json.dumps(summary, ensure_ascii=False) + "\n"
        except Exception as exc:  # pragma: no cover
            error_event = {"type": "error", "message": str(exc)}
            yield json.dumps(error_event, ensure_ascii=False) + "\n"

    return StreamingResponse(response_stream(), media_type="application/json")
