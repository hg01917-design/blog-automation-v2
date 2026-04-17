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


def _load_instructions(blog_id: str) -> str:
    """project_instructions/{blog_id}.txt + {blog_id}_rules.txt 합쳐 반환."""
    parts = []
    for fname in [f"{blog_id}.txt", f"{blog_id}_rules.txt"]:
        fpath = INSTR_DIR / fname
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8").strip()
            if content:
                parts.append(content)
    return "\n\n".join(parts)


def _build_prompt(blog_id: str, keyword: str, extra_context: str = None) -> str:
    """프로젝트 지침 파일 + 키워드 + 섹션 출력 형식으로 프롬프트 구성."""
    instructions = _load_instructions(blog_id)

    # 출력 형식 지시 (overnight_run.py 파서가 기대하는 섹션 마커)
    _SECTION_FORMAT = (
        "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
        "===제목===\n(SEO 최적화된 롱테일 제목)\n===제목끝===\n\n"
        "===본문===\n(블로그 본문 전체 — H2 소제목 3개 이상, 2000자 이상)\n===본문끝===\n\n"
        "===태그===\n태그1, 태그2, ... (10~20개)\n===태그끝===\n\n"
        "===메타===\n(검색결과 미리보기용 요약 80~120자)\n===메타끝===\n"
    )

    # 구글 SEO 제목 규칙 (Tistory·WordPress 공통)
    _SEO_TITLE_RULE = (
        "\n\n[구글 SEO 제목 규칙 — 필수 준수]\n"
        "① 제목 길이: 30~55자 (너무 짧으면 클릭률 하락)\n"
        "② 핵심 키워드를 제목 앞쪽에 배치\n"
        "③ 연도(2026), 숫자(5가지·3단계), '방법','총정리','비교','완벽정리' 중 하나 포함\n"
        "④ 구어체(~되나요, ~할까) 금지 → 명사형('방법','가이드','정리') 사용\n"
        "⑤ 같은 주제 글이 이미 존재하면 각도를 달리할 것 (중복 페널티 방지)\n"
        "[메타 디스크립션 규칙]\n"
        "① 80~120자 이내\n"
        "② 핵심 키워드 앞부분 배치, '~합니다' 마무리\n"
        "③ 숫자·기간·구체적 효과 포함하면 클릭률 상승\n"
    )

    # 전체 공통 깊이 있는 글쓰기 규칙
    _DEPTH_RULE = (
        "\n\n[깊이 있는 글쓰기 — 필수]\n"
        "이 글 하나로 독자가 완전히 준비되고 행동할 수 있어야 한다.\n"
        "① 단계별 구체적 방법: '어디서', '어떻게', '얼마에' 를 빠짐없이\n"
        "   예) T-Money 구매 → 공항 7-Eleven/GS25 위치, 충전 기계 사용법, 잔액 환불 방법\n"
        "② 실수하기 쉬운 것 반드시 포함: 독자가 현장에서 헷갈릴 포인트 1~3가지\n"
        "③ 구체적 수치 필수: 가격·시간·거리·날짜 등 숫자로 명시 (불확실하면 '기준' 표기)\n"
        "④ 나열형 금지 → 각 항목마다 이유·방법·효과까지 풀어서 설명\n"
        "⑤ 글의 내용은 '이 글 하나로 준비 끝' 수준이어야 하지만,\n"
        "   제목·소제목에 '완벽정리', '이거 하나면 끝', '총정리', '모든 것' 같은 표현은 절대 쓰지 말 것\n"
    )

    # 전체 공통 금지 표현 규칙
    _BANNED_EXPRESSIONS = (
        "\n\n[절대 금지 표현 — 전체 적용]\n"
        "① 제목·소제목(H2/H3)에 '꿀팁' 사용 금지 → '방법', '정보', '가이드', '핵심' 등으로 대체\n"
        "② 제목에 과장 표현 금지: Ultimate, Perfect, Complete, Best Ever, 완벽, 궁극 등\n"
        "③ AI 냄새 나는 문구 절대 금지:\n"
        "   - '알아보겠습니다', '살펴보겠습니다', '소개하겠습니다', '정리해드릴게요'\n"
        "   - '이번 포스팅에서는', '오늘은 ~에 대해', '함께 알아볼게요'\n"
        "   - '~해보도록 하겠습니다', '~드리도록 하겠습니다'\n"
        "④ 마무리 문구 금지: '도움이 되셨으면 좋겠습니다', '유익한 정보였으면 합니다' 류\n"
        "⑤ 본문 tip 박스(> 💡 내용)는 사용 가능하나 소제목에 '꿀팁' 단어 포함 금지\n"
    )

    # 이미지 마커 규칙 (overnight_run.py 이미지 파서용)
    _IMAGE_RULE = (
        "\n\n[이미지 규칙 — 필수]\n"
        "본문 내 H2 소제목(##) 바로 아래에 {{이미지N}} 마커 삽입 (N=1부터 순서대로).\n"
        "본문 끝에 ===이미지=== 섹션으로 각 이미지 Gemini 생성 프롬프트 작성:\n"
        "===이미지===\n[이미지1]\n- Gemini프롬프트: (영어 프롬프트)\n- 파일명: (영문-소문자-하이픈.jpg)\n- alt: (키워드 포함 한국어)\n===이미지끝===\n"
    )

    if instructions:
        # 프로젝트 지침 + 키워드 + 출력 형식
        prompt = f"{instructions}\n\n[작성 키워드]\n{keyword}{_SEO_TITLE_RULE}{_DEPTH_RULE}{_BANNED_EXPRESSIONS}{_SECTION_FORMAT}{_IMAGE_RULE}"
    else:
        # 지침 파일 없으면 기본 프롬프트 (triplog 등)
        prompt = (
            f"키워드: {keyword}\n\n"
            "위 키워드로 2000자 이상 블로그 포스팅을 작성해줘.\n"
            "H2 소제목 3개 이상, 존댓말(해요체), 구체적 수치·날짜 포함.\n"
            f"{_SEO_TITLE_RULE}{_SECTION_FORMAT}{_IMAGE_RULE}"
        )

    if extra_context:
        prompt += f"\n\n[참고 자료 — 아래 수치/날짜만 사용, 임의 수치 금지]\n{extra_context}"

    return prompt


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                  on_log=None, extra_context: str = None) -> str:
    """Claude Code CLI subprocess로 블로그 텍스트 직접 생성.

    claude_playwright.generate_text()와 동일한 인터페이스.
    응답 500자 미만이면 최대 2회 재시도.
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

    log("[Direct] Claude Code subprocess 직접 호출...")

    for attempt in range(1, 4):
        if attempt > 1:
            log(f"[Direct] === 재시도 {attempt - 1}/2 ===")

        try:
            # CLAUDECODE 관련 변수 제거 — 중첩 세션 감지로 exit 1 방지
            _REMOVE = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT",
                       "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_IDE_PORT", "CLAUDE_CODE_IDE_SELECTION_OFFSET"}
            clean_env = {k: v for k, v in os.environ.items() if k not in _REMOVE}
            clean_env["HOME"] = str(Path.home())
            # PATH 보강 — launchd 최소 환경에서 누락된 경로 추가
            default_paths = [
                str(Path.home() / ".local/bin"),
                "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
            ]
            existing_paths = clean_env.get("PATH", "").split(":")
            combined = [p for p in default_paths if p not in existing_paths] + existing_paths
            clean_env["PATH"] = ":".join(p for p in combined if p)

            # OAuth 토큰 주입 — 키체인 잠금(launchd 새벽 실행) 시 폴백 캐시 사용
            if "ANTHROPIC_API_KEY" not in clean_env:
                oauth_token = _get_claude_oauth_token()
                if oauth_token:
                    clean_env["ANTHROPIC_API_KEY"] = oauth_token

            # 프롬프트를 stdin pipe로 전달
            result = subprocess.run(
                [str(CLAUDE_BIN), "--dangerously-skip-permissions", "--print"],
                input=full_prompt,
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR),
                timeout=300,
                env=clean_env,
            )

            raw = (result.stdout or "").strip()
            err = (result.stderr or "").strip()

            if result.returncode != 0:
                stdout_preview = (result.stdout or "").strip()[:200]
                log(f"[Direct] 종료코드 {result.returncode} — stderr: {err[:500] or '(없음)'} | stdout: {stdout_preview or '(없음)'}")
                log(f"[Direct] 환경변수 수: {len(clean_env)}, CLAUDECODE제거: {'CLAUDECODE' not in clean_env}, PATH: {clean_env.get('PATH','')[:80]}")
                continue

            if err:
                log(f"[Direct] stderr: {err[:200]}")

            if not raw or len(raw) < 500:
                log(f"[Direct] 응답 너무 짧음 ({len(raw)}자) — 재시도")
                continue

            log(f"[Direct] ✅ 응답 {len(raw)}자")
            return raw

        except subprocess.TimeoutExpired:
            log(f"[Direct] 타임아웃 (5분) — 재시도")
            continue
        except Exception as e:
            log(f"[Direct] 오류: {e} — 재시도")
            continue

    log("[Direct] 3회 모두 실패")
    return ""


if __name__ == "__main__":
    # 직접 테스트: python3 claude_direct.py nolja100 "안동 하회마을 여행"
    blog = sys.argv[1] if len(sys.argv) > 1 else "nolja100"
    kw = sys.argv[2] if len(sys.argv) > 2 else "경주 불국사 여행 코스 입장료"
    print(f"테스트: blog={blog}, keyword={kw}")
    result = generate_text("", blog_id=blog, keyword=kw, on_log=print)
    print("\n=== 결과 (앞 500자) ===")
    print(result[:500] if result else "(결과 없음)")
