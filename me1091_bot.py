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
def _db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS me1091_published (
            product_name TEXT PRIMARY KEY,
            coupang_link TEXT,
            blog_url     TEXT,
            published_at TEXT
        )
    """)
    conn.commit()
    return conn

def is_already_done(name: str) -> bool:
    with _db_conn() as c:
        row = c.execute("SELECT 1 FROM me1091_published WHERE product_name=?", (name,)).fetchone()
    return row is not None

def mark_done(name: str, link: str, blog_url: str = ""):
    with _db_conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO me1091_published(product_name, coupang_link, blog_url, published_at)
            VALUES (?, ?, ?, ?)
        """, (name, link, blog_url, datetime.now().isoformat()))
        c.commit()


# ─── 쿠팡 크롤링 ─────────────────────────────────────────────────────────
def scrape_coupang_product(link: str, on_log=None) -> dict:
    """쿠팡 상품 페이지에서 상품명/가격/이미지/스펙 크롤링 (Playwright)."""
    def log_(m):
        if on_log: on_log(m)
        log(m)

    from browser import connect_cdp, get_or_create_page

    pw, browser = connect_cdp(on_log)
    page = get_or_create_page(browser)

    result = {"name": "", "price": "", "original_price": "", "images": [], "spec": "", "url": ""}

    try:
        log_(f"[쿠팡] 링크 접속: {link[:60]}")
        page.goto(link, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        result["url"] = page.url

        # 상품명
        for sel in [".prod-buy-header__title", "h1.prod-title", "h1"]:
            el = page.query_selector(sel)
            if el:
                result["name"] = el.inner_text().strip()[:100]
                break

        # 가격
        for sel in [".final-price .price-amount", ".total-price strong", ".price-amount"]:
            el = page.query_selector(sel)
            if el:
                result["price"] = el.inner_text().strip().replace(",", "")
                break
        for sel in [".original-price .price-amount", ".origin-price"]:
            el = page.query_selector(sel)
            if el:
                result["original_price"] = el.inner_text().strip().replace(",", "")
                break

        # 상세 이미지 (썸네일 슬라이더)
        img_els = page.query_selector_all(".prod-image__detail img, .thumbnail-image img, img.prod-image")
        seen = set()
        for img in img_els[:6]:
            src = img.get_attribute("src") or img.get_attribute("data-src") or ""
            if src and src not in seen and "coupangcdn" in src:
                seen.add(src)
                result["images"].append(src)
            if len(result["images"]) >= 3:
                break

        # 스펙 텍스트
        spec_el = page.query_selector(".prod-attr-table, .spec-list, table.prod-spec")
        if spec_el:
            result["spec"] = spec_el.inner_text().strip()[:500]

        log_(f"[쿠팡] 상품명: {result['name']}")
        log_(f"[쿠팡] 가격: {result['price']}원 (정가: {result['original_price']}원)")
        log_(f"[쿠팡] 이미지: {len(result['images'])}장")

    except Exception as e:
        log_(f"[쿠팡] 크롤링 오류: {e}")

    return result


# ─── 이미지 다운로드 + Gemini 재생성 ────────────────────────────────────
def download_and_regenerate_images(product_info: dict, keyword: str) -> dict:
    """쿠팡 이미지 다운로드 후 Gemini로 라이프스타일 이미지 재생성."""
    from image_router import generate_images_for_blog

    image_infos = []
    for i, img_url in enumerate(product_info["images"][:3], start=1):
        filename = f"me1091_{re.sub(r'[^\\w]', '_', keyword[:20])}_{i}.jpg"
        prompt = f"{keyword} 실제 사용 장면, 한국 가정 생활환경, 자연스러운 라이프스타일"
        image_infos.append({
            "index": i,
            "prompt": prompt,
            "filename": filename,
        })
        log(f"[이미지] [{i}] 프롬프트: {prompt[:60]}")

    if not image_infos:
        log("[이미지] 생성할 이미지 없음")
        return {}

    results = generate_images_for_blog(
        blog_id=BLOG_ID,
        image_infos=image_infos,
        skip_webp=True,
        on_log=log,
    )
    log(f"[이미지] 생성 완료: {len(results)}장")
    return results


# ─── Claude.ai 글 생성 ───────────────────────────────────────────────────
def generate_review_post(product_info: dict, coupang_link: str) -> tuple:
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

    # 상품 정보를 extra_context로 전달 → 노션 프로젝트 프롬프트와 합쳐짐
    extra = f"""[상품 정보]
상품명: {name}
카테고리: {category}
가격: {price_str}
스펙: {spec[:300] if spec else '없음'}
쿠팡파트너스 링크: {coupang_link}

[링크 삽입 형식]
본문 중간 + 말미에 아래 형식으로 자연스럽게 삽입:
👉 [쿠팡에서 최저가 확인하기]({coupang_link})
※ 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 일정액의 수수료를 제공받습니다.

[이미지 파일명 규칙]
me1091_review_1.jpg, me1091_review_2.jpg, me1091_review_3.jpg 사용
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

        if is_already_done(name):
            log(f"[스킵] 이미 처리됨: {name[:40]}")
            continue

        log(f"\n{'='*45}")
        log(f"[처리] {name[:50]}")
        log(f"[처리] 링크: {link}")

        # 2. 쿠팡 상품 크롤링
        product_info = scrape_coupang_product(link, on_log=log)
        product_info["category"] = product.get("category", "")

        if not product_info.get("name"):
            product_info["name"] = name  # fallback

        # 3. 이미지 생성
        keyword = product_info.get("name") or name
        image_paths = download_and_regenerate_images(product_info, keyword)

        # 4. 글 생성
        title, content, tags = generate_review_post(product_info, link)
        if not title or not content:
            log(f"[스킵] 글 생성 실패: {name[:40]}")
            continue

        # 5. 네이버 임시저장
        try:
            from config import ACCOUNT_MAP

            account = ACCOUNT_MAP.get(BLOG_ID)
            if not account:
                log(f"[오류] config에 {BLOG_ID} 없음")
                continue

            image_infos_list = [
                {"index": idx, "filename": Path(fp).name, "alt": f"{keyword} 이미지 {idx}"}
                for idx, fp in image_paths.items()
            ]

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
                mark_done(name, link)
                processed += 1
                log(f"[완료] ✅ {name[:40]} 임시저장 완료")

                # 텔레그램 보고
                try:
                    from notify import send_telegram
                    send_telegram(
                        f"✅ me1091 임시저장 완료\n상품: {name[:40]}\n제목: {title}"
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
