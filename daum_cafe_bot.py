"""
daum_cafe_bot.py
다음카페 자동화 봇
- salim1su 계정(daonna525) 사용
- 카페지기 부재중 + 상위노출 가능한 카페 탐색, 가입, 페르소나 활동
"""

import argparse
import random
import re
import sqlite3
import time
from datetime import datetime, timedelta

from browser import connect_cdp, get_or_create_page
from login_playwright import login_blog

DB_PATH = "keyword_engine/engine.db"
BLOG_ID = "salim1su"

# 다음카페 검색 키워드 (상위노출 가능한 틈새 키워드)
CATEGORIES = {
    "여행": ["국내여행 동호회", "혼자여행 카페", "캠핑 소모임", "제주여행 모임", "부산 여행 카페"],
    "IT/기술": ["노트북 정보 카페", "스마트폰 팁 모임", "IT정보 소모임", "가성비 전자제품"],
    "정부지원금": ["청년지원금 정보", "복지혜택 카페", "생활지원 정보 카페", "정부지원 소식"],
    "살림/가계": ["절약 생활 카페", "주부 생활정보", "살림 노하우 카페", "소비절약 모임"],
    "건강": ["건강정보 카페", "다이어트 소모임", "운동 정보 카페"],
}

COMMENTS = [
    "좋은 정보 감사해요!",
    "저도 가봤는데 좋았어요~",
    "도움이 됐어요 :)",
    "정말 유익한 글이네요!",
    "감사합니다, 잘 읽었어요~",
    "오 이런 정보가 있었군요! 감사해요",
    "좋은 글 공유해주셔서 감사합니다 :)",
    "저도 관심 있었는데 도움이 많이 됐어요!",
    "항상 좋은 정보 올려주셔서 감사해요~",
    "유용한 정보네요, 저장해뒀어요!",
]

PERSONA_POSTS = [
    ("여행 꿀팁 공유해요", "최근에 혼자 여행하면서 알게 된 꿀팁들 공유할게요. 숙소는 미리 예약하는 게 훨씬 저렴하더라고요. 특히 비수기에는 할인이 엄청 많아서 잘 찾아보시면 좋을 것 같아요."),
    ("생활비 절약 노하우", "요즘 물가가 많이 올라서 저도 절약하려고 노력 중이에요. 장볼 때는 꼭 리스트 작성하고 가고, 할인 앱 적극 활용하고 있어요. 여러분들은 어떻게 절약하시나요?"),
    ("유용한 정부지원금 안내", "이번에 알게 된 청년 지원금 정보 공유해드려요. 신청 기간이 정해져 있어서 놓치지 않으시면 좋겠어요. 직접 신청해봤는데 생각보다 간단했습니다."),
    ("오늘의 IT 정보", "최근에 스마트폰 배터리 오래 쓰는 방법을 알았는데요, 화면 밝기 조절이랑 백그라운드 앱 정리만 해도 엄청 달라지더라고요. 참고해보세요!"),
    ("주부들의 살림 노하우", "냉장고 정리할 때 투명 용기 활용하면 재료 파악이 쉬워서 음식물 낭비가 줄어요. 작은 습관 하나가 생활비 절약에 도움이 많이 된답니다."),
]


# ── DB 초기화 ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS daum_cafe_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cafe_id TEXT UNIQUE,
            cafe_name TEXT,
            category TEXT,
            url TEXT,
            joined INTEGER DEFAULT 0,
            joined_at TEXT,
            persona_days INTEGER DEFAULT 0,
            last_activity TEXT,
            member_count INTEGER DEFAULT 0,
            owner_inactive INTEGER DEFAULT 0,
            last_post_days INTEGER DEFAULT 999,
            open_posting INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS daum_cafe_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cafe_id TEXT,
            activity_type TEXT,
            content TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()


def get_conn():
    return sqlite3.connect(DB_PATH)


def log_activity(cafe_id, activity_type, content=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO daum_cafe_activity_log (cafe_id, activity_type, content) VALUES (?, ?, ?)",
        (cafe_id, activity_type, content),
    )
    conn.commit()
    conn.close()


def rand_delay(page, min_sec=1, max_sec=5):
    ms = random.randint(min_sec * 1000, max_sec * 1000)
    page.wait_for_timeout(ms)


# ── 1. 카페 탐색 ──────────────────────────────────────────────────────────────

