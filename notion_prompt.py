"""Notion API에서 블로그별 프롬프트를 가져와 {keyword} 치환"""
import re
import requests
import os
from pathlib import Path
from config import PROMPT_PAGES

# .env 파일 로드 (번들 실행 시 PROJECT_ROOT 우선)
import os as _os
_env_path = Path(_os.environ.get("BLOG_AUTO_PROJECT_ROOT", str(Path(__file__).parent))) / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _get_token():
    """환경변수에서 Notion 토큰 읽기"""
    token = os.environ.get("NOTION_TOKEN") or os.environ.get("NOTION_API_KEY")
    if not token:
        raise ValueError("NOTION_TOKEN 환경변수가 설정되지 않았습니다.")
    return token


def _headers():
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _blocks_to_text(blocks):
    """Notion 블록 리스트 → 플레인 텍스트 변환"""
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        data = block.get(btype, {})
        rich_texts = data.get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_texts)

        if btype == "heading_2":
            lines.append(f"\n## {text}")
        elif btype == "heading_3":
            lines.append(f"\n### {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"- {text}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {text}")
        elif btype == "divider":
            lines.append("---")
        elif btype == "code":
            lang = data.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif btype == "paragraph":
            lines.append(text)
        # 자식 블록이 있으면 재귀
        if block.get("has_children"):
            child_resp = requests.get(
                f"{NOTION_API}/blocks/{block['id']}/children",
                headers=_headers(),
            )
            if child_resp.ok:
                child_blocks = child_resp.json().get("results", [])
                lines.append(_blocks_to_text(child_blocks))

    return "\n".join(lines)


def fetch_prompt(blog_id: str, keyword: str, on_log=None) -> str:
    """Notion 페이지에서 프롬프트를 가져와 {keyword} 치환 후 반환"""
    def log(msg):
        if on_log:
            on_log(msg)

    page_id = PROMPT_PAGES.get(blog_id)
    if not page_id:
        raise ValueError(f"프롬프트 페이지 없음: {blog_id}")

    log(f"[Notion] {blog_id} 프롬프트 페이지 가져오는 중...")

    # 블록 children 가져오기
    url = f"{NOTION_API}/blocks/{page_id}/children?page_size=100"
    resp = requests.get(url, headers=_headers())
    resp.raise_for_status()
    blocks = resp.json().get("results", [])

    # "🔑 핵심 원칙" 섹션과 "글 생성 프롬프트" 섹션 추출
    principle_lines = []
    prompt_lines = []
    capture_principle = False
    capture_prompt = False
    for block in blocks:
        btype = block.get("type", "")
        data = block.get(btype, {})
        rich_texts = data.get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_texts)

        if btype == "heading_2":
            if "핵심 원칙" in text:
                capture_principle = True
                capture_prompt = False
                continue
            elif "글 생성 프롬프트" in text:
                capture_prompt = True
                capture_principle = False
                continue
            elif capture_principle:
                # 다음 heading_2를 만나면 핵심 원칙 캡처 중단
                capture_principle = False

        if capture_principle:
            if btype == "heading_3":
                principle_lines.append(f"\n### {text}")
            elif btype == "bulleted_list_item":
                principle_lines.append(f"- {text}")
            elif btype == "numbered_list_item":
                principle_lines.append(f"1. {text}")
            elif btype == "divider":
                principle_lines.append("---")
            elif btype == "code":
                lang = data.get("language", "")
                principle_lines.append(f"```{lang}\n{text}\n```")
            elif btype == "paragraph":
                principle_lines.append(text)
            if block.get("has_children"):
                child_resp = requests.get(
                    f"{NOTION_API}/blocks/{block['id']}/children",
                    headers=_headers(),
                )
                if child_resp.ok:
                    for cb in child_resp.json().get("results", []):
                        cbtype = cb.get("type", "")
                        cdata = cb.get(cbtype, {})
                        ctext = "".join(rt.get("plain_text", "") for rt in cdata.get("rich_text", []))
                        if cbtype == "bulleted_list_item":
                            principle_lines.append(f"  - {ctext}")
                        elif cbtype == "numbered_list_item":
                            principle_lines.append(f"  1. {ctext}")
                        elif cbtype == "paragraph" and ctext:
                            principle_lines.append(f"  {ctext}")

        if capture_prompt:
            if btype == "heading_2":
                prompt_lines.append(f"\n## {text}")
            elif btype == "heading_3":
                prompt_lines.append(f"\n### {text}")
            elif btype == "bulleted_list_item":
                prompt_lines.append(f"- {text}")
            elif btype == "numbered_list_item":
                prompt_lines.append(f"1. {text}")
            elif btype == "divider":
                prompt_lines.append("---")
            elif btype == "code":
                lang = data.get("language", "")
                prompt_lines.append(f"```{lang}\n{text}\n```")
            elif btype == "paragraph":
                prompt_lines.append(text)
            if block.get("has_children"):
                child_resp = requests.get(
                    f"{NOTION_API}/blocks/{block['id']}/children",
                    headers=_headers(),
                )
                if child_resp.ok:
                    for cb in child_resp.json().get("results", []):
                        cbtype = cb.get("type", "")
                        cdata = cb.get(cbtype, {})
                        ctext = "".join(rt.get("plain_text", "") for rt in cdata.get("rich_text", []))
                        if cbtype == "bulleted_list_item":
                            prompt_lines.append(f"  - {ctext}")
                        elif cbtype == "numbered_list_item":
                            prompt_lines.append(f"  1. {ctext}")
                        elif cbtype == "paragraph" and ctext:
                            prompt_lines.append(f"  {ctext}")

    principle_text = "\n".join(principle_lines).strip()
    prompt_text = "\n".join(prompt_lines).strip()

    # 핵심 원칙이 있으면 프롬프트 맨 앞에 추가
    if principle_text:
        prompt_text = f"## 에이전트 행동 원칙\n{principle_text}\n\n---\n\n{prompt_text}"

    if not prompt_text:
        raise ValueError(f"프롬프트 내용이 비어있습니다: {blog_id}")

    # 존댓말 규칙 추가
    prompt_text += "\n\n**문체 규칙**: 모든 문장은 반드시 존댓말로 작성 (~습니다, ~세요, ~해요)"

    # 제목 금지패턴
    prompt_text += "\n\n**제목 금지패턴**: 제목에 완벽정리/총정리/완벽가이드/꿀팁/알아보기/N가지/N종류 절대 사용 금지"

    # 글자수 규칙
    prompt_text += "\n\n**글자수 규칙**: 반드시 3000자 이상 작성할 것. 현재 글자수를 중간중간 확인하면서 작성. 3000자 미만이면 내용을 보충해서 반드시 3000자를 넘길 것."

    # 태그 규칙
    prompt_text += "\n\n**태그 규칙**: ===태그=== 섹션에 반드시 10개 이상의 태그를 작성할 것."

    # 본문 형식 규칙 추가
    prompt_text += """

**본문 출력 형식 규칙**:
- H2 소제목은 반드시 ## 으로 시작 (예: ## 아이패드 추천 이유)
- 이미지 삽입 위치는 반드시 {{이미지N}} 으로 표시 (예: {{이미지1}}, {{이미지2}})
- 애드센스 삽입 위치는 반드시 [애드센스] 으로 표시. 반드시 소제목(##) 바로 아래 또는 표 바로 아래에만 배치. 링크·이미지 근처 절대 금지
- 표는 마크다운 표 형식으로 작성 (| 열1 | 열2 | 형식)
- HTML 태그 사용 금지 — 위 마커 형식만 사용
- 일반 텍스트는 그대로 작성

**이미지 다양성 규칙 (Gemini 프롬프트 작성 시 필수)**:
- 이미지1과 이미지2는 반드시 완전히 다른 시각적 주제로 생성할 것
- 같은 오브젝트(예: 전화기, 서류, 달력)를 두 이미지에 반복 사용 절대 금지
- 이미지1: 신청자격·조건 관련 — 서류/체크리스트/사람 등 구체적 장면
- 이미지2: 금액·혜택·절차 관련 — 달력/지폐/통장/온라인신청 화면 등 다른 소재
- Gemini 프롬프트에 배경색, 오브젝트, 분위기까지 구체적으로 명시할 것
  좋은 예: "A clean infographic showing a checklist on blue background, Korean government document style"
  나쁜 예: "An image related to unemployment benefits" (너무 추상적 → 같은 이미지 반복 생성됨)"""

    # AI 패턴 금지 규칙 (강화)
    prompt_text += (
        "\n\n**AI 패턴 금지 (강화)**: 다음 표현 절대 사용 금지 → "
        "'물론입니다', '알아보겠습니다', '살펴보겠습니다', '정리해보겠습니다', "
        "'완벽정리', '총정리', '완벽가이드', '중요합니다', '필수입니다', "
        "'~해야 합니다', '다양한', '효과적인', '최적의', '첫째/둘째/셋째 나열', "
        "'~드립니다 남발'. 실제 사람이 쓴 것처럼 자연스러운 구어체로 작성."
    )

    # 블로그별 페르소나 규칙
    if blog_id == "goodisak":
        prompt_text += """

**IT 블로그 스펙/가격 표 규칙 (goodisak)**:
- 판단 기준: '내가 이 IT 블로그 운영자라면 이렇게 쓸까?' 항상 자문하며 작성
- 제품 스펙 또는 가격 비교 표가 포함된 경우, 표 바로 아래에 반드시 다음 문구를 추가:
  ※ 위 표의 스펙 및 가격은 참고용이며, 실제와 다를 수 있습니다. 구매 전 반드시 공식 페이지에서 최신 정보를 확인하세요."""

    elif blog_id == "salim1su":
        prompt_text += """

**살림 페르소나 규칙 (daonna525)**:
- 판단 기준: '내가 이 살림 블로그 운영자(하린)라면 이렇게 쓸까?' 항상 자문하며 작성
- ~더라구요, ~했어요, ~이에요, ~거든요 말투 사용 (딱딱한 ~습니다 최소화)
- 실제 살림 경험담처럼 자연스럽게 (예: "저도 처음엔 몰랐는데 해보니까 진짜 달라지더라구요")
- 숫자/금액은 구체적으로 (예: "한 달에 약 3만원 절약됐어요")

**AI 문체 금지 (salim1su 강화)**:
다음 표현 절대 사용 금지:
- "~해보시는 건 어떨까요?"
- "도움이 되셨으면 합니다"
- "함께 알아보겠습니다" / "함께 살펴보겠습니다"
- "오늘은 ~에 대해 알아볼게요" (인트로 첫 문장으로 사용 금지)
- "이상으로 ~을 마치겠습니다"
- "살펴보겠습니다" / "알아보겠습니다"

**인트로 유형 (매 글마다 아래 4가지 중 다른 유형 사용, 순환)**:
A. 질문형: "혹시 ~해보신 적 있으세요?"
B. 상황 묘사형: "지난달 고지서 보다가 깜짝 놀랐어요."
C. 결론 먼저형: "이거 알고 나서 매달 2만원 줄었어요."
D. 공감 유도형: "저만 이런 거 헷갈리는 거 아니죠?"

**마무리 유형 (매 글마다 아래 4가지 중 다른 유형 사용, 순환)**:
A. 공감 유도형: "같은 고민 있으신 분들께 조금이나마 도움이 됐으면 해요."
B. 다음 글 예고형: "다음엔 ~하는 법도 써볼게요."
C. 자기 고백형: "저도 아직 못 한 것들이 있어서 같이 해나가려고요."
D. 정보 요약형: "오늘 핵심만 다시 정리하면 ~"

**마무리 절대 금지 표현 (반복 AI 패턴)**:
- "저도 참고해보고싶어요"
- "댓글로 알려주세요" / "댓글 남겨주세요" / "댓글로 알려줘요"
- "공감 눌러주세요" / "좋아요 눌러주세요"
- "궁금한 점은 댓글로" / "의견 남겨주세요"
- 위 마무리 유형(A~D)에 없는 어떤 '독자에게 행동 요청' 문구도 금지

**네이버 제한어 규칙 (salim1su 필수 — 위반 시 저품질 처리)**:
절대 사용 금지:
- 의료: 유발, 진단, 처방, 치료, 완치, 증상, 임상, 효과 있음
- 법률/금융: 상담, 보장, 환급 확정, 수익 보장
- 과장: 무조건, 반드시, 100%, 즉시 효과, 유일한

반드시 아래 대체 표현으로 바꿔 쓸 것:
- "효과 있음" → "도움이 될 수 있음"
- "치료" → "관리"
- "보장" → "가능성"
- "무조건" → "대부분의 경우"
- "반드시" → "웬만하면" 또는 삭제
- "100%" → "대부분" 또는 구체적 수치로 교체
- "즉시 효과" → "빠르게 확인 가능"
- "유일한" → "대표적인"

**네이버 모바일 문장 스타일 (salim1su 필수)**:
- 기본: 한 문장 = 한 줄, 짧게 끊기 (20자 내외)
- 단, 리듬이 너무 일정하면 AI 티가 남 — 가끔 두 문장을 같은 줄에 붙이거나 조금 긴 문장을 섞어서 자연스러운 리듬 불규칙성을 만들 것
- 한 문단 = 2~3문장 최대, 문단 사이 빈 줄 1개
- 줄글로 이어쓰기 절대 금지
- 좋은 예시 (리듬 불규칙):
  "관리비 고지서를 처음 제대로 뜯어봤어요.
  항목이 생각보다 너무 많더라구요. 전기, 수도, 가스는 기본이고
  청소비에 경비비, 장기수선충당금까지요.
  진짜 몰랐어요."
- 나쁜 예시 (리듬 너무 일정 — AI 티):
  "관리비 고지서를 처음 뜯어봤어요.
  항목이 많더라구요.
  전기, 수도, 가스 기본이고요.
  청소비도 있었어요."

**제목 규칙 (salim1su)**:
- 메인키워드는 반드시 제목 맨 앞에 위치
- 타깃/상황 + 세부키워드 조합으로 구체성 확보
  - 상황형: '전기요금 고지서 받고 깜짝 놀란 분들을 위한 절약법'
  - 문제형: '도시가스 요금 갑자기 올랐을 때 확인할 것'
  - 인구통계는 검색 의도와 명확히 맞을 때만 사용
- 금지 패턴: 완벽정리/총정리/완벽가이드/N가지/N종류
- 40자 이내 유지

**salim1su 애드센스 규칙**:
- [애드센스] 마커 절대 사용 금지 — 네이버 블로그는 애드센스 미적용

**salim1su 이미지 규칙 (필수)**:
- H2 소제목 개수만큼 이미지를 생성할 것 (H2가 4개면 이미지 4개)
- 각 H2 소제목 바로 아래에 {{이미지N}} 배치
- 이미지 파일명은 반드시 영문으로 작성 (예: electricity-saving-tips-01.jpg)
- 각 이미지의 Gemini 프롬프트는 해당 H2 섹션 내용을 구체적으로 묘사할 것
- 모든 이미지는 시각적으로 완전히 다른 주제로 생성할 것"""
    elif blog_id == "nolja100":
        prompt_text += """

**여행 블로그 지은 페르소나 규칙 (nolja100)**:
- 페르소나: 지은 (32세, 여행을 사랑하는 콘텐츠 플래너 — 설레는 여행 정보를 친구에게 알려주듯 작성)
- 판단 기준: '내가 이 여행 블로그 운영자라면 이렇게 쓸까?' 항상 자문하며 작성
- 문체: 따뜻하고 생동감 있는 구어체 (~거든요, ~더라고요, ~이에요, ~해요) 위주, ~입니다/~합니다 최소화
- 독자에게 말 걸듯이: "여기 진짜 예쁜 곳이에요", "이 코스 강추예요", "알아두면 유용한 팁이에요" 같은 표현 활용
- 직접 방문 주장 금지 ("직접 가봤어요", "제가 먹어봤는데" 같은 체험 표현 금지) — 대신 "알아보니~", "찾아보니~", "후기를 보면~" 형태로 자연스럽게
- 불확실한 수치(입장료/운영시간)는 "기준" 또는 "변동 가능" 명시
- 조작된 고유명사·주소·가격 절대 금지 (환각 엄금)
- 숙소 관련 키워드 감지 시 본문 말미에 Agoda 링크 형식 안내 삽입: "추천 숙소: [호텔명](agoda affiliate link) (최저 00원부터)"

**여행 블로그 제목 규칙 (nolja100)**:
- 메인키워드는 반드시 제목 맨 앞에 위치
- 세부키워드는 독자가 실제로 검색할 법한 자연스러운 표현 사용
  - 나쁜 예: '일본여행 직장인 오사카 코스' (대상을 그대로 나열)
  - 좋은 예: '오사카 2박3일 코스 추천 | 짧은 휴가 일정 완성' (검색 의도에 맞게)
- 직장인/주부/혼자 등 대상은 제목에 직접 넣지 말고, 검색 의도에 자연스럽게 녹여낼 것
- 40자 이내 유지
- 제목에 숫자+일정, 지역명, 핵심 정보(코스/예산/숙소 등) 조합으로 구체성 확보"""
    elif blog_id == "baremi542":
        prompt_text += """

**정부지원금 블로그 페르소나 규칙 (baremi542)**:
- 페르소나: 정부 혜택을 직접 찾아서 정리하는 블로그 운영자 본인 시점
- 정확한 정책명·지원금액·신청기간 반드시 명시. 불확실한 정보는 "확인 필요" 표기
- 공식 출처(bokjiro.go.kr, gov.kr, korea.kr 등) 기반으로 작성
- 네이버쇼핑 언급 절대 금지
- 콜투액션 최대 2개 (본문 상단+하단): [신청하러 가기](공식URL) 형식
- 확인되지 않은 수치·날짜 단정 금지
- [애드센스] 마커는 반드시 소제목(##) 바로 아래 또는 표 바로 아래에만 배치. 링크·이미지 근처 절대 금지

**Rank Math SEO 핵심 규칙 (baremi542) — 90점 이상 목표**:

[키워드 규칙]
- 본문 첫 문장(50자 이내)에 메인 키워드 '{keyword}'를 정확히 그대로 포함 (띄어쓰기·철자 변형 절대 금지)
  예시: '{keyword}를 신청하려는 분들을 위해 직접 정리해봤어요.'
- 본문 전체에서 '{keyword}'를 최소 8회 이상 사용 (키워드 밀도 1~3% 유지)
- H2 소제목 전체에 '{keyword}' 반드시 포함
  좋은 예: ## {keyword} 신청방법 — 단계별 안내
  나쁜 예: ## 신청방법 (키워드 없음 → Rank Math 감점)
- H3 소제목에도 '{keyword}' 2회 이상 포함

[구조 규칙]
- H2 소제목: 3~4개 (모두 키워드 포함)
- H3 소제목: H2당 2~3개씩, 총 8개 이상 (키워드 2개 이상 포함)
- 이미지: {{이미지1}} {{이미지2}} 2개 이상 (첫 번째 이미지는 첫 H2 바로 아래)
- 마크다운 표: 1개 이상 (5행 이상)
- 최소 800 단어 이상 (한글 기준 약 2400자 이상)

[링크 규칙]
- 내부 링크: baremi542.com의 **특정 포스트 URL** 1개 이상
  (홈페이지 URL baremi542.com 단독은 Rank Math 내부링크 미인식 — 반드시 포스트 경로 포함)
  예: [근로장려금 신청방법](https://baremi542.com/근로장려금-신청자격/)
- 외부 공식 링크: 정부/공공기관 URL 1개 이상 (DoFollow)

**Rank Math 90점 고정 구조 템플릿 (이 순서 반드시 준수)**:

━━ 도입부 ━━
{keyword}로 시작하는 첫 문장 (1~2문장)
예: "{keyword}를 신청하려는 분들이 많아서 2026년 최신 정보로 정리해봤어요."

━━ 목차 (## 목차) ━━
- [{keyword} 신청자격](#section-1)
- [{keyword} 지원금액 및 핵심 정보](#section-2)
- [{keyword} 신청방법](#section-3)
- [{keyword} 주의사항 및 자주 묻는 질문](#section-4)

━━ baremi542 내부 링크 단락 ━━
관련 정부지원금 정보: [관련글 제목](https://baremi542.com/관련글-슬러그/) 형식으로 자연스럽게 삽입

━━ ## {keyword} 신청자격 — [구체적 부제목] ━━
{{이미지1}}
### {keyword} 대상 조건
- 내용 (100자 이상)
### {keyword} 소득 기준
- 내용 (100자 이상)
### 신청 제외 대상
- 내용 (100자 이상)
[애드센스]

━━ ## {keyword} 지원금액 및 핵심 정보 ━━
{{이미지2}}
### {keyword} 지원 금액
| 구분 | 금액 | 비고 |
|---|---|---|
| 항목1 | 금액1 | 설명 |
(5행 이상)
### {keyword} 지급 방식
- 내용
### 지원 기간
- 내용
[애드센스]
외부 공식 링크: [공식 신청 페이지](공식URL)

━━ ## {keyword} 신청방법 — 단계별 안내 ━━
### 온라인 신청
- 단계별 안내 (3단계 이상)
### 오프라인 신청
- 내용
### 필요 서류
- 목록

━━ ## {keyword} 주의사항 및 자주 묻는 질문 ━━
### 많이 하는 실수
- **실수1**: 설명
- **실수2**: 설명
### Q&A
- Q: 질문 / A: 답변 (2개 이상)

━━ 마무리 CTA ━━
[신청하러 가기](공식URL)

위 구조를 **빠짐없이** 작성. H2마다 키워드 포함 필수. H3 총 8개 이상 필수."""

    # {keyword} 치환
    prompt_text = prompt_text.replace("{keyword}", keyword)
    log(f"[Notion] 프롬프트 준비 완료 ({len(prompt_text)}자)")
    return prompt_text
