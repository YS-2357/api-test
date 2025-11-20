"""LangGraph 워크플로우와 각 LLM 호출 노드를 정의하고 스트림 이벤트를 노출한다."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, AsyncIterator, TypedDict, cast

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
from langgraph.types import Send

from app.logger import get_logger

# LangSmith UUID v7 지원
try:
    from langsmith import uuid7 as create_uuid
except ImportError:
    from uuid import uuid4 as create_uuid

# 환경변수 로드
load_dotenv()

# LangSmith 추적 설정 (노트북 파일 기준)
logging.langsmith("API-LangGraph-Test")

logger = get_logger(__name__)


def _preview(text: str, limit: int = 80) -> str:
    """긴 문자열을 로그에 표시하기 위한 요약 버전으로 변환한다."""

    compact = " ".join(text.split())
    return compact[:limit] + ("…" if len(compact) > limit else "")


class GraphState(TypedDict, total=False):
    """LangGraph 실행 시 공유되는 상태 정의."""

    question: Annotated[str, "Question"]

    openai_answer: Annotated[str | None, "OpenAI 응답"]
    gemini_answer: Annotated[str | None, "Google Gemini 응답"]
    anthropic_answer: Annotated[str | None, "Anthropic Claude 응답"]
    upstage_answer: Annotated[str | None, "Upstage 응답"]
    perplexity_answer: Annotated[str | None, "Perplexity 응답"]
    tavily_search: Annotated[str | None, "Tavily 검색 결과"]

    openai_status: Annotated[dict[str, Any] | None, "OpenAI 호출 상태"]
    gemini_status: Annotated[dict[str, Any] | None, "Gemini 호출 상태"]
    anthropic_status: Annotated[dict[str, Any] | None, "Anthropic 호출 상태"]
    upstage_status: Annotated[dict[str, Any] | None, "Upstage 호출 상태"]
    perplexity_status: Annotated[dict[str, Any] | None, "Perplexity 호출 상태"]

    messages: Annotated[list, add_messages]


def build_status_from_response(
    response: Any, default_status: int = 200, detail: str = "success"
) -> dict[str, Any]:
    """LLM 응답 객체에서 상태 메타데이터를 추출한다.

    Args:
        response: LangChain LLM 응답 객체.
        default_status: 응답에 상태 코드가 없을 때 사용할 기본 값.
        detail: 응답에 finish reason이 없을 때 사용할 기본 메시지.

    Returns:
        dict[str, Any]: `status`, `detail` 키를 포함한 상태 정보.
    """
    metadata = getattr(response, "response_metadata", None) or {}
    status = metadata.get("status_code") or metadata.get("status") or metadata.get("http_status")
    detail_text = metadata.get("finish_reason") or metadata.get("reason") or detail
    return {"status": status or default_status, "detail": detail_text}


def build_status_from_error(error: Exception) -> dict[str, Any]:
    """예외 객체를 API 상태 표현으로 변환한다.

    Args:
        error: 발생한 예외 인스턴스.

    Returns:
        dict[str, Any]: 실패 상태와 메시지를 담은 상태 정보.
    """
    status = cast(int | None, getattr(error, "status_code", None))
    if status is None:
        response = getattr(error, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
    return {"status": status or "error", "detail": str(error)}


def format_response_message(label: str, payload: Any) -> tuple[str, str]:
    """메시지 로그에 저장할 간단한 (role, content) 튜플을 생성한다.

    Args:
        label: 메시지 헤더(모델명 또는 오류 등).
        payload: 원본 응답 또는 예외 객체.

    Returns:
        tuple[str, str]: `("assistant", "[라벨] 내용")` 형태의 메시지.
    """
    return ("assistant", f"[{label}] {payload}")


def init_question(state: GraphState) -> GraphState:
    """그래프 초기 상태를 검증하고 기본 메시지를 설정한다.

    Args:
        state: LangGraph가 전달한 질문 상태.

    Returns:
        GraphState: 질문과 초기 메시지를 포함한 상태.

    Raises:
        ValueError: 질문이 비어 있는 경우.
    """
    question = state.get("question")
    if not question:
        raise ValueError("질문이 비어 있습니다.")

    logger.debug("질문 초기화: %s", _preview(question))
    return GraphState(
        question=question,
        messages=[("user", question)],
    )


async def _ainvoke(llm: Any, question: str) -> Any:
    """주어진 LLM에서 비동기 호출을 수행한다."""

    if hasattr(llm, "ainvoke"):
        return await llm.ainvoke(question)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, llm.invoke, question)


async def call_openai(state: GraphState) -> GraphState:
    """OpenAI 모델을 호출하고 응답/상태를 반환한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: OpenAI 응답/상태/메시지를 담은 상태 델타.
    """
    question = state["question"]
    llm = ChatOpenAI(model="gpt-5-nano")
    logger.debug("OpenAI 호출 시작")
    try:
        response = await _ainvoke(llm, question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        logger.info("OpenAI 응답 완료: %s", status.get("detail"))
        return GraphState(
            openai_answer=content,
            openai_status=status,
            messages=[format_response_message("OpenAI", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        logger.warning("OpenAI 호출 실패: %s", exc)
        return GraphState(
            openai_status=status,
            messages=[format_response_message("OpenAI 오류", exc)],
        )


async def call_gemini(state: GraphState) -> GraphState:
    """Google Gemini 모델을 호출한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: Gemini 응답/상태/메시지를 담은 상태 델타.
    """
    question = state["question"]
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
    logger.debug("Gemini 호출 시작")
    try:
        response = await _ainvoke(llm, question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        logger.info("Gemini 응답 완료: %s", status.get("detail"))
        return GraphState(
            gemini_answer=content,
            gemini_status=status,
            messages=[format_response_message("Gemini", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        logger.warning("Gemini 호출 실패: %s", exc)
        return GraphState(
            gemini_status=status,
            messages=[format_response_message("Gemini 오류", exc)],
        )


async def call_anthropic(state: GraphState) -> GraphState:
    """Anthropic Claude 모델을 호출한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: Claude 응답/상태/메시지를 담은 상태 델타.
    """
    question = state["question"]
    llm = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
    logger.debug("Anthropic 호출 시작")
    try:
        response = await _ainvoke(llm, question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        logger.info("Anthropic 응답 완료: %s", status.get("detail"))
        return GraphState(
            anthropic_answer=content,
            anthropic_status=status,
            messages=[format_response_message("Anthropic", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        logger.warning("Anthropic 호출 실패: %s", exc)
        return GraphState(
            anthropic_status=status,
            messages=[format_response_message("Anthropic 오류", exc)],
        )


async def call_upstage(state: GraphState) -> GraphState:
    """Upstage Solar 모델을 호출한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: Upstage 응답/상태/메시지를 담은 상태 델타.
    """
    question = state["question"]
    llm = ChatUpstage(model="solar-mini")
    logger.debug("Upstage 호출 시작")
    try:
        response = await _ainvoke(llm, question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        logger.info("Upstage 응답 완료: %s", status.get("detail"))
        return GraphState(
            upstage_answer=content,
            upstage_status=status,
            messages=[format_response_message("Upstage", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        logger.warning("Upstage 호출 실패: %s", exc)
        return GraphState(
            upstage_status=status,
            messages=[format_response_message("Upstage 오류", exc)],
        )


async def call_perplexity(state: GraphState) -> GraphState:
    """Perplexity Sonar 모델을 호출한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: Perplexity 응답/상태/메시지를 담은 상태 델타.
    """
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
    logger.debug("Perplexity 호출 시작")
    try:
        response = await _ainvoke(llm, question)
        content = response.content if hasattr(response, "content") else str(response)
        status = build_status_from_response(response)
        logger.info("Perplexity 응답 완료: %s", status.get("detail"))
        return GraphState(
            perplexity_answer=content,
            perplexity_status=status,
            messages=[format_response_message("Perplexity", response)],
        )
    except Exception as exc:
        status = build_status_from_error(exc)
        logger.warning("Perplexity 호출 실패: %s", exc)
        return GraphState(
            perplexity_status=status,
            messages=[format_response_message("Perplexity 오류", exc)],
        )


NODE_CONFIG: dict[str, dict[str, str]] = {
    "call_openai": {"label": "OpenAI", "answer_key": "openai_answer", "status_key": "openai_status"},
    "call_gemini": {"label": "Gemini", "answer_key": "gemini_answer", "status_key": "gemini_status"},
    "call_anthropic": {"label": "Anthropic", "answer_key": "anthropic_answer", "status_key": "anthropic_status"},
    "call_perplexity": {"label": "Perplexity", "answer_key": "perplexity_answer", "status_key": "perplexity_status"},
    "call_upstage": {"label": "Upstage", "answer_key": "upstage_answer", "status_key": "upstage_status"},
}


def dispatch_llm_calls(state: GraphState) -> list[Send]:
    """Send API를 활용해 각 LLM 노드를 동시에 실행할 태스크 목록을 생성한다."""

    question = state.get("question")
    if not question:
        raise ValueError("질문이 비어 있습니다.")
    # 동일한 상태를 각 노드에 전달해 LangGraph가 병렬 실행하도록 지시
    logger.info("LLM fan-out 실행: %s", ", ".join(NODE_CONFIG.keys()))
    return [Send(node_name, state) for node_name in NODE_CONFIG]


def build_workflow():
    """StateGraph를 구성하고 LangGraph 앱으로 컴파일한다.

    Returns:
        Any: 컴파일된 LangGraph 애플리케이션.
    """
    logger.debug("LangGraph 워크플로우 컴파일 시작")
    workflow = StateGraph(GraphState)
    workflow.add_node("init_question", init_question)
    workflow.add_node("call_openai", call_openai)
    workflow.add_node("call_gemini", call_gemini)
    workflow.add_node("call_anthropic", call_anthropic)
    workflow.add_node("call_upstage", call_upstage)
    workflow.add_node("call_perplexity", call_perplexity)

    workflow.add_conditional_edges("init_question", dispatch_llm_calls)

    workflow.add_edge("call_openai", END)
    workflow.add_edge("call_gemini", END)
    workflow.add_edge("call_anthropic", END)
    workflow.add_edge("call_upstage", END)
    workflow.add_edge("call_perplexity", END)

    workflow.set_entry_point("init_question")
    compiled = workflow.compile()
    logger.info("LangGraph 워크플로우 컴파일 완료")
    return compiled


_app = None


def get_app():
    """싱글턴 형태로 컴파일된 LangGraph 앱을 반환한다.

    Returns:
        Any: 재사용 가능한 LangGraph 애플리케이션 인스턴스.
    """
    global _app
    if _app is None:
        _app = build_workflow()
    return _app


def _normalize_messages(messages: list | None) -> list[dict[str, str]]:
    """Streamlit 표시를 위해 메시지를 표준화한다.

    Args:
        messages: LangGraph에서 누적된 메시지 리스트.

    Returns:
        list[dict[str, str]]: `{"role": ..., "content": ...}` 형태 리스트.
    """
    normalized: list[dict[str, str]] = []
    for message in messages or []:
        if isinstance(message, (list, tuple)) and len(message) == 2:
            role, content = message
            normalized.append({"role": str(role), "content": str(content)})
        else:
            normalized.append({"role": "system", "content": str(message)})
    return normalized


def _extend_unique_messages(
    target: list[dict[str, str]], new_messages: list[dict[str, str]] | None, seen: set[tuple[str, str]]
) -> None:
    """중복 없이 메시지를 추가한다.

    Args:
        target: 메시지를 누적할 리스트.
        new_messages: 새로 추가할 메시지 목록.
        seen: (role, content) 조합을 저장한 중복 체크 세트.
    """
    for message in new_messages or []:
        role = str(message.get("role"))
        content = str(message.get("content"))
        key = (role, content)
        if key in seen:
            continue
        seen.add(key)
        target.append({"role": role, "content": content})


async def stream_graph(question: str) -> AsyncIterator[dict[str, Any]]:
    """질문을 받아 LangGraph 워크플로우에서 발생하는 이벤트를 스트리밍한다.

    Args:
        question: 사용자 질문 문자열.

    Yields:
        dict[str, Any]: `type=partial` 이벤트(모델명/응답/상태/메시지).

    Raises:
        ValueError: 질문이 비어 있는 경우.
    """
    if not question or not question.strip():
        raise ValueError("질문을 입력해주세요.")

    logger.info("LangGraph 스트림 실행: %s", _preview(question))
    app = get_app()
    config = RunnableConfig(recursion_limit=20, configurable={"thread_id": str(create_uuid())})
    inputs: GraphState = {"question": question.strip()}

    try:
        async for event in app.astream(inputs, config=config):
            for node_name, state in event.items():
                if node_name not in NODE_CONFIG:
                    continue
                meta = NODE_CONFIG[node_name]
                logger.debug("이벤트 수신: %s", meta["label"])
                yield {
                    "model": meta["label"],
                    "node": node_name,
                    "answer": state.get(meta["answer_key"]),
                    "status": state.get(meta["status_key"]) or {},
                    "messages": _normalize_messages(state.get("messages")),
                    "type": "partial",
                }
    except Exception as exc:
        logger.error("LangGraph 스트림 오류: %s", exc)
        yield {
            "type": "error",
            "message": str(exc),
            "node": None,
            "model": None,
        }
