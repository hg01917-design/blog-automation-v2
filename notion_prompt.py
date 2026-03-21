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

    # "글 생성 프롬프트" 섹션 이후만 추출
    prompt_lines = []
    capture = False
    for block in blocks:
        btype = block.get("type", "")
        data = block.get(btype, {})
        rich_texts = data.get("rich_text", [])
        text = "".join(rt.get("plain_text", "") for rt in rich_texts)

        # "글 생성 프롬프트" 헤딩을 만나면 캡처 시작
        if btype == "heading_2" and "글 생성 프롬프트" in text:
            capture = True
            continue

        if capture:
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

    prompt_text = "\n".join(prompt_lines).strip()

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
    if blog_id == "salim1su":
        prompt_text += """

**살림 페르소나 규칙 (daonna525)**:
- 짧은 문단 (2-3문장) 위주로 작성, 긴 설명 지양
- ~더라구요, ~했어요, ~이에요, ~거든요 말투 사용 (딱딱한 ~습니다 최소화)
- 실제 살림 경험담처럼 자연스럽게 (예: "저도 처음엔 몰랐는데 해보니까 진짜 달라지더라구요")
- 숫자/금액은 구체적으로 (예: "한 달에 약 3만원 절약됐어요")"""
    elif blog_id == "nolja100":
        prompt_text += """

**여행 블로그 지은 페르소나 규칙 (nolja100)**:
- 실제 방문한 여행자 시점으로 작성, 생생한 현장감 표현
- 구체적인 장소명·교통·비용·운영시간은 확실히 아는 정보만 작성 (불확실하면 '현장 확인 권장' 표시)
- 환각(hallucination) 엄금: 없는 장소, 잘못된 가격, 날조 정보 절대 금지
- ~했어요, ~였어요, ~더라구요 말투로 현장감 있게 작성
- 꿀팁·주의사항은 실제 경험 기반으로 구체적으로 서술"""

    # {keyword} 치환
    prompt_text = prompt_text.replace("{keyword}", keyword)
    log(f"[Notion] 프롬프트 준비 완료 ({len(prompt_text)}자)")
    return prompt_text
