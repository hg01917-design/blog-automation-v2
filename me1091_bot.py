"""me1091 쿠팡파트너스 리뷰 봇

흐름:
1. 노션 페이지에서 "쿠팡파트너스 링크 목록" 테이블 읽기
2. 처리 안 된 상품에 대해:
   a. 쿠팡 상품 페이지 크롤링 (상품명/가격/이미지/스펙)
   b. 상세페이지 이미지 2-3장 다운로드 → Gemini로 재생성
   c. Claude.ai 프로젝트로 1인칭 리뷰 글 작성
   d. me1091 네이버 블로그에 임시저장
3. 처리된 상품 SQLite에 기록 (중복 방지)

사용:
    python3 me1091_bot.py
"""
import sys, os, re, json, time, random, sqlite3, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

NOTION_PAGE_ID = "3366d296-d9c1-8122-ac8c-d02516403736"
BLOG_ID = "me1091"
DB_PATH = Path(__file__).parent / "keyword_engine" / "engine.db"
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

LOG_FILE = Path(__file__).parent / "logs" / "me1091_bot.log"
LOG_FILE.parent.mkdir(exist_ok=True)

_log_lines = []
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log_lines.append(line)

# ─── 노션: 쿠팡 링크 목록 읽기 ─────────────────────────────────────────────
def fetch_notion_products() -> list:
    """노션 페이지에서 상품명 + 쿠팡 링크 목록 파싱."""
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    token = os.getenv("NOTION_TOKEN", "")
    if not token:
        log("[노션] NOTION_TOKEN 없음")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    # 페이지 블록 목록 조회
    url = f"https://api.notion.com/v1/blocks/{NOTION_PAGE_ID}/children?page_size=100"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
    except Exception as e:
        log(f"[노션] 블록 조회 실패: {e}")
        return []

    products = []
    # 테이블 블록 탐색
    for block in data.get("results", []):
        if block.get("type") != "table":
            continue
        table_id = block["id"]
        # 테이블 행 조회
        rows_url = f"https://api.notion.com/v1/blocks/{table_id}/children?page_size=100"
        req2 = urllib.request.Request(rows_url, headers=headers)
        try:
            with urllib.request.urlopen(req2, timeout=15) as r2:
                rows_data = json.loads(r2.read())
        except Exception as e:
            log(f"[노션] 테이블 행 조회 실패: {e}")
            continue

        rows = rows_data.get("results", [])
        if not rows:
            continue

        # 첫 행이 헤더인지 확인 (상품명/쿠팡 링크 포함 여부)
        def get_cell_text(cell_block):
            cells = cell_block.get("table_row", {}).get("cells", [])
            texts = []
            for cell in cells:
                for rt in cell:
                    t = rt.get("plain_text", "") or rt.get("text", {}).get("content", "")
                    texts.append(t)
                    # href 링크 추출
                    href = rt.get("href") or rt.get("text", {}).get("link", {})
                    if isinstance(href, dict):
                        href = href.get("url", "")
                    if href:
                        texts.append(f"[LINK:{href}]")
            return " ".join(texts).strip()

        header_cells = []
        if rows:
            first_row = rows[0].get("table_row", {}).get("cells", [])
            for cell in first_row:
                header_cells.append(" ".join(rt.get("plain_text","") for rt in cell).strip())

        # 상품명/링크 컬럼 인덱스 찾기
        name_idx = next((i for i, h in enumerate(header_cells) if "상품명" in h), 0)
        link_idx = next((i for i, h in enumerate(header_cells) if "링크" in h or "URL" in h.upper()), 1)
        cat_idx  = next((i for i, h in enumerate(header_cells) if "카테고리" in h), 2)

        # 데이터 행 파싱 (첫 행 헤더 스킵)
        for row in rows[1:]:
            cells = row.get("table_row", {}).get("cells", [])
            if not cells:
                continue

            def cell_text(idx):
                if idx >= len(cells):
                    return ""
                parts = []
                for rt in cells[idx]:
                    parts.append(rt.get("plain_text", "") or rt.get("text", {}).get("content", ""))
                return " ".join(parts).strip()

            def cell_link(idx):
                if idx >= len(cells):
                    return ""
                for rt in cells[idx]:
                    href = rt.get("href") or ""
                    if not href:
                        href = (rt.get("text") or {}).get("link", {})
                        if isinstance(href, dict):
                            href = href.get("url", "")
                    if href and "coupang" in href.lower():
                        return href
                # href 없으면 텍스트에서 URL 추출
                full = cell_text(idx)
                m = re.search(r"https?://[^\s>\"']+coupang[^\s>\"']+", full, re.I)
                return m.group(0) if m else ""

            name = cell_text(name_idx)
            link = cell_link(link_idx)
            category = cell_text(cat_idx)

            # 예시 행 / 빈 행 스킵
            if not name or "(예시)" in name or not link:
                continue

            products.append({"name": name, "link": link, "category": category})
            log(f"[노션] 상품 발견: {name[:40]} | {link[:50]}")

        # 첫 번째 테이블만 (쿠팡 링크 목록) 파싱 후 종료
        if products:
            break

    return products


