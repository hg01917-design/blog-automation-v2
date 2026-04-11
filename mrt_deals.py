"""MRT 파트너 블로그 모니터링 → 프로모션 자동 감지 → triplog 글 생성

흐름:
  1. 마이리얼트립 마케팅 파트너 블로그 최신 글 수집
  2. 새 프로모션(진에어 특가, 숙세페 등) 감지
  3. 이미 작성한 딜은 DB로 중복 방지
  4. 새 딜 → Claude로 긴급성 높은 triplog 글 생성 → 임시저장
"""
import os, re, sys, time, sqlite3, json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

PARTNER_BLOG_URL = "https://blog.naver.com/myrealtrip_mpartner"
PARTNER_BLOG_CATEGORY = "챌린지/이벤트"
BLOG_ID = "triplog"
DB_PATH = Path(__file__).parent / "keyword_engine" / "engine.db"

LOG_FILE = Path(__file__).parent / "logs" / "mrt_deals.log"
LOG_FILE.parent.mkdir(exist_ok=True)

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)


# ── DB ──────────────────────────────────────────────────────────────────────

def _db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mrt_deals_written (
            deal_id      TEXT PRIMARY KEY,  -- 프로모션 URL 해시 or 고유ID
            deal_title   TEXT,
            deal_url     TEXT,
            blog_post_title TEXT,
            written_at   TEXT
        )
    """)
    conn.commit()
    return conn


def is_deal_written(deal_id: str) -> bool:
    with _db_conn() as c:
        return c.execute(
            "SELECT 1 FROM mrt_deals_written WHERE deal_id=?", (deal_id,)
        ).fetchone() is not None


def mark_deal_written(deal_id: str, deal_title: str, deal_url: str, post_title: str):
    with _db_conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO mrt_deals_written(deal_id, deal_title, deal_url, blog_post_title, written_at)
            VALUES (?, ?, ?, ?, ?)
        """, (deal_id, deal_title, deal_url, post_title, datetime.now().isoformat()))
        c.commit()


# ── 파트너 블로그 스크래핑 ───────────────────────────────────────────────────

