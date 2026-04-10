"""claude.ai Playwright 자동화 — CDP 연결로 글 생성"""
import re
import time
import random
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from browser import connect_cdp as _connect_cdp, get_or_create_page
from notion_prompt import fetch_prompt

CLAUDE_URL = "https://claude.ai"

# blog_id별 Claude Project URL (없으면 일반 /new로 이동)
BLOG_PROJECT_URLS = {
    "goodisak":  "https://claude.ai/project/019ca495-0520-7706-8188-bcd875c96b68",
    "nolja100":  "https://claude.ai/project/019b689e-1dbb-706d-93f3-6174de3a4835",
    "salim1su":  "https://claude.ai/project/019c8917-8337-74e8-989b-edf14e462901",
    "baremi542": "https://claude.ai/project/019d2882-7cfb-72e0-a40f-9669bc6408d6",
    "triplog": "https://claude.ai/project/019d50f9-e07f-7022-a571-4bb71bfa8361",
    "me1091":  "https://claude.ai/project/019d50f8-d88d-7741-9dbd-b064d2e7e269",
}

# 전송 버튼 (한국어/영어 + 다양한 UI 버전 대응)
SEND_BTN_SEL = ', '.join([
    'button[aria-label="메시지 보내기"]',
    'button[aria-label="Send Message"]',
    'button[aria-label="Send message"]',
    'button[data-testid="send-button"]',
    'button[type="submit"]',
])
# assistant 응답 텍스트 셀렉터 (Claude.ai UI 버전별 대응)
RESPONSE_SEL = "div.standard-markdown"
RESPONSE_SEL_FALLBACKS = [
    "div.standard-markdown",
    "[data-testid='assistant-message-content']",
    ".font-claude-message div[class*='prose']",
    "div[class*='assistant'] div[class*='prose']",
    "div[class*='message-content']",
    "div[class*='response'] p",
]

# 응답 완료 판정 기준
MIN_CHARS_FOR_DONE = 1000   # 이 글자수 미만이면 절대 완료 아님
STABLE_SECS_REQUIRED = 20   # 텍스트 변화 없음이 이 초 이상이어야 완료
MAX_WAIT_SECS = 300         # 최대 대기 5분
# 재시도
RETRY_THRESHOLD = 500       # 이 글자수 미만이면 재시도
MAX_RETRIES = 2


def _count_body_chars(text):
    """===본문=== 안의 순수 텍스트 글자수를 센다 (##, {{}}, 공백 제외)."""
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", text, re.DOTALL)
    if not body_m:
        plain = re.sub(r"===\S+===|##.*|{{.*?}}|\[애드센스\]", "", text)
        return len(re.sub(r"\s+", "", plain))
    body = body_m.group(1)
    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    return len(re.sub(r"\s+", "", plain))


def _is_streaming_done(page):
    """스트리밍이 끝났는지 확인 — 전송 버튼 또는 stop 버튼 상태로 판단."""
    try:
        # 방법1: 전송 버튼이 다시 나타남 = 스트리밍 완료
        send_count = page.locator(SEND_BTN_SEL).count()
        if send_count > 0:
            return True
    except Exception:
        pass
    try:
        # 방법2: stop 버튼이 없으면 = 스트리밍 완료
        stop_btn = page.locator('button[aria-label="Stop Response"], button[aria-label="응답 중지"]')
        if stop_btn.count() == 0:
            return True
    except Exception:
        pass
    return False