# ─── SQLite: 처리된 상품 추적 ─────────────────────────────────────────────
# ─── 글 각도(angle) 정의 — 같은 링크로 다른 글 쓰기 ────────────────────
# (angle_id, title_hint, writing_instruction)
PRODUCT_ANGLES = [
    (
        "가격후기",
        "쿠팡 가격 와우할인 직접 확인한 후기",
        "이 글의 포커스: 쿠팡 가격과 와우 회원 할인 혜택이 핵심이야.\n"
        "인트로에서 '비슷한 제품 중 쿠팡이 제일 저렴하더라'는 발견 경험으로 시작.\n"
        "가격 앵커링(정가 vs 쿠팡가 vs 와우가 차이)을 표로 시각화해서 명확히 보여줘.\n"
        "로켓배송 빠름 + 와우 할인 = 결론적으로 어디서 사는 게 이득인지 정리로 마무리."
    ),
    (
        "장단점",
        "솔직한 장단점 직접 써본 후기",
        "이 글의 포커스: 장점 위주지만 아쉬운 점 1-2가지를 솔직하게 인정하는 구조.\n"
        "'좋은 점만 쓰는 리뷰는 믿기 어렵잖아요'라는 공감으로 시작.\n"
        "장점 3-4개 구체적 사용 경험으로, 단점은 '이런 분에겐 불편할 수도'로 부드럽게.\n"
        "결론: '그래도 이 가격에 이 품질이면 괜찮다'는 합리화로 구매 유도."
    ),
    (
        "사용법",
        "처음 써봤을 때 이것만 알면 됩니다",
        "이 글의 포커스: '어떻게 쓰는 건지 몰라서 찾아봤어요'라는 독자 니즈 공략.\n"
        "처음 쓸 때 헷갈렸던 것, 알고 나서 훨씬 편해진 점 중심으로 구성.\n"
        "단계별 사용법 또는 처음엔 몰랐던 꿀팁을 실사용 경험처럼 자연스럽게 서술.\n"
        "맺음말: '이거 알고 쓰면 훨씬 다르더라'는 문장으로 구매 후 만족감 강조."
    ),
    (
        "추천대상",
        "이런 분들께 딱 맞는 제품입니다",
        "이 글의 포커스: 어떤 사람에게 이 제품이 맞는지 구체적 대상 설정.\n"
        "'자취하는 분', '선물용', '가성비 중시', '특정 용도' 등 3가지 유형으로 나눠 설명.\n"
        "각 유형마다 왜 이 제품이 맞는지 이유를 구체적으로 서술.\n"
        "반대로 '이런 분께는 안 맞을 수도 있어요'를 1가지 솔직하게 언급해서 신뢰도 확보.\n"
        "맺음말: '결국 내 상황에 맞는지 한 번만 확인해보세요 + 링크' CTA."
    ),
    (
        "비교",
        "비슷한 제품이랑 비교해봤어요",
        "이 글의 포커스: 이 제품과 경쟁 제품(가격대 또는 브랜드) 비교.\n"
        "'어떤 걸 살까 고민하다가 결국 이걸로 결정했어요'라는 선택 스토리로 시작.\n"
        "비교 대상 1-2개와 가격·기능·품질 차이를 간단 표 or 나열로 정리.\n"
        "결론: '이 가격대면 이게 더 낫더라'는 명확한 선택 이유로 마무리."
    ),
    (
        "재구매",
        "다시 산다면 또 이걸 살 것 같아요",
        "이 글의 포커스: 이미 한 번 써본 후 재구매 의사를 묻는 구조.\n"
        "'쓰다 보니까 이게 생각보다 좋더라고요'라는 사후 만족감 공유로 시작.\n"
        "초반엔 반신반의했지만 실제로 써보니 달랐던 경험을 구체적으로 서술.\n"
        "'다음에도 이 브랜드·제품 계속 쓸 것 같다'는 재구매 의사 표명으로 마무리.\n"
        "이미 구매 경험이 있는 독자에게 '맞아, 나도'를 유발하는 공감 포커스."
    ),
]


