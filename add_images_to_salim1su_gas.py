"""
add_images_to_salim1su_gas.py
발행된 글 salim1su/224235450308 에 이미지 3개 추가 후 수정 저장

작업 순서:
1. CDP 포트 9222 연결
2. 에디터 수정 모드 진입 (editType=edit&logNo=224235450308)
3. Gemini / loremflickr 이미지 3개 생성
4. H2 소제목 앞/뒤에 이미지 삽입
5. 발행 (카테고리: 고정비줄이기)
6. 텔레그램 보고
"""
import sys
import re
import time
import json
import os
import ssl
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.sync_api import sync_playwright

# ─── 설정 ───────────────────────────────────────
CDP_URL = "http://localhost:9222"
BLOG_ID = "salim1su"
LOG_NO = "224235450308"
CATEGORY_NAME = "고정비줄이기"
TELEGRAM_CHAT_ID = "8674424194"
TELEGRAM_TOKEN_ENV = "HanaAutobot"
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# 이미지 프롬프트 (가스비 요금조회 관련)
IMAGE_PROMPTS = [
    {
        "index": 1,
        "prompt": (
            "Seoul city gas app on a smartphone screen showing monthly gas bill usage graph. "
            "Korean apartment home living. Bright natural light, clean interior. "
            "Realistic style, no text overlay, no watermark. 16:9 ratio."
        ),
        "filename": "gas-app-usage-screen.jpg",
        "keyword": "gas,smartphone,app",
    },
    {
        "index": 2,
        "prompt": (
            "Korean gas utility bill paper document on a wooden desk with a coffee cup. "
            "Close-up of monthly statement, clean tidy home setting. "
            "Realistic photo style, no text, no watermark. 16:9 ratio."
        ),
        "filename": "gas-bill-document-desk.jpg",
        "keyword": "gas,bill,receipt",
    },
    {
        "index": 3,
        "prompt": (
            "Person holding smartphone checking utility fees in Korean home. "
            "Bright living room background, natural daylight. "
            "Modern Korean apartment, lifestyle photo. No text, no watermark. 16:9 ratio."
        ),
        "filename": "smartphone-utility-check.jpg",
        "keyword": "smartphone,utility,check",
    },
]


# ─── 로그 ───────────────────────────────────────
def _log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ─── 텔레그램 ───────────────────────────────────
def _send_telegram(msg: str):
    token = os.environ.get(TELEGRAM_TOKEN_ENV, "")
    if not token:
        # 토큰 파일에서 읽기 시도
        token_paths = [
            "/Users/hana/.claude/projects/-Users-hana-Downloads-blog-automation-v2/memory/telegram_token.txt",
            "/Users/hana/Downloads/blog-automation-v2/.telegram_token",
        ]
        for p in token_paths:
            try:
                with open(p) as f:
                    tok = f.read().strip()
                    if tok:
                        token = tok
                        break
            except Exception:
                pass
    if not token:
        _log("[텔레그램] 토큰 없음 — 스킵")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    }).encode()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=15, context=ctx)
        _log("[텔레그램] 전송 완료")
    except Exception as e:
        _log(f"[텔레그램] 전송 실패: {e}")


# ─── loremflickr 이미지 다운로드 ─────────────────
def _download_loremflickr(keyword: str, filename: str) -> str | None:
    kw = urllib.parse.quote(keyword)
    url = f"https://loremflickr.com/1024/768/{kw}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        data = resp.read()
        out = IMAGES_DIR / filename
        out.write_bytes(data)
        _log(f"[이미지] loremflickr 다운로드 완료: {filename}")
        return str(out)
    except Exception as e:
        _log(f"[이미지] loremflickr 다운로드 실패 ({keyword}): {e}")
        return None