def fetch_partner_blog_posts(page, max_posts: int = 5) -> list[dict]:
    """MRT 파트너 블로그 RSS에서 최신 게시글 목록 수집."""
    rss_url = f"{PARTNER_BLOG_URL}?blogId=myrealtrip_mpartner&categoryNo=0&currentPage=1&viewdate=&countPerPage=10"
    # 네이버 블로그 RSS 피드 사용
    rss_feed = "https://rss.blog.naver.com/myrealtrip_mpartner.xml"
    log(f"[딜모니터] RSS 스캔: {rss_feed}")

    posts = []
    try:
        import urllib.request
        req = urllib.request.Request(rss_feed, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read().decode("utf-8", errors="ignore")

        # item 단위 파싱 (CDATA 형식)
        items_raw = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
        for item in items_raw:
            title_m = re.search(r'<title><!\[CDATA\[(.*?)\]\]>', item)
            link_m  = re.search(r'<guid>(https://blog\.naver\.com/[^\s<]+)</guid>', item)
            if not title_m or not link_m:
                continue
            title = title_m.group(1).strip()
            link  = re.sub(r'\?fromRss.*', '', link_m.group(1).strip())
            # 프로모션/이벤트 관련 글만 필터
            if any(kw in title for kw in ["특가", "할인", "이벤트", "프로모션", "세일", "LIVE", "라이브"]):
                posts.append({"title": title, "url": link})
                if len(posts) >= max_posts:
                    break

        # RSS에 없는 최신 공지글 보완: 파트너 블로그 직접 스캔
        if len(posts) < max_posts:
            page.goto(PARTNER_BLOG_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(4)
            for frame in page.frames:
                try:
                    items_pw = frame.evaluate("""() => {
                        const seen = new Set();
                        const result = [];
                        for (const a of document.querySelectorAll('a[href]')) {
                            const href = a.href || '';
                            if (!href.includes('myrealtrip_mpartner') || !/\\/\\d{9,}/.test(href)) continue;
                            if (seen.has(href)) continue;
                            seen.add(href);
                            const title = (a.innerText || a.title || '').trim().replace(/\\s+/g,' ');
                            if (title.length < 5) continue;
                            result.push({title, url: href});
                            if (result.length >= 10) break;
                        }
                        return result;
                    }""")
                    for p in (items_pw or []):
                        if p["url"] not in [x["url"] for x in posts]:
                            posts.append(p)
                        if len(posts) >= max_posts:
                            break
                    if posts:
                        break
                except:
                    pass
    except Exception as e:
        log(f"[딜모니터] RSS 실패: {e} — Playwright 폴백")
        # 폴백: Playwright로 특정 게시글 직접 접근
        page.goto(PARTNER_BLOG_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        for frame in page.frames:
            try:
                items = frame.evaluate("""() => {
                    const seen = new Set();
                    const result = [];
                    for (const a of document.querySelectorAll('a[href]')) {
                        const href = a.href || '';
                        if (!href.includes('naver.com') || !/\\/\\d{9,}/.test(href)) continue;
                        if (seen.has(href)) continue;
                        seen.add(href);
                        const title = (a.innerText || a.title || '').trim().replace(/\\s+/g,' ');
                        if (title.length < 5) continue;
                        result.push({title, url: href});
                        if (result.length >= 10) break;
                    }
                    return result;
                }""")
                if items and len(items) > 0:
                    posts = items[:max_posts]
                    break
            except:
                pass

    log(f"[딜모니터] 게시글 {len(posts)}개 발견")
    return posts


def extract_deals_from_post(page, post_url: str) -> list[dict]:
    """블로그 게시글에서 프로모션 URL과 정보 추출."""
    page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    deals = []
    for frame in page.frames:
        try:
            text = frame.evaluate("() => document.body.innerText")
            if len(text) < 200:
                continue

            # MRT 프로모션 URL 패턴 추출
            promo_urls = re.findall(
                r'https://(?:www\.|accommodation\.)?myrealtrip\.com/promotions/[\w_-]+',
                text
            )
            # 상품 URL도 추출
            offer_urls = re.findall(
                r'https://(?:www\.|experiences\.)?myrealtrip\.com/offers/\d+',
                text
            )

            all_urls = list(dict.fromkeys(promo_urls + offer_urls))  # 순서 유지 중복제거

            for url in all_urls:
                # 프로모션 이름 추출 (URL 앞 문맥)
                idx = text.find(url)
                context = text[max(0, idx-200):idx+100].strip()

                # 만료일/기간 탐지
                expires = ""
                for pat in [r'\d+월\s*\d+일까지', r'\d+/\d+까지', r'~\d+\.\d+']:
                    m = re.search(pat, context)
                    if m:
                        expires = m.group()
                        break

                # 할인율 탐지
                discount = ""
                m = re.search(r'최대\s*\d+%|[\d]+%\s*할인', context)
                if m:
                    discount = m.group()

                deals.append({
                    "url": url,
                    "context": context[:300],
                    "expires": expires,
                    "discount": discount,
                    "source_post": post_url,
                })
            break
        except:
            pass

    log(f"[딜모니터] '{post_url[:60]}' → 딜 {len(deals)}개 추출")
    return deals


# ── 제휴 링크 생성 ───────────────────────────────────────────────────────────

def _get_affiliate_link_for_promo(promo_url: str) -> str:
    """프로모션 URL → MRT API로 제휴 링크 생성."""
    from mrt_affiliate import create_affiliate_link
    result = create_affiliate_link(promo_url, on_log=log)
    return result if result else promo_url


# ── 글 생성 ─────────────────────────────────────────────────────────────────

def generate_deal_post(deal: dict, affiliate_url: str) -> tuple:
    """딜 정보로 triplog 블로그 글 생성. (title, content, tags) 반환."""
    from claude_playwright import generate_text

    promo_url = deal["url"]
    context = deal.get("context", "")
    expires = deal.get("expires", "")
    discount = deal.get("discount", "")

    # 프로모션 유형 판단
    is_flight = any(w in context for w in ["항공", "진에어", "아시아나", "제주항공", "에어", "flight"])
    is_hotel = any(w in context for w in ["숙박", "호텔", "리조트", "호캉스", "숙세페"])
    is_live = any(w in context for w in ["LIVE", "라이브", "live"])

    # 만료 긴급도
    urgency_str = ""
    if expires:
        urgency_str = f"마감: {expires}"
    if is_live:
        urgency_str = "라이브 오픈 — 한정 시간 특가"

    promo_type = "항공 특가" if is_flight else "숙박 특가" if is_hotel else "여행 특가"

    extra = f"""[프로모션 정보]
유형: {promo_type}
컨텍스트: {context}
긴급도: {urgency_str}
할인율: {discount}
제휴 링크: {affiliate_url}

[이번 글 작성 지시]
이 프로모션을 발견한 여행 블로거가 팔로워에게 긴급 공유하는 톤으로 작성해.
도입부: "이거 지금 당장 봐야 해요" 류의 강한 후킹으로 시작.
중간: 이 딜이 왜 좋은지 (가격, 기간 한정, 희소성) 구체적으로 설명.
{'항공권은 단가가 높아서 마이리얼트립에서 한 건만 예약해도 수십만원대라는 점 자연스럽게 언급.' if is_flight else ''}
{'라이브 오픈이므로 "예약 알림 신청해두세요", "오픈되면 바로 들어가야 해요" 긴급성 강조.' if is_live else ''}
맺음말 직전: 제휴 링크 CTA — "지금 바로 확인하러 가기" 버튼 형식으로.

[링크 삽입 — 필수 2회]
1회차: 첫 소제목 아래
  👉 <a href="{affiliate_url}" target="_blank" style="color:#1a73e8;font-weight:bold;">지금 {promo_type} 확인하기</a>
2회차: 맺음말 직전
  👉 <a href="{affiliate_url}" target="_blank" style="color:#e74c3c;font-weight:bold;">마감 전에 예약하러 가기 →</a>

[수수료 고지 — 최상단 필수]
「이 글에는 마이리얼트립 파트너스 제휴 링크가 포함되어 있으며, 예약 시 소정의 수수료를 받을 수 있습니다.」

[출력 형식]
===제목===
(30~45자. '{promo_type}' 키워드 포함. 긴급성/혜택이 느껴지는 제목.
 예) '진에어 단독특가 4월13일 오픈 마이리얼트립 예약 방법'
 예) '숙박세일페스타 최대88% 호텔 특가 쿠폰 받는 법')
===제목끝===

===본문===
(2000자 이상. 긴급성 높은 여행 딜 소개글.)
===본문끝===

===태그===
{promo_type}, 마이리얼트립, 여행특가, 항공특가, 여행할인, 특가항공권, 숙박할인, 호텔특가, 여행꿀팁, 제휴여행
===태그끝===
"""

    log(f"[딜] Claude 글 생성 시작: {promo_type}")
    raw = generate_text("", blog_id=BLOG_ID, keyword=promo_type, on_log=log, extra_context=extra)
    if not raw or "추출 실패" in raw:
        log("[딜] 글 생성 실패")
        return None, None, []

    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m  = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===",  raw, re.DOTALL)
    tag_m   = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===",  raw, re.DOTALL)

    title   = title_m.group(1).strip().split("\n")[0].strip() if title_m else promo_type
    content = body_m.group(1).strip() if body_m else raw
    tags    = [t.strip() for t in tag_m.group(1).strip().split(",") if t.strip()] if tag_m else []

    log(f"[딜] 제목: {title} | {len(content)}자")
    return title, content, tags


# ── 메인 ────────────────────────────────────────────────────────────────────

def run_deal_check(dry_run: bool = False) -> int:
    """파트너 블로그 모니터링 → 새 딜 발견 시 triplog 글 생성. 생성 건수 반환."""
    from browser import connect_cdp

    pw, browser = connect_cdp(on_log=log)
    written_count = 0

    try:
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()

        # 1. 파트너 블로그 최신 게시글 수집
        posts = fetch_partner_blog_posts(page, max_posts=3)
        if not posts:
            log("[딜모니터] 게시글 없음")
            page.close()
            return 0

        # 2. 각 게시글에서 딜 추출
        all_deals = []
        for post in posts:
            deals = extract_deals_from_post(page, post["url"])
            for d in deals:
                d["post_title"] = post["title"]
            all_deals.extend(deals)

        log(f"[딜모니터] 총 딜 {len(all_deals)}개 발견")

        # 3. 새 딜만 처리
        new_deals = []
        for deal in all_deals:
            deal_id = re.sub(r'[^a-zA-Z0-9_-]', '', deal["url"].split("/")[-1]) or deal["url"][-20:]
            if is_deal_written(deal_id):
                log(f"[딜] 이미 작성됨: {deal_id}")
                continue
            deal["deal_id"] = deal_id
            new_deals.append(deal)

        log(f"[딜모니터] 새 딜 {len(new_deals)}개")

        for deal in new_deals[:2]:  # 한 번에 최대 2개
            # 4. 제휴 링크 생성
            affiliate_url = _get_affiliate_link_for_promo(page, deal["url"])

            # 5. 글 생성
            title, content, tags = generate_deal_post(deal, affiliate_url)
            if not title or not content:
                continue

            deal_id = deal["deal_id"]

            if dry_run:
                log(f"[DRY RUN] 생성 완료: {title}")
                mark_deal_written(deal_id, deal.get("post_title", ""), deal["url"], title)
                written_count += 1
                continue

            # 6. triplog 임시저장
            try:
                from poster import post_single
                from image_router import generate_images_for_blog

                # 이미지 생성
                promo_type = "항공 특가" if any(w in deal.get("context","") for w in ["항공","진에어","항공권"]) else "여행 특가"
                image_infos = [
                    {"prompt": f"travel deal promotion flight hotel discount vibrant colorful poster style", "alt": f"{promo_type} 마이리얼트립", "index": i}
                    for i in range(1, 4)
                ]
                image_paths, image_infos_out = generate_images_for_blog(
                    blog_id=BLOG_ID, keyword=promo_type,
                    image_infos=image_infos, skip_webp=False, on_log=log
                )

                ok = post_single(
                    blog_id=BLOG_ID,
                    title=title,
                    content=content,
                    tags=tags,
                    image_paths=image_paths,
                    image_infos=image_infos_out,
                    keyword=promo_type,
                    on_log=log,
                )
                if ok:
                    mark_deal_written(deal_id, deal.get("post_title", ""), deal["url"], title)
                    written_count += 1
                    log(f"[딜] ✅ 임시저장 완료: {title}")

                    try:
                        from notify import send_telegram
                        send_telegram(
                            f"🔥 MRT 딜 글 생성\n블로그: triplog\n제목: {title}\n딜: {deal['url']}"
                        )
                    except Exception:
                        pass
            except Exception as e:
                log(f"[딜] 포스팅 오류: {e}")

        page.close()

    except Exception as e:
        log(f"[딜모니터] 오류: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pw.stop()

    log(f"[딜모니터] 완료 — {written_count}개 글 생성")
    return written_count


KNOWN_DEALS = [
    {
        "deal_id": "flight_live_LJ_onstyle_2604",
        "url": "https://www.myrealtrip.com/promotions/flight_live_LJ_onstyle_2604",
        "context": "진에어 단독 특가 4월 13일 저녁 8시 LIVE OPEN. 항공권 단가 높은 카테고리. 마이리얼트립 국제선 항공권 예약당 평균 수십만원대.",
        "expires": "4월 13일 라이브",
        "discount": "",
        "post_title": "진에어 단독특가 & LIVE",
    },
    {
        "deal_id": "accommodation_salefesta_spring2604",
        "url": "https://accommodation.myrealtrip.com/union/events/salefesta",
        "context": "숙박세일페스타 봄편 4월 8일부터 4월 30일까지. 국내외 호텔·리조트 최대 88% 할인. 한정 수량 할인쿠폰 선착순 소진.",
        "expires": "4월 30일까지",
        "discount": "최대 88% 할인",
        "post_title": "숙박세일페스타 봄편",
    },
    {
        "deal_id": "hocance_ep155_gangneung_shilla",
        "url": "https://www.myrealtrip.com/promotions/hocance_ep155",
        "context": "강릉 신라 모노그램 10만원대 단독 특가. 오션뷰 호텔. 숙세페 쿠폰 3만원 추가 적용.",
        "expires": "4월 30일까지",
        "discount": "숙세페 쿠폰 3만원 추가",
        "post_title": "강릉 신라모노그램 10만원대 특가",
    },
]


def _collect_affiliate_links(deals: list) -> dict:
    """API로 모든 딜의 제휴 링크를 수집. {deal_id: affiliate_url}"""
    result = {}
    for deal in deals:
        aff = _get_affiliate_link_for_promo(deal["url"])
        result[deal["deal_id"]] = aff
        log(f"[딜] {deal['deal_id']} → {aff}")
    return result


def run_known_deals(dry_run: bool = False) -> int:
    """미리 알고 있는 딜 목록으로 직접 글 생성 (파트너 블로그 스캔 없이).
    Playwright 충돌 방지: 제휴링크 수집 → pw.stop() → Claude 글생성 → 임시저장 순서로 실행.
    """
    # 처리할 딜만 필터
    pending = [d for d in KNOWN_DEALS if not is_deal_written(d["deal_id"])]
    if not pending:
        log("[딜] 처리할 새 딜 없음")
        return 0

    # Step 1: 제휴 링크 수집 (Playwright 세션 완전히 닫힌 후 종료)
    log(f"[딜] 제휴 링크 수집: {len(pending)}개")
    aff_map = _collect_affiliate_links(pending)

    # Step 2: Claude 글 생성 + 임시저장 (별도 Playwright 세션)
    written_count = 0
    for deal in pending:
        deal_id = deal["deal_id"]
        affiliate_url = aff_map.get(deal_id, deal["url"])
        log(f"\n[딜] 처리: {deal['post_title']} | 제휴링크: {affiliate_url}")

        title, content, tags = generate_deal_post(deal, affiliate_url)
        if not title or not content:
            continue

        if dry_run:
            log(f"[DRY RUN] 제목: {title}")
            mark_deal_written(deal_id, deal["post_title"], deal["url"], title)
            written_count += 1
            continue

        try:
            from poster import post_single
            from image_router import generate_images_for_blog

            is_flight = "항공" in deal["context"] or "진에어" in deal["context"]
            promo_type = "항공 특가" if is_flight else "숙박 특가"
            image_infos = [
                {
                    "prompt": f"{'airplane flight korea travel deal promotion vibrant' if is_flight else 'hotel resort ocean view korea spring discount'}",
                    "alt": f"{promo_type} 마이리얼트립",
                    "index": i,
                }
                for i in range(1, 4)
            ]
            image_paths, image_infos_out = generate_images_for_blog(
                blog_id=BLOG_ID, keyword=promo_type,
                image_infos=image_infos, skip_webp=False, on_log=log
            )
            ok = post_single(
                blog_id=BLOG_ID, title=title, content=content,
                tags=tags, image_paths=image_paths, image_infos=image_infos_out,
                keyword=promo_type, on_log=log,
            )
            if ok:
                mark_deal_written(deal_id, deal["post_title"], deal["url"], title)
                written_count += 1
                log(f"[딜] ✅ 임시저장 완료: {title}")
                try:
                    from notify import send_telegram
                    send_telegram(f"🔥 MRT 딜 글 임시저장\n블로그: triplog\n제목: {title}")
                except Exception:
                    pass
        except Exception as e:
            log(f"[딜] 포스팅 오류: {e}")
            import traceback; traceback.print_exc()

    return written_count


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--known", action="store_true", help="파트너 블로그 스캔 없이 알려진 딜만 처리")
    args = parser.parse_args()
    if args.known:
        run_known_deals(dry_run=args.dry_run)
    else:
        run_deal_check(dry_run=args.dry_run)
