from __future__ import annotations

import os
from typing import Annotated, Any, TypedDict, cast

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_teddynote import logging
from langchain_teddynote.models import ChatPerplexity
from langchain_upstage import ChatUpstage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

# LangSmith UUID v7 지원
try:
    from langsmith import uuid7 as create_uuid
except ImportError:
    from uuid import uuid4 as create_uuid

# 환경변수 로드
load_dotenv()

# LangSmith 추적 설정 (노트북 파일 기준)
logging.langsmith("API-LangGraph-Test")


class GraphState(TypedDict, total=False):
    question: Annotated[str, "Question"]

    openai_answer: Annotated[str | None, "OpenAI 응답"]
    gemini_answer: Annotated[str | None, "Google Gemini 응답"]
    anthropic_answer: Annotated[str | None, "Anthropic Claude 응답"]
    upstage_answer: Annotated[str | None, "Upstage 응답"]
    perplexity_answer: Annotated[str | None, "Perplexity 응답"]
    tavily_search: Annotated[str | None, "Tavily 검색 결과"]

    answer: Annotated[dict[str, Any] | None, "최종 답변"]

    api_status: Annotated[dict[str, Any] | None, "API별 호출 메타데이터"]

    openai_status: Annotated[dict[str, Any] | None, "OpenAI 호출 상태"]
    gemini_status: Annotated[dict[str, Any] | None, "Gemini 호출 상태"]
    anthropic_status: Annotated[dict[str, Any] | None, "Anthropic 호출 상태"]
    upstage_status: Annotated[dict[str, Any] | None, "Upstage 호출 상태"]
    perplexity_status: Annotated[dict[str, Any] | None, "Perplexity 호출 상태"]

    messages: Annotated[list, add_messages]


def build_status_from_response(
    response: Any, default_status: int = 200, detail: str = "success"
) -> dict[str, Any]:
    metadata = getattr(response, "response_metadata", None) or {}
    status = metadata.get("status_code") or metadata.get("status") or metadata.get("http_status")
    detail_text = metadata.get("finish_reason") or metadata.get("reason") or detail
    return {"status": status or default_status, "detail": detail_text}


