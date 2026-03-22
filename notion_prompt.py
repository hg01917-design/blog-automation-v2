"""Notion API에서 블로그별 프롬프트를 가져와 {keyword} 치환"""
import re
import requests
import os
from pathlib import Path
from config import PROMPT_PAGES

# .env 파일 로드
_env_path = Path(__file__).parent / ".env"
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
    prompt_text += "\n\n**제목 금지패턴**: 제목에 완벽정리/총정리/완벽가이드/N가지/N종류 절대 사용 금지"

    # 글자수 규칙
    prompt_text += "\n\n**글자수 규칙**: 반드시 3000자 이상 작성할 것. 현재 글자수를 중간중간 확인하면서 작성. 3000자 미만이면 내용을 보충해서 반드시 3000자를 넘길 것."

    # 태그 규칙
    prompt_text += "\n\n**태그 규칙**: ===태그=== 섹션에 반드시 10개 이상의 태그를 작성할 것."

    # 본문 형식 규칙 추가
    prompt_text += """

**본문 출력 형식 규칙**:
- H2 소제목은 반드시 ## 으로 시작 (예: ## 아이패드 추천 이유)
- 이미지 삽입 위치는 반드시 {{이미지N}} 으로 표시 (예: {{이미지1}}, {{이미지2}})
- 애드센스 삽입 위치는 반드시 [애드센스] 으로 표시
- 표는 마크다운 표 형식으로 작성 (| 열1 | 열2 | 형식)
- HTML 태그 사용 금지 — 위 마커 형식만 사용
- 일반 텍스트는 그대로 작성"""

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
- 짧은 문단 (2-3문장) 위주로 작성, 긴 설명 지양
- ~더라구요, ~했어요, ~이에요, ~거든요 말투 사용 (딱딱한 ~습니다 최소화)
- 실제 살림 경험담처럼 자연스럽게 (예: "저도 처음엔 몰랐는데 해보니까 진짜 달라지더라구요")
- 숫자/금액은 구체적으로 (예: "한 달에 약 3만원 절약됐어요")

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
- 한 문장 = 한 줄 (문장 끝나면 무조건 줄바꿈)
- 한 문장은 20자 내외로 짧게 끊기
- 한 문단 = 2~3문장 최대, 문단 사이 빈 줄 1개
- 줄글로 이어쓰기 절대 금지
- 좋은 예시:
  "관리비 고지서를 처음 뜯어봤어요.
  항목이 생각보다 너무 많더라구요.
  전기, 수도, 가스는 기본이고요.
  청소비, 경비비까지 있었어요."
- 나쁜 예시:
  "관리비 고지서를 처음 뜯어봤을 때 항목이 생각보다 너무 많아서 전기, 수도, 가스는 기본이고 청소비까지 있었어요."

**제목 규칙 (salim1su)**:
- 메인키워드는 반드시 제목 맨 앞에 위치
- 타깃/상황 + 세부키워드 조합으로 구체성 확보
  - 상황형: '전기요금 고지서 받고 깜짝 놀란 분들을 위한 절약법'
  - 문제형: '도시가스 요금 갑자기 올랐을 때 확인할 것'
  - 인구통계는 검색 의도와 명확히 맞을 때만 사용
- 금지 패턴: 완벽정리/총정리/완벽가이드/N가지/N종류
- 40자 이내 유지"""
    elif blog_id == "nolja100":
        prompt_text += """

**여행 블로그 지은 페르소나 규칙 (nolja100)**:
- 페르소나: 지은 (32세 콘텐츠 플래너, 리서치 기반)
- 1인칭 체험 주장 절대 금지: "직접 가봤어요", "제가 먹어봤는데" 같은 표현 금지
- 정보는 리서치 기반으로 작성. 불확실한 수치(환율/입장료/운영시간)는 반드시 "조사 기준" 명시
- 조작된 고유명사·주소·가격 절대 금지 (환각 엄금)
- 문체: 정보 전달형 (~입니다, ~합니다) + 자연스러운 구어체 (~요)
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
- Rank Math SEO 메타 포함: 메타 제목(60자 이내), 메타 설명(160자 이내)
- 콜투액션 최대 2개 (본문 상단+하단): [신청하러 가기](URL) 형식
- 확인되지 않은 수치·날짜 단정 금지"""

    # {keyword} 치환
    prompt_text = prompt_text.replace("{keyword}", keyword)
    log(f"[Notion] 프롬프트 준비 완료 ({len(prompt_text)}자)")
    return prompt_text
