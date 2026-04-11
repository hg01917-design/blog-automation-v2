"""네이버 브랜드커넥트 제휴 링크 자동 포스팅 봇

흐름:
  1. naver_connect_products.json 에서 상품명 + naver.me 제휴 링크 읽기
  2. naver.me → 실제 네이버 쇼핑 상품 페이지로 이동 → 정보 추출
     (상품명, 가격, 원가, 할인율, 평점, 리뷰수, 스토어, 리뷰, 이미지)
  3. Claude.ai 프로젝트로 살림/생활 관점 리뷰 글 작성
  4. salim1su 네이버 블로그에 임시저장
  5. SQLite로 처리된 상품 추적 (중복 방지)

사용:
    python3 naver_connect_bot.py

상품 추가:
    naver_connect_products.json 파일에 아래 형식으로 추가
    [
      {"name": "상품명", "link": "https://naver.me/XXXXX", "category": "주방/생활"},
      ...
    ]
"""
import sys, os, re, json, time, random, sqlite3, urllib.request
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

BLOG_ID = "salim1su"
DB_PATH = Path(__file__).parent / "keyword_engine" / "engine.db"
IMAGES_DIR = Path(__file__).parent / "images"
IMAGES_DIR.mkdir(exist_ok=True)

PRODUCTS_FILE = Path(__file__).parent / "naver_connect_products.json"
LOG_FILE = Path(__file__).parent / "logs" / "naver_connect_bot.log"
LOG_FILE.parent.mkdir(exist_ok=True)

# 각도 정의 (me1091_bot.py 동일 구조)
PRODUCT_ANGLES = [
    (
        "가격분석",
        "네이버 최저가 직접 비교해본 후기",
        "이 글의 포커스: 네이버 쇼핑에서 이 상품이 왜 가격 대비 좋은지.\n"
        "인트로: '비슷한 거 찾다가 이걸로 결정했어요'처럼 비교 경험으로 시작.\n"
        "가격 앵커링: 정가 vs 현재가 차이를 명확히 보여줘.\n"
        "결론: 어디서 사는 게 이득인지 정리."
    ),
    (
        "솔직후기",
        "직접 써본 솔직한 장단점",
        "이 글의 포커스: 좋은 점 위주지만 아쉬운 점 1가지 솔직하게 언급.\n"
        "공감 인트로: '좋은 것만 쓰는 리뷰는 믿기 어렵잖아요'.\n"
        "장점 3가지 구체적 사용 경험, 단점 1가지 부드럽게.\n"
        "결론: '이 가격에 이 품질이면 괜찮다'는 합리화로 구매 유도."
    ),
    (
        "추천대상",
        "이런 분들께 딱 맞는 제품",
        "이 글의 포커스: 어떤 사람에게 이 제품이 맞는지.\n"
        "'자취하는 분', '선물용', '가성비 중시' 등 3가지 유형으로 설명.\n"
        "반대로 '이런 분께는 안 맞을 수도'를 1가지 솔직하게.\n"
        "맺음말: '내 상황에 맞는지 확인해보세요 + 링크' CTA."
    ),
    (
        "사용법",
        "처음 쓸 때 이것만 알면 됩니다",
        "이 글의 포커스: 처음 쓸 때 헷갈렸던 것, 알고 나서 편해진 점.\n"
        "단계별 또는 꿀팁 위주로 실사용 경험처럼 자연스럽게.\n"
        "맺음말: '이거 알고 쓰면 훨씬 다르더라'로 구매 후 만족감 강조."
    ),
    (
        "비교",
        "비슷한 제품이랑 비교해봤어요",
        "이 글의 포커스: 경쟁 제품과 비교.\n"
        "'어떤 걸 살까 고민하다가 이걸로 결정'이라는 선택 스토리로 시작.\n"
        "비교표 또는 항목별 비교로 시각화.\n"
        "결론: 이 제품을 선택한 이유 명확하게."
    ),
    (
        "재구매",
        "재구매할 정도로 만족했어요",
        "이 글의 포커스: 재구매 경험 기반 신뢰 구축.\n"
        "'처음엔 반신반의했는데 재구매까지 했어요'로 시작.\n"
        "왜 재구매했는지 구체적 이유 3가지.\n"
        "맺음말: '이미 검증된 제품이니 믿고 써보세요' 강한 추천."
    ),
]

_log_lines = []
def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _log_lines.append(line)