def _wait_for_response(page, prev_response_count, log):
    """claude.ai 스트리밍 응답이 완료될 때까지 대기한다.

    완료 조건 (모두 충족해야 함):
    1. 텍스트 길이가 20초 이상 변화 없음
    2. 글자수가 1000자 이상
    예외: 스트리밍이 확실히 끝났으면 (전송 버튼 재출현) 글자수 무관하게 완료

    반환: (final_len, streamed_text) — 스트리밍 중 포착된 ===제목=== 포함 텍스트
    """
    prev_len = 0
    stable_count = 0
    best_streamed_text = ""  # 스트리밍 중 ===제목=== 포함 최선의 텍스트

    _JS_CAPTURE_STREAMING = """() => {
        const sels = [
            'div.standard-markdown',
            '[data-testid="assistant-message-content"]',
            '[class*="assistant-message"] [class*="prose"]',
            '[class*="message-content"]',
            '[class*="response"] p',
        ];
        // 1단계: 단일 요소에 ===제목=== + 본문 모두 있으면 그것을 사용
        let best = '';
        for (const sel of sels) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                const t = el.innerText || '';
                if (t.includes('===제목===') && t.length > best.length) {
                    best = t;
                }
            }
        }
        if (best.includes('===본문===') || best.includes('===태그===') || best.length > 500) return best;
        // 2단계: 제목 요소와 본문 요소가 분리된 경우 합치기 (tool result collapse 대응)
        let bodyPart = '';
        for (const sel of sels) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
                const t = el.innerText || '';
                if (!t.includes('===제목===') && (t.includes('===본문===') || t.includes('===태그===') || t.includes('===이미지===')) && t.length > bodyPart.length) {
                    bodyPart = t;
                }
            }
        }
        if (best && bodyPart) return best + '\n' + bodyPart;
        return best || bodyPart;
    }"""

    for i in range(MAX_WAIT_SECS):
        page.wait_for_timeout(1000)

        # 현재 응답 길이 (여러 셀렉터 시도)
        cur_len = 0
        try:
            cur_len = page.evaluate("""(prevCount) => {
                const sels = [
                    'div.standard-markdown',
                    '[data-testid="assistant-message-content"]',
                    '[class*="assistant-message"] [class*="prose"]',
                    '[class*="message-content"]',
                    '[class*="response"] p',
                ];
                for (const sel of sels) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > prevCount) {
                        const t = els[els.length - 1].innerText;
                        if (t && t.length > 0) return t.length;
                    }
                    if (els.length > 0) {
                        const t = els[els.length - 1].innerText;
                        if (t && t.length > 100) return t.length;
                    }
                }
                return 0;
            }""", prev_response_count)
        except Exception:
            pass

        # 10초마다 로그
        if i > 0 and i % 10 == 0:
            log(f"[Playwright] {i}초 경과... ({cur_len}자 생성됨, 안정 {stable_count}초)")

        # 텍스트 변화 감지 — 10자 이하는 노이즈(사용자 메시지/thinking 표시)로 간주, 안정 카운트 안 함
        effective_len = cur_len if cur_len > 10 else 0
        if effective_len > 0 and effective_len == prev_len:
            stable_count += 1
        else:
            stable_count = 0
        prev_len = cur_len

        # 스트리밍 중 ===제목=== 포함 텍스트 포착 (나중에 collapse되기 전에 저장)
        # 매 5초마다 + cur_len > 100 이면 확인 — 더 긴 버전이 올 때마다 갱신
        if cur_len >= 100 or i % 5 == 0:
            try:
                captured = page.evaluate(_JS_CAPTURE_STREAMING)
                if captured and "===제목===" in captured and len(captured) > len(best_streamed_text):
                    best_streamed_text = captured
                    log(f"[Playwright] 스트리밍 중 응답 포착 ({len(best_streamed_text)}자)")
            except Exception:
                pass

        # ── 완료 판정 ──

        # 조건A: 충분한 글자수 + 20초 변화 없음
        if cur_len >= MIN_CHARS_FOR_DONE and stable_count >= STABLE_SECS_REQUIRED:
            # 완료 직전 마지막 포착 시도
            try:
                captured = page.evaluate(_JS_CAPTURE_STREAMING)
                if captured and "===제목===" in captured and len(captured) > len(best_streamed_text):
                    best_streamed_text = captured
            except Exception:
                pass
            log(f"[Playwright] 응답 완료 ({cur_len}자, {stable_count}초 변화 없음)")
            return cur_len, best_streamed_text

        # 조건B: 스트리밍이 확실히 끝남 (전송 버튼 재출현) + 최소 대기 20초
        if i >= 20 and stable_count >= 5 and _is_streaming_done(page):
            if cur_len >= MIN_CHARS_FOR_DONE:
                try:
                    captured = page.evaluate(_JS_CAPTURE_STREAMING)
                    if captured and "===제목===" in captured and len(captured) > len(best_streamed_text):
                        best_streamed_text = captured
                except Exception:
                    pass
                log(f"[Playwright] 응답 완료 (스트리밍 종료 확인, {cur_len}자)")
                return cur_len, best_streamed_text
            else:
                # 글자수 부족하지만 스트리밍은 끝남
                log(f"[Playwright] ⚠ 스트리밍 종료됐지만 글자수 부족 ({cur_len}자 < {MIN_CHARS_FOR_DONE}자)")
                # 글자수가 매우 짧으면(≤50) Claude가 확인 메시지만 보낸 것일 수 있음
                # 처음 한 번만 어떤 요소에서 왔는지 로그 출력
                if cur_len <= 50 and stable_count == 5:
                    try:
                        src = page.evaluate("""(prevCount) => {
                            const sels = ['div.standard-markdown','[data-testid="assistant-message-content"]',
                                '[class*="assistant-message"] [class*="prose"]','[class*="message-content"]','[class*="response"] p'];
                            for (const sel of sels) {
                                const els = document.querySelectorAll(sel);
                                if (els.length > 0) {
                                    const t = els[els.length-1].innerText||'';
                                    if (t.length > 0) return sel + ' → ' + t.substring(0,30);
                                }
                            }
                            return 'not found';
                        }""", prev_response_count)
                        log(f"[Playwright] 6자 출처: {src}")
                    except Exception:
                        pass
                # 추가 30초 대기 후 변화 없을 때만 포기
                if cur_len <= 50 and stable_count < STABLE_SECS_REQUIRED + 30:
                    continue
                if stable_count >= STABLE_SECS_REQUIRED:
                    log(f"[Playwright] 응답 정지 확정 ({cur_len}자)")
                    return cur_len, best_streamed_text

    log(f"[Playwright] 최대 대기 시간 초과 (5분) — {prev_len}자")
    return prev_len, best_streamed_text