def build_status_from_error(error: Exception) -> dict[str, Any]:
    status = cast(int | None, getattr(error, "status_code", None))
    if status is None:
        response = getattr(error, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
    return {"status": status or "error", "detail": str(error)}


def format_response_message(label: str, payload: Any) -> tuple[str, str]:
    return ("assistant", f"[{label}] {payload}")


def init_question(state: GraphState) -> GraphState:
    question = state.get("question")
    if not question:
        raise ValueError("질문이 비어 있습니다.")

    return GraphState(
        question=question,
        messages=[("user", question)],
        api_status={},
    )


def call_openai(state: GraphState) -> GraphState:
    question = state["question"]
    llm = ChatOpenAI(model="gpt-5-nano")
    try:
        response = llm.invoke(question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        return GraphState(
            openai_answer=content,
            openai_status=status,
            messages=[format_response_message("OpenAI", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        return GraphState(
            openai_status=status,
            messages=[format_response_message("OpenAI 오류", exc)],
        )


def call_gemini(state: GraphState) -> GraphState:
    question = state["question"]
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
    try:
        response = llm.invoke(question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        return GraphState(
            gemini_answer=content,
            gemini_status=status,
            messages=[format_response_message("Gemini", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        return GraphState(
            gemini_status=status,
            messages=[format_response_message("Gemini 오류", exc)],
        )


def call_anthropic(state: GraphState) -> GraphState:
    question = state["question"]
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    try:
        response = llm.invoke(question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        return GraphState(
            anthropic_answer=content,
            anthropic_status=status,
            messages=[format_response_message("Anthropic", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        return GraphState(
            anthropic_status=status,
            messages=[format_response_message("Anthropic 오류", exc)],
        )


def call_upstage(state: GraphState) -> GraphState:
    question = state["question"]
    llm = ChatUpstage(model="solar-mini")
    try:
        response = llm.invoke(question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        return GraphState(
            upstage_answer=content,
            upstage_status=status,
            messages=[format_response_message("Upstage", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        return GraphState(
            upstage_status=status,
            messages=[format_response_message("Upstage 오류", exc)],
        )


def call_perplexity(state: GraphState) -> GraphState:
    question = state["question"]
    llm = ChatPerplexity(
        model="sonar",
        temperature=0.2,
        top_p=0.9,
        search_domain_filter=["perplexity.ai"],
        return_images=False,
        return_related_questions=True,
        top_k=0,
        stream=False,
    )
    try:
        response = llm.invoke(question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        return GraphState(
            perplexity_answer=content,
            perplexity_status=status,
            messages=[format_response_message("Perplexity", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        return GraphState(
            perplexity_status=status,
            messages=[format_response_message("Perplexity 오류", exc)],
        )


LLM_FIELDS: list[tuple[str, str, str | None]] = [
    ("openai_answer", "OpenAI", "openai_status"),
    ("gemini_answer", "Gemini", "gemini_status"),
    ("anthropic_answer", "Anthropic", "anthropic_status"),
    ("perplexity_answer", "Perplexity", "perplexity_status"),
    ("upstage_answer", "Upstage", "upstage_status"),
]


def summarize_answers(state: GraphState) -> GraphState:
    answers: dict[str, Any] = {}
    api_status: dict[str, Any] = {}

    for answer_key, label, status_key in LLM_FIELDS:
        answers[label] = state.get(answer_key)
        if status_key is not None:
            status_value = state.get(status_key)
            if status_value is not None:
                api_status[label] = status_value

    return GraphState(
        answer=answers,
        api_status=api_status,
    )


def build_workflow():
    workflow = StateGraph(GraphState)
    workflow.add_node("init_question", init_question)
    workflow.add_node("call_openai", call_openai)
    workflow.add_node("call_gemini", call_gemini)
    workflow.add_node("call_anthropic", call_anthropic)
    workflow.add_node("call_upstage", call_upstage)
    workflow.add_node("call_perplexity", call_perplexity)
    workflow.add_node("summarize_answers", summarize_answers)

    workflow.add_edge("init_question", "call_openai")
    workflow.add_edge("init_question", "call_gemini")
    workflow.add_edge("init_question", "call_anthropic")
    workflow.add_edge("init_question", "call_upstage")
    workflow.add_edge("init_question", "call_perplexity")

    workflow.add_edge("call_openai", "summarize_answers")
    workflow.add_edge("call_gemini", "summarize_answers")
    workflow.add_edge("call_anthropic", "summarize_answers")
    workflow.add_edge("call_upstage", "summarize_answers")
    workflow.add_edge("call_perplexity", "summarize_answers")
    workflow.add_edge("summarize_answers", END)

    workflow.set_entry_point("init_question")
    return workflow.compile()


_app = None


def get_app():
    global _app
    if _app is None:
        _app = build_workflow()
    return _app


def _normalize_messages(messages: list | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in messages or []:
        if isinstance(message, (list, tuple)) and len(message) == 2:
            role, content = message
            normalized.append({"role": str(role), "content": str(content)})
        else:
            normalized.append({"role": "system", "content": str(message)})
    return normalized


def run_graph(question: str) -> dict[str, Any]:
    if not question or not question.strip():
        raise ValueError("질문을 입력해주세요.")

    app = get_app()
    config = RunnableConfig(recursion_limit=20, configurable={"thread_id": str(create_uuid())})
    inputs: GraphState = {"question": question.strip()}
    outputs = app.invoke(inputs, config=config)

    return {
        "question": outputs.get("question"),
        "answers": outputs.get("answer") or {},
        "api_status": outputs.get("api_status") or {},
        "messages": _normalize_messages(outputs.get("messages")),
    }
