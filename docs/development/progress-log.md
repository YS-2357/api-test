# 개발 진행 로그

## 사용 방법
- 주요 결정/성과를 날짜순으로 기록하고 changelog와 연결한다.
- 각 항목은 **날짜 / 상태 요약 / 변경 사항 / 다음 단계** 형식으로 작성한다.

---

### 2025-11-19
- **상태 요약**: 서비스 출시 목표 확정 및 로드맵 수립
- **변경 사항**: 아키텍처 분리 방향 결정, DB/인증 요구사항 정의, `docs/roadmap-2025.md` 작성
- **다음 단계**: Phase 1 세부 이슈화, LangGraph 비동기화 검토, Streamlit UX 초안

### 2025-11-20
- **상태 요약**: 코드 패키지화/스트리밍 전환/문서 보강
- **변경 사항**:
  1. `app/`, `scripts/` 구조 도입과 실행 스크립트 단순화
  2. LangGraph partial 스트리밍 + FastAPI StreamingResponse + Streamlit 실시간 표시 구현
  3. README/Changelog 업데이트 및 주요 모듈 docstring/주석 추가
- **다음 단계**:
  1. Phase 1 DB/인증 스켈레톤 파일 추가
  2. SSE/WebSocket 등 고급 스트리밍 프로토콜 검토
  3. 간단한 e2e 테스트 스크립트/모니터링 기준 마련