def _extract_response(page, prev_response_count, log):
    """DOM에서 응답 텍스트를 추출한다. HTML→마크다운 변환으로 볼드/헤딩 보존."""
    page.wait_for_timeout(2000)
    response_text = ""

    # HTML 노드를 순회해 마크다운으로 변환 (볼드/**볼드**, 헤딩 ## 보존)
    _JS_TO_MD = """(sel) => {
        function toMd(el) {
            let r = '';
            for (const n of el.childNodes) {
                if (n.nodeType === 3) {
                    r += n.textContent;
                } else if (n.nodeType === 1) {
                    const t = n.tagName.toLowerCase();
                    if (t === 'strong' || t === 'b') r += '**' + toMd(n) + '**';
                    else if (t === 'em' || t === 'i') r += '*' + toMd(n) + '*';
                    else if (t === 'h2') r += '\\n## ' + toMd(n) + '\\n';
                    else if (t === 'h3') r += '\\n### ' + toMd(n) + '\\n';
                    else if (t === 'h1') r += '\\n# ' + toMd(n) + '\\n';
                    else if (t === 'p') r += toMd(n) + '\\n\\n';
                    else if (t === 'br') r += '\\n';
                    else if (t === 'li') r += '- ' + toMd(n) + '\\n';
                    else if (t === 'ul' || t === 'ol') r += '\\n' + toMd(n);
                    else if (t === 'code') r += '`' + n.textContent + '`';
                    else if (t === 'pre') r += '\\n```\\n' + n.textContent + '\\n```\\n';
                    else if (t === 'table') {
                        const rows = [];
                        for (const tr of n.querySelectorAll('tr')) {
                            const cells = [];
                            for (const td of tr.querySelectorAll('th, td')) {
                                cells.push((td.innerText || '').trim().replace(/\\|/g, '\\\\|'));
                            }
                            if (cells.length) rows.push('| ' + cells.join(' | ') + ' |');
                        }
                        if (rows.length >= 2) {
                            const sep = '| ' + rows[0].split('|').slice(1,-1).map(() => '---').join(' | ') + ' |';
                            rows.splice(1, 0, sep);
                        }
                        r += '\\n' + rows.join('\\n') + '\\n\\n';
                    }
                    else r += toMd(n);
                }
            }
            return r;
        }
        const els = document.querySelectorAll(sel);
        if (!els.length) return '';
        const md = toMd(els[els.length - 1]);
        return (md && md.trim().length > 50) ? md : '';
    }"""

    for sel in RESPONSE_SEL_FALLBACKS:
        try:
            candidate = page.evaluate(_JS_TO_MD, sel)
            if candidate and len(candidate.strip()) > 50:
                # ===본문=== 포함하는 더 긴 응답을 우선 사용 (제목만 있는 50자짜리보다 본문 있는 응답 선호)
                prefer = "===본문===" in candidate and "===본문===" not in response_text
                longer = len(candidate.strip()) > len(response_text.strip())
                if prefer or (longer and "===본문===" not in response_text):
                    response_text = candidate
                    if sel != RESPONSE_SEL:
                        log(f"[Playwright] 응답 셀렉터 폴백 사용: {sel}")
        except Exception:
            pass

    # 최후 수단: innerText (볼드 손실)
    if not response_text.strip():
        try:
            response_text = page.evaluate("""() => {
                const sels = [
                    'div.standard-markdown',
                    '[data-testid*="assistant"]',
                    '[class*="assistant-message"]',
                    '[class*="response-content"]',
                ];
                for (const s of sels) {
                    const els = document.querySelectorAll(s);
                    if (els.length > 0) {
                        const t = els[els.length - 1].innerText;
                        if (t && t.length > 50) return t;
                    }
                }
                return '';
            }""")
        except Exception:
            pass

    # 최후 수단1.5: 가장 긴 텍스트 블록 자동 탐색 (셀렉터 변경 대응)
    if not response_text.strip():
        try:
            dom_info = page.evaluate("""() => {
                // 텍스트 100자 이상인 요소 중 가장 긴 것 3개 찾기
                const all = Array.from(document.querySelectorAll('div,article,section,p'));
                const candidates = all
                    .filter(el => {
                        const t = el.innerText || '';
                        return t.length > 100 && t.includes('===');
                    })
                    .sort((a, b) => (b.innerText||'').length - (a.innerText||'').length)
                    .slice(0, 3);
                return candidates.map(el => ({
                    tag: el.tagName,
                    cls: el.className.substring(0, 80),
                    id: el.id,
                    len: (el.innerText||'').length,
                    text: (el.innerText||'').substring(0, 200),
                }));
            }""")
            if dom_info:
                log(f"[Playwright] DOM 후보 요소 {len(dom_info)}개 발견:")
                for d in dom_info:
                    log(f"  <{d['tag']} class='{d['cls']}' id='{d['id']}'> {d['len']}자")
                # 가장 긴 후보에서 텍스트 추출
                best = page.evaluate("""() => {
                    const all = Array.from(document.querySelectorAll('div,article,section'));
                    const cands = all
                        .filter(el => (el.innerText||'').includes('===제목==='))
                        .sort((a, b) => (b.innerText||'').length - (a.innerText||'').length);
                    return cands.length ? cands[0].innerText : '';
                }""")
                if best and "===제목===" in best:
                    response_text = best
                    log(f"[Playwright] DOM 자동 탐색 성공: {len(best)}자")
        except Exception as e:
            log(f"[Playwright] DOM 자동 탐색 실패: {e}")

    # 최후 수단2: 페이지 전체 텍스트에서 ===제목=== 패턴 직접 탐색
    if not response_text.strip() or "추출 실패" in response_text:
        try:
            all_text = page.evaluate("""() => {
                // 모든 텍스트 노드에서 ===제목=== 패턴 검색
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                let full = '';
                let n;
                while ((n = walker.nextNode())) full += n.textContent;
                return full;
            }""")
            if all_text and "===제목===" in all_text:
                # ===제목=== ~ ===이미지끝=== 구간 추출
                m = re.search(r"===제목===(.*?)(?:===이미지끝===|$)", all_text, re.DOTALL)
                if m:
                    response_text = "===제목===" + m.group(1)
                    if "===이미지끝===" in all_text:
                        response_text += "===이미지끝==="
                    log(f"[Playwright] 최후 폴백: 페이지 텍스트에서 섹션 추출 ({len(response_text)}자)")
        except Exception as e:
            log(f"[Playwright] 최후 폴백 실패: {e}")

    # 최종 검증: ===제목=== 없으면 UI 텍스트나 garbage를 잘못 추출한 것
    if response_text.strip() and "===제목===" not in response_text:
        log(f"[Playwright] ⚠ 추출된 텍스트에 ===제목=== 없음 — 잘못된 추출로 판단, 무효화")
        log(f"[Playwright] 추출 텍스트 앞 100자: {response_text[:100]}")
        response_text = ""

    if not response_text.strip():
        response_text = "[추출 실패] DOM에서 응답을 찾지 못했습니다."

    return response_text.strip()


