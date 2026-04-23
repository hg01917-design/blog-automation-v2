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

CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"
BASE_DIR = Path(__file__).parent
INSTR_DIR = BASE_DIR / "project_instructions"
_TOKEN_CACHE = BASE_DIR / ".claude_token_cache"  # 키체인 잠금 시 폴백용


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
    _is_naver = blog_id == "salim1su"

    if _is_naver:
        _SEO_TITLE_RULE = (
            "\n\n[네이버 SEO 제목 규칙 — 필수 준수]\n"
            "① 제목 길이: 20~35자 (네이버는 짧고 명확한 제목 선호)\n"
            "② 핵심 키워드를 제목 맨 앞에 정확히 포함\n"
            "③ 검색자가 그대로 검색할 법한 자연스러운 표현 사용\n"
            "④ 숫자·연도 포함 시 클릭률 상승\n"
            "⑤ 메타 디스크립션 불필요 (네이버는 본문 첫 문단을 미리보기로 사용)\n"
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
        "\n\n[절대 금지 표현]\n"
        "① 소제목에 '꿀팁' 금지 → '방법', '정보', '가이드', '핵심' 대체\n"
        "② 과장 표현 금지: 완벽, 궁극, Ultimate, Perfect 등\n"
        "③ AI 문구 절대 금지: '알아보겠습니다', '살펴보겠습니다', '소개하겠습니다',\n"
        "   '이번 포스팅에서는', '오늘은 ~에 대해', '함께 알아볼게요',\n"
        "   '~해보도록 하겠습니다', '정리해드릴게요'\n"
        "④ 마무리에 '도움이 되셨으면', '유익한 정보였으면' 류 금지\n"
    )

    _ADSENSE_RULE = (
        "\n\n[애드센스 배치 규칙 — 필수]\n"
        "본문 전체에 [애드센스] 마커를 정확히 3개 삽입.\n"
        "① 2번째 [H2] 소제목 바로 아래 문단 끝에 1개 고정.\n"
        "② 나머지 2개는 서로 다른 소제목 섹션에 1개씩 분산 배치.\n"
        "   - 우선순위: 표(|-로 구성된 표) 바로 아래 → 키워드 포함 문장 바로 아래\n"
        "   - 같은 소제목 섹션에 2개 이상 배치 금지\n"
        "③ 이미지([이미지N]) 바로 위·아래 금지, 버튼링크 바로 위·아래 금지.\n"
        "④ [애드센스] 위아래에 반드시 빈 줄 2칸.\n"
        "⑤ 각 소제목 본문 마지막 줄과 다음 [H2] 사이에 빈 줄 2칸.\n"
    )

    # ── 플랫폼별 출력 형식 ──────────────────────────────────────────────
    if is_wordpress:
        _SECTION_FORMAT = (
            "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
            "===제목===\n(SEO 최적화된 롱테일 제목)\n===제목끝===\n\n"
            "===본문===\n"
            "<h2>소제목</h2> 바로 아래에 [이미지N] 마커 삽입\n"
            "강조는 <strong>텍스트</strong> 사용\n"
            "마크다운 기호(##, **) 절대 사용 금지\n"
            "[애드센스] 마커 3개 본문에 분산 삽입 (위아래 빈 줄 2칸)\n"
            "===본문끝===\n\n"
            "===태그===\n태그1, 태그2, ... (10~20개)\n===태그끝===\n\n"
            "===메타===\n(검색결과 미리보기용 요약 80~120자)\n===메타끝===\n"
        )
        _IMAGE_RULE = (
            "\n\n[이미지 규칙 — 필수]\n"
            "각 <h2> 소제목 바로 아래 줄에 [이미지N] 마커 삽입 (N=1부터 순서대로).\n"
            "본문 끝에 ===이미지=== 섹션:\n"
            "===이미지===\n[이미지1]\n- 프롬프트: (영어)\n- 파일명: (영문-소문자-하이픈.jpg)\n- alt: (한국어)\n===이미지끝===\n"
        )
    else:
        # Playwright 타입 (Tistory / Naver)
        _SECTION_FORMAT = (
            "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
            "===제목===\n(SEO 최적화된 롱테일 제목)\n===제목끝===\n\n"
            "===본문===\n"
            "[H2]소제목[/H2]  ← 소제목 마커\n"
            "[이미지N]        ← 소제목 바로 다음 줄에 고정\n"
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

    if instructions:
        prompt = f"{instructions}\n\n[작성 키워드]\n{keyword}{_SEO_TITLE_RULE}{_DEPTH_RULE}{_BANNED_EXPRESSIONS}{_SECTION_FORMAT}{_IMAGE_RULE}{_ADSENSE_RULE}"
    else:
        prompt = (
            f"키워드: {keyword}\n\n"
            "위 키워드로 순수 텍스트 3000자 블로그 포스팅을 작성해줘.\n"
            "소제목 4~5개, 존댓말(해요체), 구체적 수치·날짜 포함.\n"
            f"{_SEO_TITLE_RULE}{_DEPTH_RULE}{_BANNED_EXPRESSIONS}{_SECTION_FORMAT}{_IMAGE_RULE}{_ADSENSE_RULE}"
        )

    if extra_context:
        prompt += f"\n\n[참고 자료 — 아래 수치/날짜만 사용, 임의 수치 금지]\n{extra_context}"

    return prompt


_POLISH_PROMPT = """아래는 블로그 초안이다. 구조(===제목===, ===본문===, ===태그===, ===메타===, [H2], [H3], [BOLD], [이미지N], [애드센스] 마커)는 절대 바꾸지 마라.

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

수정한 전체 글을 원본과 동일한 형식으로 출력해라. 설명·주석 없이 글만 출력.

===초안===
{draft}
===초안끝==="""


def _run_claude(full_prompt: str, on_log=None, timeout: int = 300) -> str:
    """Claude CLI subprocess 호출. 성공 시 stdout 반환, 실패 시 빈 문자열."""
    def log(msg):
        if on_log:
            on_log(msg)

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
        result = subprocess.run(
            [str(CLAUDE_BIN), "--dangerously-skip-permissions", "--print", "--model", "claude-haiku-4-5-20251001"],
            input=full_prompt,
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


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                  on_log=None, extra_context: str = None) -> str:
    """블로그 텍스트 2단계 생성.

    1단계: 내용 초안 생성
    2단계: AI 패턴 제거 + 도입부 개선 (polish)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if blog_id and keyword:
        full_prompt = _build_prompt(blog_id, keyword, extra_context)
        log(f"[Direct] blog={blog_id}, keyword='{keyword}', 프롬프트={len(full_prompt)}자")
    elif prompt:
        full_prompt = prompt
        if extra_context:
            full_prompt += f"\n\n[참고 자료]\n{extra_context}"
        log(f"[Direct] 직접 프롬프트 {len(full_prompt)}자")
    else:
        log("[Direct] 프롬프트 없음 — 스킵")
        return ""

    # ── 1단계: 초안 생성 ──
    log("[Direct] 1단계: 초안 생성 중...")
    raw = ""
    for attempt in range(1, 4):
        if attempt > 1:
            log(f"[Direct] 1단계 재시도 {attempt - 1}/2")
        raw = _run_claude(full_prompt, on_log=on_log)
        if raw and len(raw) >= 500:
            log(f"[Direct] 1단계 완료 ({len(raw)}자)")
            break
        log(f"[Direct] 1단계 응답 짧음 ({len(raw)}자) — 재시도")

    if not raw or len(raw) < 500:
        log("[Direct] 1단계 3회 실패")
        return ""

    # ── 2단계: AI 패턴 제거 + 도입부 개선 ──
    log("[Direct] 2단계: 문체 다듬기 중...")
    polish_prompt = _POLISH_PROMPT.format(draft=raw)
    polished = _run_claude(polish_prompt, on_log=on_log, timeout=300)

    if polished and len(polished) >= 500:
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
