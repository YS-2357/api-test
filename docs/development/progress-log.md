# 개발 진행 로그

## 사용 방법
- 주요 결정/성과를 날짜순으로 기록하고 changelog와 연결한다.
- 각 항목은 **날짜 / 상태 요약 / 변경 사항 / 다음 단계** 형식으로 작성한다.

---

### 2025-11-19
- **상태 요약**: 서비스 출시 목표 확정 및 로드맵 수립
- **변경 사항**: 아키텍처 분리 방향 결정, DB/인증 요구사항 정의, `docs/roadmap-2025.md` 작성
- **다음 단계**: Phase 1 세부 이슈화, LangGraph 비동기화 검토, Streamlit UX 초안

### 2025-11-20 (오전)
- **상태 요약**: 코드 패키지화/스트리밍 전환/문서 보강
- **변경 사항**:
  1. `app/`, `scripts/` 구조 도입과 실행 스크립트 단순화
  2. LangGraph partial 스트리밍 + FastAPI StreamingResponse + Streamlit 실시간 표시 구현
  3. README/Changelog 업데이트 및 주요 모듈 docstring/주석 추가
- **다음 단계**:
  1. Phase 1 DB/인증 스켈레톤 파일 추가
  2. SSE/WebSocket 등 고급 스트리밍 프로토콜 검토
  3. 간단한 e2e 테스트 스크립트/모니터링 기준 마련

### 2025-11-20 (오후)
- **상태 요약**: LangGraph 병렬/비동기 처리 아키텍처 검토 및 LLM 확장 계획 수립
- **주요 논의 내용**:
  1. **LangGraph 병렬 처리 방법**
     - 기존 코드의 잘못된 병렬 처리 패턴 발견 (단순 add_edge는 병렬 실행 안 됨)
     - **Send API** 사용이 진정한 병렬 실행 방법임을 확인
     - `operator.add`를 활용한 State 병합 패턴 학습

  2. **비동기(async/await) 적용**
     - 노드 함수를 `async def`로 정의
     - LLM 호출: `llm.ainvoke()` 사용
     - 벡터 스토어: `vectorstore.asimilarity_search()` 사용
     - 그래프 실행: `app.ainvoke()` / `app.astream()` 사용
     - 성능 개선: 순차 9초 → 병렬 4초 예상

  3. **프로덕션 확장성 전략**
     - 스트리밍으로 실시간 응답 (사용자 경험 향상)
     - LangGraph Cloud로 자동 스케일링
     - 체크포인터(PostgresSaver)로 중단/재개 지원
     - Redis 캐싱으로 중복 호출 방지

  4. **LLM 확장 계획**
     - **현재 사용 중 (5개)**: OpenAI, Gemini, Claude, Upstage, Perplexity
     - **추가 추천 (LangChain 공식 지원)**:
       - **Tier A (우선 추가)**:
         - Mistral AI (GDPR 준수, 보안성)
         - Groq (초고속 추론, 무료 티어)
         - Cohere (엔터프라이즈, RAG 특화)
       - **Tier B (선택적)**: Together AI, Fireworks AI
     - **Perplexity 처리**:
       - LangChain 공식 미지원 (테디노트 커스텀 모듈 사용)
       - 유지 권장 (검색 통합 기능 우수)
       - Tavily Search 추가로 백업/보완 고려

  5. **최종 권장 구성 (7개 LLM)**:
     ```
     1. Claude (Anthropic)    - 안전성, 윤리적 응답
     2. GPT (OpenAI)          - 범용성, 안정성
     3. Gemini (Google)       - 무료, 다국어
     4. Upstage Solar         - 한국어 특화
     5. Mistral AI            - GDPR/보안 (추가)
     6. Groq                  - 속도/무료 (추가)
     7. Cohere                - 엔터프라이즈 (추가)

     검색: Perplexity 유지 or Tavily 추가/대체
     ```

- **기술적 결정**:
  - Send API + async/await 조합으로 최고 성능 확보
  - FastAPI 비동기 엔드포인트로 동시 요청 처리
  - LangChain 공식 지원 LLM 우선 사용 (유지보수성)

- **다음 단계**:
  1. `app/services/langgraph.py`에 Send API 패턴 적용
  2. 모든 노드 함수를 `async def`로 변환
  3. Mistral, Groq, Cohere 통합 구현
  4. 비동기 스트리밍 성능 테스트
  5. 체크포인터 설정 (PostgreSQL)

### 2025-11-20 (야간)
- **상태 요약**: 스트리밍 흐름 외 사용되지 않는 LangGraph 동기 실행 헬퍼를 제거해 코드 경로를 단일화
- **변경 사항**:
  1. `_aggregate_stream()`/`run_graph()`를 삭제하고 FastAPI 스트리밍만 남김
  2. `app/services/__init__.py`에서 `run_graph` export 제거
- **다음 단계**:
  1. Tavily 검색 노드 추가 준비 (상태 필드 이미 확보)
  2. 비동기/Send API 리팩터링 작업에 돌입

### 2025-11-21
- **상태 요약**: LangGraph 노드부터 FastAPI 스트림까지 전체 호출 체인을 비동기/Send API 기반 병렬 실행으로 전환
- **변경 사항**:
  1. 모든 LLM 노드를 `async def`로 변경하고 공용 `_ainvoke` 헬퍼로 `ainvoke` 우선 호출, 미지원 모델은 스레드풀에서 실행
  2. Send API 기반 `dispatch_llm_calls`를 통해 `init_question`에서 5개 LLM 노드를 동시에 fan-out
  3. `stream_graph`를 `app.astream` 기반 비동기 제너레이터로 수정해 LangGraph 이벤트를 asyncio 스트림으로 노출
  4. `/api/ask` 라우터의 스트리밍 응답을 비동기 제너레이터로 재작성해 FastAPI가 이벤트를 즉시 push하고, 완료 순서/최초 응답/오류 정보를 요약에 포함
  5. Streamlit 클라이언트를 `httpx.stream()` 기반으로 교체하고 UI에 최초 완료 모델과 오류 로그를 강조
  6. `app/logger.py` 이모지 로거를 추가하고 서비스/라우터/Streamlit/실행 스크립트 전반에 적용해 실행 상황을 콘솔에서 모니터링 가능
- **다음 단계**:
  1. Streamlit 클라이언트에서 asyncio/HTTPX 전환 여부 평가
  2. Send API fan-out 이후 결과를 집계/우선순위화할 후처리 전략 검토
  3. 오류 이벤트를 기반으로 자동 재시도/알림 훅을 붙이는 방안 모색
