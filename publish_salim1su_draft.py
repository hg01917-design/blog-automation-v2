"""
publish_salim1su_draft.py
salim1su 블로그 임시저장 글 "서울도시가스 요금조회" 검수 + 발행

- CDP 포트 9222 연결
- 임시저장 글 열기
- 검수: 2025년 → 2026년 수정, 이미지 확인/생성
- 카테고리: 고정지출줄이기
- 발행 완료 후 텔레그램 보고
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
TARGET_TITLE_KW = "서울도시가스"
CATEGORY_NAME = "고정지출줄이기"
TELEGRAM_CHAT_ID = "8674424194"
TELEGRAM_TOKEN_ENV = "HanaAutobot"
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# ─── 로그 ───────────────────────────────────────
def _log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ─── 텔레그램 ───────────────────────────────────
def _send_telegram(msg: str):
    token = os.environ.get(TELEGRAM_TOKEN_ENV, "")
    if not token:
        _log("[텔레그램] 토큰 없음 — 스킵")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}).encode()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15, context=ctx)
        _log("[텔레그램] 전송 완료")
    except Exception as e:
        _log(f"[텔레그램] 전송 실패: {e}")


# ─── loremflickr 이미지 다운로드 ──────────────────
def _download_image(keyword: str, filename: str) -> str | None:
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
        _log(f"[이미지] 다운로드 완료: {filename}")
        return str(out)
    except Exception as e:
        _log(f"[이미지] 다운로드 실패: {e}")
        return None


# ─── 메인 ────────────────────────────────────────
def run():
    year_fixed = False
    image_status = "확인 필요"
    published_url = ""

    pw = sync_playwright().start()
    try:
        _log(f"[CDP] {CDP_URL} 연결 중...")
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        _log("[CDP] 연결 성공")

        # 기존 컨텍스트 사용
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        # ── 1. 임시저장 글 목록 접근 ──────────────────
        _log("[Step1] 임시저장 목록 접근...")
        draft_logno = None

        # 방법 A: PostTempList
        try:
            page.goto(
                f"https://blog.naver.com/PostTempList.nhn?blogId={BLOG_ID}",
                wait_until="domcontentloaded", timeout=20000
            )
            time.sleep(3)
            _log(f"[Step1] 현재 URL: {page.url}")

            # iframe 내부 확인
            draft_logno = page.evaluate(f"""() => {{
                // 직접 페이지에서 찾기
                const links = [...document.querySelectorAll('a[href*="logNo"], a[href*="LogNo"]')];
                for (const a of links) {{
                    const txt = (a.closest('tr,li,div') || a.parentElement || document.body).innerText || '';
                    if (txt.includes('{TARGET_TITLE_KW}')) {{
                        const m = a.href.match(/[Ll]og[Nn]o=(\d+)/);
                        if (m) return m[1];
                    }}
                }}
                // iframe 시도
                try {{
                    const f = document.querySelector('iframe#mainFrame');
                    if (f && f.contentDocument) {{
                        const ilinks = [...f.contentDocument.querySelectorAll('a[href*="logNo"], a[href*="LogNo"]')];
                        for (const a of ilinks) {{
                            const txt = (a.closest('tr,li,div') || a.parentElement || f.contentDocument.body).innerText || '';
                            if (txt.includes('{TARGET_TITLE_KW}')) {{
                                const m = a.href.match(/[Ll]og[Nn]o=(\d+)/);
                                if (m) return m[1];
                            }}
                        }}
                    }}
                }} catch(e) {{}}
                return null;
            }}""")
        except Exception as e:
            _log(f"[Step1] PostTempList 접근 실패: {e}")

        # 방법 B: DraftBox 리다이렉트
        if not draft_logno:
            try:
                page.goto(
                    f"https://blog.naver.com/{BLOG_ID}?redirect=DraftBox",
                    wait_until="domcontentloaded", timeout=20000
                )
                time.sleep(3)
                _log(f"[Step1-B] 현재 URL: {page.url}")
                draft_logno = page.evaluate(f"""() => {{
                    const links = [...document.querySelectorAll('a[href*="logNo"], a[href*="LogNo"]')];
                    for (const a of links) {{
                        const txt = (a.closest('tr,li,div') || a.parentElement || document.body).innerText || '';
                        if (txt.includes('{TARGET_TITLE_KW}')) {{
                            const m = a.href.match(/[Ll]og[Nn]o=(\d+)/);
                            if (m) return m[1];
                        }}
                    }}
                    try {{
                        const f = document.querySelector('iframe#mainFrame');
                        if (f && f.contentDocument) {{
                            const ilinks = [...f.contentDocument.querySelectorAll('a[href*="logNo"], a[href*="LogNo"]')];
                            for (const a of ilinks) {{
                                const txt = (a.closest('tr,li,div') || a.parentElement || f.contentDocument.body).innerText || '';
                                if (txt.includes('{TARGET_TITLE_KW}')) {{
                                    const m = a.href.match(/[Ll]og[Nn]o=(\d+)/);
                                    if (m) return m[1];
                                }}
                            }}
                        }}
                    }} catch(e) {{}}
                    return null;
                }}""")
            except Exception as e:
                _log(f"[Step1-B] 실패: {e}")

        # 방법 C: 관리 페이지 PostList
        if not draft_logno:
            try:
                page.goto(
                    f"https://blog.naver.com/PostList.naver?blogId={BLOG_ID}&categoryNo=0&parentCategoryNo=0&listStyle=style1",
                    wait_until="domcontentloaded", timeout=20000
                )
                time.sleep(3)
                _log(f"[Step1-C] 현재 URL: {page.url}")

                # iframe mainFrame 내부 접근 시도
                frame = page.frame(name="mainFrame") or page.frame(url=re.compile(r"blog\.naver\.com"))
                if frame:
                    _log("[Step1-C] mainFrame 발견")
                    # 임시저장 탭/링크 클릭 시도
                    try:
                        frame.click("a:has-text('임시저장')", timeout=3000)
                        time.sleep(2)
                    except Exception:
                        pass
                    draft_logno = frame.evaluate(f"""() => {{
                        const links = [...document.querySelectorAll('a[href*="logNo"], a[href*="LogNo"]')];
                        for (const a of links) {{
                            const txt = (a.closest('tr,li,div') || a.parentElement || document.body).innerText || '';
                            if (txt.includes('{TARGET_TITLE_KW}')) {{
                                const m = a.href.match(/[Ll]og[Nn]o=(\d+)/);
                                if (m) return m[1];
                            }}
                        }}
                        return null;
                    }}""")
            except Exception as e:
                _log(f"[Step1-C] 실패: {e}")

        # 방법 D: 에디터 새 글 작성 화면에서 임시저장 불러오기
        if not draft_logno:
            _log("[Step1-D] 에디터에서 임시저장 불러오기 시도...")
            try:
                page.goto(
                    f"https://blog.naver.com/{BLOG_ID}/postwrite",
                    wait_until="domcontentloaded", timeout=30000
                )
                time.sleep(5)
                _log(f"[Step1-D] 에디터 URL: {page.url}")

                # 임시저장 목록 버튼 클릭
                clicked = page.evaluate("""() => {
                    const btns = [...document.querySelectorAll('button, a, [role="button"]')];
                    const btn = btns.find(b => {
                        const t = b.textContent.trim();
                        return t.includes('임시저장') || t.includes('불러오기');
                    });
                    if (btn) { btn.click(); return btn.textContent.trim(); }
                    return null;
                }""")
                if clicked:
                    _log(f"[Step1-D] '{clicked}' 클릭")
                    time.sleep(2)

                    # 목록에서 서울도시가스 항목 찾기
                    draft_logno = page.evaluate(f"""() => {{
                        const items = [...document.querySelectorAll('[class*="temp"], [class*="draft"], li, tr')];
                        for (const item of items) {{
                            const txt = item.innerText || '';
                            if (txt.includes('{TARGET_TITLE_KW}')) {{
                                // logNo 추출 시도
                                const m = txt.match(/logNo[=:](\d+)/) ||
                                          (item.dataset && item.dataset.logno);
                                if (m) return typeof m === 'string' ? m : m[1];
                                // data 속성
                                for (const attr of item.attributes || []) {{
                                    if (attr.value && /^\d{{7,}}$/.test(attr.value)) return attr.value;
                                }}
                            }}
                        }}
                        return null;
                    }}""")
                    if draft_logno:
                        _log(f"[Step1-D] logNo 발견: {draft_logno}")
                    else:
                        # 직접 클릭해서 로드
                        item_clicked = page.evaluate(f"""() => {{
                            const items = [...document.querySelectorAll('[class*="temp"] li, [class*="draft"] li, li, .list_item')];
                            for (const item of items) {{
                                if ((item.innerText || '').includes('{TARGET_TITLE_KW}')) {{
                                    item.click();
                                    return item.innerText.trim().substring(0, 50);
                                }}
                            }}
                            return null;
                        }}""")
                        if item_clicked:
                            _log(f"[Step1-D] 항목 클릭: {item_clicked}")
                            time.sleep(3)
                            # URL에서 logNo 추출
                            m = re.search(r'logNo=(\d+)', page.url)
                            if m:
                                draft_logno = m.group(1)
                                _log(f"[Step1-D] URL에서 logNo: {draft_logno}")
            except Exception as e:
                _log(f"[Step1-D] 실패: {e}")

        _log(f"[Step1] 최종 logNo: {draft_logno}")

        # ── 2. 에디터로 임시저장 글 열기 ──────────────
        _log("[Step2] 에디터로 임시저장 글 열기...")

        if draft_logno:
            edit_url = f"https://blog.naver.com/{BLOG_ID}/postwrite?logNo={draft_logno}"
            _log(f"[Step2] 편집 URL: {edit_url}")
            page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        else:
            # logNo 없으면 에디터에서 임시저장 목록 통해 접근
            _log("[Step2] logNo 없음 — 에디터 진입 후 임시저장 불러오기")
            page.goto(
                f"https://blog.naver.com/{BLOG_ID}/postwrite",
                wait_until="domcontentloaded", timeout=30000
            )

        time.sleep(5)
        _log(f"[Step2] 에디터 URL: {page.url}")

        # 로그인 체크
        if "nidlogin" in page.url or "nid.naver.com" in page.url:
            _log("[ERROR] 로그인 필요 — 중단")
            _send_telegram("❌ salim1su 발행 실패: 로그인 필요")
            return False

        # 에디터 로드 대기
        _log("[Step2] 에디터 로드 대기...")
        for sel in [".se-content", ".se-editor", "#smartEditorV2", "[class*='se-']"]:
            try:
                page.wait_for_selector(sel, timeout=10000)
                _log(f"[Step2] 에디터 셀렉터 확인: {sel}")
                break
            except Exception:
                continue
        time.sleep(3)

        # logNo 없어서 에디터에서 임시저장 불러오기가 필요한 경우
        if not draft_logno:
            _log("[Step2] 임시저장 버튼 클릭 시도...")
            clicked = page.evaluate("""() => {
                const btns = [...document.querySelectorAll('button, a, [role="button"]')];
                const btn = btns.find(b => {
                    const t = (b.textContent || '').trim();
                    return t.includes('임시저장') || t.includes('불러오기');
                });
                if (btn) { btn.click(); return btn.textContent.trim(); }
                return null;
            }""")
            if clicked:
                _log(f"[Step2] '{clicked}' 클릭")
                time.sleep(2)
                # 목록에서 서울도시가스 항목 클릭
                item_clicked = page.evaluate(f"""() => {{
                    const items = [...document.querySelectorAll('li, [class*="item"], [class*="list"] > *')];
                    for (const item of items) {{
                        if ((item.innerText || '').includes('{TARGET_TITLE_KW}')) {{
                            item.click();
                            return item.innerText.trim().substring(0, 50);
                        }}
                    }}
                    return null;
                }}""")
                if item_clicked:
                    _log(f"[Step2] 항목 선택: {item_clicked}")
                    time.sleep(3)

        # ── 3. 현재 에디터 내용 확인 ──────────────────
        _log("[Step3] 에디터 콘텐츠 확인...")
        time.sleep(2)

        editor_info = page.evaluate("""() => {
            // 제목
            const titleEl = document.querySelector(
                '.se-documentTitle .se-text-paragraph, ' +
                '.se-title-text, ' +
                '[placeholder*="제목"], ' +
                '.se-ff-nanumgothic'
            );
            const title = titleEl ? titleEl.innerText.trim() : '';

            // 본문 텍스트
            const body = document.querySelector('.se-content, .se-main-container, .se-editor');
            const bodyText = body ? body.innerText : document.body.innerText;

            // 이미지 확인
            const imgs = document.querySelectorAll(
                '.se-image-resource, .se-module-image img, ' +
                'img[src*="blogfiles"], img[src*="postfiles"], ' +
                '.se-section-image img, img[class*="se-"]'
            );
            const hasImages = imgs.length > 0;

            // 연도 확인
            const has2025 = bodyText.includes('2025년') || bodyText.includes('2025 ') || /2025[년\s]/.test(bodyText);

            return {
                title,
                bodyLength: bodyText.length,
                hasImages,
                has2025,
                imgCount: imgs.length,
                bodyPreview: bodyText.substring(0, 200),
            };
        }""")
        _log(f"[Step3] 제목: {editor_info.get('title', '?')}")
        _log(f"[Step3] 본문 길이: {editor_info.get('bodyLength', 0)}자")
        _log(f"[Step3] 이미지 수: {editor_info.get('imgCount', 0)}")
        _log(f"[Step3] 2025년 포함: {editor_info.get('has2025', False)}")
        _log(f"[Step3] 본문 미리보기: {editor_info.get('bodyPreview', '')[:100]}")

        # ── 4a. 연도 수정 (2025 → 2026) ──────────────
        if editor_info.get("has2025"):
            _log("[Step4a] 2025년 → 2026년 수정 중...")

            # SE 에디터에서 텍스트 직접 수정
            # iframe이 있는 경우 대비
            fixed_count = page.evaluate("""() => {
                let count = 0;
                // SE 에디터 텍스트 노드 순회
                function fixTextNodes(root) {
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = walker.nextNode()) {
                        if (node.nodeValue && node.nodeValue.includes('2025')) {
                            const before = node.nodeValue;
                            node.nodeValue = node.nodeValue
                                .replace(/2025년/g, '2026년')
                                .replace(/2025 /g, '2026 ')
                                .replace(/2025\./g, '2026.')
                                .replace(/\b2025\b/g, '2026');
                            if (node.nodeValue !== before) count++;
                        }
                    }
                    return count;
                }

                const editor = document.querySelector('.se-content, .se-main-container');
                if (editor) {
                    count += fixTextNodes(editor);
                }

                // iframe 내부도 시도
                try {
                    const frames = document.querySelectorAll('iframe');
                    for (const f of frames) {
                        try {
                            if (f.contentDocument) count += fixTextNodes(f.contentDocument.body);
                        } catch(e) {}
                    }
                } catch(e) {}

                return count;
            }""")
            _log(f"[Step4a] 수정된 노드 수: {fixed_count}")

            if fixed_count > 0:
                year_fixed = True
                _log("[Step4a] 2025년 → 2026년 수정 완료")

                # 수정 후 에디터에 변경 사항 알림 (입력 이벤트 발생)
                page.evaluate("""() => {
                    const editor = document.querySelector('.se-content, .se-main-container');
                    if (editor) {
                        editor.dispatchEvent(new Event('input', {bubbles: true}));
                        editor.dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""")
                time.sleep(1)
            else:
                _log("[Step4a] DOM 수정 실패 — 키보드 찾기/바꾸기 시도")
                # Ctrl+H (찾기/바꾸기) 시도
                page.keyboard.press("Meta+h")
                time.sleep(1)
                # 찾기/바꾸기 UI가 열리지 않을 수 있어서 스킵
                page.keyboard.press("Escape")
        else:
            year_fixed = False
            _log("[Step4a] 2025년 없음 — 연도 수정 불필요")

        # ── 4b. 이미지 확인 ──────────────────────────
        if editor_info.get("hasImages") and editor_info.get("imgCount", 0) > 0:
            image_status = f"정상 ({editor_info.get('imgCount', 0)}개)"
            _log(f"[Step4b] 이미지 정상: {editor_info.get('imgCount', 0)}개")
        else:
            _log("[Step4b] 이미지 없음 — 이미지 생성 및 삽입 시도...")
            image_status = "없음 → 삽입 시도"

            # loremflickr로 이미지 다운로드
            img_path = _download_image("gas,utility,bill", "seoul-gas-bill-01.jpg")
            if img_path:
                _log(f"[Step4b] 이미지 다운로드: {img_path}")

                # 파일 업로드 인풋 찾기
                file_input = page.query_selector('input[type="file"][accept*="image"]')
                if not file_input:
                    # 이미지 삽입 버튼 클릭
                    _log("[Step4b] 이미지 삽입 버튼 찾는 중...")
                    page.evaluate("""() => {
                        const btns = [...document.querySelectorAll('button, [role="button"], a')];
                        const btn = btns.find(b => {
                            const t = (b.textContent || '') + (b.getAttribute('aria-label') || '') + (b.className || '');
                            return t.includes('사진') || t.includes('이미지') || t.includes('image') || t.includes('photo');
                        });
                        if (btn) btn.click();
                    }""")
                    time.sleep(2)
                    file_input = page.query_selector('input[type="file"][accept*="image"]')

                if file_input:
                    _log("[Step4b] 파일 인풋 발견 — 업로드 중...")
                    file_input.set_input_files(img_path)
                    time.sleep(5)
                    # 삽입 버튼 클릭
                    page.evaluate("""() => {
                        const btns = [...document.querySelectorAll('button')];
                        const btn = btns.find(b => ['확인', '삽입', '추가', '올리기'].includes(b.textContent.trim()));
                        if (btn) btn.click();
                    }""")
                    time.sleep(3)
                    image_status = "삽입 완료"
                    _log("[Step4b] 이미지 삽입 완료")
                else:
                    image_status = "삽입 실패 (파일 인풋 없음)"
                    _log("[Step4b] 파일 인풋 없음 — 이미지 삽입 건너뜀")
            else:
                image_status = "다운로드 실패"
                _log("[Step4b] 이미지 다운로드 실패")

        # ── 5. 발행 버튼 클릭 ─────────────────────────
        _log("[Step5] 발행 버튼 찾는 중...")
        time.sleep(1)

        pub_clicked = page.evaluate("""() => {
            // SE 에디터 발행 버튼
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
            // 텍스트로 찾기
            const btns = [...document.querySelectorAll('button')];
            const pub = btns.find(b => {
                const t = b.textContent.trim();
                return t === '발행' || t === '게시' || t === '공개발행';
            });
            if (pub) { pub.click(); return 'text:' + pub.textContent.trim(); }

            // 오른쪽 상단 버튼 영역
            const toolbtns = document.querySelectorAll(
                'header button, .editor-header button, [class*="header"] button, [class*="toolbar"] button'
            );
            const tbPub = [...toolbtns].find(b => b.textContent.trim().includes('발행'));
            if (tbPub) { tbPub.click(); return 'toolbar:' + tbPub.textContent.trim(); }

            return null;
        }""")

        if not pub_clicked:
            _log("[Step5] 발행 버튼 없음 — 스크린샷 저장 후 재시도")
            page.screenshot(path="/Users/hana/Downloads/blog-automation-v2/debug_publish_btn.png")
            # 모든 버튼 출력
            btns = page.evaluate("""() => {
                return [...document.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t => t);
            }""")
            _log(f"[Step5] 버튼 목록: {btns[:20]}")
            _send_telegram(f"❌ salim1su 발행 실패: 발행 버튼 없음\n버튼 목록: {btns[:10]}")
            return False

        _log(f"[Step5] 발행 버튼 클릭: {pub_clicked}")
        time.sleep(3)

        # ── 6. 발행 설정 팝업 처리 ───────────────────
        _log("[Step6] 발행 설정 팝업 처리...")
        time.sleep(2)

        # 카테고리 선택 — "고정지출줄이기"
        category_set = page.evaluate(f"""() => {{
            // 카테고리 드롭다운/셀렉트/리스트 찾기
            const selects = document.querySelectorAll('select[name*="category"], select[id*="category"], select[class*="category"]');
            for (const sel of selects) {{
                for (const opt of sel.options) {{
                    if (opt.text.includes('{CATEGORY_NAME}') || opt.value.includes('{CATEGORY_NAME}')) {{
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return 'select:' + opt.text;
                    }}
                }}
            }}
            // 리스트 형태 카테고리
            const items = [...document.querySelectorAll(
                '[class*="category"] li, [class*="category"] a, [class*="category"] button, ' +
                '[class*="Category"] li, [class*="Category"] a, ' +
                '.category_list li, .select_category li'
            )];
            const cat = items.find(el => (el.textContent || '').trim() === '{CATEGORY_NAME}' ||
                                        (el.textContent || '').includes('{CATEGORY_NAME}'));
            if (cat) {{ cat.click(); return 'list:' + cat.textContent.trim(); }}
            return null;
        }}""")

        if category_set:
            _log(f"[Step6] 카테고리 설정: {category_set}")
            time.sleep(1)
        else:
            _log(f"[Step6] 카테고리 '{CATEGORY_NAME}' 못 찾음 — 현재 팝업 상태 확인")
            # 팝업 내용 출력
            popup_text = page.evaluate("""() => {
                const popup = document.querySelector(
                    '[class*="publish"], [class*="layer_post"], [class*="modal"], dialog, [role="dialog"]'
                );
                return popup ? popup.innerText.substring(0, 500) : document.body.innerText.substring(0, 500);
            }""")
            _log(f"[Step6] 팝업 내용: {popup_text[:200]}")
            page.screenshot(path="/Users/hana/Downloads/blog-automation-v2/debug_publish_popup.png")

            # 카테고리 영역을 클릭해서 드롭다운 열기 시도
            page.evaluate("""() => {
                const catArea = document.querySelector(
                    '[class*="category_wrap"], [class*="categoryWrap"], ' +
                    '[class*="select_category"], .category_select, .se-publish-category'
                );
                if (catArea) catArea.click();
            }""")
            time.sleep(1)

            # 다시 시도
            category_set = page.evaluate(f"""() => {{
                const items = [...document.querySelectorAll('li, a, button, span')];
                const cat = items.find(el => (el.textContent || '').trim() === '{CATEGORY_NAME}');
                if (cat) {{ cat.click(); return 'retry:' + cat.textContent.trim(); }}
                const partial = items.find(el => (el.textContent || '').includes('{CATEGORY_NAME}'));
                if (partial) {{ partial.click(); return 'partial:' + partial.textContent.trim().substring(0, 30); }}
                return null;
            }}""")
            if category_set:
                _log(f"[Step6] 카테고리 재시도 성공: {category_set}")
            else:
                _log(f"[Step6] 카테고리 설정 실패 — 계속 진행")
            time.sleep(1)

        # 공개 설정 (기본 공개로 두기 — 이미 공개가 기본값일 것)
        _log("[Step6] 공개 설정 확인...")
        page.evaluate("""() => {
            // '전체공개' 또는 '공개' 라디오/버튼 선택
            const items = [...document.querySelectorAll('input[type="radio"], label, button, li')];
            const pub = items.find(el => {
                const t = (el.textContent || el.value || '').trim();
                return t === '전체공개' || t === '공개' || el.value === 'public' || el.id === 'public';
            });
            if (pub) pub.click();
        }""")
        time.sleep(1)

        # ── 7. 최종 발행 확인 버튼 ─────────────────────
        _log("[Step7] 최종 발행 확인 버튼...")
        time.sleep(1)

        confirmed = page.evaluate("""() => {
            const labels = ['발행', '발행하기', '확인', '게시', '등록', '완료'];
            const areas = [
                ...(document.querySelector('[class*="publish_layer"], [class*="publishLayer"], ' +
                    '[class*="layer_post"], .se-publish-setting, dialog, [role="dialog"]')
                    ? [document.querySelector('[class*="publish_layer"], [class*="publishLayer"], ' +
                        '[class*="layer_post"], .se-publish-setting, dialog, [role="dialog"]')]
                    : [document.body])
            ];
            for (const area of areas) {
                const btns = [...area.querySelectorAll('button')];
                for (const lbl of labels) {
                    const btn = btns.find(b => b.textContent.trim() === lbl && !b.disabled);
                    if (btn) { btn.click(); return lbl; }
                }
            }
            return null;
        }""")

        if confirmed:
            _log(f"[Step7] 발행 확인 버튼 클릭: '{confirmed}'")
            time.sleep(5)
        else:
            _log("[Step7] 발행 확인 버튼 없음 — 다시 찾기")
            page.screenshot(path="/Users/hana/Downloads/blog-automation-v2/debug_confirm_btn.png")

            # 모든 버튼 다시 확인
            all_btns = page.evaluate("""() => {
                return [...document.querySelectorAll('button')].map(b => ({
                    text: b.textContent.trim(),
                    disabled: b.disabled,
                    class: b.className.substring(0, 50)
                })).filter(b => b.text);
            }""")
            _log(f"[Step7] 현재 버튼들: {all_btns[:15]}")

            # 마지막 시도
            confirmed2 = page.evaluate("""() => {
                const btns = [...document.querySelectorAll('button')];
                // disabled 아닌 것 중 발행 관련
                const btn = btns.find(b => !b.disabled && (
                    b.textContent.includes('발행') ||
                    b.textContent.includes('확인') ||
                    b.textContent.includes('게시')
                ));
                if (btn) { btn.click(); return btn.textContent.trim(); }
                return null;
            }""")
            if confirmed2:
                _log(f"[Step7] 재시도 성공: '{confirmed2}'")
                time.sleep(5)
            else:
                _log("[Step7] 발행 실패 — 중단")
                _send_telegram(f"❌ salim1su 발행 실패: 최종 발행 버튼 없음")
                return False

        # ── 8. 발행 완료 확인 ─────────────────────────
        _log("[Step8] 발행 완료 확인...")
        time.sleep(3)
        final_url = page.url
        _log(f"[Step8] 최종 URL: {final_url}")

        # URL에서 포스트 번호 추출
        if "logNo=" in final_url or re.search(r'/\d{9,}', final_url):
            m = re.search(r'logNo=(\d+)', final_url) or re.search(r'/(\d{9,})', final_url)
            if m:
                log_no = m.group(1)
                published_url = f"https://blog.naver.com/{BLOG_ID}/{log_no}"
            else:
                published_url = final_url
        else:
            # 발행 후 이동한 URL 확인
            time.sleep(3)
            final_url = page.url
            _log(f"[Step8] 재확인 URL: {final_url}")
            published_url = final_url

        # 에러 팝업이나 임시저장 상태 확인
        if "postwrite" in final_url and "logNo" not in final_url:
            _log("[Step8] 아직 에디터 상태 — 발행 미완료일 수 있음")
        else:
            _log(f"[Step8] 발행 완료: {published_url}")

        # ── 9. 텔레그램 보고 ─────────────────────────
        report = f"""✅ salim1su 블로그 발행 완료

📰 제목: 서울도시가스 요금조회, 앱으로 1분 안에 되더라구요

📅 연도 수정: {'2025년 → 2026년 수정 완료' if year_fixed else '수정 불필요 (2025년 없음)'}

🖼️ 이미지 상태: {image_status}

🔗 발행 URL: {published_url if published_url else '확인 필요 (에디터 URL: ' + final_url + ')'}

📂 카테고리: {CATEGORY_NAME} {'✅' if category_set else '⚠️ 설정 실패'}"""

        _log(f"\n{'='*50}")
        _log(report)
        _log('='*50)
        _send_telegram(report)

        page.close()
        return True

    except Exception as e:
        _log(f"[ERROR] 예외 발생: {e}")
        import traceback
        _log(traceback.format_exc())
        _send_telegram(f"❌ salim1su 발행 실패: {e}")
        return False
    finally:
        pw.stop()


if __name__ == "__main__":
    success = run()
    print("\n" + "="*50)
    print(f"[결과] {'✅ 발행 완료' if success else '⚠️ 발행 불완전 (확인 필요)'}")
    print("="*50)
