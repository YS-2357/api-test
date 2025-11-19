"""LangGraph 워크플로우와 각 LLM 호출 노드를 정의하고 스트림 이벤트를 노출한다."""

from __future__ import annotations

from typing import Annotated, Any, Iterator, TypedDict, cast

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

    return GraphState(
        question=question,
        messages=[("user", question)],
    )


def call_openai(state: GraphState) -> GraphState:
    """OpenAI 모델을 호출하고 응답/상태를 반환한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: OpenAI 응답/상태/메시지를 담은 상태 델타.
    """
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
    """Google Gemini 모델을 호출한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: Gemini 응답/상태/메시지를 담은 상태 델타.
    """
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
    """Anthropic Claude 모델을 호출한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: Claude 응답/상태/메시지를 담은 상태 델타.
    """
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
    """Upstage Solar 모델을 호출한다.

    Args:
        state: 질문을 포함한 그래프 상태.

    Returns:
        GraphState: Upstage 응답/상태/메시지를 담은 상태 델타.
    """
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


NODE_CONFIG: dict[str, dict[str, str]] = {
    "call_openai": {"label": "OpenAI", "answer_key": "openai_answer", "status_key": "openai_status"},
    "call_gemini": {"label": "Gemini", "answer_key": "gemini_answer", "status_key": "gemini_status"},
    "call_anthropic": {"label": "Anthropic", "answer_key": "anthropic_answer", "status_key": "anthropic_status"},
    "call_perplexity": {
        "label": "Perplexity",
        "answer_key": "perplexity_answer",
        "status_key": "perplexity_status",
    },
    "call_upstage": {"label": "Upstage", "answer_key": "upstage_answer", "status_key": "upstage_status"},
}


def build_workflow():
    """StateGraph를 구성하고 LangGraph 앱으로 컴파일한다.

    Returns:
        Any: 컴파일된 LangGraph 애플리케이션.
    """
    workflow = StateGraph(GraphState)
    workflow.add_node("init_question", init_question)
    workflow.add_node("call_openai", call_openai)
    workflow.add_node("call_gemini", call_gemini)
    workflow.add_node("call_anthropic", call_anthropic)
    workflow.add_node("call_upstage", call_upstage)
    workflow.add_node("call_perplexity", call_perplexity)

    workflow.add_edge("init_question", "call_openai")
    workflow.add_edge("init_question", "call_gemini")
    workflow.add_edge("init_question", "call_anthropic")
    workflow.add_edge("init_question", "call_upstage")
    workflow.add_edge("init_question", "call_perplexity")

    workflow.add_edge("call_openai", END)
    workflow.add_edge("call_gemini", END)
    workflow.add_edge("call_anthropic", END)
    workflow.add_edge("call_upstage", END)
    workflow.add_edge("call_perplexity", END)

    workflow.set_entry_point("init_question")
    return workflow.compile()


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


def stream_graph(question: str) -> Iterator[dict[str, Any]]:
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

    app = get_app()
    config = RunnableConfig(recursion_limit=20, configurable={"thread_id": str(create_uuid())})
    inputs: GraphState = {"question": question.strip()}

    for event in app.stream(inputs, config=config):
        for node_name, state in event.items():
            if node_name not in NODE_CONFIG:
                continue
            meta = NODE_CONFIG[node_name]
            yield {
                "model": meta["label"],
                "node": node_name,
                "answer": state.get(meta["answer_key"]),
                "status": state.get(meta["status_key"]) or {},
                "messages": _normalize_messages(state.get("messages")),
                "type": "partial",
            }


def _aggregate_stream(question: str, partial_events: list[dict[str, Any]]) -> dict[str, Any]:
    """부분 이벤트를 최종 응답 형태로 변환한다.

    Args:
        question: 사용자 질문.
        partial_events: `stream_graph`에서 수집한 partial 이벤트 목록.

    Returns:
        dict[str, Any]: `/api/ask` 기존 JSON 응답과 동일한 구조.
    """
    answers: dict[str, Any] = {}
    api_status: dict[str, Any] = {}
    messages: list[dict[str, str]] = [{"role": "user", "content": question}]
    seen_messages: set[tuple[str, str]] = {("user", question)}

    for event in partial_events:
        model = event.get("model")
        if not model:
            continue
        answers[model] = event.get("answer")
        status = event.get("status")
        if status:
            api_status[model] = status
        _extend_unique_messages(messages, event.get("messages"), seen_messages)

    return {
        "question": question,
        "answers": answers,
        "api_status": api_status,
        "messages": messages,
    }


def run_graph(question: str) -> dict[str, Any]:
    """질문 전체를 실행하고 최종 결과를 반환한다.

    Args:
        question: 사용자 질문 문자열.

    Returns:
        dict[str, Any]: question/answers/api_status/messages 필드를 포함한 최종 응답.
    """
    question_normalized = question.strip()
    partials = list(stream_graph(question_normalized))
    return _aggregate_stream(question_normalized, partials)
