"""Streamlit 기반 멀티 LLM 비교 대시보드."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import streamlit as st

from app.logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_api_url() -> str:
    """FastAPI 엔드포인트를 환경변수 → 파일 → 기본값 순으로 로드한다.

    Returns:
        호출할 FastAPI `/api/ask` URL.
    """
    env_value = os.getenv("FASTAPI_URL")
    if env_value:
        return env_value

    config_path = PROJECT_ROOT / ".fastapi_url"
    if config_path.exists():
        return config_path.read_text().strip()
    return "http://127.0.0.1:8000/api/ask"


API_URL = load_api_url()
logger = get_logger(__name__)
logger.info("Streamlit UI 초기화 - FastAPI URL: %s", API_URL)

st.set_page_config(page_title="API LangGraph 테스트", layout="wide")
st.title("API LangGraph 테스트 대시보드")
st.caption("FastAPI 백엔드와 LangGraph를 호출해 각 LLM 응답을 확인합니다.")
st.caption(f"FastAPI 엔드포인트: {API_URL}")

if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_error" not in st.session_state:
    st.session_state.last_error = None
if "partial_data" not in st.session_state:
    st.session_state.partial_data = {}
if "partial_order" not in st.session_state:
    st.session_state.partial_order = []
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


def render_partial_results() -> str:
    """현재까지 수신한 부분 결과를 Markdown으로 변환한다."""

    if not st.session_state.partial_data:
        return "LLM 응답을 기다리는 중입니다..."

    lines: list[str] = []
    for model in st.session_state.partial_order:
        event = st.session_state.partial_data.get(model)
        if not event:
            continue
        answer = event.get("answer") or "응답 없음"
        status = event.get("status") or {}
        status_code = status.get("status") or "대기"
        detail = status.get("detail")
        status_text = f"{status_code} ({detail})" if detail else status_code
        lines.append(f"**{model}** — {status_text}\n\n{answer}")
    return "\n\n---\n\n".join(lines)


def format_summary_message(result: dict[str, Any]) -> str:
    """채팅 이력에 남길 요약 메시지를 Markdown 형태로 생성한다."""

    lines: list[str] = []
    order = result.get("order") or []
    if order:
        lines.append("**모델 완료 순서**: " + " → ".join(order))

    primary = result.get("primary_answer")
    if primary and primary.get("model"):
        status = primary.get("status") or {}
        status_code = status.get("status")
        detail = status.get("detail")
        status_text = f"{status_code} ({detail})" if detail else status_code
        lines.append(f"**최초 완료 모델**: {primary.get('model')} — {status_text or '상태 정보 없음'}")

    answers = result.get("answers") or {}
    if answers:
        lines.append("### 모델 응답")
        for model_name, answer in answers.items():
            lines.append(f"- **{model_name}**\n\n{answer or '응답 없음'}")
    else:
        lines.append("모델 응답이 없습니다.")

    api_status = result.get("api_status") or {}
    if api_status:
        lines.append("### API 상태")
        for model_name, status in api_status.items():
            status_code = status.get("status")
            detail = status.get("detail")
            status_text = f"{status_code} ({detail})" if detail else status_code
            lines.append(f"- **{model_name}**: {status_text}")

    errors = result.get("errors") or []
    if errors:
        lines.append("### 오류")
        for error in errors:
            model = error.get("model") or "알 수 없음"
            node = error.get("node") or "-"
            message = error.get("message") or "메시지 없음"
            lines.append(f"- **{model}** (노드: {node}): {message}")

    return "\n\n".join(lines)


chat_container = st.container()
with chat_container:
    if st.session_state.chat_history:
        for entry in st.session_state.chat_history:
            with st.chat_message(entry["role"]):
                st.markdown(entry["content"])
    else:
        st.info("질문을 입력하고 그래프를 실행해보세요.")
    partial_placeholder = st.empty()
    if st.session_state.partial_data:
        partial_placeholder.markdown(render_partial_results())

prompt = st.chat_input("무엇이든 물어보세요.")

if prompt is not None:
    question = prompt.strip()
    if not question:
        st.warning("질문을 입력해주세요.")
    else:
        logger.info("챗 입력 수신")
        st.session_state.chat_history.append({"role": "user", "content": question})
        st.session_state.last_error = None
        st.session_state.last_result = None
        st.session_state.partial_data = {}
        st.session_state.partial_order = []
        partial_placeholder.info("LLM 응답을 대기 중입니다.")
        try:
            with httpx.stream(
                "POST",
                API_URL,
                json={"question": question},
                headers={"Content-Type": "application/json"},
                timeout=180.0,
            ) as response:
                response.raise_for_status()
                for line in response.iter_text():
                    if not line:
                        continue
                    event = json.loads(line)
                    event_type = event.get("type", "partial")
                    if event_type == "partial":
                        model = event.get("model")
                        if model and model not in st.session_state.partial_order:
                            st.session_state.partial_order.append(model)
                        if model:
                            st.session_state.partial_data[model] = event
                            logger.debug("부분 응답 갱신: %s", model)
                        partial_placeholder.markdown(render_partial_results())
                    elif event_type == "summary":
                        st.session_state.last_result = event.get("result")
                        logger.info("요약 이벤트 수신")
                    elif event_type == "error":
                        error_message = event.get("message", "알 수 없는 오류가 발생했습니다.")
                        st.session_state.last_error = error_message
                        logger.warning("오류 이벤트 수신: %s", error_message)
                        continue
        except httpx.HTTPStatusError as http_error:
            response = http_error.response
            try:
                detail = response.json().get("detail") if response else str(http_error)
            except Exception:
                detail = str(http_error)
            status_text = response.status_code if response else "Unknown"
            st.session_state.last_error = f"요청 실패 (HTTP {status_text}): {detail}"
            logger.error("HTTP 오류: %s", st.session_state.last_error)
        except httpx.ConnectError:
            st.session_state.last_error = f"연결 오류: FastAPI 서버에 연결할 수 없습니다. URL을 확인하세요: {API_URL}"
            logger.error("FastAPI 연결 실패: %s", API_URL)
        except httpx.ReadTimeout:
            st.session_state.last_error = "시간 초과: 요청이 3분을 초과했습니다. 서버 상태를 확인하세요."
            logger.error("요청 시간 초과")
        except httpx.RequestError as request_error:
            st.session_state.last_error = f"알 수 없는 오류: {request_error}"
            logger.error("기타 요청 오류: %s", request_error)
        finally:
            if not st.session_state.partial_data:
                partial_placeholder.empty()
            else:
                partial_placeholder.markdown(render_partial_results())

result = st.session_state.last_result
if result:
    summary_markdown = format_summary_message(result)
    st.session_state.chat_history.append({"role": "assistant", "content": summary_markdown})
    st.session_state.last_result = None
    st.session_state.partial_data = {}
    st.session_state.partial_order = []
    partial_placeholder.empty()
    st.rerun()

if st.session_state.last_error:
    error_text = st.session_state.last_error
    st.session_state.chat_history.append({"role": "assistant", "content": f"❌ {error_text}"})
    st.session_state.last_error = None
    partial_placeholder.empty()
    st.rerun()
