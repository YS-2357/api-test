"""애플리케이션 설정 모듈."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """환경 변수를 통해 주입되는 기본 설정."""

    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8000
    streamlit_port: int = 8501
    streamlit_headless: bool = True

    env: Literal["local", "test", "prod"] = "local"
    langsmith_project: str = "API-LangGraph-Test"

    @staticmethod
    def from_env() -> Settings:
        """환경 변수와 `.env` 값을 기반으로 Settings를 생성한다.

        Returns:
            Settings: 현재 실행 환경에 맞춘 설정 인스턴스.
        """

        return Settings(
            fastapi_host=os.getenv("FASTAPI_HOST", "127.0.0.1"),
            fastapi_port=int(os.getenv("FASTAPI_PORT", "8000")),
            streamlit_port=int(os.getenv("STREAMLIT_SERVER_PORT", "8501")),
            streamlit_headless=os.getenv("STREAMLIT_SERVER_HEADLESS", "true").lower() == "true",
            env=os.getenv("APP_ENV", "local"),  # type: ignore[assignment]
            langsmith_project=os.getenv("LANGSMITH_PROJECT", "API-LangGraph-Test"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """전역적으로 재사용 가능한 Settings 인스턴스를 반환한다.

    Returns:
        Settings: 캐싱된 설정 인스턴스.
    """

    return Settings.from_env()