# ── DB ──────────────────────────────────────────────────────────────────────
def _db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS naver_connect_written (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            angle        TEXT NOT NULL,
            affiliate_url TEXT,
            blog_url     TEXT,
            written_at   TEXT,
            UNIQUE(product_name, angle)
        )
    """)
    conn.commit()
    return conn


def get_next_angle(product_name: str) -> tuple:
    """처리 안 된 각도 반환. 모두 처리됐으면 가장 오래된 각도."""
    used = []
    with _db_conn() as c:
        rows = c.execute(
            "SELECT angle, written_at FROM naver_connect_written WHERE product_name=? ORDER BY written_at",
            (product_name,)
        ).fetchall()
        used = [r[0] for r in rows]

    all_angles = [a[0] for a in PRODUCT_ANGLES]
    unused = [a for a in all_angles if a not in used]
    if unused:
        angle_id = unused[0]
    else:
        angle_id = used[0] if used else all_angles[0]

    angle = next(a for a in PRODUCT_ANGLES if a[0] == angle_id)
    return angle  # (angle_id, title_hint, instruction)


def mark_done(product_name: str, affiliate_url: str, angle: str = "", blog_url: str = ""):
    with _db_conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO naver_connect_written
              (product_name, angle, affiliate_url, blog_url, written_at)
            VALUES (?, ?, ?, ?, ?)
        """, (product_name, angle, affiliate_url, blog_url, datetime.now().isoformat()))
        c.commit()