def _db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS me1091_published (
            product_name TEXT,
            angle        TEXT DEFAULT '',
            coupang_link TEXT,
            blog_url     TEXT,
            published_at TEXT,
            PRIMARY KEY (product_name, angle)
        )
    """)
    # 기존 테이블에 angle 컬럼이 없으면 추가 (마이그레이션)
    try:
        conn.execute("ALTER TABLE me1091_published ADD COLUMN angle TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass  # 이미 있으면 무시
    conn.commit()
    return conn


def get_next_angle(name: str) -> tuple | None:
    """상품명에 대해 아직 사용하지 않은 다음 angle 반환. 모두 소진 시 가장 오래된 것 재사용."""
    with _db_conn() as c:
        used = {
            row[0]
            for row in c.execute(
                "SELECT angle FROM me1091_published WHERE product_name=?", (name,)
            ).fetchall()
        }
    all_ids = [a[0] for a in PRODUCT_ANGLES]
    # 미사용 각도 우선
    for angle_id, title_hint, instruction in PRODUCT_ANGLES:
        if angle_id not in used:
            return angle_id, title_hint, instruction
    # 전부 소진 → 가장 먼저 쓴 각도부터 순환
    with _db_conn() as c:
        oldest = c.execute(
            "SELECT angle FROM me1091_published WHERE product_name=? ORDER BY published_at ASC LIMIT 1",
            (name,)
        ).fetchone()
    if oldest:
        recycle_id = oldest[0]
        for angle_id, title_hint, instruction in PRODUCT_ANGLES:
            if angle_id == recycle_id:
                return angle_id, title_hint, instruction
    return PRODUCT_ANGLES[0][0], PRODUCT_ANGLES[0][1], PRODUCT_ANGLES[0][2]


def mark_done(name: str, link: str, angle: str = "", blog_url: str = ""):
    with _db_conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO me1091_published(product_name, angle, coupang_link, blog_url, published_at)
            VALUES (?, ?, ?, ?, ?)
        """, (name, angle, link, blog_url, datetime.now().isoformat()))
        c.commit()


