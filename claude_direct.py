"""
claude_direct.py — Claude Code CLI subprocess로 직접 블로그 텍스트 생성
======================================================================
기존 claude_playwright.py(chrome 9222 → claude.ai)를 대체.
동일한 generate_text() 인터페이스 유지.

project_instructions/ 폴더에서 블로그별 지침을 읽어 프롬프트 구성.
- chrome 9222 의존성 없음 (텍스트 생성 단계)
- claude.ai Playwright 파싱 오류 없음
- subprocess로 claude --print 호출 → 응답 즉시 반환
"""
import subprocess
import sys
import os
import re
from pathlib import Path
from config import is_naver_blog

CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"
BASE_DIR = Path(__file__).parent
INSTR_DIR = BASE_DIR / "project_instructions"
_TOKEN_CACHE = BASE_DIR / ".claude_token_cache"  # 키체인 잠금 시 폴백용

# ── 모델 설정 ──────────────────────────────────────────────────────────────
CLAUDE_MODEL_IDS = {
    "haiku":  "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus":   "claude-opus-4-7",
}
GEMINI_MODEL_IDS = {
    "gemini-2.5-pro":   "gemini-2.5-pro",
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.0-flash": "gemini-2.0-flash",
    "gemini-1.5-pro":   "gemini-1.5-pro",
    "gemini-1.5-flash": "gemini-1.5-flash",
}

def _current_model() -> str:
    """WRITING_MODEL 환경변수로 선택된 모델 키 반환. 기본값: haiku"""
    return os.environ.get("WRITING_MODEL", "haiku")


