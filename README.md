# API LangGraph Test

FastAPI와 Streamlit 기반의 멀티 LLM 비교 테스트 애플리케이션

## 📋 프로젝트 개요

5개의 주요 LLM API(OpenAI, Google Gemini, Anthropic Claude, Upstage Solar, Perplexity)를 병렬로 호출하여 동일한 질문에 대한 각 모델의 응답을 비교할 수 있는 웹 애플리케이션입니다.

## 🏗️ 아키텍처

- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: Streamlit
- **워크플로우**: LangGraph (병렬 실행)
- **추적/로깅**: LangSmith
- **배포**: 로컬 (단일 프로세스에서 FastAPI + Streamlit 동시 실행)

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 가상환경 생성 (이미 있으면 생략)
python -m venv .venv

# 가상환경 활성화
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일에 필요한 API 키 설정:

```env
OPENAI_API_KEY=your-openai-key
GOOGLE_API_KEY=your-google-key
ANTHROPIC_API_KEY=your-anthropic-key
UPSTAGE_API_KEY=your-upstage-key
PPLX_API_KEY=your-perplexity-key
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=API-LangGraph-Test
```

### 3. 실행

```bash
# 가상환경에서 실행
.venv/Scripts/python.exe main.py

# 또는
python main.py
```

서버가 시작되면:
- **FastAPI**: http://127.0.0.1:8001
- **Streamlit**: http://localhost:8502

## 📁 프로젝트 구조

```
api-test/
├── main.py                 # 메인 실행 파일 (FastAPI + Streamlit 통합)
├── server.py               # FastAPI 서버 정의
├── streamlit_app.py        # Streamlit UI
├── langgraph_service.py    # LangGraph 워크플로우 및 LLM 호출 로직
├── notebooks/              # Jupyter 노트북 (개발/테스트용)
│   └── api_langgraph_test.ipynb
├── docs/                   # 문서
│   └── changelog/          # 날짜별 변경 이력
└── .env                    # 환경변수 (API 키 등)
```

## 🔧 주요 기능

### 1. 멀티 LLM 병렬 호출
- OpenAI GPT-5-nano
- Google Gemini 2.5 Flash Lite
- Anthropic Claude Haiku 4.5
- Upstage Solar Mini
- Perplexity Sonar

### 2. LangGraph 워크플로우
- 질문 초기화 → 5개 LLM 병렬 호출 → 응답 수집 및 요약
- 각 LLM의 성공/실패 상태 추적
- 에러 발생 시에도 다른 모델의 응답은 정상 수집

### 3. LangSmith 추적
- 모든 LLM 호출이 LangSmith에 자동 기록
- 프로젝트: `API-LangGraph-Test`
- 토큰 사용량, 응답 시간, 에러 로그 추적

### 4. Streamlit UI
- 간단한 질문 입력 인터페이스
- 모델별 응답 비교 (Expander로 구성)
- API 상태 코드 표시
- 에러 메시지 상세 표시

## 🔗 API 엔드포인트

### Health Check
```bash
GET /health
```

### 질문 처리
```bash
POST /api/ask
Content-Type: application/json

{
  "question": "당신의 질문을 입력하세요"
}
```

**응답 예시:**
```json
{
  "question": "AI란 무엇인가?",
  "answers": {
    "OpenAI": "AI는...",
    "Gemini": "AI는...",
    "Anthropic": "AI는...",
    "Perplexity": "AI는...",
    "Upstage": "AI는..."
  },
  "api_status": {
    "OpenAI": {"status": 200, "detail": "stop"},
    "Gemini": {"status": 200, "detail": "STOP"},
    ...
  },
  "messages": [...]
}
```

## 📝 변경 이력

상세한 날짜별 변경 이력은 [`docs/changelog/`](docs/changelog/) 디렉토리를 참조하세요.

## 🛠️ 개발 가이드

### 노트북 기준 개발
- `notebooks/api_langgraph_test.ipynb`가 기준 구현
- 노트북에서 검증된 코드만 프로덕션 코드로 이식
- LangSmith 로깅 설정은 노트북 기준 유지

### 코드 수정 시 주의사항
1. 노트북 파일은 수정하지 않음 (기준 유지)
2. 모델명은 노트북과 동일하게 유지
3. LangSmith 프로젝트명: `API-LangGraph-Test`
4. UUID v7 사용 (LangSmith 권장)

## ⚠️ 알려진 이슈

### 1. 응답 시간
- 5개 LLM을 병렬로 호출하므로 1~2분 소요
- Streamlit timeout: 180초 (3분)

### 2. 패키지 호환성
- `numpy` 버전 충돌 가능 → 가상환경 사용 필수
- `langchain-upstage`의 의존성 버전 주의

## 📄 라이선스

MIT License

## 👥 기여

버그 리포트 및 기능 제안은 이슈로 등록해주세요.