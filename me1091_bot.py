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


# ─── 쿠팡파트너스 API 상품 소싱 (다양성 확보) ─────────────────────────────
_API_SEARCH_POOL = [
    ("로봇청소기", "청소/생활"),
    ("무선청소기", "청소/생활"),
    ("물걸레청소기", "청소/생활"),
    ("에어프라이어", "주방가전"),
    ("전기밥솥", "주방가전"),
    ("전기포트", "주방가전"),
    ("핸드믹서", "주방가전"),
    ("공기청정기", "가전"),
    ("가습기", "가전"),
    ("제습기", "가전"),
    ("미니선풍기", "가전"),
    ("섬유유연제", "세탁용품"),
    ("세탁세제", "세탁용품"),
    ("비타민C", "건강식품"),
    ("유산균 프로바이오틱스", "건강식품"),
    ("오메가3", "건강식품"),
    ("단백질 보충제", "건강식품"),
    ("강아지 사료", "반려동물"),
    ("고양이 간식", "반려동물"),
    ("펫 매트", "반려동물"),
    ("메모리폼 베개", "수면"),
    ("매트리스 토퍼", "수면"),
    ("멀티탭 USB", "생활잡화"),
    ("무선충전기", "전자기기"),
    ("수납함 정리함", "생활잡화"),
    ("밀폐용기 세트", "주방잡화"),
    ("핸드크림", "뷰티"),
    ("선크림 자외선차단제", "뷰티"),
    ("마스크팩", "뷰티"),
    ("두피케어 샴푸", "뷰티"),
    ("스테인리스 냄비", "주방잡화"),
    ("테프론 프라이팬", "주방잡화"),
    ("보온병 텀블러", "주방잡화"),
    ("탈취제", "생활잡화"),
    ("방향제", "생활잡화"),
    ("전동칫솔", "생활잡화"),
    ("체중계 스마트", "생활잡화"),
    ("접이식 캠핑의자", "아웃도어"),
    ("캠핑 랜턴", "아웃도어"),
    ("등산화", "아웃도어"),
]


def fetch_api_products(n_keywords: int = 5) -> list:
    """쿠팡파트너스 API로 다양한 카테고리 상품을 무작위 수집.

    _API_SEARCH_POOL에서 n_keywords개를 무작위 선택해 각 최대 3개 상품 반환.
    더미 URL (link.coupang.com/a/dummy) 은 제외.
    """
    import random as _rand
    try:
        from coupang_api import search_products as _search
    except ImportError:
        log("[API소싱] coupang_api 임포트 실패")
        return []

    chosen = _rand.sample(_API_SEARCH_POOL, min(n_keywords, len(_API_SEARCH_POOL)))
    products = []
    seen_names: set = set()

    for kw, cat in chosen:
        try:
            items = _search(kw, category=cat, limit=3)
            for item in items:
                nm = item.get("name", "")
                url = item.get("url", "")
                # 더미 / 유효하지 않은 URL 제외
                if not nm or not url or "dummy" in url or not url.startswith("https://"):
                    continue
                if nm in seen_names:
                    continue
                seen_names.add(nm)
                products.append({"name": nm, "link": url, "category": cat})
                log(f"[API소싱] {kw} → {nm[:40]} ({cat})")
        except Exception as e:
            log(f"[API소싱] '{kw}' 검색 오류: {e}")

    log(f"[API소싱] 총 {len(products)}개 상품 수집")
    return products


# ─── 공정위 문구 이미지 (캐시: images/me1091/disclosure.png) ──────────────
DISCLOSURE_IMG_PATH = Path(__file__).parent / "images" / "me1091" / "disclosure.png"