def _get_claude_oauth_token() -> str:
    """macOS 키체인에서 Claude Code OAuth 토큰을 읽어 반환.
    성공하면 캐시 파일에도 저장. 실패하면 캐시 파일에서 읽기 시도.
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import json as _json
            cred = _json.loads(result.stdout.strip())
            token = cred.get("claudeAiOauth", {}).get("accessToken", "")
            if token:
                # 캐시 파일에 저장 (키체인 잠금 시 폴백)
                try:
                    _TOKEN_CACHE.write_text(token, encoding="utf-8")
                except Exception:
                    pass
                return token
    except Exception:
        pass

    # 키체인 실패 → 캐시 파일에서 읽기
    try:
        if _TOKEN_CACHE.exists():
            token = _TOKEN_CACHE.read_text(encoding="utf-8").strip()
            if token:
                return token
    except Exception:
        pass

    return ""


_PLAYWRIGHT_BLOGS = {"goodisak", "nolja100", "salim1su", "me1091", "woll100", "phn0502"}
_WORDPRESS_BLOGS = {"baremi542", "triplog", "blogspot_it", "blogspot_travel", "blogspot_daily"}


def _load_instructions(blog_id: str, keyword: str = "") -> str:
    """project_instructions/{blog_id}.txt + {blog_id}_rules.txt 합쳐 반환.
    {keyword} 플레이스홀더가 있으면 실제 키워드로 치환.
    """
    parts = []
    for fname in [f"{blog_id}.txt", f"{blog_id}_rules.txt"]:
        fpath = INSTR_DIR / fname
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8").strip()
            if keyword:
                content = content.replace("{keyword}", keyword)
            if content:
                parts.append(content)
    return "\n\n".join(parts)


def _build_prompt(blog_id: str, keyword: str, extra_context: str = None) -> str:
    """프로젝트 지침 파일 + 키워드 + 섹션 출력 형식으로 프롬프트 구성."""
    instructions = _load_instructions(blog_id, keyword=keyword)

    is_wordpress = blog_id in _WORDPRESS_BLOGS

    # ── SEO 규칙 (플랫폼별 분기) ────────────────────────────────────────
    # me1091: 네이버 산문형 리뷰 블로그 (소제목 없음, 애드센스 없음)
    _is_naver = is_naver_blog(blog_id)

    if _is_naver:
        _SEO_TITLE_RULE = (
            "\n\n[네이버 SEO 제목 규칙 — 필수 준수]\n"
            "① 제목은 반드시 [메인키워드] + [서브키워드1] + [서브키워드2] 구조로 만든다.\n"
            "② 메인키워드는 제목 맨 앞에 고정하고 절대 다른 단어를 앞에 두지 않는다.\n"
            "③ 구조 의도는 '큰 검색어 + 구체 대상 + 검색 의도'로 맞춘다.\n"
            "④ 최종 출력 제목에는 '/'를 넣지 말고 공백으로 자연스럽게 연결한다.\n"
            "⑤ 제목 길이는 가능하면 25자 이내(최대 30자 이내 권장).\n"
            "⑥ 키워드 나열식 금지: 실제 검색창에 입력할 법한 조합으로만 작성한다.\n"
            "⑦ '2026', '주부', '실사용' 같은 단어는 기본 제목에 자동 삽입 금지.\n"
            "⑧ 연도는 법/제도/가격/혜택/정책처럼 최신성이 중요한 주제일 때만 사용한다.\n"
            "⑨ '실사용 후기'는 길면 '후기'로 축약한다.\n"
            "⑩ 서브키워드1 우선순위: 상품명/장소명/브랜드명 > 상황키워드 > 사용대상키워드.\n"
            "⑪ 서브키워드2는 검색 의도 단어로 구성: 후기, 추천, 비교, 방법, 가격, 신청, 조식후기, 숙박후기 등.\n"
            "⑫ 제목 후보를 5개 생성한 뒤, 가장 자연스럽고 네이버 통합검색 의도에 맞는 1개만 최종 제목으로 출력한다.\n"
            "⑬ 메타 디스크립션 불필요 (네이버는 본문 첫 문단을 미리보기로 사용).\n"
            "⑭ 블로그 지수가 낮은 초기 블로그 기준으로, 메인키워드도 처음부터 롱테일 조합형으로 잡는다.\n"
            "   - 단일 대키워드(예: 냉장고정리, 주방정리) 단독 메인 사용 금지\n"
            "   - 메인키워드 예시 형태: '냉장고정리트레이 추천', '냉장고 회전트레이 후기', '냉장고 정리함 다이소'\n"
            "⑮ 초기 블로그 제목 구성 우선순위:\n"
            "   메인키워드(롱테일) + 상황/대상 + 검색의도(후기/비교/방법/가격 등).\n"
            "⑯ 본문 주제가 넓어 제품 유형이 여러 개인 경우, 한 제목에 모두 넣지 말고 세부 키워드 중심 단일 의도 제목을 우선한다.\n"
            "   필요 시 분할 발행 가능한 제목 후보를 만든다.\n"
        )
    else:
        _SEO_TITLE_RULE = (
            "\n\n[구글 SEO 제목 규칙 — 필수 준수]\n"
            "① 제목 길이: 30~55자\n"
            "② 핵심 키워드를 제목 앞쪽에 배치\n"
            "③ 연도(2026)·구체적 숫자·'방법','가이드','정리' 중 하나 포함\n"
            "④ 구어체(~되나요, ~할까) 금지 → 명사형 사용\n"
            "⑤ 같은 주제 글이 이미 존재하면 각도를 달리할 것\n"
            "[메타 디스크립션 규칙]\n"
            "① 80~120자 이내, 핵심 키워드 앞부분 배치, '~합니다' 마무리\n"
            "② 숫자·기간·구체적 효과 포함하면 클릭률 상승\n"
        )

    _DEPTH_RULE = (
        "\n\n[깊이 있는 글쓰기 — 필수]\n"
        "이 글 하나로 독자가 완전히 준비되고 행동할 수 있어야 한다.\n"
        "① 단계별 구체적 방법: '어디서', '어떻게', '얼마에' 빠짐없이\n"
        "② 실수하기 쉬운 포인트 1~3가지 반드시 포함\n"
        "③ 구체적 수치 필수: 가격·시간·거리·날짜 (불확실하면 '기준' 표기)\n"
        "④ 나열형 금지 → 각 항목마다 이유·방법·효과까지 풀어서 설명\n"
        "⑤ 문단 구분 필수: 2~3문장마다 반드시 빈 줄(빈 행) 하나 추가. 문장을 줄줄이 이어 쓰지 말 것.\n"
    )

    _BANNED_EXPRESSIONS = (
        "\n\n[절대 금지 표현 — 위반 시 글 전체 재작성]\n"
        "① 소제목에 '꿀팁' 금지 → '방법', '정보', '가이드', '핵심' 대체\n"
        "② 제목·소제목에 '완전 정리', '완벽 정리', '총정리', '완벽 가이드' 금지\n"
        "③ 과장 표현 금지: 완벽, 궁극, Ultimate, Perfect, 완전히, 확실히\n"
        "④ AI 문구 절대 금지: '알아보겠습니다', '살펴보겠습니다', '소개하겠습니다',\n"
        "   '알려드릴게요', '알려드리겠습니다', '설명드리겠습니다',\n"
        "   '이번 포스팅에서는', '오늘은 ~에 대해', '함께 알아볼게요',\n"
        "   '~해보도록 하겠습니다', '정리해드릴게요', '종합적으로', '결론적으로',\n"
        "   '다양한 측면에서', '물론입니다', '당연히', '첫째/둘째/셋째 나열'\n"
        "⑤ 과도한 강조 금지: '가장 중요해요', '정말 중요해요', '매우 중요합니다' 반복 금지\n"
        "   → 강조는 1번만, 구체적 근거와 함께 쓸 것\n"
        "⑥ 설명조 어미 남발 금지: '충분히 ~에요', '~라고 할 수 있어요', '~인 셈이에요'\n"
        "⑦ 마무리에 '도움이 되셨으면', '유익한 정보였으면' 류 금지\n"
        "⑧ 본문 첫 줄 소제목 절대 금지: 반드시 도입부 텍스트 2~3문장 먼저 작성 후 첫 소제목 시작.\n"
        "   소제목(## / [H2])으로 바로 시작하면 글 전체 재작성 기준임.\n"
    )

    if _is_naver:
        # 네이버 블로그는 자체 광고 시스템 사용 — 애드센스 마커 금지
        _ADSENSE_RULE = "\n\n[주의] 이 글은 네이버 블로그용입니다. [애드센스] 마커를 본문에 절대 삽입하지 마세요.\n"
    else:
        _ADSENSE_RULE = (
            "\n\n[애드센스 배치 규칙 — 필수]\n"
            "① 개수 기준: 본문 1,000자당 1개 (2,000자→2개 / 3,000자→3개 / 4,000자→4개)\n"
            "② 첫 번째 [애드센스]: 반드시 2번째 소제목 바로 아래 문단 끝에 고정.\n"
            "③ 나머지: 문맥광고가 뜰 만한 텍스트(핵심 키워드 밀집 문단) 바로 아래 배치.\n"
            "   - 같은 소제목 섹션에 2개 이상 배치 금지\n"
            "④ 이미지 바로 위·아래 배치 절대 금지. 버튼링크 바로 위·아래 배치 절대 금지.\n"
            "⑤ [애드센스] 위아래에 반드시 빈 줄 2칸.\n"
            "⑥ 소제목과 이미지·텍스트 사이 빈 줄 2칸.\n"
        )

    # ── 블로그별 페르소나 규칙 ─────────────────────────────────────────
    _PERSONA_RULE = ""
    if blog_id == "salim1su":
        _PERSONA_RULE = (
            f"\n\n[작성자 설정 — 살림 블로그 페르소나]\n"
            f"이 블로그는 30~40대 주부가 운영하는 살림·절약 네이버 블로그야.\n"
            f"가족 구성: 남편 + 본인 + 자녀 3명 = 5인 가족. 수량·예산 등 숫자 기준은 항상 5인 기준으로 작성.\n"
            f"예시: 식비 예산, 식재료 양, 요리 분량 등 모두 5인 기준. '2인 기준', '1인분' 등 2인 이하 기준 표현 금지.\n"
            f"말투: 따뜻하고 친근한 해요체. '~해봤어요', '~더라고요', '~하더라고요', '~해요' 위주.\n"
            f"독자를 '여러분'으로 호칭. 딱딱한 설명조(~입니다, ~합니다) 최소화.\n"
            f"⚠️ 반드시 '{keyword}' 주제만 작성. 다른 주제 절대 금지.\n"
            f"\n[깊이 있는 글쓰기 — 핵심 규칙]\n"
            f"'{keyword}' 중 핵심 한 가지를 골라 단계별(1단계→2단계→3단계)로 깊이 파고들어.\n"
            f"겉핥기식 나열(A방법, B방법, C방법... 각 2~3줄씩) 절대 금지.\n"
            f"하나의 방법을 선택하면 → 준비물·이유·과정·주의사항·실제 경험담 순으로 충분히 설명.\n"
            f"실제로 해본 사람만 아는 구체적 디테일(실패담, 깨달은 점, 예상과 달랐던 점) 포함.\n"
            f"가격 언급 시 '몇천 원대', '저렴하게' 등 범위 표현 사용. 검증 어려운 특정 금액 금지.\n"
            f"글 마지막에 반드시 마무리 단락 포함 — '오늘 소개한 방법이 도움이 됐으면 좋겠어요' 식의 자연스러운 마무리.\n"
            f"마무리 단락은 소제목 없이 본문 마지막에 텍스트로만 작성. 글이 뚝 끊기는 느낌 절대 금지.\n"
            f"글은 반드시 도입부 텍스트 2~3문장으로 시작 (소제목·[H2]로 바로 시작 절대 금지).\n"
            f"폰트 크기: 본문은 기본 크기(15pt 기준). 소제목은 [H2] 마커 사용.\n"
        )
    elif blog_id == "me1091":
        _PERSONA_RULE = (
            "\n\n[작성자 설정 — 리뷰 블로그 페르소나]\n"
            "실제로 구매·사용해본 30대 생활 블로거 톤.\n"
            "말투: '~했어요', '~좋더라고요', '~써봤는데' 등 자연스러운 구어체.\n"
        )

    # ── 플랫폼별 출력 형식 ──────────────────────────────────────────────
    if is_wordpress:
        _SECTION_FORMAT = (
            "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
            "===제목===\n(SEO 최적화된 롱테일 제목)\n===제목끝===\n\n"
            "===본문===\n"
            "(도입부 2~3문장 — 독자 상황 공감으로 시작, 소제목 없이 텍스트만. 소제목으로 바로 시작 절대 금지)\n\n"
            "## 소제목1\n"
            "[이미지1]\n"
            "프롬프트: (영어 장면 묘사)\n"
            "파일명: (영문-소문자-하이픈.jpg)\n"
            "alt: (한국어 설명)\n"
            "[/이미지1]\n"
            "본문 내용...\n\n"
            "[애드센스]\n\n"
            "## 소제목2\n"
            "[이미지2]\n"
            "프롬프트: (영어 — 동일 프롬프트)\n"
            "파일명: (영문-소문자-하이픈-2.jpg)\n"
            "alt: (한국어)\n"
            "[/이미지2]\n"
            "본문 내용...\n"
            "===본문끝===\n\n"
            "===태그===\n태그1, 태그2, ... (10~20개)\n===태그끝===\n\n"
            "===메타===\n(검색결과 미리보기용 요약 80~120자)\n===메타끝===\n"
        )
        _IMAGE_RULE = (
            "\n\n[이미지 규칙 — 필수]\n"
            "각 소제목(## 또는 <h2>) 바로 다음 줄에 [이미지N]...[/이미지N] 블록 삽입 (N=1부터 순서대로).\n"
            "형식:\n"
            "[이미지N]\n"
            "프롬프트: (영어, 글 전체 주제 장면 묘사 — 모든 블록 동일)\n"
            "파일명: (영문-소문자-하이픈.jpg)\n"
            "alt: (한국어, 해당 소제목 관련 설명)\n"
            "[/이미지N]\n"
            "※ ===이미지=== 섹션 별도 추가 절대 금지. {{이미지N}} 형식 사용 금지.\n"
        )
    else:
        # Playwright 타입 (Tistory / Naver)
        if _is_naver:
            _SECTION_FORMAT = (
                "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
                "===제목===\n(SEO 최적화된 롱테일 제목)\n===제목끝===\n\n"
                "===본문===\n"
                "(도입부 2~3문장 — 독자 상황 공감으로 시작, 소제목 없이 텍스트만. 소제목으로 바로 시작 절대 금지)\n\n"
                "[H2]소제목[/H2]  ← 소제목 마커\n"
                "[이미지N]        ← 소제목 바로 다음 줄에 고정\n"
                "프롬프트: (영어, 해당 소제목 장면을 구체적으로 묘사)\n"
                "alt: (한국어, 해당 소제목 관련 설명)\n"
                "[/이미지N]\n"
                "본문 내용...\n"
                "\n"
                "강조는 [BOLD]텍스트[/BOLD] 사용 (** 마크다운 절대 사용 금지)\n"
                "소제목은 [H2]...[/H2] 마커만 사용 (## 마크다운 절대 사용 금지)\n"
                "HTML 태그(<h2>, <strong>, <p> 등) 본문에 직접 작성 금지\n"
                "[애드센스] 마커 절대 삽입 금지 (네이버 자체 광고 시스템 사용)\n"
                "===본문끝===\n\n"
                "===태그===\n태그1, 태그2, ... (10~20개)\n===태그끝===\n\n"
                "===메타===\n(검색결과 미리보기용 요약 80~120자)\n===메타끝===\n"
            )
        else:
            _SECTION_FORMAT = (
                "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
                "===제목===\n(SEO 최적화된 롱테일 제목)\n===제목끝===\n\n"
                "===본문===\n"
                "[H2]소제목[/H2]\n"
                "[이미지N]\n"
                "프롬프트: (영어, 글 전체 주제 장면 묘사 — 모든 블록 동일)\n"
                "alt: (한국어, 해당 소제목 관련 설명)\n"
                "[/이미지N]\n"
                "본문 내용...\n"
                "\n"
                "[애드센스]\n"
                "\n"
                "강조는 [BOLD]텍스트[/BOLD] 사용 (** 마크다운 절대 사용 금지)\n"
                "소제목은 [H2]...[/H2] 마커만 사용 (## 마크다운 절대 사용 금지)\n"
                "HTML 태그(<h2>, <strong>, <p> 등) 본문에 직접 작성 금지\n"
                "===본문끝===\n\n"
                "===태그===\n태그1, 태그2, ... (10~20개)\n===태그끝===\n\n"
                "===메타===\n(검색결과 미리보기용 요약 80~120자)\n===메타끝===\n"
            )
        if _is_naver:
            _IMAGE_RULE = (
                "\n\n[이미지 규칙 — 필수]\n"
                "1) 각 [H2]소제목[/H2] 바로 다음 줄에 [이미지N]...[/이미지N] 블록 삽입 (N=1부터 순서대로, H2 개수와 동일).\n"
                "2) 썸네일 이미지는 작성하지 마라. 썸네일은 시스템이 image0으로 별도 생성한다.\n"
                "3) 각 이미지 프롬프트는 해당 H2 소제목의 장면·소품·구도를 다르게 작성한다. 동일 프롬프트 반복 금지.\n"
                "4) 프롬프트에는 no text, no watermark, no people, Korean home setting을 포함한다.\n"
                "5) alt는 각 소제목에 맞게 다르게 작성한다.\n"
                "형식:\n"
                "[이미지N]\n"
                "프롬프트: (영어, 한 줄, 해당 소제목 장면 묘사)\n"
                "alt: (한국어, 해당 소제목 관련 설명)\n"
                "[/이미지N]\n"
                "※ ===이미지=== 섹션 절대 사용 금지.\n"
            )
        else:
            _IMAGE_RULE = (
                "\n\n[이미지 규칙 — 필수]\n"
                "1) 각 [H2]소제목[/H2] 바로 다음 줄에 [이미지N]...[/이미지N] 블록 삽입 (N=1부터 순서대로, H2 개수와 동일).\n"
                "2) 프롬프트는 글 전체를 관통하는 통합 프롬프트 1개만 작성 — 모든 이미지 블록에 동일하게 사용.\n"
                "   (소제목마다 다른 프롬프트 금지. Bing이 4장씩 배치 생성하므로 같은 프롬프트로 충분)\n"
                "3) alt는 각 소제목에 맞게 다르게 작성.\n"
                "형식:\n"
                "[이미지N]\n"
                "프롬프트: (영어, 한 줄, 글 전체 주제 장면 묘사 — 모든 블록 동일)\n"
                "alt: (한국어, 해당 소제목 관련 설명)\n"
                "[/이미지N]\n"
                "※ ===이미지=== 섹션 절대 사용 금지.\n"
            )

    _MOBILE_READABILITY_RULE = ""
    if _is_naver:
        _MOBILE_READABILITY_RULE = (
            "\n\n[네이버 모바일 가독성 규칙 — 매우 중요]\n"
            "1. 본문은 모바일 화면 기준으로 짧게 끊어 쓴다.\n"
            "2. 한 줄은 가능하면 띄어쓰기 포함 10~18자 내외로 작성한다.\n"
            "3. 한 문장 안에서도 의미가 나뉘면 줄바꿈 1번으로 나눈다.\n"
            "4. 문장이 끝나면 반드시 빈 줄 1개를 둔다. 즉 Enter 2번으로 다음 문단을 시작한다.\n"
            "5. 2문장 이상이 빈 줄 없이 붙어 있는 긴 문단은 금지한다.\n"
            "6. 표, 태그, 이미지 마커, [H2] 소제목 마커에는 이 규칙을 적용하지 않는다.\n"
        )

    _RHYTHM_RANDOM_RULE = ""
    if _is_naver:
        _RHYTHM_RANDOM_RULE = (
            "\n\n[문단 리듬 랜덤화 규칙 — 매우 중요]\n"
            "1. SEO 구조(제목/키워드/소제목/이미지마커)는 유지하되, 섹션별 문단 전개 리듬은 서로 다르게 작성한다.\n"
            "2. 각 [H2] 섹션마다 아래 패턴 중 하나를 선택해 섞어라(섹션 간 같은 패턴 반복 최소화):\n"
            "   - A: 짧은 문장 → 짧은 문장 → 구체 예시\n"
            "   - B: 경험담 → 설명 문장 → 짧은 결론\n"
            "   - C: 문제 상황 → 예상과 달랐던 점 → 짧은 정리\n"
            "   - D: 구체 품목 예시 → 사용 후 변화 → 아쉬운 점\n"
            "   - E: 실패담 → 이유 → 다음에 바꿀 점\n"
            "   - F: 사용 전 상황 → 사용 후 변화 → 개인적 판단\n"
            "3. 문단 길이는 매번 다르게(1~4문장) 구성하고, 같은 길이 문단이 연속 3회 이상 나오지 않게 한다.\n"
            "4. 문단 시작 표현은 다양하게 바꾸고, 같은 시작 표현/같은 연결어가 연속 2회 이상 반복되지 않게 한다.\n"
            "5. 연결어(처음엔/그런데/그래서/문제는/핵심은)는 연속 반복 금지, 다른 표현으로 순환한다.\n"
            "6. 전체 본문 중간 섹션들에 경험 요소를 최소 3개 이상 분산 삽입한다(후반 몰아쓰기 금지):\n"
            "   직접 겪은 상황, 구체 품목명, 예상과 달랐던 점, 실패담, 아쉬운 점, 다시 산다면 바꿀 점, 가족/생활패턴 차이, 사용 전후 비교.\n"
            "7. 소제목은 5개 이상 유지하고, 소제목 유형을 섞는다. 메인 키워드는 소제목 1~2개에만 자연스럽게 포함한다.\n"
            "8. 모든 섹션을 결론형 문장으로 끝내지 말고, 질문형/관찰형/여운형 문장을 섞는다.\n"
            "9. 아래 표현은 반복 사용 금지(필요 시 자연어로 대체):\n"
            "   생각보다 훨씬, 핵심입니다, 효율적입니다, 꼭 확인하세요, 추천드립니다, 도움이 되셨길 바랍니다,\n"
            "   완벽하게, 제일 큰 장점, 직접적으로 연결, 한눈에 보기 좋습니다, 삶의 질이 올라갑니다,\n"
            "   알아보겠습니다, 정리해보겠습니다, 이 글에서는\n"
            "10. 모든 소제목의 전개 순서를 동일하게 쓰지 마라. 섹션마다 시작 방식을 바꿔라(경험담 시작/실패담 시작/결론 먼저 제시/관찰로 시작).\n"
            "11. 일부 문단에는 아래 요소를 랜덤하게 섞어라: 개인 실수, 가족 반응, 구매 후 후회, 사용 전후 차이.\n"
            "12. 모든 단락을 '문제→해결→추천' 구조로 끝내지 마라. 일부 단락은 열린 결말 또는 관찰형 문장으로 마무리한다.\n"
            "13. 모바일 가독성은 유지하되, 모든 문장을 2~3줄 단위로 기계적으로 자르지 마라.\n"
            "14. 짧은 문장/중간 길이 문장/긴 문장을 섞고, 한 문단 안에 2~3문장을 자연스럽게 이어 쓰는 구간을 포함한다.\n"
        )

    if instructions:
        prompt = f"{instructions}\n\n[작성 키워드]\n{keyword}{_PERSONA_RULE}{_SEO_TITLE_RULE}{_DEPTH_RULE}{_BANNED_EXPRESSIONS}{_SECTION_FORMAT}{_IMAGE_RULE}{_MOBILE_READABILITY_RULE}{_RHYTHM_RANDOM_RULE}{_ADSENSE_RULE}"
    else:
        prompt = (
            f"키워드: {keyword}\n\n"
            "위 키워드로 순수 텍스트 3000자 블로그 포스팅을 작성해줘.\n"
            "소제목 4~5개, 존댓말(해요체), 구체적 수치·날짜 포함.\n"
            f"{_PERSONA_RULE}{_SEO_TITLE_RULE}{_DEPTH_RULE}{_BANNED_EXPRESSIONS}{_SECTION_FORMAT}{_IMAGE_RULE}{_MOBILE_READABILITY_RULE}{_RHYTHM_RANDOM_RULE}{_ADSENSE_RULE}"
        )

    if extra_context:
        prompt += f"\n\n[참고 자료 — 아래 수치/날짜만 사용, 임의 수치 금지]\n{extra_context}"

    return prompt


_POLISH_PROMPT_NAVER = """아래는 블로그 초안이다. 구조(===제목===, ===본문===, ===태그===, ===메타===, [H2], [H3], [BOLD], [이미지N], [애드센스] 마커)는 절대 바꾸지 마라.