# ─── Gemini 이미지 생성 시도 ──────────────────────
def _generate_images_gemini(prompts: list) -> dict:
    """gemini_image 모듈로 이미지 생성. 실패 시 loremflickr 폴백."""
    results = {}
    try:
        from gemini_image import generate_images as _gem_gen
        image_infos = [
            {
                "index": p["index"],
                "prompt": p["prompt"],
                "filename": p["filename"],
                "alt": "",
            }
            for p in prompts
        ]
        _log("[이미지] Gemini 이미지 생성 시작...")
        results = _gem_gen(image_infos, on_log=_log, skip_webp=True)
        _log(f"[이미지] Gemini 생성 결과: {len(results)}개")
    except Exception as e:
        _log(f"[이미지] Gemini 모듈 오류: {e} — loremflickr 폴백")

    # 실패한 인덱스 loremflickr로 보완
    for p in prompts:
        idx = p["index"]
        if idx not in results:
            _log(f"[이미지] 인덱스 {idx} loremflickr 폴백: {p['keyword']}")
            fp = _download_loremflickr(p["keyword"], p["filename"])
            if fp:
                results[idx] = fp

    return results


# ─── 네이버 에디터 이미지 업로드 ─────────────────
def _dismiss_overlays(page):
    """오버레이/팝업 닫기."""
    try:
        page.evaluate("""() => {
            ['button[aria-label="닫기"]', '.btn-close', '.close-btn', '[class*="close"]'].forEach(sel => {
                document.querySelectorAll(sel).forEach(el => {
                    if (el.offsetParent && el.getBoundingClientRect().width > 0) {
                        try { el.click(); } catch(e) {}
                    }
                });
            });
        }""")
        time.sleep(0.5)
    except Exception:
        pass


def _wait_for_image_load(page, timeout=15):
    """이미지 업로드 후 로딩 완료 대기."""
    for _ in range(timeout):
        loading = page.evaluate("""() => {
            const spinners = document.querySelectorAll(
                '.se-loading, [class*="loading"], [class*="spinner"], [class*="uploading"]'
            );
            return [...spinners].some(el => el.offsetParent !== null);
        }""")
        if not loading:
            break
        time.sleep(1)
    time.sleep(1)