# ─── 쿠팡 크롤링 (Playwright CDP — 리뷰이미지/텍스트 포함) ──────────────
def scrape_coupang_product(link: str, on_log=None) -> dict:
    """쿠팡 상품 페이지에서 상품명/가격/이미지/리뷰 크롤링.

    Playwright CDP(포트 9222)로 실제 Chrome에서 크롤링:
    - 상품 이미지 (492x492)
    - 상품평 탭 클릭 → 리뷰 이미지 (320px) + 리뷰 텍스트
    리뷰 이미지/텍스트는 Claude 글 생성 컨텍스트로 활용.
    """
    import ssl, html, asyncio

    result = {
        "name": "", "price": "", "original_price": "",
        "images": [],        # Coupang 상품 이미지 로컬 경로
        "review_images": [], # Coupang 리뷰 이미지 로컬 경로
        "reviews": [],       # 리뷰 텍스트 목록
        "spec": "", "url": "",
    }

    _lg = on_log or log

    COUPANG_DIR = IMAGES_DIR / "coupang_product"
    COUPANG_DIR.mkdir(exist_ok=True)

    # ── HTTP로 상품명/가격만 먼저 파싱 ──
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    http_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://www.coupang.com/",
    }

    try:
        req = urllib.request.Request(link, headers=http_headers)
        with urllib.request.urlopen(req, timeout=20, context=ssl_ctx) as r:
            body = r.read().decode("utf-8", errors="ignore")
            final_url = r.url
        result["url"] = final_url
        m = re.search(r'property="og:title"\s+content="([^"]+)"', body)
        if not m:
            m = re.search(r'<title>([^<]+)</title>', body)
        if m:
            result["name"] = html.unescape(m.group(1)).strip().split("|")[0].strip()[:100]
        price_m = re.search(r'"price"\s*:\s*"?([\d,]+)"?', body)
        if price_m:
            result["price"] = price_m.group(1).replace(",", "")
        _lg(f"[쿠팡] 상품명: {result['name'][:60]} | 가격: {result['price']}원")
    except Exception as e:
        _lg(f"[쿠팡] HTTP 파싱 오류: {e}")
        result["url"] = link

    # ── Playwright CDP로 이미지 + 리뷰 스크래핑 ──
    async def _pw_scrape():
        from playwright.async_api import async_playwright

        product_url = result["url"] or link
        _lg(f"[쿠팡] Playwright CDP 접속: {product_url[:80]}")

        async with async_playwright() as pw:
            browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            ctx = browser.contexts[0]

            # 기존 쿠팡 탭 재사용 또는 새 탭
            page = None
            for p in ctx.pages:
                if "coupang.com/vp/products" in p.url:
                    # 같은 상품인지 확인
                    if product_url.split("?")[0].split("/")[-1] in p.url:
                        page = p
                        _lg("[쿠팡] 기존 탭 재사용")
                        break
            if not page:
                page = await ctx.new_page()
                await page.goto(product_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

            # 스크롤로 이미지 로드
            await page.evaluate("window.scrollTo(0, 600)")
            await asyncio.sleep(1)

            content = await page.content()

            # 492x492 상품 이미지 URL
            prod_imgs = list(dict.fromkeys(re.findall(
                r'https://thumbnail\d*\.coupangcdn\.com/thumbnails/remote/492x492[^"\'<>\s]+',
                content
            )))
            if not prod_imgs:
                prod_imgs = list(dict.fromkeys(re.findall(
                    r'https://thumbnail\d*\.coupangcdn\.com/thumbnails/remote/292x292[^"\'<>\s]+',
                    content
                )))
            _lg(f"[쿠팡] 상품 이미지 URL: {len(prod_imgs)}개")

            # 상품평 탭 클릭
            for sel in ['a:has-text("상품평")', '[data-tab-id="sdp-review"]', '.tab__item:has-text("상품평")']:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        await el.click()
                        await asyncio.sleep(2)
                        _lg("[쿠팡] 상품평 탭 클릭 완료")
                        break
                except Exception:
                    pass

            await page.evaluate("window.scrollBy(0, 800)")
            await asyncio.sleep(1)

            content2 = await page.content()

            # 리뷰 이미지 URL (320px)
            review_img_urls = list(dict.fromkeys(re.findall(
                r'https://thumbnail[^"\'<>\s]+/PRODUCTREVIEW/[^"\'<>\s]+\.(?:jpg|jpeg|png|webp)',
                content2
            )))
            review_320 = [u for u in review_img_urls if '/320/' in u]
            _lg(f"[쿠팡] 리뷰 이미지 URL: {len(review_320)}개")

            # 리뷰 텍스트 수집
            sdp_texts = await page.evaluate("""() => {
                const sdp = document.querySelector('.sdp-review');
                if (!sdp) return [];
                const seen = new Set();
                const texts = [];
                sdp.querySelectorAll('p, span, div').forEach(el => {
                    const t = el.textContent.trim();
                    if (t.length > 100 && t.length < 1500 && el.querySelectorAll('p,span').length < 3 && !seen.has(t)) {
                        seen.add(t);
                        texts.push(t);
                    }
                });
                return texts.slice(0, 10);
            }""")
            _lg(f"[쿠팡] 리뷰 텍스트: {len(sdp_texts)}개")

            # 이미지 다운로드
            cookies = await page.context.cookies()
            cookie_str = '; '.join(f"{c['name']}={c['value']}" for c in cookies if 'coupang' in c.get('domain', ''))
            dl_headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://www.coupang.com/',
                'Cookie': cookie_str[:500],
            }

            def _dl(url, fpath):
                try:
                    req = urllib.request.Request(url, headers=dl_headers)
                    resp = urllib.request.urlopen(req, timeout=15, context=ssl_ctx)
                    data = resp.read()
                    if len(data) > 5000:
                        Path(fpath).write_bytes(data)
                        return True
                except Exception:
                    pass
                return False

            # 상품 이미지 최대 5장
            for i, url in enumerate(prod_imgs[:5]):
                fpath = COUPANG_DIR / f"product_{i+1}.jpg"
                if _dl(url, fpath):
                    result["images"].append(str(fpath))

            # 리뷰 이미지 최대 10장
            for i, url in enumerate(review_320[:10]):
                fpath = COUPANG_DIR / f"review_{i+1}.jpg"
                if _dl(url, fpath):
                    result["review_images"].append(str(fpath))

            result["reviews"] = sdp_texts

            _lg(f"[쿠팡] 수집 완료 — 상품이미지:{len(result['images'])}장, 리뷰이미지:{len(result['review_images'])}장, 리뷰:{len(result['reviews'])}개")

            # 탭 닫기 (새로 열었을 때만)
            if "coupang.com/vp/products" not in (result["url"] or ""):
                try:
                    await page.close()
                except Exception:
                    pass

    try:
        asyncio.run(_pw_scrape())
    except Exception as e:
        _lg(f"[쿠팡] Playwright 스크래핑 오류: {e}")

    return result