다음 기준으로 본문 문장만 다듬어라:

1. 독자가 첫 문단에서 "나 얘기다"라고 느껴야 한다. 도입부는 독자의 상황·고민에서 시작하고, 이 글을 읽어야 할 이유(후킹)를 자연스럽게 담아라. "이 글에서는~" 식 AI 도입부 완전 금지.

2. 아래 표현이 있으면 반드시 자연스러운 말로 바꿔라:
   - 알아보겠습니다 / 살펴보겠습니다 / 소개하겠습니다 / 정리해드릴게요
   - 이번 포스팅에서는 / 오늘은 ~에 대해 / 함께 알아볼게요
   - ~해보도록 하겠습니다 / 도움이 되셨으면 좋겠습니다
   - 한번에 정리 / 완벽하게 / 한눈에

3. 존댓말(~습니다, ~합니다)로 통일. 반말 섞이면 수정.

4. 나열형("먼저~, 다음으로~, 마지막으로~") 대신 각 내용을 이유·효과까지 풀어서 써라.

5. 마무리 문장에 "도움이 되셨으면", "유익한 정보" 류 금지. 자연스럽게 끝내라.

6. 문단 구분: 2~3문장마다 빈 줄 하나. 문장이 줄줄이 이어지는 덩어리 문단은 반드시 나눠라.

