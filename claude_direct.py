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
        "===태그===\n태그1, 태그2, ... (10~20개)\n===태그끝===\n"
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
        prompt = f"{instructions}\n\n[작성 키워드]\n{keyword}{_SECTION_FORMAT}{_IMAGE_RULE}"
    else:
        # 지침 파일 없으면 기본 프롬프트 (triplog 등)
        prompt = (
            f"키워드: {keyword}\n\n"
            "위 키워드로 2000자 이상 블로그 포스팅을 작성해줘.\n"
            "H2 소제목 3개 이상, 존댓말(해요체), 구체적 수치·날짜 포함.\n"
            f"{_SECTION_FORMAT}{_IMAGE_RULE}"
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
            result = subprocess.run(
                [
                    str(CLAUDE_BIN),
                    "--dangerously-skip-permissions",
                    "--print",
                    full_prompt,
                ],
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR),
                timeout=300,
                env={**os.environ, "HOME": str(Path.home())},
            )

            raw = (result.stdout or "").strip()
            err = (result.stderr or "").strip()

            if err and "error" in err.lower():
                log(f"[Direct] stderr: {err[:300]}")

            if result.returncode != 0:
                log(f"[Direct] 종료코드 {result.returncode} — 재시도")
                continue

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