def repair_text(raw: str, issues: list, on_log=None) -> str:
    """검수 실패한 글을 이슈 목록 기반으로 Claude에 부분 수정 요청.

    전체 재생성 대신 기존 글 + 문제점만 전달해서 빠르게 수정.
    Returns: 수정된 raw 텍스트 (실패 시 None)
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

    log("[repair] 부분 수정 요청 중...")
    result = generate_text(repair_prompt, on_log=on_log)
    if result and "추출 실패" not in result and len(result) > 200:
        log("[repair] ✓ 부분 수정 완료")
        return result
    log("[repair] 부분 수정 실패")
    return None


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                   on_log=None, extra_context: str = None):
    """claude.ai에 프롬프트를 보내고 응답 텍스트를 반환한다.

    blog_id + keyword가 주어지면 Notion에서 프롬프트를 가져와 사용.
    extra_context가 있으면 프롬프트 맨 앞에 참고 자료로 주입.
    응답 500자 미만이면 최대 2회 재시도.
    Claude 실패 시 Gemini로 자동 폴백.
    """

    def log(msg):
        if on_log:
            on_log(msg)

    # 볼드 처리 + 제목 형식 + 이미지 공통 규칙
    _BOLD_RULE = (
        "\n\n[볼드 처리 규칙]\n"
        "중요한 내용은 반드시 **볼드** 처리해줘.\n"
        "볼드 처리 대상: 핵심 키워드, 중요 수치/금액, 신청 기간 및 마감일, 자격 조건, 주의사항\n"
        "볼드 남용 금지: 한 문단에 1~2개 이내\n"
        "제목(H2/H3)은 볼드 처리 불필요\n"
        "\n[제목 규칙]\n"
        "===제목=== 안의 제목은 반드시 명사형/명사구로 작성해.\n"
        "문장형 어미(~습니다/~해요/~입니다/~세요/~합니다/~있어요) 절대 금지.\n"
        "제목에 '완벽가이드', '완벽정리', '완벽정복', '완벽 가이드', '완벽 정리', '완벽 정복', '총정리', '꿀팁', '마이리얼트립', '한눈에 보기', '한눈에 정리', '알아보기', '쉽게 알아보는', '대해서 알아보자' 등 마케팅/요약 문구 절대 금지.\n"
        "제목이 '정리'로 끝나는 것도 금지 (예: '~항목 정리', '~내용 정리'). 단 '정리수납' 같은 합성어는 허용.\n"
        "제목은 구체적인 롱테일 검색어처럼 — 조건/날짜/지역/방법 등 세부 정보 포함.\n"
        "예) X: '다자녀 혜택 지원금 총정리'\n"
        "예) O: '다자녀 혜택 2026 신청 조건 자격 지원금 종류'\n"
        "키워드에 아래 패턴이 포함되면 해당 질문형/공감형 제목으로 변환:\n"
        "  ~안될때 → '~가 안 될 때 이렇게 해결했어요'\n"
        "  ~오류   → '~오류 떴을 때 원인과 해결법'\n"
        "  ~이유   → '왜 ~이 되는 걸까요'\n"
        "  ~후기   → '직접 써본 ~ 후기'\n"
        "  ~비교   → '~, 뭐가 더 나을까요'\n"
        "예) X: '제주도 3박4일 완벽 가이드'\n"
        "예) O: '제주도 3박4일 뚜벅이 여행 코스 숙소 경비'\n"
        "예) X: '갤럭시 S25 배터리 설정 방법을 알아보겠습니다'\n"
        "예) O: '갤럭시 S25 배터리 설정 방법'\n"
        "\n[이미지 규칙]\n"
        "반드시 ===이미지=== 섹션에 이미지 2개를 포함해줘.\n"
        "형식:\n"
        "===이미지===\n"
        "[이미지1]\n"
        "- Gemini프롬프트: (Gemini 이미지 생성용 영어 또는 한국어 프롬프트)\n"
        "- 파일명: (영문-소문자-하이픈.webp)\n"
        "- alt: (키워드 포함 한국어 alt 텍스트)\n"
        "[이미지2]\n"
        "- Gemini프롬프트: ...\n"
        "- 파일명: ...\n"
        "- alt: ...\n"
        "===이미지끝==="
    )

    # 본문 헤딩/볼드 형식 강제 규칙 (프로젝트 모드 포함 모든 블로그에 적용)
    _FORMAT_RULE = (
        "\n\n[제목 규칙 — 필수]\n"
        "===제목=== 안의 제목에 '완벽가이드', '완벽정리', '완벽정복', '완벽 가이드', '완벽 정리', '완벽 정복', '총정리', '꿀팁', '마이리얼트립', '한눈에 보기', '한눈에 정리', '알아보기', '쉽게 알아보는', '대해서 알아보자' 절대 금지.\n"
        "제목이 '정리'로 끝나는 것도 금지 (예: '~항목 정리', '~내용 정리'). 단 '정리수납' 같은 합성어는 허용.\n"
        "제목은 구체적인 롱테일 검색어처럼 — 조건/날짜/지역/방법 등 세부 정보 포함. 예) '제주도 3박4일 뚜벅이 여행 코스 숙소 경비'\n"
        "키워드에 아래 패턴이 포함되면 해당 질문형/공감형 제목으로 변환:\n"
        "  ~안될때 → '~가 안 될 때 이렇게 해결했어요'\n"
        "  ~오류   → '~오류 떴을 때 원인과 해결법'\n"
        "  ~이유   → '왜 ~이 되는 걸까요'\n"
        "  ~후기   → '직접 써본 ~ 후기'\n"
        "  ~비교   → '~, 뭐가 더 나을까요'\n"
        "\n[말투 규칙 — 필수]\n"
        "본문 전체를 반드시 존댓말(해요체/합니다체)로 작성해. 예) '~해요', '~입니다', '~됩니다', '~있어요'.\n"
        "독자에게 반말(~야, ~해, ~봐, ~지) 절대 금지. 친한 독자에게 정보를 안내하는 따뜻한 해요체.\n"
        "문장이 마침표('.')로 끝날 경우 반드시 빈 줄(엔터 두 번)로 단락을 구분해. 모바일 가독성 최우선.\n"
        "\n[AI 글쓰기 금지 패턴 — 필수]\n"
        "아래는 AI 특유의 어색한 표현 — 절대 사용 금지:\n"
        "금지 단어: '정말', '압도적으로', '환상적이다', '환상적인', '마치', '놀라운', '실로', '탁월한', '눈에 띄게', '뛰어나다', '한마디로', '경이로운'\n"
        "금지 패턴: '~살펴보겠습니다', '~알아보겠습니다', '~라고 할 수 있습니다', '~라고 볼 수 있습니다', '다양한 ~', '여러 가지 ~', '~해 보겠습니다'\n"
        "금지 문장: '100% 확신합니다', '무조건 추천드려요', '완벽한 선택입니다'\n"
        "대체 표현: '꽤', '꽤나', '진짜', '괜찮던데요', '마음에 들더라고요', '~더라고요', '~하던데요', '~더라고요'\n"
        "\n[본문 형식 규칙 — 필수]\n"
        "본문 첫 소제목 바로 위에 핵심요약 박스를 3줄 이내로 작성해 (HTML div 사용):\n"
        "<div style=\"background:#f8f9fa;border-left:4px solid #4A90D9;padding:12px 16px;margin:16px 0;border-radius:4px\">\n"
        "💡 핵심요약<br>• (핵심 정보 1줄)<br>• (핵심 정보 2줄)<br>• (핵심 정보 3줄)\n"
        "</div>\n"
        "본문 소제목은 반드시 ## (H2) 또는 ### (H3) 마크다운 헤딩 형식으로 작성해.\n"
        "예) ## 소제목 텍스트\n"
        "중요 키워드·수치·조건은 **볼드** 처리해. (한 문단 1~2개 이내)\n"
        "구체적 수치·날짜·금액 반드시 포함. 모호한 '알려져 있습니다' '~로 보입니다' 금지.\n"
        "본문 마지막 단락에 면책 문구 한 줄 추가: '※ 이 글은 2026년 기준으로 작성되었으며, 정책·요금은 변동될 수 있습니다.'\n"
        "본문 길이: 공백 제외 순수 텍스트 **반드시 2000자 이상** 작성 (소제목 3개 이상, 각 소제목 아래 3~5문단).\n"
        "\n[이미지 규칙 — 필수]\n"
        "본문 내 소제목 아래에 {{이미지1}}, {{이미지2}}, {{이미지3}} 마커를 반드시 삽입해 (글 내용과 연관된 위치에).\n"
        "그리고 본문 끝에 ===이미지=== 섹션으로 각 이미지의 Gemini 생성 프롬프트를 작성해.\n"
        "이미지는 글 주제와 직접 연관된 내용으로 — 연관없는 스톡 이미지 금지.\n"
        "===이미지===\n"
        "[이미지1]\n"
        "- Gemini프롬프트: (글 내용과 연관된 구체적 영어 프롬프트)\n"
        "- 파일명: (영문-소문자-하이픈.jpg)\n"
        "- alt: (키워드 포함 한국어 alt 텍스트)\n"
        "[이미지2]\n"
        "- Gemini프롬프트: ...\n"
        "- 파일명: ...\n"
        "- alt: ...\n"
        "[이미지3]\n"
        "- Gemini프롬프트: ...\n"
        "- 파일명: ...\n"
        "- alt: ...\n"
        "===이미지끝===\n"
    )

    # Claude Project가 설정된 blog_id면 키워드만 전송 — 프로젝트 지침이 모든 규칙 담당
    # 팩트(공식사이트 수치)는 동적 데이터라 프로젝트에 넣을 수 없으므로 별도 주입
    # 프로젝트 미설정 blog_id면 기존대로 Notion에서 전체 프롬프트 가져오기
    if blog_id and keyword:
        if blog_id in BLOG_PROJECT_URLS:
            # 프로젝트 모드: 키워드 + 모바일 문단 규칙 추가
            _MOBILE_PARA_RULE = (
                "\n\n[모바일 가독성 규칙 — 필수]\n"
                "각 문단은 1~2문장으로 짧게 작성해. 문장이 끝나면 반드시 빈 줄(엔터 두 번)로 구분해.\n"
                "긴 문단(3문장 이상 연속) 절대 금지. 모바일에서 스크롤하기 편하게 짧은 덩어리로 나눠줘.\n"
            )
            prompt = keyword + _MOBILE_PARA_RULE

            # 롱테일 키워드 → 1가지 주제 심층 작성 (블로그별)
            if blog_id in {"nolja100", "triplog"}:
                prompt += (
                    "\n\n[작성자 설정 — 여행 블로거 필수]\n"
                    "주말 나들이나 여행 코스를 친근하게 소개하는 30대 블로거의 편안한 말투로 작성해.\n"
                    "'~했어요', '~하더라고요', '~가볼 만해요', '괜찮더라고요' 등 자연스러운 구어체 사용.\n"
                    "뉴스 기사나 백과사전처럼 딱딱하게 쓰는 것 금지. 동네 친구가 여행 후기 얘기해주는 느낌.\n"
                )
                # 2박3일/1박2일 코스 키워드는 일정 중심, 그 외는 1곳 집중
                is_itinerary = any(w in keyword for w in ["2박3일", "1박2일", "3박4일", "당일치기", "일정", "코스"])
                if is_itinerary:
                    prompt += (
                        "\n\n[여행 코스 작성 규칙 — 필수]\n"
                        "이 키워드를 검색하는 사람은 '실제로 어떻게 다닐지' 모르는 상태야.\n"
                        "단순 관광지 나열 금지. 아래를 반드시 포함해:\n"
                        "1. 날짜별 상세 동선 (몇 시에 어디서 출발 → 어디로 이동)\n"
                        "2. 각 장소 실제 입장료·운영시간·주차 정보\n"
                        "3. 숙소 추천 지역 + 가격대 (실제 예산)\n"
                        "4. 교통 수단별 비용 (지하철, 버스, 택시)\n"
                        "5. 현지인만 아는 꿀팁 (줄 서는 시간, 비수기 팁 등)\n"
                        "Wikipedia·관광청 자료 수준 금지. 실제 여행자에게 바로 도움 되는 정보만.\n"
                    )
                else:
                    prompt += (
                        "\n\n[장소 심층 작성 규칙 — 필수]\n"
                        "이 키워드를 검색하는 사람은 '어디가 좋은지'를 모르는 상태야.\n"
                        "키워드에서 가장 적합한 장소(관광지·식당·숙소·코스) 1곳을 직접 선정해서 그 장소만 깊게 작성해.\n"
                        "예) '속초 여행 추천 강원도 뚜벅이' → '속초 영금정' 1곳 집중\n"
                        "여러 장소를 나열하는 가이드 글 금지. 1곳의 볼거리·먹거리·교통·시간·꿀팁을 구체적으로 작성해.\n"
                        "반드시 포함: 실제 입장료, 운영시간, 주차 유무, 가는 법 (버스 번호·도보 시간).\n"
                    )
            elif blog_id in {"goodisak"}:
                prompt += (
                    "\n\n[주제 심층 작성 규칙 — 필수]\n"
                    "goodisak 블로그는 IT 기기 리뷰·추천, 금융 정보, 정부지원·복지 혜택을 다루는 블로그야.\n"
                    "이 키워드를 검색하는 사람이 진짜 알고 싶어하는 1가지 핵심 정보를 직접 선정해서 깊게 작성해.\n"
                    "예) '삼성노트북 추천 2026' → 갤럭시북6 구체적 스펙·가격·용도별 추천\n"
                    "예) '청년도약계좌 신청방법' → 대상·금액·신청절차 1가지 집중\n"
                    "여러 제품/제도를 단순 나열하는 글 금지. 1가지를 구체적 수치·조건·사용 경험 기준으로 깊게 작성해.\n"
                )
            elif blog_id in {"salim1su"}:
                prompt += (
                    "\n\n[주제 심층 작성 규칙 — 필수]\n"
                    "이 키워드를 검색하는 사람은 '어떻게 하면 되는지' 구체적인 방법을 모르는 상태야.\n"
                    "키워드에서 가장 적합한 살림 방법·절약 팁·생활 정보 1가지를 직접 선정해서 그것만 깊게 작성해.\n"
                    "예) '냉장고 전기세 절약 방법 여름' → '냉장고 온도 설정 1가지' 집중\n"
                    "여러 방법을 나열하는 글 금지. 1가지를 단계별로 구체적으로 작성해.\n"
                )
            elif blog_id in {"baremi542"}:
                prompt += (
                    "\n\n[주제 심층 작성 규칙 — 필수]\n"
                    "이 키워드를 검색하는 사람은 '어떤 혜택을 받을 수 있는지' 모르는 상태야.\n"
                    "키워드에서 가장 적합한 정부지원·복지·생활정보 1가지를 직접 선정해서 그것만 깊게 작성해.\n"
                    "예) '2026 복지 혜택 신청 방법 서민' → '주거급여' 1가지 집중\n"
                    "여러 혜택을 나열하는 글 금지. 1가지의 대상·신청절차·금액·유의사항을 구체적으로 작성해.\n"
                    "\n[글쓰기 형식 — 필수]\n"
                    "반드시 정보성 가이드 형식으로 작성해. 경험담/후기 형식 절대 금지.\n"
                    "1인칭 서술('저는', '다녀왔어요', '해봤어요', '찾아봤어요') 절대 금지.\n"
                    "독자에게 정보를 전달하는 설명체로 작성해. 예) '신청 방법은 ~입니다', '대상은 ~이에요'\n"
                    "마치 실제 경험한 것처럼 쓰는 것 금지. 공식 정보를 정확하게 가이드하는 글로 작성해.\n"
                )

            # 프로젝트 모드에도 본문 길이 + 이미지 형식 규칙 명시 (짧은 글 방지)
            prompt += _FORMAT_RULE
            log(f"[Playwright] 프로젝트 모드 — 키워드+모바일규칙+형식규칙 전송: '{keyword}'")
        else:
            try:
                prompt = fetch_prompt(blog_id, keyword, on_log)
                prompt = prompt + _BOLD_RULE
            except Exception as e:
                log(f"[Notion] 프롬프트 가져오기 실패: {e}")
                log("[Notion] 기본 프롬프트로 진행합니다.")
                # Notion 페이지 없을 때 키워드 + 형식 규칙으로 기본 프롬프트 구성
                if keyword and not prompt.strip():
                    _SECTION_FORMAT = (
                        "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
                        "===제목===\n"
                        "(SEO 최적화된 롱테일 제목 — 구체적 조건/지역/방법 포함 명사구, 25~45자)\n"
                        "===제목끝===\n\n"
                        "===본문===\n"
                        "(블로그 본문 전체)\n"
                        "===본문끝===\n\n"
                        "===태그===\n"
                        "태그1, 태그2, 태그3 (10~20개)\n"
                        "===태그끝===\n"
                    )
                    prompt = keyword + _SECTION_FORMAT + _FORMAT_RULE + _BOLD_RULE

    # 팩트 컨텍스트 주입 — 프로젝트 모드 포함 항상 주입 (할루시네이션 방지 핵심)
    # 키워드 뒤에 붙여서 프로젝트 지침이 앞에 오도록 구조 유지
    if extra_context:
        prompt = f"{prompt}\n\n[참고 자료 — 아래 수치/날짜만 사용, 임의 수치 금지]\n{extra_context}"
        log(f"[Playwright] 팩트 컨텍스트 주입: {len(extra_context)}자")

    # 프롬프트 내용 확인 로그
    log(f"[Playwright] 프롬프트 길이: {len(prompt)}자")
    log(f"[Playwright] 프롬프트 처음 200자: {prompt[:200]}...")

    log("[Playwright] CDP 연결 중...")
    pw, browser = _connect_cdp(on_log)
    page = get_or_create_page(browser, url_contains="claude.ai", navigate_to=CLAUDE_URL)

    # blog_id에 해당하는 프로젝트 URL 결정
    project_url = BLOG_PROJECT_URLS.get(blog_id) if blog_id else None
    if project_url:
        log(f"[Playwright] 프로젝트 모드: {blog_id} → {project_url}")
    else:
        log(f"[Playwright] 일반 모드: /new")

    try:
        response_text = ""
        for attempt in range(1, MAX_RETRIES + 2):
            if attempt > 1:
                log(f"[Playwright] === 재시도 {attempt - 1}/{MAX_RETRIES} ===")
                page.wait_for_timeout(5000)

            log(f"[Playwright] claude.ai 페이지 준비 ({page.url})")

            # 새 대화 시작
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            except Exception:
                pass

            # JavaScript 다이얼로그 자동 수락 (페이지 이동 시 confirm/alert 팝업 방지)
            page.on("dialog", lambda d: d.dismiss())

            if project_url:
                # 재시도 시 또는 현재 URL이 특정 채팅이면 프로젝트 루트로 새 채팅 시작
                if attempt > 1 or "/chat/" in page.url:
                    log(f"[Playwright] 프로젝트 루트로 새 채팅 시작")
                    page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(4000)
                else:
                    page.goto(project_url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
            else:
                page.goto(f"{CLAUDE_URL}/new", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                if "/new" not in page.url:
                    log("[Playwright] /new 페이지 로딩 재시도...")
                    page.goto(f"{CLAUDE_URL}/new", wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(3000)

            # 입력창
            input_sel = 'div[contenteditable="true"]'
            page.wait_for_selector(input_sel, state="visible", timeout=30000)
            log(f"[Playwright] 프롬프트 입력 중 ({len(prompt)}자)...")

            page.locator(input_sel).first.click()
            page.wait_for_timeout(300)
            page.evaluate("""(text) => {
                const el = document.querySelector('div[contenteditable="true"]');
                el.focus();
                document.execCommand('insertText', false, text);
            }""", prompt)
            page.wait_for_timeout(500)

            # 입력된 텍스트 길이 확인
            typed_len = page.evaluate("""() => {
                const el = document.querySelector('div[contenteditable="true"]');
                return el ? el.innerText.length : 0;
            }""")
            log(f"[Playwright] 입력창에 {typed_len}자 입력됨")

            min_len = 3 if project_url else 100
            if typed_len < min_len:
                log("[Playwright] ⚠ 프롬프트 입력 실패 — 재시도")
                page.wait_for_timeout(2000)
                continue

            # 전송
            log("[Playwright] 전송 중...")
            sent = False
            try:
                send_btn = page.locator(SEND_BTN_SEL).first
                if send_btn.count() > 0:
                    send_btn.click(timeout=5000)
                    sent = True
                    log("[Playwright] 전송 버튼 클릭")
            except Exception as e:
                log(f"[Playwright] 전송 버튼 클릭 실패: {e}")

            if not sent:
                # 폴백: Enter 키
                log("[Playwright] 폴백 — Enter 키로 전송")
                page.keyboard.press("Enter")

            page.wait_for_timeout(2000)

            prev_response_count = page.locator(RESPONSE_SEL).count()
            log(f"[Playwright] 기존 응답 블록: {prev_response_count}개")

            # 응답 대기
            log("[Playwright] 응답 대기 중...")
            final_len, streamed_text = _wait_for_response(page, prev_response_count, log)

            # 스트리밍 중 포착된 텍스트가 있으면 우선 사용 (tool result collapse 대응)
            # 단, 본문(===본문===)이 포함된 경우에만 사용 — 제목만 있는 50자짜리 캡처는 스킵
            if streamed_text and "===제목===" in streamed_text and "===본문===" in streamed_text:
                response_text = streamed_text
                log(f"[Playwright] 스트리밍 포착 텍스트 사용 ({len(response_text)}자)")
            else:
                # 응답 추출
                log("[Playwright] 응답 추출 중...")
                # 현재 페이지에 있는 응답 블록 수 확인 (디버그용)
                try:
                    cur_sel_counts = {}
                    for _sel in RESPONSE_SEL_FALLBACKS[:3]:
                        cur_sel_counts[_sel] = page.locator(_sel).count()
                    log(f"[Playwright] 셀렉터별 응답 블록 수: {cur_sel_counts}")
                except Exception:
                    pass
                response_text = _extract_response(page, prev_response_count, log)
                # DOM 추출 실패 시 스트리밍 중 포착된 텍스트를 폴백으로 사용
                if "[추출 실패]" in response_text and streamed_text and "===제목===" in streamed_text and len(streamed_text) > 500:
                    response_text = streamed_text
                    log(f"[Playwright] DOM 추출 실패 → 스트리밍 포착 텍스트 폴백 사용 ({len(response_text)}자)")

            # 글자수 확인
            body_chars = _count_body_chars(response_text)
            log(f"[Playwright] 추출 완료 (전체 {len(response_text)}자, 본문 순수 {body_chars}자)")
            log(f"[Playwright] 응답 처음 200자: {response_text[:200]}")

            # 500자 이상이면 성공
            if body_chars >= RETRY_THRESHOLD:
                return response_text

            # 그리팅 감지: 짧은 응답 + "키워드" 언급 → 프로젝트가 키워드를 별도로 요청하는 중
            # 새 채팅 열지 말고 같은 창에서 키워드만 다시 전송
            is_greeting = (
                len(response_text) < 600
                and "===제목===" not in response_text
                and project_url is not None
                and keyword is not None
                and any(w in response_text for w in ["키워드", "시작할게", "알려주", "입력해", "시작하겠", "확인했어요", "선정할게", "방향"])
            )
            if is_greeting and attempt <= MAX_RETRIES:
                log(f"[Playwright] ⚠ 그리팅 응답 감지 — 같은 창에서 키워드 재전송")
                page.wait_for_timeout(2000)
                input_sel = 'div[contenteditable="true"]'
                try:
                    page.wait_for_selector(input_sel, state="visible", timeout=10000)
                    page.locator(input_sel).first.click()
                    page.wait_for_timeout(300)
                    # 키워드만 전송 (프로젝트 지침이 형식 담당)
                    page.evaluate("""(text) => {
                        const el = document.querySelector('div[contenteditable="true"]');
                        el.focus();
                        document.execCommand('insertText', false, text);
                    }""", keyword)
                    page.wait_for_timeout(500)
                    send_btn = page.locator(SEND_BTN_SEL).first
                    if send_btn.count() > 0:
                        send_btn.click(timeout=5000)
                        log("[Playwright] 키워드 재전송 완료")
                    else:
                        page.keyboard.press("Enter")
                    page.wait_for_timeout(2000)
                    prev_response_count2 = page.locator(RESPONSE_SEL).count()
                    final_len2, streamed_text2 = _wait_for_response(page, prev_response_count2, log)
                    if streamed_text2 and "===제목===" in streamed_text2 and "===본문===" in streamed_text2:
                        response_text = streamed_text2
                    else:
                        response_text = _extract_response(page, prev_response_count2, log)
                    body_chars2 = _count_body_chars(response_text)
                    log(f"[Playwright] 키워드 재전송 후 응답: {body_chars2}자")
                    if body_chars2 >= RETRY_THRESHOLD:
                        return response_text
                except Exception as e:
                    log(f"[Playwright] 키워드 재전송 실패: {e}")
                page.wait_for_timeout(2000)
                continue

            # 500자 미만이고 재시도 횟수 남았으면 재시도
            if attempt <= MAX_RETRIES:
                log(f"[Playwright] ⚠ 본문 {body_chars}자 < {RETRY_THRESHOLD}자 — 재시도합니다")
                page.wait_for_timeout(3000)
                continue

            # 재시도 소진
            log(f"[Playwright] ⚠ 재시도 소진 — {body_chars}자로 진행")
            return response_text

        return response_text

    finally:
        pw.stop()


def ask_with_image(image_path: str, question: str, blog_id: str = None, on_log=None) -> str:
    """Claude.ai에 이미지 + 질문을 보내고 응답 텍스트를 반환한다.

    블로그 글 생성이 아닌 단순 질의응답용 (이미지 분석 → 짧은 텍스트 반환).
    blog_id가 있으면 해당 프로젝트 URL로 이동.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    from pathlib import Path as _Path

    pw, browser = _connect_cdp(on_log)
    page = get_or_create_page(browser, url_contains="claude.ai", navigate_to=CLAUDE_URL)

    project_url = BLOG_PROJECT_URLS.get(blog_id) if blog_id else None
    nav_url = project_url or f"{CLAUDE_URL}/new"

    try:
        page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # 이미지 첨부
        image_attached = False
        if image_path and _Path(image_path).exists():
            try:
                attach_selectors = [
                    'button[aria-label="Attach files"]',
                    'button[aria-label="파일 첨부"]',
                    'button[aria-label="Add attachment"]',
                    'button[aria-label*="ttach"]',
                    '[data-testid="attach-file-button"]',
                    'label[for*="file"]',
                ]
                clicked = False
                with page.expect_file_chooser(timeout=8000) as fc_info:
                    for sel in attach_selectors:
                        try:
                            btn = page.locator(sel).first
                            if btn.is_visible(timeout=1000):
                                btn.click()
                                clicked = True
                                break
                        except Exception:
                            pass
                    if not clicked:
                        # 숨겨진 파일 input 직접 탐색
                        page.evaluate("""() => {
                            const inp = document.querySelector('input[type="file"]');
                            if (inp) inp.click();
                        }""")
                if clicked or True:
                    fc_info.value.set_files(image_path)
                    page.wait_for_timeout(2000)
                    image_attached = True
                    log(f"[Claude] 이미지 첨부 완료: {_Path(image_path).name}")
            except Exception as e:
                log(f"[Claude] 이미지 첨부 실패 (텍스트만 전송): {e}")

        # 질문 입력
        input_sel = 'div[contenteditable="true"]'
        page.wait_for_selector(input_sel, state="visible", timeout=30000)
        page.locator(input_sel).first.click()
        page.wait_for_timeout(300)
        page.evaluate("""(text) => {
            const el = document.querySelector('div[contenteditable="true"]');
            el.focus();
            document.execCommand('insertText', false, text);
        }""", question)
        page.wait_for_timeout(500)

        # 전송
        sent = False
        try:
            send_btn = page.locator(SEND_BTN_SEL).first
            if send_btn.count() > 0:
                send_btn.click(timeout=5000)
                sent = True
        except Exception:
            pass
        if not sent:
            page.keyboard.press("Enter")
        log("[Claude] 이미지+질문 전송, 응답 대기...")

        # 응답 대기 (짧은 응답이라 기준 낮춤 — 최대 90초, 5초 이상 안정되면 완료)
        prev_len = 0
        stable_count = 0
        for i in range(90):
            page.wait_for_timeout(1000)
            cur_len = 0
            try:
                cur_len = page.evaluate("""() => {
                    const sels = [
                        'div.standard-markdown',
                        '[data-testid="assistant-message-content"]',
                        '[class*="assistant-message"] [class*="prose"]',
                        '[class*="message-content"]',
                    ];
                    for (const sel of sels) {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) {
                            const t = (els[els.length-1].innerText || '').trim();
                            if (t.length > 10) return t.length;
                        }
                    }
                    return 0;
                }""")
            except Exception:
                pass

            if cur_len > 10 and cur_len == prev_len:
                stable_count += 1
            else:
                stable_count = 0
            prev_len = cur_len

            if stable_count >= 5 and cur_len > 20:
                log(f"[Claude] 응답 완료 ({cur_len}자, {stable_count}초 안정)")
                break

            if i > 0 and i % 15 == 0:
                log(f"[Claude] 대기 중... {i}초 ({cur_len}자)")

        # 응답 텍스트 추출
        response = page.evaluate("""() => {
            const sels = [
                'div.standard-markdown',
                '[data-testid="assistant-message-content"]',
                '[class*="assistant-message"] [class*="prose"]',
                '[class*="message-content"]',
            ];
            for (const sel of sels) {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) {
                    const t = (els[els.length-1].innerText || '').trim();
                    if (t.length > 10) return t;
                }
            }
            return '';
        }""")

        log(f"[Claude] 응답 추출: {len(response)}자 | {response[:80]}...")
        return response.strip()

    except Exception as e:
        log(f"[Claude] ask_with_image 오류: {e}")
        return ""
    finally:
        pw.stop()


def generate_text_with_fallback(prompt: str, blog_id: str = None, keyword: str = None,
                                 on_log=None, extra_context: str = None):
    """AI_PROVIDER 환경변수에 따라 Claude 또는 Gemini로 글을 생성한다.

    AI_PROVIDER=claude (기본) → Claude.ai 사용
    AI_PROVIDER=gemini        → Gemini 사용
    """
    import os
    provider = os.environ.get("AI_PROVIDER", "claude").lower()

    def log(msg):
        if on_log:
            on_log(msg)

    if provider == "gemini":
        log("[Writer] Gemini.google.com으로 글 생성...")
        import gemini_playwright as _gemini
        return _gemini.generate_text(prompt, blog_id=blog_id, keyword=keyword,
                                     on_log=on_log, extra_context=extra_context)
    else:
        log("[Writer] Claude.ai로 글 생성...")
        return generate_text(prompt, blog_id=blog_id, keyword=keyword,
                             on_log=on_log, extra_context=extra_context)