7. 네이버 모바일 가독성: 본문 한 줄은 가능하면 띄어쓰기 포함 10~18자 내외로 짧게 끊어라. 한 문장 안에서도 의미가 나뉘면 줄바꿈 1번으로 나누고, 문장이 끝나면 빈 줄 1개를 둬라. 단, [H2], [이미지N], [BOLD], [애드센스], 태그 형식은 절대 바꾸지 마라.

수정한 전체 글을 원본과 동일한 형식으로 출력해라. 설명·주석 없이 글만 출력.

===초안===
{draft}
===초안끝==="""


_POLISH_PROMPT_WEB = """아래는 블로그 초안이다. 구조(===제목===, ===본문===, ===태그===, ===메타===, [H2], [H3], [BOLD], [이미지N], [애드센스] 마커)는 절대 바꾸지 마라.

다음 기준으로 본문 문장만 다듬어라:

1. 독자가 첫 문단에서 "나 얘기다"라고 느껴야 한다. 도입부는 독자의 상황·고민에서 시작하고, 이 글을 읽어야 할 이유(후킹)를 자연스럽게 담아라. "이 글에서는~" 식 AI 도입부 완전 금지.

2. 아래 표현이 있으면 반드시 자연스러운 말로 바꿔라:
   - 알아보겠습니다 / 살펴보겠습니다 / 소개하겠습니다 / 정리해드릴게요
   - 이번 포스팅에서는 / 오늘은 ~에 대해 / 함께 알아볼게요
   - ~해보도록 하겠습니다 / 도움이 되셨으면 좋겠습니다
   - 한번에 정리 / 완벽하게 / 한눈에