# ── 상품 목록 로드 ────────────────────────────────────────────────────────────
def load_products() -> list:
    """naver_connect_products.json에서 상품 목록 읽기."""
    if not PRODUCTS_FILE.exists():
        # 예시 파일 생성
        example = [
            {
                "name": "예시 상품명 (여기에 실제 상품명 입력)",
                "link": "https://naver.me/XXXXXXXX",
                "category": "주방/생활"
            }
        ]
        PRODUCTS_FILE.write_text(json.dumps(example, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"[상품목록] {PRODUCTS_FILE} 예시 파일 생성됨 — 실제 상품 추가 후 다시 실행")
        return []

    try:
        products = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
        # 예시 행 제거
        products = [p for p in products if "(예시)" not in p.get("name", "") and "XXXXXXXX" not in p.get("link", "")]
        log(f"[상품목록] {len(products)}개 상품 로드")
        return products
    except Exception as e:
        log(f"[상품목록] 로드 실패: {e}")
        return []


# ── 네이버 쇼핑 상품 정보 수집 ────────────────────────────────────────────────
def scrape_naver_product(page, affiliate_url: str) -> dict:
    """naver.me 링크 → 네이버 쇼핑 상품 페이지 → 상품 정보 추출."""
    log(f"[크롤링] {affiliate_url[:60]}")

    # naver.me 리다이렉트 따라가기
    page.goto(affiliate_url, wait_until="domcontentloaded", timeout=20000)
    time.sleep(3)

    final_url = page.url
    log(f"[크롤링] 리다이렉트 → {final_url[:80]}")

    # 상품명
    title = page.evaluate("""() => {
        const selectors = [
            'h3.product_title', '.prd_main_title h1', 'h1.ProductTitle_title',
            'meta[property="og:title"]', '.title_area h1', '.product-title h2',
            'h3._3EB55uWEa6', '.css-1w5vtgs'
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const val = el.content || el.innerText || el.textContent;
                if (val && val.trim().length > 2) return val.trim().replace(/\\s+/g, ' ');
            }
        }
        return document.title.split('|')[0].split(':')[0].trim();
    }""") or ""

    # 가격
    price = page.evaluate("""() => {
        const selectors = [
            '.price_num', '.sale_price', '.price strong', 'strong.price_num',
            '[class*="price"] strong', '[class*="Price"] strong',
            '.css-12jlmiv', '.price_area strong'
        ];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const txt = (el.innerText || el.textContent || '').replace(/[^\\d,]/g, '');
                if (txt && txt.length > 2) return txt + '원';
            }
        }
        return '';
    }""") or ""

    # 원가
    original_price = page.evaluate("""() => {
        const selectors = ['.origin_price', '.original_price', 'del', '.price_before'];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const txt = (el.innerText || el.textContent || '').replace(/[^\\d,]/g, '');
                if (txt && txt.length > 2) return txt + '원';
            }
        }
        return '';
    }""") or price

    # 할인율
    discount = page.evaluate("""() => {
        const selectors = ['.discount_rate', '.sale_rate', '.percent', '[class*="discount"]'];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt && txt.includes('%')) return txt;
            }
        }
        return '';
    }""") or ""

    # 평점
    rating = page.evaluate("""() => {
        const selectors = ['.star_score', '.rating_num', '.grade_num', '[class*="rating"]'];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const txt = (el.innerText || el.textContent || '').trim();
                if (txt && /[\\d.]+/.test(txt)) return txt.match(/[\\d.]+/)[0];
            }
        }
        return '';
    }""") or ""

    # 리뷰수
    review_count = page.evaluate("""() => {
        const selectors = ['.review_count', '.review_num', '[class*="review"] span', '[class*="Review"] span'];
        for (const sel of selectors) {
            const el = document.querySelector(sel);
            if (el) {
                const txt = (el.innerText || el.textContent || '').replace(/[^\\d,]/g, '');
                if (txt) return txt;
            }
        }
        return '';
    }""") or ""

    # 리뷰 텍스트
    reviews = page.evaluate("""() => {
        const selectors = [
            '.reviewItems .text', '.review_text', '[class*="reviewBody"]',
            '.review_cont', '.reviewArticle'
        ];
        const results = [];
        for (const sel of selectors) {
            for (const el of document.querySelectorAll(sel)) {
                const txt = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ');
                if (txt.length > 20 && txt.length < 300 && !results.includes(txt)) {
                    results.push(txt);
                    if (results.length >= 3) break;
                }
            }
            if (results.length >= 3) break;
        }
        return results;
    }""") or []

    # 이미지
    images = page.evaluate("""() => {
        const imgs = [];
        const selectors = [
            '.product_img img', '.image_area img', '.prd_img img',
            'img[class*="product"]', 'img[class*="main"]'
        ];
        for (const sel of selectors) {
            for (const img of document.querySelectorAll(sel)) {
                const src = img.src || img.getAttribute('data-src') || '';
                if (src && src.startsWith('http') && !imgs.includes(src)) {
                    imgs.push(src);
                    if (imgs.length >= 5) break;
                }
            }
            if (imgs.length >= 3) break;
        }
        return imgs;
    }""") or []

    # og:image 폴백
    if not images:
        og_img = page.evaluate("""() => {
            const m = document.querySelector('meta[property="og:image"]');
            return m ? m.content : '';
        }""")
        if og_img:
            images = [og_img]

    result = {
        "title": title,
        "price": price,
        "original_price": original_price,
        "discount": discount,
        "rating": rating,
        "review_count": review_count,
        "reviews": reviews,
        "images": images,
        "final_url": final_url,
    }
    log(f"[크롤링] 상품명: {title[:40]} | 가격: {price} | 평점: {rating} | 이미지: {len(images)}장")
    return result


# ── 글 생성 ─────────────────────────────────────────────────────────────────
def generate_review_post(product: dict, info: dict, angle_id: str, angle_hint: str, angle_instruction: str) -> tuple:
    """네이버 브랜드커넥트 상품 리뷰 글 생성. (title, content, tags) 반환."""
    from claude_playwright import generate_text

    name = product["name"]
    affiliate_url = product["link"]
    category = product.get("category", "생활용품")

    price_str = info.get("price", "")
    orig_str  = info.get("original_price", "")
    discount  = info.get("discount", "")
    rating    = info.get("rating", "")
    reviews   = info.get("reviews", [])
    review_text = "\n".join(f"- {r}" for r in reviews[:3]) if reviews else ""

    extra = f"""[상품 정보 — 네이버 브랜드커넥트 제휴]
상품명: {name}
카테고리: {category}
판매가: {price_str}
원가: {orig_str}
할인율: {discount}
평점: {rating}
실제 구매자 리뷰:
{review_text if review_text else '(리뷰 정보 없음)'}

제휴 링크: {affiliate_url}

[이번 글 각도]
각도: {angle_hint}
{angle_instruction}

[링크 삽입 — 필수 2회]
1회차: 첫 소제목 아래
  👉 <a href="{affiliate_url}" target="_blank" style="color:#03c75a;font-weight:bold;">{name[:20]} 네이버 최저가 확인하기</a>
2회차: 맺음말 직전
  👉 <a href="{affiliate_url}" target="_blank" style="color:#e74c3c;font-weight:bold;">지금 바로 구매하러 가기 →</a>

[수수료 고지 — 최상단 필수]
「이 글에는 네이버 브랜드커넥트 제휴 링크가 포함되어 있으며, 구매 시 소정의 수수료를 받을 수 있습니다.」

[출력 형식]
===제목===
(30~45자. '{category}' 또는 관련 키워드 포함. 검색 의도를 반영한 제목.
 예) '{name[:15]} 솔직 후기 가격까지 비교해봤어요'
 예) '{name[:15]} 써본 사람이 알려주는 꿀팁')
===제목끝===

===본문===
(1800자 이상. 살림/생활 블로그 독자에게 친근하게. 모바일 가독성 위해 짧은 문단.)
===본문끝===

===태그===
(10개, 쉼표 구분. 상품 카테고리 + 실제 검색어 기반.)
===태그끝===
"""

    log(f"[글생성] '{name[:30]}' — 각도: {angle_id}")
    raw = generate_text("", blog_id=BLOG_ID, keyword=name, on_log=log, extra_context=extra)
    if not raw or "추출 실패" in raw:
        log("[글생성] 실패")
        return None, None, []

    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m  = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===",  raw, re.DOTALL)
    tag_m   = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===",  raw, re.DOTALL)

    title   = title_m.group(1).strip().split("\n")[0].strip() if title_m else f"{name} 후기"
    content = body_m.group(1).strip() if body_m else raw
    tags    = [t.strip() for t in tag_m.group(1).strip().split(",") if t.strip()] if tag_m else []

    log(f"[글생성] 제목: {title} | {len(content)}자")
    return title, content, tags


# ── 메인 ────────────────────────────────────────────────────────────────────
def run_one_product():
    """미처리 상품 1개 처리."""
    products = load_products()
    if not products:
        log("[봇] 처리할 상품 없음 — naver_connect_products.json 확인")
        return False

    # 각도 미완료 상품 선택
    target = None
    angle_info = None
    for p in products:
        angle = get_next_angle(p["name"])
        with _db_conn() as c:
            done_count = c.execute(
                "SELECT COUNT(*) FROM naver_connect_written WHERE product_name=? AND angle=?",
                (p["name"], angle[0])
            ).fetchone()[0]
        if done_count == 0:
            target = p
            angle_info = angle
            break

    if not target:
        log("[봇] 모든 상품의 모든 각도 완료")
        return False

    name = target["name"]
    affiliate_url = target["link"]
    angle_id, angle_hint, angle_instruction = angle_info

    log(f"\n{'='*50}")
    log(f"[봇] 처리: {name[:40]} | 각도: {angle_id}")
    log(f"[봇] 제휴링크: {affiliate_url}")

    from browser import connect_cdp, get_or_create_page

    pw, browser = connect_cdp(on_log=log)
    info = {}

    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = get_or_create_page(ctx if hasattr(ctx, 'new_page') else browser, navigate_to=affiliate_url)

        # 1. 상품 정보 크롤링
        info = scrape_naver_product(page, affiliate_url)
        page.close()

    except Exception as e:
        log(f"[봇] 크롤링 오류: {e}")
    finally:
        pw.stop()

    if not info.get("title"):
        log("[봇] 상품 정보 추출 실패")
        return False

    # 2. 글 생성 (Playwright 세션 닫힌 후)
    title, content, tags = generate_review_post(target, info, angle_id, angle_hint, angle_instruction)
    if not title or not content:
        return False

    # 3. 이미지 생성 + 임시저장
    try:
        from poster import post_single
        from image_router import generate_images_for_blog

        image_infos = [
            {"prompt": f"{name} 생활용품 실사용 모습 깔끔한 인테리어", "alt": name, "index": i}
            for i in range(1, 4)
        ]
        image_paths, image_infos_out = generate_images_for_blog(
            blog_id=BLOG_ID,
            image_infos=image_infos,
            skip_webp=True,
            on_log=log,
            title=name,
        )

        ok = post_single(
            blog_id=BLOG_ID,
            title=title,
            content=content,
            tags=tags,
            image_paths=image_paths,
            image_infos=image_infos_out,
            keyword=name,
            on_log=log,
        )

        if ok:
            mark_done(name, affiliate_url, angle_id)
            log(f"[봇] ✅ 임시저장 완료: {title}")
            try:
                from notify import send_telegram
                send_telegram(
                    f"✅ 네이버커넥트 글 생성\n"
                    f"블로그: {BLOG_ID}\n"
                    f"제목: {title}\n"
                    f"각도: {angle_id}"
                )
            except Exception:
                pass
            return True

    except Exception as e:
        log(f"[봇] 포스팅 오류: {e}")
        import traceback; traceback.print_exc()

    return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1, help="처리할 상품 수 (기본 1)")
    args = parser.parse_args()

    success = 0
    for i in range(args.count):
        log(f"\n[봇] {i+1}/{args.count} 처리 중...")
        ok = run_one_product()
        if ok:
            success += 1
            if i < args.count - 1:
                log("[봇] 4시간 대기 후 다음 상품...")
                time.sleep(4 * 3600)
        else:
            log("[봇] 처리 실패 또는 더 이상 처리할 상품 없음")
            break

    log(f"\n[봇] 완료: {success}/{args.count}개 성공")