# ─── 쿠팡 이미지 참고 → Gemini 실사진 재생성 ────────────────────────────
def _ask_claude_for_gemini_prompt(image_path: str, keyword: str) -> str:
    """쿠팡 리뷰 이미지를 Claude.ai에 보내 Gemini 이미지 생성용 영문 프롬프트 반환.

    Claude.ai(me1091 프로젝트)에 이미지를 첨부하고,
    "이 이미지 분위기로 실사진 스타일 이미지를 Gemini에서 만들 영문 프롬프트 작성"을 요청.
    """
    from claude_playwright import ask_with_image

    question = (
        f"이미지의 조명/배경/구도만 참고하고, 이미지에 보이는 특정 브랜드·상품은 무시해. "
        f"핵심 주제는 반드시 '{keyword}'야. "
        f"이 구도와 분위기로 '{keyword}' 제품을 촬영한 것처럼 실사진 스타일 이미지를 Gemini로 만들기 위한 "
        f"영문 프롬프트만 한 단락으로 작성해줘. "
        f"반드시 포함: the main subject is {keyword}, photorealistic real photo style, no AI look, "
        f"no text overlay, no people, no faces, no brand logos, no watermarks, 4K quality, Korean home/lifestyle setting. "
        f"설명 없이 영문 프롬프트만 출력해."
    )

    log(f"[Claude] 이미지 분석 → Gemini 프롬프트 요청: {Path(image_path).name}")
    prompt = ask_with_image(image_path, question, blog_id=BLOG_ID, on_log=log)

    if not prompt or len(prompt) < 20:
        log("[Claude] 프롬프트 생성 실패 → 기본 프롬프트 사용")
        return (
            f"{keyword} actual product in use, Korean home interior setting, "
            f"photorealistic real photo style, natural window light, clean minimal background, "
            f"no text, no faces, no logos, 4K quality"
        )

    # 코드블록/따옴표 등 불필요한 래퍼 제거
    prompt = re.sub(r'^```[^\n]*\n?', '', prompt.strip())
    prompt = re.sub(r'\n?```$', '', prompt.strip())
    prompt = prompt.strip('"\'`').strip()

    log(f"[Claude] 생성된 Gemini 프롬프트: {prompt[:100]}...")
    return prompt