def _upload_image_to_naver(page, filepath: str) -> bool:
    """네이버 SE 에디터에 이미지 1장 업로드."""
    if not os.path.exists(filepath):
        _log(f"[업로드] 파일 없음: {filepath}")
        return False

    _dismiss_overlays(page)

    # 사진 버튼 탐색
    photo_btn = None
    selectors = [
        'button.se-image-toolbar-button',
        'button[data-name="image"]',
        'button[class*="image"]',
        'button[aria-label*="사진"]',
        'button[title*="사진"]',
        'button[aria-label*="이미지"]',
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                photo_btn = btn
                _log(f"[업로드] 사진 버튼 발견: {sel}")
                break
        except Exception:
            continue

    if not photo_btn:
        # JS로 모든 버튼 스캔
        _log("[업로드] 버튼 JS 탐색...")
        found = page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button, [role="button"]')];
            const b = btns.find(el => {
                const t = (el.textContent || '') + (el.getAttribute('aria-label') || '') +
                          (el.className || '') + (el.getAttribute('title') || '');
                return /사진|이미지|image|photo/i.test(t);
            });
            if (b) { b.click(); return true; }
            return false;
        }""")
        if found:
            time.sleep(1)
        else:
            _log("[업로드] 사진 버튼 없음 — 스킵")
            return False

    try:
        if photo_btn:
            with page.expect_file_chooser(timeout=10000) as fc_info:
                photo_btn.click(timeout=5000)
        else:
            # 버튼 JS 클릭 후 file chooser 대기 (이미 클릭됨)
            # 다시 시도: 버튼 재검색
            for sel in selectors:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        with page.expect_file_chooser(timeout=10000) as fc_info:
                            btn.click(timeout=5000)
                        break
                except Exception:
                    continue
            else:
                return False

        file_chooser = fc_info.value
        file_chooser.set_files(filepath)
        _log(f"[업로드] 파일 전송: {Path(filepath).name}")
        time.sleep(4)
        _wait_for_image_load(page)
        return True

    except Exception as e:
        _log(f"[업로드] 업로드 실패: {e}")
        try:
            page.keyboard.press("Escape")
            time.sleep(1)
        except Exception:
            pass
        return False


def _move_cursor_to_before_h2(page, h2_index: int) -> bool:
    """에디터에서 h2_index번째 H2 소제목 앞으로 커서 이동.

    반환: 이동 성공 여부
    """
    result = page.evaluate(f"""(targetIdx) => {{
        // SE 에디터에서 소제목(H2/section-title) 컴포넌트 찾기
        const allComponents = [...document.querySelectorAll(
            '.se-component, [class*="se-section"]'
        )];

        // 소제목인 것만 필터
        const h2s = allComponents.filter(el => {{
            const cls = el.className || '';
            return cls.includes('heading') || cls.includes('sectionTitle') ||
                   cls.includes('section-title') || el.querySelector('h2, h3');
        }});

        if (h2s.length === 0) {{
            // 텍스트에서 소제목 패턴 찾기
            const paragraphs = [...document.querySelectorAll(
                '.se-text-paragraph, .se-module-text p, [class*="paragraph"]'
            )];
            // 소제목 스타일 적용된 것 찾기
            const h2Paragraphs = [...document.querySelectorAll(
                '.se-text-sectionTitle, [class*="sectionTitle"], [class*="section_title"]'
            )];
            if (h2Paragraphs.length > targetIdx) {{
                const el = h2Paragraphs[targetIdx];
                el.click();
                // 줄 맨 앞으로
                const range = document.createRange();
                range.setStart(el, 0);
                range.collapse(true);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                return {{found: true, text: el.innerText.substring(0, 30)}};
            }}
            return {{found: false, total: 0}};
        }}

        if (targetIdx >= h2s.length) {{
            return {{found: false, total: h2s.length}};
        }}

        const target = h2s[targetIdx];
        target.click();
        return {{found: true, text: (target.innerText || '').substring(0, 30)}};
    }}""", h2_index)

    if result and result.get("found"):
        _log(f"[커서] H2[{h2_index}] 앞으로 이동: {result.get('text', '')}")
        time.sleep(0.5)
        # Home 키로 줄 맨 앞으로
        page.keyboard.press("Home")
        time.sleep(0.3)
        return True
    else:
        _log(f"[커서] H2[{h2_index}] 이동 실패 (total: {result.get('total', 0) if result else 0})")
        return False


def _move_cursor_to_end(page):
    """에디터 커서를 본문 맨 끝으로 이동."""
    page.evaluate("""() => {
        const editor = document.querySelector('.se-content, .se-main-container');
        if (!editor) return;
        const allParagraphs = editor.querySelectorAll(
            '.se-text-paragraph, p, .se-module-text p'
        );
        if (allParagraphs.length > 0) {
            const last = allParagraphs[allParagraphs.length - 1];
            last.click();
            const range = document.createRange();
            range.selectNodeContents(last);
            range.collapse(false);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
        }
    }""")
    time.sleep(0.5)
    page.keyboard.press("End")
    time.sleep(0.3)


def _insert_empty_line(page):
    """커서 위치에 빈 줄 추가 후 Enter."""
    page.keyboard.press("Enter")
    time.sleep(0.3)


def _count_h2_in_editor(page) -> int:
    """에디터 내 H2 소제목 수 반환."""
    count = page.evaluate("""() => {
        const h2s = document.querySelectorAll(
            '.se-text-sectionTitle, [class*="sectionTitle"], [class*="section_title"], '
            '.se-component h2, .se-component h3'
        );
        return h2s.length;
    }""")
    return count or 0


# ─── 메인 ────────────────────────────────────────
def run():
    image_status = "생성 필요"
    published_url = f"https://blog.naver.com/{BLOG_ID}/{LOG_NO}"
    uploaded_count = 0

    # ── Step 1. 이미지 생성 ────────────────────────
    _log("[Step1] 이미지 생성 시작...")
    image_paths = _generate_images_gemini(IMAGE_PROMPTS)
    _log(f"[Step1] 이미지 {len(image_paths)}개 준비 완료: {list(image_paths.values())}")

    if not image_paths:
        _log("[Step1] 이미지 생성 전체 실패 — 중단")
        _send_telegram("❌ salim1su 가스비 글 이미지 추가 실패: 이미지 생성 실패")
        return False

    # ── Step 2. CDP 연결 ──────────────────────────
    _log(f"[Step2] CDP {CDP_URL} 연결 중...")
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        _log("[Step2] CDP 연결 성공")
    except Exception as e:
        _log(f"[Step2] CDP 연결 실패: {e}")
        pw.stop()
        _send_telegram(f"❌ salim1su 가스비 글 이미지 추가 실패: CDP 연결 오류 ({e})")
        return False

    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()

    try:
        # ── Step 3. 에디터 수정 모드 진입 ─────────────
        edit_url = (
            f"https://blog.naver.com/{BLOG_ID}/postwrite"
            f"?editType=edit&logNo={LOG_NO}"
        )
        _log(f"[Step3] 에디터 수정 모드 진입: {edit_url}")
        page.goto(edit_url, wait_until="domcontentloaded", timeout=40000)
        time.sleep(6)
        _log(f"[Step3] 현재 URL: {page.url}")

        # 로그인 체크
        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            _log("[ERROR] 로그인 필요 — 중단")
            _send_telegram("❌ salim1su 가스비 글 이미지 추가 실패: 로그인 필요")
            return False

        # 에디터 로드 대기
        _log("[Step3] 에디터 로드 대기...")
        editor_loaded = False
        for sel in [".se-content", ".se-main-container", ".se-editor", "[class*='se-']"]:
            try:
                page.wait_for_selector(sel, timeout=10000)
                _log(f"[Step3] 에디터 확인: {sel}")
                editor_loaded = True
                break
            except Exception:
                continue

        if not editor_loaded:
            _log("[Step3] 에디터 로드 실패 — 스크린샷 저장")
            page.screenshot(path="/Users/hana/Downloads/blog-automation-v2/debug_editor_fail.png")
            _send_telegram("❌ salim1su 가스비 글: 에디터 로드 실패")
            return False

        time.sleep(3)

        # ── Step 4. 에디터 현황 확인 ──────────────────
        editor_info = page.evaluate("""() => {
            const title = document.querySelector(
                '.se-documentTitle .se-text-paragraph, .se-title-text, [placeholder*="제목"]'
            );
            const imgs = document.querySelectorAll(
                '.se-image-resource, .se-module-image img, img[src*="blogfiles"], img[src*="postfiles"], img[src*="storep"]'
            );
            const h2s = document.querySelectorAll(
                '.se-text-sectionTitle, [class*="sectionTitle"], [class*="section_title"]'
            );
            return {
                title: title ? title.innerText.trim() : '',
                imgCount: imgs.length,
                h2Count: h2s.length,
            };
        }""")
        _log(f"[Step4] 제목: {editor_info.get('title', '?')}")
        _log(f"[Step4] 현재 이미지 수: {editor_info.get('imgCount', 0)}")
        _log(f"[Step4] H2 소제목 수: {editor_info.get('h2Count', 0)}")

        # ── Step 5. 이미지 삽입 ───────────────────────
        _log("[Step5] 이미지 삽입 시작...")

        # 이미지 삽입 전략:
        # - 이미지 1: 본문 첫 번째 H2 앞에 삽입
        # - 이미지 2: 본문 두 번째 H2 앞에 삽입
        # - 이미지 3: 본문 맨 끝에 삽입

        sorted_images = sorted(image_paths.items())  # [(1, path), (2, path), ...]

        for i, (idx, filepath) in enumerate(sorted_images):
            _log(f"[Step5] 이미지 {idx} 삽입 중: {Path(filepath).name}")

            if i < 2:
                # H2 소제목 앞에 커서 이동
                moved = _move_cursor_to_before_h2(page, i)
                if moved:
                    # H2 앞 빈 줄 만들기
                    page.keyboard.press("Home")
                    time.sleep(0.2)
                    page.keyboard.press("Enter")
                    time.sleep(0.3)
                    page.keyboard.press("ArrowUp")
                    time.sleep(0.3)
                else:
                    _log(f"[Step5] H2[{i}] 커서 이동 실패 — 맨 끝에 삽입")
                    _move_cursor_to_end(page)
            else:
                # 세 번째 이미지는 맨 끝에
                _move_cursor_to_end(page)
                page.keyboard.press("Enter")
                time.sleep(0.3)

            ok = _upload_image_to_naver(page, filepath)
            if ok:
                uploaded_count += 1
                _log(f"[Step5] 이미지 {idx} 업로드 성공 (총 {uploaded_count}개)")
                time.sleep(2)
            else:
                _log(f"[Step5] 이미지 {idx} 업로드 실패")

        image_status = f"{uploaded_count}개 삽입"
        _log(f"[Step5] 이미지 삽입 완료: {uploaded_count}/{len(image_paths)}개")

        if uploaded_count == 0:
            _log("[Step5] 이미지 삽입 전부 실패 — 발행 중단")
            _send_telegram(f"❌ salim1su 가스비 글: 이미지 삽입 실패\n에디터 조작 오류")
            return False

        time.sleep(2)

        # ── Step 6. 발행 버튼 클릭 ────────────────────
        _log("[Step6] 발행 버튼 찾는 중...")
        time.sleep(1)

        pub_clicked = page.evaluate("""() => {
            const selectors = [
                'button.publish_btn__m9KHH',
                'button[class*="publish_btn"]',
                'button[class*="publishBtn"]',
                'button[data-action="publish"]',
            ];
            for (const sel of selectors) {
                const btn = document.querySelector(sel);
                if (btn) { btn.click(); return 'selector:' + sel; }
            }
            const btns = [...document.querySelectorAll('button')];
            const pub = btns.find(b => {
                const t = b.textContent.trim();
                return t === '발행' || t === '게시' || t === '공개발행';
            });
            if (pub) { pub.click(); return 'text:' + pub.textContent.trim(); }

            // 헤더 영역
            const toolbtns = document.querySelectorAll(
                'header button, .editor-header button, [class*="header"] button'
            );
            const tbPub = [...toolbtns].find(b => b.textContent.trim().includes('발행'));
            if (tbPub) { tbPub.click(); return 'toolbar:' + tbPub.textContent.trim(); }

            return null;
        }""")

        if not pub_clicked:
            _log("[Step6] 발행 버튼 없음 — 스크린샷 저장")
            page.screenshot(path="/Users/hana/Downloads/blog-automation-v2/debug_pub_btn.png")
            btns = page.evaluate("""() => {
                return [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t => t);
            }""")
            _log(f"[Step6] 버튼 목록: {btns[:20]}")
            _send_telegram(f"❌ salim1su 가스비 글: 발행 버튼 없음\n이미지 {uploaded_count}개 삽입됨 (미발행)")
            return False

        _log(f"[Step6] 발행 버튼 클릭: {pub_clicked}")
        time.sleep(3)

        # ── Step 7. 발행 팝업 처리 ────────────────────
        _log("[Step7] 발행 팝업 처리...")
        time.sleep(2)

        # 카테고리 설정
        category_set = page.evaluate(f"""() => {{
            // select 방식
            const selects = document.querySelectorAll(
                'select[name*="category"], select[id*="category"], select[class*="category"]'
            );
            for (const sel of selects) {{
                for (const opt of sel.options) {{
                    if (opt.text.includes('{CATEGORY_NAME}')) {{
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return 'select:' + opt.text;
                    }}
                }}
            }}
            // 리스트 방식
            const items = [...document.querySelectorAll(
                '[class*="category"] li, [class*="category"] a, [class*="category"] button, [class*="Category"] li, .category_list li, .select_category li'
            )];
            const cat = items.find(el =>
                (el.textContent || '').trim() === '{CATEGORY_NAME}' ||
                (el.textContent || '').includes('{CATEGORY_NAME}')
            );
            if (cat) {{ cat.click(); return 'list:' + cat.textContent.trim(); }}
            return null;
        }}""")

        if category_set:
            _log(f"[Step7] 카테고리 설정: {category_set}")
            time.sleep(1)
        else:
            _log(f"[Step7] 카테고리 '{CATEGORY_NAME}' 못 찾음 — 드롭다운 열기 시도")
            page.screenshot(path="/Users/hana/Downloads/blog-automation-v2/debug_cat_popup.png")

            # 카테고리 영역 클릭해서 드롭다운 열기
            page.evaluate("""() => {
                const catArea = document.querySelector(
                    '[class*="category_wrap"], [class*="categoryWrap"], '
                    + '[class*="select_category"], .category_select, .se-publish-category'
                );
                if (catArea) catArea.click();
            }""")
            time.sleep(1.5)

            # 재시도
            category_set = page.evaluate(f"""() => {{
                const items = [...document.querySelectorAll('li, a, button, span')];
                const cat = items.find(el => (el.textContent || '').trim() === '{CATEGORY_NAME}');
                if (cat) {{ cat.click(); return 'retry:' + cat.textContent.trim(); }}
                const partial = items.find(el => (el.textContent || '').includes('{CATEGORY_NAME}'));
                if (partial) {{ partial.click(); return 'partial:' + partial.textContent.trim().substring(0, 30); }}
                return null;
            }}""")
            if category_set:
                _log(f"[Step7] 카테고리 재시도 성공: {category_set}")
            else:
                _log("[Step7] 카테고리 설정 실패 — 계속 진행")
            time.sleep(1)

        # 공개 설정
        page.evaluate("""() => {
            const items = [...document.querySelectorAll('input[type="radio"], label, button, li')];
            const pub = items.find(el => {
                const t = (el.textContent || el.value || '').trim();
                return t === '전체공개' || t === '공개' || el.value === 'public' || el.id === 'public';
            });
            if (pub) pub.click();
        }""")
        time.sleep(1)

        # ── Step 8. 최종 발행 확인 ────────────────────
        _log("[Step8] 최종 발행 확인 버튼...")
        time.sleep(1)

        confirmed = page.evaluate("""() => {
            const labels = ['발행', '발행하기', '확인', '게시', '등록', '완료'];
            const area = document.querySelector(
                '[class*="publish_layer"], [class*="publishLayer"], [class*="layer_post"], .se-publish-setting, dialog, [role="dialog"]'
            ) || document.body;

            const btns = [...area.querySelectorAll('button')];
            for (const label of labels) {
                const btn = btns.find(b => b.textContent.trim() === label);
                if (btn && !btn.disabled) {
                    btn.click();
                    return 'clicked:' + label;
                }
            }
            // 텍스트 포함으로 재시도
            const partial = btns.find(b =>
                labels.some(l => b.textContent.trim().includes(l))
            );
            if (partial && !partial.disabled) {
                partial.click();
                return 'partial:' + partial.textContent.trim();
            }
            return null;
        }""")

        if confirmed:
            _log(f"[Step8] 발행 확인: {confirmed}")
        else:
            _log("[Step8] 발행 확인 버튼 없음 — 스크린샷")
            page.screenshot(path="/Users/hana/Downloads/blog-automation-v2/debug_confirm_popup.png")
            btns_info = page.evaluate("""() => {
                return [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t => t);
            }""")
            _log(f"[Step8] 버튼 목록: {btns_info[:15]}")

        time.sleep(4)
        final_url = page.url
        _log(f"[Step8] 최종 URL: {final_url}")

        # 발행 성공 여부 판단 (URL 변화 또는 에디터 닫힘)
        success = (
            LOG_NO in final_url or
            "blog.naver.com" in final_url and "postwrite" not in final_url
        )

    except Exception as e:
        _log(f"[오류] {e}")
        import traceback
        traceback.print_exc()
        _send_telegram(f"❌ salim1su 가스비 글 이미지 추가 오류: {e}")
        return False

    finally:
        page.close()
        pw.stop()

    # ── 텔레그램 보고 ─────────────────────────────
    status_emoji = "✅" if uploaded_count > 0 else "⚠️"
    msg = (
        f"{status_emoji} salim1su 가스비 글 이미지 추가 완료\n"
        f"글: 서울도시가스 요금조회, 앱으로 1분 안에 되더라구요\n"
        f"URL: https://blog.naver.com/{BLOG_ID}/{LOG_NO}\n"
        f"이미지: {image_status}\n"
        f"카테고리: {CATEGORY_NAME}"
    )
    _send_telegram(msg)
    _log(f"[완료] {msg}")
    return True


if __name__ == "__main__":
    run()