def find_cafes(on_log=None):
    """다음카페 검색으로 카테고리별 카페 목록 수집 후 DB 저장
    조건: 카페지기 부재중(최근 활동 없음) + 글 상위노출 가능(공개 카페, 적당한 회원수)
    """
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg, flush=True)

    init_db()
    login_blog(BLOG_ID, on_log)
    pw, browser = connect_cdp(on_log)

    try:
        context = browser.contexts[0]
        page = context.new_page()

        for category, keywords in CATEGORIES.items():
            for kw in keywords:
                try:
                    log(f"[탐색] 키워드: {kw} (카테고리: {category})")
                    # 다음 카페 검색
                    search_url = f"https://search.daum.net/search?w=cafe&q={kw}"
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    rand_delay(page, 2, 4)

                    # Step1: 검색 결과에서 카페 URL/이름 수집
                    collected = []
                    seen_ids = set()

                    # 다음 카페 검색 결과 링크 수집
                    links_data = page.evaluate("""() => {
                        const results = [];
                        // 카페 검색 결과 링크
                        const selectors = [
                            'a[href*="cafe.daum.net/"]',
                            'a[href*="m.cafe.daum.net/"]',
                        ];
                        for (const sel of selectors) {
                            const els = document.querySelectorAll(sel);
                            for (const el of els) {
                                const href = el.href || '';
                                const text = el.innerText.trim();
                                if (href) results.push({href, text});
                            }
                        }
                        return results.slice(0, 30);
                    }""")

                    for item in links_data:
                        href = item.get('href', '')
                        text = item.get('text', '')
                        # cafe.daum.net/CAFE_ID 또는 cafe.daum.net/CAFE_ID/...
                        m = re.search(r'cafe\.daum\.net/([^/?#\s]+)', href)
                        if not m:
                            continue
                        cafe_id = m.group(1)
                        # 게시글 링크 제외 (articleview 등)
                        skip = {'articleview', 'ArticleView', 'search', 'SearchPost'}
                        if cafe_id in skip or cafe_id in seen_ids:
                            continue
                        # 다음카페 게시글 ID처럼 보이는 숫자만인 경우 제외
                        if cafe_id.isdigit():
                            continue
                        # 너무 짧은 카페 ID 제외 (t, p 등)
                        if len(cafe_id) <= 2:
                            continue
                        seen_ids.add(cafe_id)
                        # URL 도메인이 포함된 텍스트 제거
                        clean_text = text.split('\n')[0].strip()
                        clean_text = re.sub(r'https?://\S+', '', clean_text).strip()
                        clean_text = re.sub(r'cafe\.daum\.net[^\s]*', '', clean_text).strip()
                        cafe_name = clean_text or cafe_id
                        collected.append((cafe_id, cafe_name))

                    log(f"[탐색] '{kw}' 검색 결과 수집: {len(collected)}개")

                    # Step2: 각 카페 방문하여 조건 확인
                    saved = 0
                    for cafe_id, cafe_name in collected:
                        try:
                            cafe_url = f"https://cafe.daum.net/{cafe_id}"
                            page.goto(cafe_url, wait_until="domcontentloaded", timeout=20000)
                            rand_delay(page, 1, 3)

                            info = page.evaluate("""() => {
                                const bodyText = document.body.innerText || '';
                                const html = document.body.innerHTML || '';

                                // 회원수 파싱
                                let memberCount = 0;
                                const memPatterns = [
                                    /멤버[\\s:]*([\\d,]+)/,
                                    /회원수[\\s:]*([\\d,]+)/,
                                    /([\\d,]+)\\s*명/,
                                ];
                                for (const pat of memPatterns) {
                                    const m = bodyText.match(pat);
                                    if (m) {
                                        memberCount = parseInt(m[1].replace(/,/g, ''));
                                        if (memberCount > 0) break;
                                    }
                                }

                                // 카페 공개 여부 (비공개면 글 상위노출 불가)
                                const isPrivate = bodyText.includes('비공개 카페') ||
                                    bodyText.includes('가입해야') ||
                                    html.includes('private');
                                const openPosting = !isPrivate;

                                // 카페지기 활동 여부 파싱
                                // - 공지 날짜 확인
                                const datePattern = /(\\d{4})\\.(\\d{1,2})\\.(\\d{1,2})/g;
                                const dates = [];
                                let match;
                                while ((match = datePattern.exec(bodyText)) !== null) {
                                    const y = parseInt(match[1]);
                                    const mo = parseInt(match[2]);
                                    const d = parseInt(match[3]);
                                    if (y >= 2020 && y <= 2030) {
                                        dates.push(new Date(y, mo-1, d));
                                    }
                                }
                                let lastPostDays = 999;
                                if (dates.length > 0) {
                                    const latest = new Date(Math.max(...dates));
                                    const now = new Date();
                                    lastPostDays = Math.floor((now - latest) / (1000 * 60 * 60 * 24));
                                }

                                // 카페 이름
                                const nameEl = document.querySelector('.cafe_name, h1.tit_cafe, .tit_cafe, h1');
                                const pageName = nameEl ? nameEl.innerText.trim() : '';

                                // 실명인증 필요 여부
                                const requiresAuth = bodyText.includes('실명인증') || bodyText.includes('본인인증');

                                return {
                                    memberCount,
                                    openPosting,
                                    lastPostDays,
                                    pageName,
                                    requiresAuth
                                };
                            }""")

                            member_count = info.get('memberCount', 0)
                            open_posting = 1 if info.get('openPosting', True) else 0
                            last_post_days = info.get('lastPostDays', 999)
                            page_name = info.get('pageName', '') or cafe_name
                            requires_auth = info.get('requiresAuth', False)

                            # 필터링 조건
                            if requires_auth:
                                log(f"[탐색] {cafe_id} — 실명인증 필요, 스킵")
                                continue
                            if not open_posting:
                                log(f"[탐색] {cafe_id} — 비공개 카페, 스킵")
                                continue
                            if member_count > 100000:
                                log(f"[탐색] {cafe_id} — 회원수 너무 많음({member_count:,}명), 스킵")
                                continue
                            if 0 < member_count < 200:
                                log(f"[탐색] {cafe_id} — 회원수 너무 적음({member_count:,}명), 스킵")
                                continue

                            # 카페지기 부재중 판단: 최근 게시글이 30일 이상 없는 경우
                            owner_inactive = 1 if last_post_days > 30 else 0

                            conn = get_conn()
                            try:
                                conn.execute(
                                    """INSERT OR IGNORE INTO daum_cafe_list
                                       (cafe_id, cafe_name, category, url, member_count,
                                        owner_inactive, last_post_days, open_posting)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (cafe_id, page_name, category, cafe_url, member_count,
                                     owner_inactive, last_post_days, open_posting),
                                )
                                conn.commit()
                                saved += 1
                                inactive_str = "카페지기 부재중 ✓" if owner_inactive else f"최근활동 {last_post_days}일전"
                                log(f"[탐색] 저장: {page_name} ({cafe_id}) | 회원 {member_count:,}명 | {inactive_str}")
                            except Exception:
                                pass
                            finally:
                                conn.close()

                        except Exception as e:
                            log(f"[탐색] {cafe_id} 방문 오류: {e}")
                            continue

                    log(f"[탐색] '{kw}' 결과 {saved}개 저장")
                    rand_delay(page, 2, 4)

                except Exception as e:
                    log(f"[탐색] 오류 ({kw}): {e}")
                    continue

        page.close()
        log("[탐색] 완료")

    except Exception as e:
        log(f"[탐색] 전체 오류: {e}")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


# ── 2. 카페 가입 ──────────────────────────────────────────────────────────────

def join_cafe(cafe_id=None, on_log=None):
    """미가입 다음카페에 가입"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg, flush=True)

    init_db()
    conn = get_conn()
    if cafe_id:
        rows = conn.execute(
            "SELECT cafe_id, cafe_name, url FROM daum_cafe_list WHERE cafe_id=? AND joined=0",
            (cafe_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT cafe_id, cafe_name, url FROM daum_cafe_list WHERE joined=0 LIMIT 10"
        ).fetchall()
    conn.close()

    if not rows:
        log("[가입] 가입할 카페 없음")
        return

    login_blog(BLOG_ID, on_log)
    pw, browser = connect_cdp(on_log)
    try:
        context = browser.contexts[0]
        page = context.new_page()

        for row in rows:
            cid, cname, curl = row
            try:
                log(f"[가입] {cname} ({cid}) 가입 시도...")
                page.goto(curl, wait_until="domcontentloaded", timeout=20000)
                rand_delay(page, 2, 4)

                # 다음카페 로그인 확인 (다음 계정 필요)
                # Kakao/Daum 계정으로 로그인되어 있어야 함
                current_url = page.url
                if "login" in current_url or "auth" in current_url:
                    log(f"[가입] {cid} — 다음 로그인 필요. 현재 URL: {current_url}")
                    continue

                # 가입 버튼 찾기
                join_btn = None
                join_selectors = [
                    'a[href*="join"]',
                    'button:has-text("가입")',
                    'a:has-text("가입하기")',
                    'a:has-text("카페가입")',
                    '.btn_join',
                    '#btnCafeJoin',
                ]
                for sel in join_selectors:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_visible():
                            join_btn = btn
                            break
                    except Exception:
                        continue

                if not join_btn:
                    # 이미 가입된 경우 확인
                    body_text = page.inner_text("body")
                    if "가입된" in body_text or "회원입니다" in body_text:
                        log(f"[가입] {cid} — 이미 가입됨")
                        conn2 = get_conn()
                        conn2.execute(
                            "UPDATE daum_cafe_list SET joined=1, joined_at=datetime('now','localtime') WHERE cafe_id=?",
                            (cid,),
                        )
                        conn2.commit()
                        conn2.close()
                    else:
                        log(f"[가입] {cid} — 가입 버튼 없음")
                    continue

                # 오버레이 제거 후 클릭
                page.evaluate("""() => {
                    const overlays = document.querySelectorAll('[class*="popup"], [class*="modal"], [class*="layer"]');
                    overlays.forEach(el => { try { el.style.display='none'; } catch(e){} });
                }""")
                page.evaluate("el => el.click()", join_btn)
                rand_delay(page, 2, 4)

                # 가입 확인 버튼 처리
                confirm_selectors = [
                    'button:has-text("확인")',
                    'button:has-text("가입")',
                    'input[type="submit"]',
                    '.btn_confirm',
                ]
                for sel in confirm_selectors:
                    try:
                        btn2 = page.query_selector(sel)
                        if btn2 and btn2.is_visible():
                            page.evaluate("el => el.click()", btn2)
                            rand_delay(page, 1, 2)
                            break
                    except Exception:
                        continue

                rand_delay(page, 2, 3)

                # 가입 완료 확인
                body_after = page.inner_text("body")
                if "가입" in body_after or "완료" in body_after or "환영" in body_after:
                    log(f"[가입] {cname} 가입 완료!")
                    conn2 = get_conn()
                    conn2.execute(
                        "UPDATE daum_cafe_list SET joined=1, joined_at=datetime('now','localtime') WHERE cafe_id=?",
                        (cid,),
                    )
                    conn2.commit()
                    conn2.close()
                    log_activity(cid, "join", f"가입 완료")
                else:
                    log(f"[가입] {cid} — 가입 결과 불확실")

                rand_delay(page, 2, 4)

            except Exception as e:
                log(f"[가입] {cid} 오류: {e}")
                continue

        page.close()
        log("[가입] 완료")

    except Exception as e:
        log(f"[가입] 전체 오류: {e}")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


# ── 3. 페르소나 활동 ──────────────────────────────────────────────────────────

def do_persona_activity(on_log=None):
    """가입된 다음카페에서 댓글/좋아요 등 페르소나 활동"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg, flush=True)

    init_db()
    conn = get_conn()
    rows = conn.execute(
        """SELECT cafe_id, cafe_name, url FROM daum_cafe_list
           WHERE joined=1
           ORDER BY last_activity ASC NULLS FIRST
           LIMIT 5"""
    ).fetchall()
    conn.close()

    if not rows:
        log("[페르소나] 가입된 카페 없음")
        return

    login_blog(BLOG_ID, on_log)
    pw, browser = connect_cdp(on_log)
    try:
        context = browser.contexts[0]
        page = context.new_page()

        for row in rows:
            cid, cname, curl = row
            try:
                log(f"[페르소나] {cname} ({cid}) 활동 시작...")
                _do_daum_activity(page, cid, cname, curl, log)
                rand_delay(page, 3, 6)
            except Exception as e:
                log(f"[페르소나] {cid} 오류: {e}")
                continue

        page.close()
        log("[페르소나] 완료")

    except Exception as e:
        log(f"[페르소나] 전체 오류: {e}")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


def _do_daum_activity(page, cafe_id, cafe_name, cafe_url, log):
    """단일 다음카페에서 게시글 댓글 + 좋아요 활동"""
    page.goto(cafe_url, wait_until="domcontentloaded", timeout=20000)
    rand_delay(page, 2, 3)

    # 게시글 링크 찾기
    article_url = None

    # 다음카페 게시글 링크 패턴: cafe.daum.net/CAFE_ID/XXX/123
    links_data = page.evaluate("""() => {
        const links = [];
        const els = document.querySelectorAll('a[href]');
        for (const el of els) {
            const href = el.href || '';
            // 카페 게시글 패턴
            if (/cafe\\.daum\\.net\\/[^/]+\\/[A-Za-z0-9]+\\/\\d+/.test(href)) {
                links.push(href);
            }
        }
        return [...new Set(links)].slice(0, 10);
    }""")

    if links_data:
        article_url = random.choice(links_data)
    else:
        log(f"[페르소나] {cafe_id} — 게시글 링크 없음, 스킵")
        return

    log(f"[페르소나] {cafe_id} 게시글: {article_url}")
    page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
    rand_delay(page, 2, 4)

    activity_done = False

    # 좋아요 시도
    like_selectors = [
        'button[class*="like"]',
        'a[class*="like"]',
        '.btn_like',
        '#likeCnt',
        'button:has-text("공감")',
    ]
    for sel in like_selectors:
        try:
            like_btn = page.query_selector(sel)
            if like_btn and like_btn.is_visible():
                page.evaluate("el => el.click()", like_btn)
                rand_delay(page, 1, 2)
                log(f"[페르소나] {cafe_id} — 좋아요 클릭")
                activity_done = True
                break
        except Exception:
            continue

    # 댓글 시도
    comment_text = random.choice(COMMENTS)
    comment_selectors = [
        'textarea[placeholder*="댓글"]',
        'textarea[name*="comment"]',
        '#replyContent',
        '.txt_comment',
        'textarea',
    ]
    for sel in comment_selectors:
        try:
            textarea = page.query_selector(sel)
            if textarea and textarea.is_visible():
                textarea.click()
                rand_delay(page, 1, 2)
                textarea.fill(comment_text)
                rand_delay(page, 1, 2)

                # 등록 버튼
                submit_selectors = [
                    'button:has-text("등록")',
                    'button[type="submit"]',
                    'input[value="등록"]',
                    '.btn_submit',
                ]
                submitted = False
                for sub_sel in submit_selectors:
                    try:
                        sub_btn = page.query_selector(sub_sel)
                        if sub_btn and sub_btn.is_visible():
                            page.evaluate("el => el.click()", sub_btn)
                            rand_delay(page, 1, 2)
                            log(f"[댓글] {cafe_id} — 댓글 등록: {comment_text[:20]}...")
                            submitted = True
                            activity_done = True
                            break
                    except Exception:
                        continue
                if submitted:
                    break
        except Exception:
            continue

    if activity_done:
        conn = get_conn()
        conn.execute(
            "UPDATE daum_cafe_list SET last_activity=datetime('now','localtime'), persona_days=persona_days+1 WHERE cafe_id=?",
            (cafe_id,),
        )
        conn.commit()
        conn.close()
        log_activity(cafe_id, "comment", comment_text)
    else:
        log(f"[페르소나] {cafe_id} — 활동 실패 (버튼/textarea 없음)")


# ── 4. 블로그 글 공유 ─────────────────────────────────────────────────────────

def share_blog_post(blog_url=None, blog_title=None, blog_excerpt=None, on_log=None):
    """다음카페에 블로그 글 공유 (새 게시글로 등록)"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg, flush=True)

    if not blog_url:
        log("[공유] blog_url 필수")
        return

    init_db()
    conn = get_conn()
    rows = conn.execute(
        """SELECT cafe_id, cafe_name, url FROM daum_cafe_list
           WHERE joined=1 AND open_posting=1
           ORDER BY RANDOM() LIMIT 3"""
    ).fetchall()
    conn.close()

    if not rows:
        log("[공유] 공유할 카페 없음 (가입된 공개 카페 필요)")
        return

    title = blog_title or "좋은 정보 공유해요"
    excerpt = blog_excerpt or ""
    post_content = f"{excerpt}\n\n원문: {blog_url}"

    login_blog(BLOG_ID, on_log)
    pw, browser = connect_cdp(on_log)
    try:
        context = browser.contexts[0]
        page = context.new_page()

        for row in rows:
            cid, cname, curl = row
            try:
                log(f"[공유] {cname} ({cid}) 게시글 작성 시도...")
                # 다음카페 글쓰기 페이지
                write_url = f"https://cafe.daum.net/{cid}/write"
                page.goto(write_url, wait_until="domcontentloaded", timeout=20000)
                rand_delay(page, 2, 4)

                # 제목 입력
                title_sel = 'input[name*="title"], input[placeholder*="제목"], #articleTitle'
                title_input = page.query_selector(title_sel)
                if title_input:
                    title_input.fill(title)
                    rand_delay(page, 1, 2)

                # 내용 입력 (iframe editor 또는 textarea)
                editor_frame = None
                for frame in page.frames:
                    if "cafe" in frame.url and frame != page.main_frame:
                        editor_frame = frame
                        break

                content_filled = False
                if editor_frame:
                    try:
                        editor_frame.evaluate(f"""() => {{
                            const body = document.body || document.querySelector('[contenteditable]');
                            if (body) body.innerText = {repr(post_content)};
                        }}""")
                        content_filled = True
                    except Exception:
                        pass

                if not content_filled:
                    content_sel = 'textarea[name*="content"], #articleContent, [contenteditable="true"]'
                    content_el = page.query_selector(content_sel)
                    if content_el:
                        content_el.fill(post_content)
                        content_filled = True

                if not content_filled:
                    log(f"[공유] {cid} — 내용 입력 실패")
                    continue

                rand_delay(page, 1, 2)

                # 등록 버튼
                submit_btn = None
                for sel in ['button:has-text("등록")', 'button:has-text("작성")', 'input[value="등록"]']:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_visible():
                            submit_btn = btn
                            break
                    except Exception:
                        continue

                if submit_btn:
                    page.evaluate("el => el.click()", submit_btn)
                    rand_delay(page, 2, 3)
                    log(f"[공유] {cname} 게시글 등록 완료")
                    log_activity(cid, "blog_share", blog_url)
                else:
                    log(f"[공유] {cid} — 등록 버튼 없음")

                rand_delay(page, 2, 4)

            except Exception as e:
                log(f"[공유] {cname} 오류: {e}")
                continue

        page.close()
        log("[공유] 전체 완료")

    except Exception as e:
        log(f"[공유] 전체 오류: {e}")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


# ── DB 현황 조회 ──────────────────────────────────────────────────────────────

def show_status(on_log=None):
    """다음카페 DB 현황 출력"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg, flush=True)

    init_db()
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM daum_cafe_list").fetchone()[0]
    joined = conn.execute("SELECT COUNT(*) FROM daum_cafe_list WHERE joined=1").fetchone()[0]
    inactive = conn.execute("SELECT COUNT(*) FROM daum_cafe_list WHERE owner_inactive=1").fetchone()[0]
    activities = conn.execute("SELECT COUNT(*) FROM daum_cafe_activity_log").fetchone()[0]

    log(f"[현황] 총 카페: {total}개 | 가입: {joined}개 | 카페지기 부재중: {inactive}개 | 활동 기록: {activities}건")

    if joined > 0:
        log("[현황] 가입된 카페 목록:")
        for row in conn.execute(
            "SELECT cafe_name, cafe_id, member_count, owner_inactive, last_post_days FROM daum_cafe_list WHERE joined=1"
        ).fetchall():
            status = "부재중" if row[3] else f"{row[4]}일전 활동"
            log(f"  - {row[0]} ({row[1]}) | {row[2]:,}명 | 카페지기: {status}")

    conn.close()


# ── 메인 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="다음카페 자동화 봇")
    parser.add_argument(
        "--mode",
        choices=["find", "join", "persona", "share", "status"],
        required=True,
        help="실행 모드: find=카페탐색 | join=카페가입 | persona=페르소나활동 | share=블로그공유 | status=현황",
    )
    parser.add_argument("--cafe-id", default=None, help="join 모드 시 특정 카페 ID 지정")
    parser.add_argument("--blog-url", default=None, help="share 모드 시 블로그 글 URL")
    parser.add_argument("--blog-title", default=None, help="share 모드 시 블로그 글 제목")
    parser.add_argument("--blog-excerpt", default=None, help="share 모드 시 블로그 글 요약")

    args = parser.parse_args()

    if args.mode == "find":
        find_cafes()
    elif args.mode == "join":
        join_cafe(cafe_id=args.cafe_id)
    elif args.mode == "persona":
        do_persona_activity()
    elif args.mode == "share":
        share_blog_post(
            blog_url=args.blog_url,
            blog_title=args.blog_title,
            blog_excerpt=args.blog_excerpt,
        )
    elif args.mode == "status":
        show_status()