def prepare_images_with_gemini(product_info: dict, keyword: str) -> tuple:
    """쿠팡 리뷰/상품 이미지 → Claude.ai 분석 → Gemini 프롬프트 생성 → Gemini 실사진 재생성.

    흐름:
      1. 리뷰이미지 2장 + 상품이미지 1장 선별 (최대 3장)
      2. 각 이미지를 Claude.ai에 보내 Gemini 프롬프트 받기
      3. 그 프롬프트 + 참고이미지로 Gemini에서 실사진 생성
    Returns: (image_paths: {idx: path}, image_infos: [{'index', 'filename', 'alt'}])
    """
    from image_router import generate_images_for_blog

    review_imgs = product_info.get("review_images", [])[:2]   # 리뷰 이미지 최대 2장
    product_imgs = product_info.get("images", [])[:1]          # 상품 이미지 최대 1장
    ref_images_list = review_imgs + product_imgs

    image_infos_input = []
    reference_images = []
    kw_slug = re.sub(r'[^\w]', '_', keyword[:20])

    if ref_images_list:
        log(f"[이미지] 쿠팡 참고 이미지 {len(ref_images_list)}장 → Claude 분석 → Gemini 재생성")
        for i, fpath in enumerate(ref_images_list, start=1):
            # Claude.ai에 이미지 보내서 Gemini 프롬프트 받기
            prompt = _ask_claude_for_gemini_prompt(fpath, keyword)
            image_infos_input.append({
                "index": i,
                "prompt": prompt,
                "filename": f"me1091_{kw_slug}_{i}.jpg",
            })
            reference_images.append(fpath)
            log(f"[이미지] [{i}] 참고: {Path(fpath).name} | 프롬프트: {prompt[:60]}...")
    else:
        log("[이미지] 쿠팡 참고 이미지 없음 — 기본 프롬프트로 생성")
        for i in range(1, 4):
            image_infos_input.append({
                "index": i,
                "prompt": (
                    f"{keyword} real usage in Korean home, photorealistic lifestyle photo, "
                    f"natural daylight, clean minimal interior, no text, no faces"
                ),
                "filename": f"me1091_{kw_slug}_{i}.jpg",
            })
        reference_images = None

    results = generate_images_for_blog(
        blog_id=BLOG_ID,
        image_infos=image_infos_input,
        skip_webp=True,
        on_log=log,
        reference_images=reference_images,
    )
    image_infos = [
        {"index": k, "filename": Path(v).name, "alt": f"{keyword} 실제 사용 모습 {k}"}
        for k, v in results.items()
    ]
    log(f"[이미지] Gemini 재생성 완료: {len(results)}장")
    return results, image_infos


# ─── Claude.ai 글 생성 ───────────────────────────────────────────────────
def generate_review_post(product_info: dict, coupang_link: str,
                         angle_id: str = "", angle_hint: str = "", angle_instruction: str = "") -> tuple:
    """Claude.ai me1091 프로젝트로 리뷰 글 생성. (title, content, tags) 반환."""
    from claude_playwright import generate_text

    name = product_info.get("name", "")
    price = product_info.get("price", "")
    original_price = product_info.get("original_price", "")
    spec = product_info.get("spec", "")
    category = product_info.get("category", "")

    price_str = ""
    if price:
        price_str = f"현재가: {price}원"
        if original_price and original_price != price:
            price_str += f" (정가: {original_price}원)"

    # 리뷰 텍스트 → 컨텍스트 (최대 3개)
    reviews = product_info.get("reviews", [])[:3]
    reviews_str = ""
    if reviews:
        reviews_str = "\n\n[실제 구매자 리뷰 — 글 작성 참고용]\n"
        for i, rv in enumerate(reviews, 1):
            reviews_str += f"리뷰{i}: {rv[:300]}\n\n"

    # 각도 지시문
    angle_section = ""
    if angle_instruction:
        angle_section = f"\n[이번 글 포커스 — 반드시 따를 것]\n{angle_instruction}\n"

    # 제목 힌트 (각도별 다른 방향)
    title_direction = ""
    if angle_hint:
        title_direction = (
            f"이번 글 각도: '{angle_hint}'\n"
            f"제목은 이 각도를 반영한 구체적 검색어 형태로 작성 (상품명 + 각도 키워드 조합).\n"
            f"예시 방향: '{name[:15]} {angle_hint}'\n"
            f"단, 매번 새로운 형태의 제목이 나오도록 단순 복붙 금지."
        )
    else:
        title_direction = (
            "핵심 원칙: 사람들이 이 제품을 검색할 때 실제로 가지는 궁금증이나 고민을 제목에 담을 것.\n"
            "질문, 결과, 비교, 고민해결, 타깃 독자 명시 등 다양한 방식으로 자유롭게 응용하되\n"
            "매번 다른 형태의 제목이 나오도록 창의적으로 작성.\n"
            "'직접 써본 후기', '사용기', '직접 써봤어요' 같은 단순 후기형 제목은 사용 금지."
        )

    # 상품 정보를 extra_context로 전달 → 노션 프로젝트 프롬프트와 합쳐짐
    extra = f"""[상품 정보]
상품명: {name}
카테고리: {category}
가격: {price_str}
스펙: {spec[:300] if spec else '없음'}
쿠팡파트너스 링크: {coupang_link}
{reviews_str}{angle_section}
[링크 삽입 형식]
본문 상단 첫 소제목 아래 + 말미에 아래 형식으로 반드시 2회 삽입:
👉 [쿠팡에서 최저가 확인하기]({coupang_link})
※ 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 일정액의 수수료를 제공받습니다.

[출력 형식 — 반드시 아래 마커 사용]
===제목===
(SEO 최적화 제목 — 30~45자, 상품명 포함.
{title_direction})
===제목끝===

===본문===
(1인칭 리뷰 본문 전체 — 2000자 이상, 실제 리뷰 내용 자연스럽게 참고)
===본문끝===

===태그===
태그1, 태그2, 태그3, ... (10~15개)
===태그끝===
"""

    log(f"[Claude] {BLOG_ID} 글 생성 시작: {name[:40]} (각도: {angle_id or '기본'})")
    raw = generate_text("", blog_id=BLOG_ID, keyword=name, on_log=log, extra_context=extra)
    if not raw or "추출 실패" in raw:
        log("[Claude] 글 생성 실패")
        return None, None, []

    # 파싱
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m  = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===",  raw, re.DOTALL)
    tag_m   = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===",  raw, re.DOTALL)

    title   = title_m.group(1).strip().split("\n")[0].strip() if title_m else name[:40]
    content = body_m.group(1).strip() if body_m else raw
    tags    = [t.strip() for t in tag_m.group(1).strip().split(",") if t.strip()] if tag_m else [name]

    log(f"[Claude] 제목: {title}")
    log(f"[Claude] 본문: {len(content)}자, 태그: {len(tags)}개")
    return title, content, tags


