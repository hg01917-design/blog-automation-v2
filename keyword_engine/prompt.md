# 천하무적 키워드 엔진 — 자동 실행 프롬프트

## 목표
AdSense 수익화 Tistory 블로그들의 RSS를 직접 수집 → 글 제목에서 키워드 역추출 → 기회점수 계산 → Notion 키워드 큐에 적재

API 비용 없이 WebFetch로만 동작.

---

## 블로그별 카테고리 (정확히 지킬 것)

| 블로그 ID | 주제 | 해당 키워드 예시 |
|-----------|------|-----------------|
| goodisak | IT/가전 추천·비교 | 노트북 추천, 스마트폰 비교, 이어폰 추천 |
| nolja100 | 국내외 여행 | 제주도 여행, 맛집, 가볼만한곳, 올레길 |
| salim1su | 고정지출 절약 | 전기요금 절약, 통신비 줄이기, 관리비, 가스비, 넷플릭스 요금제, 구독서비스 해지 |
| baremi542 | 정부지원금·복지 | 청년월세지원, 근로장려금, 실업급여, 지원금 신청 |

---

## 실행 순서

### 1단계: Tistory RSS 수집
아래 Tistory 블로그들의 RSS(`{url}/rss`)를 WebFetch로 가져와서 글 제목 전부 수집.
각 블로그당 최대 50개 제목.

**IT/가전 블로그:**
- https://junggutv.tistory.com/rss
- https://techterview.tistory.com/rss
- https://bllaads.tistory.com/rss
- https://bespoker4.tistory.com/rss

**여행 블로그:**
- https://springaria0199.tistory.com/rss
- https://altrip.tistory.com/rss
- https://tamnastory.tistory.com/rss

**고정지출/생활비 절약 블로그:**
- https://moonwalker.tistory.com/rss
- https://changeoflife.tistory.com/rss
- https://goodbypoor.tistory.com/rss

**정부지원금 블로그:**
- https://the-greatman.tistory.com/rss
- https://moneymakers.tistory.com/rss

### 2단계: 키워드 추출
수집된 제목들에서 검색 키워드 후보 추출:
- 제목 전체 또는 구분자(|, -, :)로 나뉜 앞부분
- 2~3어절 조합
- 한글 2자 이상 포함 필수
- 문장 조각(어미로 끝나는 것) 제외

### 3단계: 블로그별 키워드 분류
각 키워드를 위 카테고리 표에 맞게 블로그에 배정.
**salim1su는 반드시 고정지출 절약 관련 키워드만** (뷰티, 건강보조제, 여행 등 제외).

### 4단계: Notion 키워드 큐 적재
Notion DB ID: `d6bb5b75-3f1b-4963-891d-e02427411276`

각 키워드를 아래 형식으로 Notion에 추가:
- 키워드: (키워드명)
- 블로그: (블로그 ID)
- 상태: 대기
- 유형: 에버그린 또는 트렌딩
- 수집일: 오늘 날짜
- 메모: "천하무적엔진"

중복 체크: 이미 DB에 있는 키워드는 스킵.

---

## 완료 후
총 수집된 키워드 수와 블로그별 적재 수 요약 출력.
