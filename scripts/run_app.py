"""FastAPI와 Streamlit을 함께 실행하는 CLI 스크립트."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import uvicorn

from app.config import get_settings
from app.main import app as fastapi_app

BASE_DIR = Path(__file__).resolve().parents[1]
STREAMLIT_SCRIPT = BASE_DIR / "app" / "ui" / "streamlit_app.py"
FASTAPI_URL_FILE = BASE_DIR / ".fastapi_url"


def run_fastapi(host: str, port: int) -> None:
    """별도 스레드에서 FastAPI(Uvicorn) 서버를 실행한다.

    Args:
        host: FastAPI 서버가 바인딩할 호스트/IP.
        port: FastAPI 서버 포트.

    Returns:
        None
    """
    config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def ensure_streamlit_config() -> None:
    """Streamlit 실행에 필요한 최소 설정 파일을 생성한다.

    Returns:
        None
    """
    config_dir = Path.home() / ".streamlit"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"
    if not config_file.exists():
        config_file.write_text("[browser]\ngatherUsageStats = false\n")


def run_streamlit(port: int, env: dict[str, str]) -> None:
    """지정된 포트에서 Streamlit 앱을 실행한다.

    Args:
        port: Streamlit 서버 포트.
        env: subprocess에 전달할 환경변수 사본.

    Returns:
        None
    """
    ensure_streamlit_config()
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(STREAMLIT_SCRIPT),
        "--server.port",
        str(port),
        "--server.headless=true",
    ]
    subprocess.run(cmd, check=False, env=env)


def main() -> None:
    """FastAPI와 Streamlit 프로세스를 함께 부트스트랩한다.

    Returns:
        None
    """
    settings = get_settings()
    host = settings.fastapi_host
    fastapi_port = settings.fastapi_port
    streamlit_port = settings.streamlit_port

    fastapi_url = f"http://{host}:{fastapi_port}/api/ask"

    # FastAPI URL을 파일과 환경변수 모두에 저장
    try:
        FASTAPI_URL_FILE.write_text(fastapi_url)
    except OSError:
        pass

    # 환경변수 설정 (subprocess에 전달하기 위해 os.environ 직접 수정)
    os.environ["FASTAPI_URL"] = fastapi_url
    os.environ["STREAMLIT_SERVER_PORT"] = str(streamlit_port)
    os.environ["STREAMLIT_SERVER_HEADLESS"] = str(settings.streamlit_headless).lower()

    env = os.environ.copy()

    api_thread = threading.Thread(
        target=run_fastapi,
        args=(host, fastapi_port),
        name="fastapi-thread",
        daemon=True,
    )
    api_thread.start()

    print(f"[INFO] FastAPI: http://{host}:{fastapi_port}")
    print(f"[INFO] Streamlit: http://{host}:{streamlit_port}")
    print(f"[INFO] FastAPI URL이 설정되었습니다: {fastapi_url}")

    try:
        run_streamlit(streamlit_port, env)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