def make_disclosure_image() -> Path | None:
    """공정위 표시광고 문구 이미지를 생성(또는 캐시 반환)."""
    if DISCLOSURE_IMG_PATH.exists():
        return DISCLOSURE_IMG_PATH
    try:
        from PIL import Image, ImageDraw, ImageFont
        DISCLOSURE_IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
        W, H = 800, 52
        img = Image.new("RGB", (W, H), "#f9f9f9")
        draw = ImageDraw.Draw(img)
        # 위/아래 얇은 구분선
        draw.line([(0, 0), (W, 0)], fill="#d8d8d8", width=1)
        draw.line([(0, H - 1), (W, H - 1)], fill="#d8d8d8", width=1)
        text = "※ 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
        try:
            font = ImageFont.truetype("/System/Library/Fonts/AppleSDGothicNeo.ttc", 18)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = max(16, (W - tw) // 2)
        draw.text((x, (H - (bbox[3] - bbox[1])) // 2), text, font=font, fill="#777777")
        img.save(DISCLOSURE_IMG_PATH, "PNG")
        log(f"[공정위] 이미지 생성 완료: {DISCLOSURE_IMG_PATH.name}")
        return DISCLOSURE_IMG_PATH
    except Exception as e:
        log(f"[공정위] 이미지 생성 실패: {e}")
        return None


def _inject_image_markers(content: str, image_keys: list) -> str:
    """본문 단락 사이에 {{이미지N}} 마커를 균등 배치한다."""
    if not image_keys:
        return content
    paras = [p for p in content.split('\n\n') if p.strip()]
    n = len(paras)
    keys = sorted(image_keys)
    placements = []
    for i, idx in enumerate(keys):
        pos = max(1, min(n - 1, round((i + 1) * n / (len(keys) + 1))))
        placements.append((pos, idx))
    # 뒤에서부터 삽입해서 앞 인덱스가 밀리지 않도록
    for pos, idx in sorted(placements, key=lambda x: -x[0]):
        paras.insert(pos, f'{{{{이미지{idx}}}}}')
    return '\n\n'.join(paras)


# ─── SQLite: 처리된 상품 추적 ─────────────────────────────────────────────
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
            new_page_opened = False
            for p in ctx.pages:
                if "coupang.com/vp/products" in p.url:
                    if product_url.split("?")[0].split("/")[-1] in p.url:
                        page = p
                        _lg("[쿠팡] 기존 탭 재사용")
                        break
            if not page:
                page = await ctx.new_page()
                new_page_opened = True
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

            # 새로 연 탭이면 닫기 (재사용 탭은 유지)
            if new_page_opened:
                try:
                    await page.close()
                    _lg("[쿠팡] 탭 닫기 완료")
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
        f"이 구도와 분위기로 '{keyword}' 제품을 한국 일반 가정집에서 실제 사용 중인 라이프스타일 사진처럼 Gemini로 만들기 위한 "
        f"영문 프롬프트만 한 단락으로 작성해줘. "
        f"절대 금지: white background product photo, studio shot, advertising photo, isolated product. "
        f"반드시 포함: the product naturally placed in a real Korean home, in-use lifestyle scene, "
        f"photorealistic real photo style, natural daylight or warm indoor light, "
        f"no text overlay, no people, no faces, no brand logos, no watermarks, 4K quality. "
        f"설명 없이 영문 프롬프트만 출력해."
    )

    log(f"[Claude] 이미지 분석 → Gemini 프롬프트 요청: {Path(image_path).name}")
    prompt = ask_with_image(image_path, question, blog_id=BLOG_ID, on_log=log)

    _FALLBACK = (
        f"{keyword} actual product in use, Korean home interior setting, "
        f"photorealistic real photo style, natural window light, clean minimal background, "
        f"no text, no faces, no logos, 4K quality"
    )

    if not prompt or len(prompt) < 20:
        log("[Claude] 프롬프트 생성 실패 → 기본 프롬프트 사용")
        return _FALLBACK

    # Claude가 이미지를 못 봤을 때 반환하는 에러 메시지 감지
    _ERROR_PHRASES = [
        "이미지가 보이지", "이미지를 볼 수", "첨부된 이미지", "참고할 이미지",
        "이미지를 업로드", "업로드해주세요", "이미지를 첨부", "이미지 파일",
        "죄송합니다", "cannot see", "can't see", "i cannot", "i can't",
        "no image", "image not", "please upload", "please attach",
        "[추출 실패]", "추출 실패", "dom에서 응답",
    ]
    prompt_lower = prompt.lower()
    if any(phrase.lower() in prompt_lower for phrase in _ERROR_PHRASES):
        log(f"[Claude] 이미지 인식 실패 응답 감지 → 기본 프롬프트 사용: {prompt[:60]}")
        return _FALLBACK

    # 영문 프롬프트가 아닌 경우 (한국어 응답 등) 폴백
    english_ratio = sum(1 for c in prompt if ord(c) < 128) / max(len(prompt), 1)
    if english_ratio < 0.5:
        log(f"[Claude] 영문 프롬프트 아님 (영문비율 {english_ratio:.0%}) → 기본 프롬프트 사용")
        return _FALLBACK

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

    # 실패한 이미지는 reference 없이 재시도 (쿠팡 제품사진이 Gemini 콘텐츠 필터 유발)
    failed = [info for info in image_infos_input if info["index"] not in results]
    if failed and reference_images:
        log(f"[이미지] {len(failed)}장 실패 → reference 없이 재시도")
        retry_results = generate_images_for_blog(
            blog_id=BLOG_ID,
            image_infos=failed,
            skip_webp=True,
            on_log=log,
            reference_images=None,
        )
        results.update(retry_results)

    image_infos = [
        {"index": k, "filename": Path(v).name, "alt": f"{keyword} 실제 사용 모습 {k}"}
        for k, v in results.items()
    ]
    log(f"[이미지] Gemini 재생성 완료: {len(results)}장")
    return results, image_infos


# ─── Claude.ai 글 생성 ───────────────────────────────────────────────────
def generate_review_post(product_info: dict, coupang_link: str) -> tuple:
    """Claude.ai me1091 프로젝트로 리뷰 글 생성. (title, content, tags) 반환."""
    try:
        from claude_direct import generate_text
    except ImportError:
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

    reviews = product_info.get("reviews", [])[:3]
    reviews_str = ""
    if reviews:
        reviews_str = "\n\n[실제 구매자 리뷰 참고]\n"
        for i, rv in enumerate(reviews, 1):
            reviews_str += f"리뷰{i}: {rv[:300]}\n\n"

    extra = f"""[상품 정보]
상품명: {name}
카테고리: {category}
가격: {price_str}
스펙: {spec[:300] if spec else '없음'}
쿠팡파트너스 링크: {coupang_link}
{reviews_str}
[글 방향]
이 상품이 실제로 어떤 상황에서 유용한지, 어떻게 쓰면 좋은지를 자연스럽게 담은 생활 정보글.
상품의 실제 용도에 맞게 제목과 내용을 자유롭게 잡을 것. 상품명을 제목에 넣어도 됨.
구매 전 고민했던 점, 쓰면서 느낀 점, 이런 분께 맞을 것 같다는 개인 의견을 솔직하게.

[글 스타일]
- 해요체로 작성. '~했다', '~이다', '~한다', '~됩니다', '~아/어요' 어미 혼용 금지.
  종결어미는 반드시 '~했어요', '~예요', '~이에요', '~네요', '~더라고요', '~거든요' 등 해요체만 사용.
- 실제 사람이 쓴 것처럼 자연스러운 구어체. AI가 쓴 느낌 절대 금지.
- 소제목(##, bold 헤딩) 사용 금지 — 문단으로만 흐름 이어갈 것
- "💡", "정리하자면", 번호 나열, 글머리 기호 금지
- "도움이 됐으면 좋겠어요" 같은 마무리 금지
- 2000자 이상

[링크 삽입 형식]
본문에서 상품 언급 시 + 말미에 2회:
👉 [쿠팡에서 확인하기]({coupang_link})
(공정위 문구는 별도 이미지로 처리하므로 본문에 넣지 말 것)

[출력 형식]
===제목===
(제목 — 20~40자. 검색에 걸릴 만한 자연스러운 키워드 포함.)
===제목끝===

===본문===
(본문 전체 — 2000자 이상, 소제목 없는 산문)
===본문끝===

===태그===
태그1, 태그2, ... (10~15개 — 상품명, 용도, 상황 키워드 혼합)
===태그끝===
"""

    log(f"[Claude] {BLOG_ID} 글 생성 시작: {name[:40]}")
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
    """쿠팡파트너스 API에서 상품을 수집해 리뷰 글 작성 후 임시저장. overnight_run.py에서 호출."""
    def _log(m):
        if on_log: on_log(m)
        log(m)

    products = fetch_api_products(n_keywords=6)
    if not products:
        _log("[me1091] API 상품 수집 실패 — 처리할 상품 없음")
        return False

    # 발행 이력 확인 — 미발행 상품 우선, 없으면 아무거나
    import random as _rand
    _rand.shuffle(products)
    with _db_conn() as c:
        published_names = {
            row[0] for row in c.execute("SELECT product_name FROM me1091_published").fetchall()
        }
    fresh = [p for p in products if p["name"] not in published_names]
    selected_product = fresh[0] if fresh else products[0]

    name = selected_product["name"]
    link = selected_product["link"]
    _log(f"[me1091] 처리: {name[:40]}")

    product_info = scrape_coupang_product(link, on_log=_log)
    product_info["category"] = selected_product.get("category", "")
    if not product_info.get("name"):
        product_info["name"] = name

    keyword = product_info.get("name") or name

    # 원본 URL → 쿠팡파트너스 단축 링크 변환
    from coupang_api import create_affiliate_link as _make_aff_link
    affiliate_link = _make_aff_link(link, on_log=_log)
    if affiliate_link == link and "link.coupang.com" not in link:
        _log(f"[me1091] ⚠️ 파트너스 링크 변환 실패 — 원본 URL 사용: {link[:60]}")

    # 쿠팡 이미지(리뷰+상품) 참고 → Gemini 실사진 재생성
    image_paths, image_infos_list = prepare_images_with_gemini(product_info, keyword)

    title, content, tags = generate_review_post(product_info, affiliate_link)
    if not title or not content:
        _log(f"[me1091] 글 생성 실패: {name[:40]}")
        return False

    import re as _re

    # 텍스트 공정위 문구 모두 제거 (이미지로 대체) — "이 포스팅은..." 또는 "수수료가 발생..." 변형 모두 처리
    content = _re.sub(r'※[^\n]*(?:파트너스|수수료|제공받)[^\n]*\n?', '', content).lstrip()

    # 공정위 이미지 → image_paths[0], {{이미지0}} 맨 위에 삽입
    disc_path = make_disclosure_image()
    if disc_path:
        image_paths[0] = str(disc_path)
        image_infos_list.insert(0, {
            "index": 0,
            "filename": disc_path.name,
            "alt": "쿠팡파트너스 수수료 안내",
        })
        content = "{{이미지0}}\n\n" + content
        _log("[me1091] 공정위 이미지 삽입")

    # Gemini 이미지 마커 자동 삽입 (본문 균등 배치)
    gemini_keys = [k for k in image_paths if k != 0]
    if gemini_keys:
        content = _inject_image_markers(content, gemini_keys)
        _log(f"[me1091] Gemini 이미지 마커 {len(gemini_keys)}개 삽입")

    try:
        from poster import post_single
        seo_keyword = title[:15] if title else keyword
        ok = post_single(
            blog_id=BLOG_ID,
            title=title,
            content=content,
            tags=tags,
            image_paths=image_paths,
            image_infos=image_infos_list,
            keyword=seo_keyword,
            on_log=_log,
        )
        if ok:
            mark_done(name, affiliate_link)
            _log(f"[me1091] ✅ 임시저장 완료: {title}")
        return ok
    except Exception as e:
        _log(f"[me1091] 포스팅 오류: {e}")
        return False


# ─── 메인 파이프라인 ─────────────────────────────────────────────────────
def run():
    log("=" * 55)
    log(f"me1091 봇 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 55)

    ok = run_one_product()
    log(f"\n[봇] {'완료' if ok else '실패'}")
    LOG_FILE.write_text("\n".join(_log_lines), encoding="utf-8")


if __name__ == "__main__":
    run()