# ─── 단일 상품 처리 (overnight_run.py에서 호출) ─────────────────────────
def run_one_product(on_log=None) -> bool:
    """Notion 상품 풀에서 다음 (상품, 각도) 조합을 처리. overnight_run.py에서 호출."""
    def _log(m):
        if on_log: on_log(m)
        log(m)

    products = fetch_notion_products()
    if not products:
        _log("[me1091] 처리할 Notion 상품 없음")
        return False

    # 모든 상품에 대해 사용 가능한 각도가 있는 것 우선 선택
    # 우선순위: 1) 미사용 각도 있는 상품 → 2) 가장 오래된 각도 순환 상품
    selected_product = None
    selected_angle = None

    # 1순위: 미사용 각도가 있는 상품 (DB에 없거나 일부만 사용한 상품)
    for product in products:
        name = product["name"]
        angle_info = get_next_angle(name)
        if angle_info is None:
            continue
        angle_id, angle_hint, angle_instruction = angle_info
        # 이 (name, angle_id) 조합이 실제로 미사용인지 확인
        with _db_conn() as c:
            used = c.execute(
                "SELECT 1 FROM me1091_published WHERE product_name=? AND angle=?",
                (name, angle_id)
            ).fetchone()
        if not used:
            selected_product = product
            selected_angle = (angle_id, angle_hint, angle_instruction)
            break

    # 2순위: 전체 각도 소진 시 가장 오래된 것 순환
    if selected_product is None:
        for product in products:
            name = product["name"]
            angle_info = get_next_angle(name)
            if angle_info:
                selected_product = product
                selected_angle = angle_info
                break

    if selected_product is None:
        _log("[me1091] 사용 가능한 상품·각도 조합 없음")
        return False

    name = selected_product["name"]
    link = selected_product["link"]
    angle_id, angle_hint, angle_instruction = selected_angle
    _log(f"[me1091] 처리: {name[:40]} | 각도: {angle_id}")

    product_info = scrape_coupang_product(link, on_log=_log)
    product_info["category"] = selected_product.get("category", "")
    if not product_info.get("name"):
        product_info["name"] = name

    keyword = product_info.get("name") or name

    # 쿠팡 이미지(리뷰+상품) 참고 → Gemini 실사진 재생성
    image_paths, image_infos_list = prepare_images_with_gemini(product_info, keyword)

    title, content, tags = generate_review_post(
        product_info, link,
        angle_id=angle_id, angle_hint=angle_hint, angle_instruction=angle_instruction
    )
    if not title or not content:
        _log(f"[me1091] 글 생성 실패: {name[:40]}")
        return False

    # 수수료 문구 맨 위 강제 삽입
    DISCLOSURE = "※ 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.\n\n"
    if DISCLOSURE.strip() not in content:
        content = DISCLOSURE + content

    try:
        from poster import post_single
        ok = post_single(
            blog_id=BLOG_ID,
            title=title,
            content=content,
            tags=tags,
            image_paths=image_paths,
            image_infos=image_infos_list,
            keyword=keyword,
            on_log=_log,
        )
        if ok:
            mark_done(name, link, angle=angle_id)
            _log(f"[me1091] ✅ 임시저장 완료: {title} (각도: {angle_id})")
        return ok
    except Exception as e:
        _log(f"[me1091] 포스팅 오류: {e}")
        return False


