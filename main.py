from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
from pathlib import Path

import uvicorn

from server import app as fastapi_app


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def choose_port(host: str, start_port: int, label: str) -> int:
    port = start_port
    while port < start_port + 20:
        if is_port_available(host, port):
            return port
        port += 1
    raise RuntimeError(f"{label} 포트를 확보할 수 없습니다. 시작 포트: {start_port}")


def run_fastapi(host: str, port: int):
    config = uvicorn.Config(fastapi_app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    server.run()


def ensure_streamlit_config():
    config_dir = Path.home() / ".streamlit"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.toml"
    if not config_file.exists():
        config_file.write_text("[browser]\ngatherUsageStats = false\n")


def run_streamlit(port: int, env: dict[str, str]):
    ensure_streamlit_config()
    script_path = Path(__file__).resolve().parent / "streamlit_app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script_path),
        "--server.port",
        str(port),
        "--server.headless=true",
    ]
    subprocess.run(cmd, check=False, env=env)


def main():
    host = os.getenv("FASTAPI_HOST", "127.0.0.1")
    desired_api_port = int(os.getenv("FASTAPI_PORT", "8000"))
    desired_ui_port = int(os.getenv("STREAMLIT_SERVER_PORT", "8501"))

    fastapi_port = choose_port(host, desired_api_port, "FastAPI")
    streamlit_port = choose_port(host, desired_ui_port, "Streamlit")

    fastapi_url = f"http://{host}:{fastapi_port}/api/ask"

    # FastAPI URL을 파일과 환경변수 모두에 저장
    config_path = Path(__file__).resolve().parent / ".fastapi_url"
    try:
        config_path.write_text(fastapi_url)
    except OSError:
        pass

    # 환경변수 설정 (subprocess에 전달하기 위해 os.environ 직접 수정)
    os.environ["FASTAPI_URL"] = fastapi_url
    os.environ["STREAMLIT_SERVER_PORT"] = str(streamlit_port)
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

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