3. 존댓말(~습니다, ~합니다)로 통일. 반말 섞이면 수정.

4. 나열형("먼저~, 다음으로~, 마지막으로~") 대신 각 내용을 이유·효과까지 풀어서 써라.

5. 마무리 문장에 "도움이 되셨으면", "유익한 정보" 류 금지. 자연스럽게 끝내라.

6. 문단 구분: 2~3문장마다 빈 줄 하나. 문장이 줄줄이 이어지는 덩어리 문단은 반드시 나눠라.

7. 모바일 가독성은 유지하되, 본문 한 줄을 기계적으로 10~18자 단위로 과도 분절하지 마라. 워드프레스 가독성 기준으로 한 문단 2~4문장 흐름을 유지하고, 문장 내부 줄바꿈은 꼭 필요한 경우에만 사용한다.

수정한 전체 글을 원본과 동일한 형식으로 출력해라. 설명·주석 없이 글만 출력.

===초안===
{draft}
===초안끝==="""


_FORMAT_ENFORCE_PREFIX = (
    "[출력 규칙 — 최우선]\n"
    "반드시 ===제목=== 으로 시작하는 블로그 글 형식으로만 출력한다.\n"
    "분석·질문·설명·작업계획 등 일절 금지. 지금 바로 ===제목===부터 시작해라.\n\n"
)


def _run_claude(full_prompt: str, on_log=None, timeout: int = 300,
                model_key: str = None, enforce_blog_format: bool = False) -> str:
    """Claude CLI subprocess 호출. 성공 시 stdout 반환, 실패 시 빈 문자열."""
    def log(msg):
        if on_log:
            on_log(msg)

    key = model_key or _current_model()
    model_id = CLAUDE_MODEL_IDS.get(key, CLAUDE_MODEL_IDS["haiku"])

    _REMOVE = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT",
               "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_IDE_PORT", "CLAUDE_CODE_IDE_SELECTION_OFFSET",
               "ANTHROPIC_API_KEY"}
    clean_env = {k: v for k, v in os.environ.items() if k not in _REMOVE}
    clean_env["HOME"] = str(Path.home())
    default_paths = [str(Path.home() / ".local/bin"), "/usr/local/bin", "/usr/bin", "/bin"]
    existing_paths = clean_env.get("PATH", "").split(":")
    combined = [p for p in default_paths if p not in existing_paths] + existing_paths
    clean_env["PATH"] = ":".join(p for p in combined if p)

    try:
        prompt_input = (_FORMAT_ENFORCE_PREFIX if enforce_blog_format else "") + full_prompt
        result = subprocess.run(
            [str(CLAUDE_BIN), "--dangerously-skip-permissions", "--print", "--model", model_id],
            input=prompt_input,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            timeout=timeout,
            env=clean_env,
            start_new_session=True,
        )
        if result.returncode != 0:
            log(f"[Direct] 종료코드 {result.returncode}")
            return ""
        return (result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        log("[Direct] 타임아웃")
        return ""
    except Exception as e:
        log(f"[Direct] 오류: {e}")
        return ""


def _run_gemini(full_prompt: str, on_log=None, timeout: int = 300,
                model_key: str = None, enforce_blog_format: bool = False) -> str:
    """Gemini API 호출. 성공 시 텍스트 반환, 실패 시 빈 문자열."""
    def log(msg):
        if on_log:
            on_log(msg)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        # .env 파일에서 직접 읽기 (프로젝트 루트 → 부모 디렉터리 순서로 탐색)
        for env_path in [BASE_DIR / ".env", BASE_DIR.parent / ".env"]:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        if api_key:
                            break
            if api_key:
                break
    if not api_key:
        log("[Gemini] GEMINI_API_KEY 없음 — ⚙ 설정에서 키를 입력하세요")
        return ""

    key = model_key or _current_model()
    model_id = GEMINI_MODEL_IDS.get(key, "gemini-2.0-flash")
    log(f"[Gemini] 모델: {model_id}")

    try:
        import google.genai as genai
        client = genai.Client(api_key=api_key)
        prompt_input = (_FORMAT_ENFORCE_PREFIX if enforce_blog_format else "") + full_prompt
        response = client.models.generate_content(
            model=model_id,
            contents=prompt_input,
        )
        return (response.text or "").strip()
    except Exception as e:
        log(f"[Gemini] 오류: {e}")
        return ""


def _repair_truncated(text: str, on_log=None) -> str:
    """===본문끝=== 누락 시 자동 복구. 본문이 2000자 이상이면 끝 마커 자동 추가."""
    if "===본문===" not in text or "===본문끝===" in text:
        return text
    body_start = text.find("===본문===") + 7
    body_len = len(text[body_start:].strip())
    if body_len < 2000:
        return text  # 너무 짧음 — 실제 실패
    if on_log:
        on_log(f"[Direct] ⚠️ ===본문끝=== 누락 감지 (본문 {body_len}자) — 자동 복구")
    result = text.rstrip()
    if "===태그===" not in result:
        result += "\n===본문끝===\n\n===태그===\n===태그끝===\n\n===메타===\n===메타끝==="
    else:
        result += "\n===본문끝==="
    return result


def _verify_content(text: str, on_log=None, blog_id: str = None) -> bool:
    """검증 전용 하이쿠 인스턴스로 블로그 글 형식 검증.
    생성 AI와 완전히 분리된 별도 호출.
    """
    # me1091: 산문 형태(소제목 없음) + 네이버 자체광고 → H2/adsense 체크 모두 제외
    # salim1su: 네이버 자체광고 → adsense 체크 제외
    is_prose = blog_id == "me1091"
    is_naver = is_naver_blog(blog_id)

    h2_rule = (
        "3. (me1091: 소제목 없는 산문 형태 — 이 항목은 PASS 조건에서 제외)\n"
        if is_prose else
        "3. 소제목([H2] 또는 ## 또는 <h2>) 2개 이상\n"
    )
    adsense_rule = (
        "4. (네이버 블로그: [애드센스] 마커 없어야 정상 — 이 항목은 PASS 조건에서 제외)\n"
        if is_naver else
        "4. [애드센스] 마커 1개 이상\n"
    )
    # 앞 2000자 + 뒤 500자로 구조 마커가 잘리지 않도록
    if len(text) > 2500:
        text_sample = text[:2000] + "\n...[중략]...\n" + text[-500:]
    else:
        text_sample = text
    verify_prompt = (
        "[출력 규칙 — 최우선]\n"
        "아래 텍스트가 블로그 형식을 갖추면 'PASS' 한 단어만 출력.\n"
        "그렇지 않으면 'FAIL: 이유 한 줄' 형식으로만 출력.\n"
        "다른 설명·분석·인사 일절 금지.\n\n"
        "검증 기준 (모두 충족해야 PASS):\n"
        "1. ===제목=== 과 ===제목끝=== 포함\n"
        "2. ===본문=== 과 ===본문끝=== 포함\n"
        f"{h2_rule}"
        f"{adsense_rule}"
        "5. CLAUDE.md·세션 시작·확인하겠습니다 등 메타 텍스트 없음\n\n"
        f"===검증대상===\n{text_sample}\n===검증대상끝==="
    )
    result = _run_claude(verify_prompt, on_log=on_log, timeout=60)
    result = result.strip()
    if result.startswith("PASS"):
        if on_log:
            on_log("[Verify] ✅ 검증 통과")
        return True
    if on_log:
        on_log(f"[Verify] ❌ 검증 실패: {result[:120]}")
    return False


_CLAUDE_META_PHRASES = [
    "CLAUDE.md", "세션 시작", "확인하겠습니다", "어떻게 진행하면 좋을까요",
    "임시저장 글 검수", "git pull origin main", "노션 현황판",
    "draft_saved", "pending_publish", "다음 작업을 지시", "어떻게 진행할까요",
    "WordPress draft 확인", "먼저 아래를 확인", "확인하고 싶은 것",
    # 하이쿠가 clarification 요청 시 뱉는 패턴
    "명시해 주세요", "지정해 주세요", "알려주세요", "말씀해 주세요",
    "작성하겠습니다", "글을 써드리겠습니다", "지침에 따라",
    "구체적으로 어떤", "어떤 주제", "어떤 영화", "어떤 제품",
    "제목을 지정", "키워드를 알려", "내용을 입력",
]


def _is_valid_blog_content(text: str, blog_id: str = None) -> bool:
    """블로그 본문 형식인지 확인. Claude 분석/메타 텍스트면 False."""
    if "===제목===" not in text and "===본문===" not in text:
        return False
    text_lower = text.lower()
    for phrase in _CLAUDE_META_PHRASES:
        if phrase.lower() in text_lower:
            return False

    # 본문 길이 규칙 기반 검증 (AI 검증보다 신뢰도 높음)
    body_match = text[text.find("===본문===") + 7:]
    if "===본문끝===" in body_match:
        body = body_match[:body_match.find("===본문끝===")]
    else:
        body = body_match
    # me1091: 산문 형태 — 1500자 이상이면 통과
    if blog_id == "me1091":
        return len(body.strip()) >= 1500

    # salim1su: 네이버 살림 블로그 — 2000자 이상 + [H2] 소제목 2개 이상 필수
    if blog_id == "salim1su":
        if len(body.strip()) < 2000:
            return False
        import re as _re
        h2_count = len(_re.findall(r'\[H2\]|^##\s+', body, _re.IGNORECASE | _re.MULTILINE))
        return h2_count >= 2

    # 그 외 블로그: 1500자 이상 + 소제목 최소 2개 필수
    if len(body.strip()) < 1500:
        return False  # 본문 1500자 미만 = 메타 텍스트로 간주
    import re as _re
    h2_count = len(_re.findall(r'\[H2\]|<h2\b|^##\s+', body, _re.IGNORECASE | _re.MULTILINE))
    if h2_count < 2:
        return False

    return True


def repair_text(raw: str, issues: list, on_log=None) -> str:
    """검수 실패한 글을 Claude Code CLI로 부분 수정.

    claude_playwright.repair_text 대체 — claude.ai 웹 의존 없음.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    issues_str = "\n".join(f"- {i}" for i in issues)
    repair_prompt = f"""아래 블로그 글에서 검수 실패한 부분만 수정해줘.
수정 후 동일한 ===섹션=== 형식 그대로 전체 글을 다시 출력해줘.

【수정해야 할 문제점】
{issues_str}

【수정 규칙】
- 문제가 없는 부분은 절대 바꾸지 말 것
- AI 패턴(당연히/살펴보겠습니다 등)은 자연스러운 구어체로 교체
- 제목에 직장인/주부 등 대상이 있으면 제거하고 검색 의도만 남길 것
- 형식(===제목===, ===본문===, ===태그===, ===이미지===)은 그대로 유지

【원본 글】
{raw}"""

    log("[repair] 부분 수정 요청 중 (Claude Code)...")
    result = _run_claude(repair_prompt, on_log=on_log, timeout=300,
                         model_key=_current_model(), enforce_blog_format=True)
    if result and len(result) > 200 and "===제목===" in result:
        log("[repair] ✓ 부분 수정 완료")
        return result
    log("[repair] 부분 수정 실패")
    return None


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                  on_log=None, extra_context: str = None) -> str:
    """블로그 텍스트 2단계 생성.

    WRITING_MODEL 환경변수로 모델 선택:
      Claude: haiku / sonnet / opus
      Gemini: gemini-2.5-pro / gemini-2.5-flash / gemini-2.0-flash / gemini-1.5-pro / gemini-1.5-flash

    1단계: 내용 초안 생성
    2단계: AI 패턴 제거 + 도입부 개선 (polish, Claude haiku 고정)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    model_key = _current_model()
    is_gemini = model_key in GEMINI_MODEL_IDS

    if blog_id and keyword:
        full_prompt = _build_prompt(blog_id, keyword, extra_context)
        log(f"[Direct] blog={blog_id}, keyword='{keyword}', 모델={model_key}, 프롬프트={len(full_prompt)}자")
    elif prompt:
        full_prompt = prompt
        if extra_context:
            full_prompt += f"\n\n[참고 자료]\n{extra_context}"
        log(f"[Direct] 직접 프롬프트 {len(full_prompt)}자, 모델={model_key}")
    else:
        log("[Direct] 프롬프트 없음 — 스킵")
        return ""

    def _call_model(p):
        if is_gemini:
            return _run_gemini(p, on_log=on_log, model_key=model_key, enforce_blog_format=True)
        else:
            return _run_claude(p, on_log=on_log, model_key=model_key, enforce_blog_format=True)

    # ── 1단계: 초안 생성 (최대 3회, 메타 텍스트 감지 시 재시도) ──
    log(f"[Direct] 1단계: 초안 생성 중... (모델: {model_key})")
    raw = ""
    for attempt in range(1, 4):
        if attempt > 1:
            log(f"[Direct] 1단계 재시도 {attempt - 1}/2")
        raw = _call_model(full_prompt)
        if not raw or len(raw) < 500:
            log(f"[Direct] 1단계 응답 짧음 ({len(raw)}자) — 재시도")
            continue
        raw = _repair_truncated(raw, on_log=on_log)
        if not _is_valid_blog_content(raw, blog_id=blog_id):
            log(f"[Direct] ⛔ 블로그 형식 아님 (메타 텍스트 감지) — 재시도 ({attempt}/3)")
            raw = ""
            continue
        # 검증은 항상 Claude haiku로 (비용 효율)
        if not _verify_content(raw, on_log=on_log, blog_id=blog_id):
            log(f"[Direct] ⛔ 검증 AI 불합격 — 재시도 ({attempt}/3)")
            raw = ""
            continue
        log(f"[Direct] 1단계 완료 ({len(raw)}자)")
        break

    if not raw:
        log("[Direct] 1단계 3회 모두 실패 (짧음 또는 메타 텍스트) — failed 처리")
        return ""

    # ── 2단계: AI 패턴 제거 + 도입부 개선 (polish, Claude haiku 고정) ──
    log("[Direct] 2단계: 문체 다듬기 중...")
    polish_template = _POLISH_PROMPT_NAVER if is_naver_blog(blog_id or "") else _POLISH_PROMPT_WEB
    polish_prompt = polish_template.format(draft=raw)
    polished = _run_claude(polish_prompt, on_log=on_log, timeout=300,
                           model_key="haiku", enforce_blog_format=True)

    if polished and len(polished) >= 500 and _is_valid_blog_content(polished):
        log(f"[Direct] 2단계 완료 ({len(polished)}자) ✅")
        return polished
    else:
        log(f"[Direct] 2단계 실패 — 1단계 초안 사용 ({len(raw)}자)")
        return raw


if __name__ == "__main__":
    # 직접 테스트: python3 claude_direct.py nolja100 "안동 하회마을 여행"
    blog = sys.argv[1] if len(sys.argv) > 1 else "nolja100"
    kw = sys.argv[2] if len(sys.argv) > 2 else "경주 불국사 여행 코스 입장료"
    print(f"테스트: blog={blog}, keyword={kw}")
    result = generate_text("", blog_id=blog, keyword=kw, on_log=print)
    print("\n=== 결과 (앞 500자) ===")
    print(result[:500] if result else "(결과 없음)")