# ─── 메인 파이프라인 ─────────────────────────────────────────────────────
def run():
    log("=" * 55)
    log(f"me1091 봇 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 55)

    # 1. 노션에서 상품 목록 읽기
    products = fetch_notion_products()
    if not products:
        log("[봇] 처리할 상품 없음")
        return

    log(f"[봇] 총 {len(products)}개 상품 발견")

    processed = 0
    for product in products:
        name = product["name"]
        link = product["link"]

        angle_info = get_next_angle(name)
        if angle_info is None:
            log(f"[스킵] 각도 없음: {name[:40]}")
            continue
        angle_id, angle_hint, angle_instruction = angle_info

        # 이미 사용한 (name, angle_id) 조합이면 스킵
        with _db_conn() as c:
            already = c.execute(
                "SELECT 1 FROM me1091_published WHERE product_name=? AND angle=?",
                (name, angle_id)
            ).fetchone()
        if already:
            log(f"[스킵] 모든 각도 소진: {name[:40]}")
            continue

        log(f"\n{'='*45}")
        log(f"[처리] {name[:50]} | 각도: {angle_id}")
        log(f"[처리] 링크: {link}")

        # 2. 쿠팡 상품 크롤링
        product_info = scrape_coupang_product(link, on_log=log)
        product_info["category"] = product.get("category", "")

        if not product_info.get("name"):
            product_info["name"] = name  # fallback

        # 3. 쿠팡 이미지(리뷰+상품) 참고 → Gemini 실사진 재생성
        keyword = product_info.get("name") or name
        image_paths, image_infos_list = prepare_images_with_gemini(product_info, keyword)

        # 4. 글 생성 (각도 적용)
        title, content, tags = generate_review_post(
            product_info, link,
            angle_id=angle_id, angle_hint=angle_hint, angle_instruction=angle_instruction
        )
        if not title or not content:
            log(f"[스킵] 글 생성 실패: {name[:40]}")
            continue

        # 수수료 문구 맨 위 강제 삽입
        DISCLOSURE = "※ 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.\n\n"
        if DISCLOSURE.strip() not in content:
            content = DISCLOSURE + content

        # 5. 네이버 임시저장
        try:
            from poster import post_single
            log(f"[발행] me1091 네이버 임시저장 시작")
            ok = post_single(
                blog_id=BLOG_ID,
                title=title,
                content=content,
                tags=tags,
                image_paths=image_paths,
                image_infos=image_infos_list,
                keyword=product_info.get("name", ""),
                on_log=log,
            )

            if ok:
                mark_done(name, link, angle=angle_id)
                processed += 1
                log(f"[완료] ✅ {name[:40]} (각도: {angle_id}) 임시저장 완료")

                # 텔레그램 보고
                try:
                    from notify import send_telegram
                    send_telegram(
                        f"✅ me1091 임시저장 완료\n상품: {name[:40]}\n각도: {angle_id}\n제목: {title}"
                    )
                except Exception:
                    pass
            else:
                log(f"[실패] ❌ {name[:40]}")

        except Exception as e:
            log(f"[오류] {e}")
            import traceback
            traceback.print_exc()

        # 상품 간 대기 (자연스럽게)
        if processed > 0:
            wait = random.randint(300, 600)
            log(f"[대기] {wait}초 후 다음 상품 처리")
            time.sleep(wait)

    log(f"\n[봇] 완료 — {processed}/{len(products)}개 처리")
    LOG_FILE.write_text("\n".join(_log_lines), encoding="utf-8")


if __name__ == "__main__":
    run()
