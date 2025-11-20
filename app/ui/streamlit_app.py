"""Streamlit 기반 멀티 LLM 비교 대시보드."""

from __future__ import annotations

import json
import os
from pathlib import Path

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


def render_partial_results() -> str:
    """현재까지 수신한 부분 결과를 Markdown으로 변환한다.

    Returns:
        str: 모델별 응답/상태를 정리한 Markdown 문자열.
    """
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

question = st.text_area(
    "질문",
    placeholder="무엇이든 물어보세요.",
    height=120,
    key="question_input",
)

live_updates_placeholder = st.empty()
live_updates_placeholder.info("LLM 응답을 대기 중입니다.")

if st.button("그래프 실행", type="primary"):
    logger.info("그래프 실행 버튼 클릭")
    st.session_state.last_error = None
    st.session_state.last_result = None
    st.session_state.partial_data = {}
    st.session_state.partial_order = []
    if not question or not question.strip():
        st.session_state.last_error = "질문을 입력해주세요."
    else:
        try:
            with st.spinner("그래프 실행 중... (부분 응답이 순차적으로 표시됩니다)"):
                with httpx.stream(
                    "POST",
                    API_URL,
                    json={"question": question.strip()},
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
                            live_updates_placeholder.markdown(render_partial_results())
                        elif event_type == "summary":
                            st.session_state.last_result = event.get("result")
                            logger.info("요약 이벤트 수신")
                        elif event_type == "error":
                            st.session_state.last_error = event.get("message", "알 수 없는 오류가 발생했습니다.")
                            # 오류 이벤트가 와도 요약을 위해 스트림을 계속 읽는다.
                            logger.warning("오류 이벤트 수신: %s", st.session_state.last_error)
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
                live_updates_placeholder.info("LLM 응답을 대기 중입니다.")
            else:
                live_updates_placeholder.markdown(render_partial_results())

if st.session_state.last_error:
    st.error(st.session_state.last_error)
elif st.session_state.partial_data:
    live_updates_placeholder.markdown(render_partial_results())

result = st.session_state.last_result
if result:
    completion_order = result.get("order") or []
    if completion_order:
        st.caption("모델 완료 순서: " + " → ".join(completion_order))
    errors = result.get("errors") or []
    if errors:
        st.warning(
            "일부 모델 호출에서 오류가 발생했습니다. 세부 정보는 아래 오류 목록을 확인하세요."
        )
    primary = result.get("primary_answer")
    if primary:
        st.subheader("최초 완료 모델")
        model_name = primary.get("model")
        st.write(
            f"- **{model_name}**: {primary.get('answer') or '응답 없음'}"
            if model_name
            else primary.get("answer") or "응답 없음"
        )
        status = primary.get("status") or {}
        if status:
            st.caption(
                f"상태: {status.get('status')} ({status.get('detail')})"
                if status.get("detail")
                else f"상태: {status.get('status')}"
            )

    st.subheader("모델 응답")
    answers = result.get("answers") or {}
    if answers:
        for model_name, answer in answers.items():
            with st.expander(model_name, expanded=False):
                st.write(answer or "응답 없음")
    else:
        st.info("응답 데이터가 없습니다.")

    st.subheader("API 상태")
    api_status = result.get("api_status") or {}
    if api_status:
        for model_name, status in api_status.items():
            status_code = status.get("status")
            detail = status.get("detail")
            st.write(f"- **{model_name}**: {status_code} ({detail})" if detail else f"- **{model_name}**: {status_code}")
    else:
        st.info("상태 데이터가 없습니다.")

    st.subheader("메시지 로그")
    messages = result.get("messages") or []
    if messages:
        for message in messages:
            st.write(f"{message.get('role')}: {message.get('content')}")
    else:
        st.info("메시지 로그가 없습니다.")

    if errors:
        st.subheader("오류 로그")
        for error in errors:
            model = error.get("model") or "알 수 없음"
            node = error.get("node") or "-"
            message = error.get("message") or "메시지 없음"
            st.write(f"- **{model}** (노드: {node}): {message}")
else:
    st.info("질문을 입력하고 그래프를 실행해보세요.")
