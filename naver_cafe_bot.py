"""
네이버 카페 자동화 봇
- salim1su 계정(daonna525) 사용
- 카페 탐색, 가입, 페르소나 활동, 블로그 공유 기능
"""

import argparse
import random
import sqlite3
import time
from datetime import datetime, timedelta

from browser import connect_cdp, get_or_create_page
from login_playwright import login_blog

DB_PATH = "keyword_engine/engine.db"
BLOG_ID = "salim1su"

CATEGORIES = {
    "여행": ["여행", "국내여행", "해외여행", "여행정보"],
    "IT/기술": ["IT", "기술", "개발", "스마트폰"],
    "정부지원금/복지": ["정부지원금", "복지", "지원금", "보조금"],
    "살림/가계": ["살림", "가계", "절약", "주부"],
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


# ── DB 초기화 ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS cafe_list (
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
            requires_auth INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS cafe_activity_log (
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
        "INSERT INTO cafe_activity_log (cafe_id, activity_type, content) VALUES (?, ?, ?)",
        (cafe_id, activity_type, content),
    )
    conn.commit()
    conn.close()


def rand_delay(page, min_sec=1, max_sec=5):
    ms = random.randint(min_sec * 1000, max_sec * 1000)
    page.wait_for_timeout(ms)


# ── 1. 카페 탐색 ──────────────────────────────────────────────────────────────

def find_cafes(on_log=None):
    """네이버 카페 검색으로 카테고리별 카페 목록 수집 후 DB 저장"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg)

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
                    search_url = f"https://search.naver.com/search.naver?where=cafe&query={kw}+카페"
                    page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    rand_delay(page, 2, 4)

                    # Step1: 검색 결과에서 카페 ID/이름 수집 (페이지 이동 전)
                    SKIP_IDS = {"", "ArticleRead.nhn", "SectionCafeSearch", "ca-fe"}
                    collected = []
                    seen_ids = set()
                    for link in page.query_selector_all("a[href*='cafe.naver.com/']")[:40]:
                        try:
                            href = link.get_attribute("href") or ""
                            parts = href.split("cafe.naver.com/")
                            if len(parts) < 2:
                                continue
                            cafe_id = parts[1].split("/")[0].split("?")[0].strip()
                            if cafe_id in SKIP_IDS or cafe_id in seen_ids:
                                continue
                            seen_ids.add(cafe_id)
                            raw_name = link.inner_text().strip()
                            if "cafe.naver.com" in raw_name or not raw_name:
                                cafe_name = cafe_id
                            else:
                                cafe_name = raw_name.split("\n")[0].strip() or cafe_id
                            collected.append((cafe_id, cafe_name))
                        except Exception:
                            continue

                    # Step2: 각 카페 방문하여 회원수/실명인증 확인
                    saved = 0
                    for cafe_id, cafe_name in collected:
                        try:
                            cafe_url = f"https://cafe.naver.com/{cafe_id}"
                            page.goto(cafe_url, wait_until="domcontentloaded", timeout=15000)
                            rand_delay(page, 1, 2)

                            info = page.evaluate("""() => {
                                const bodyText = document.body.innerText;
                                let memberCount = 0;
                                const memLabelIdx = bodyText.indexOf('카페멤버수');
                                if (memLabelIdx >= 0) {
                                    const after = bodyText.substring(memLabelIdx, memLabelIdx + 30);
                                    const m = after.match(/([\\d,]+)/);
                                    if (m) memberCount = parseInt(m[1].replace(/,/g,''));
                                }
                                if (!memberCount) {
                                    const m2 = bodyText.match(/회원수[^\\n]*?([\\d,]+)/);
                                    if (m2) memberCount = parseInt(m2[1].replace(/,/g,''));
                                }
                                const requiresAuth = bodyText.includes('실명인증') || bodyText.includes('본인인증') || bodyText.includes('휴대폰 인증');
                                // 카페 이름을 페이지에서 추출
                                const titleEl = document.querySelector('h2.cafe_name, .cafe_name, #cafe-name, h1');
                                const pageTitle = titleEl ? titleEl.innerText.trim() : '';
                                return {memberCount, requiresAuth, pageTitle};
                            }""")

                            member_count = info.get('memberCount', 0)
                            requires_auth = 1 if info.get('requiresAuth', False) else 0
                            page_title = info.get('pageTitle', '') or cafe_name

                            if requires_auth:
                                log(f"[탐색] {cafe_id} — 실명인증 필요, 스킵")
                                continue
                            if member_count > 50000:
                                log(f"[탐색] {cafe_id} — 회원수 너무 많음({member_count:,}명), 스킵")
                                continue
                            if 0 < member_count < 300:
                                log(f"[탐색] {cafe_id} — 회원수 너무 적음({member_count:,}명), 스킵")
                                continue

                            conn = get_conn()
                            try:
                                conn.execute(
                                    """INSERT OR IGNORE INTO cafe_list
                                       (cafe_id, cafe_name, category, url, member_count, requires_auth)
                                       VALUES (?, ?, ?, ?, ?, ?)""",
                                    (cafe_id, page_title, category, cafe_url, member_count, requires_auth),
                                )
                                conn.commit()
                                saved += 1
                                log(f"[탐색] 저장: {page_title} ({cafe_id}, 회원 {member_count:,}명)")
                            except Exception:
                                pass
                            finally:
                                conn.close()
                        except Exception:
                            continue

                    log(f"[탐색] '{kw}' 결과 {saved}개 저장")
                    rand_delay(page, 1, 3)

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
    """미가입 카페에 가입 (cafe_id 지정 시 해당 카페만, 없으면 전체 미가입 카페)"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg)

    init_db()
    conn = get_conn()
    if cafe_id:
        rows = conn.execute(
            "SELECT cafe_id, cafe_name, url FROM cafe_list WHERE cafe_id=? AND joined=0 AND requires_auth=0",
            (cafe_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT cafe_id, cafe_name, url FROM cafe_list WHERE joined=0 AND requires_auth=0 LIMIT 10"
        ).fetchall()
    conn.close()

    if not rows:
        log("[가입] 가입할 카페 없음")
        return

    login_blog(BLOG_ID, on_log)
    pw, browser = connect_cdp(on_log)
    try:
        context = browser.contexts[0]

        for (cid, cname, curl) in rows:
            page = None
            try:
                log(f"[가입] {cname} ({cid}) 가입 시도...")
                page = context.new_page()
                page.goto(curl, wait_until="domcontentloaded", timeout=30000)
                rand_delay(page, 2, 4)

                # 가입 버튼 탐색
                join_btn = None
                for selector in [
                    "a:has-text('카페가입')",
                    "a:has-text('가입하기')",
                    "button:has-text('가입')",
                    ".cafe-join-btn",
                    "#joinBtnWrap a",
                ]:
                    try:
                        join_btn = page.query_selector(selector)
                        if join_btn:
                            break
                    except Exception:
                        continue

                if not join_btn:
                    log(f"[가입] {cname} — 가입 버튼 없음 (이미 가입 혹은 비공개)")
                    page.close()
                    continue

                join_btn.click()
                rand_delay(page, 2, 4)

                # 실명인증 감지 → 스킵
                auth_required = page.evaluate("""() => {
                    const t = document.body.innerText;
                    return t.includes('실명인증') || t.includes('본인인증') || t.includes('휴대폰 인증');
                }""")
                if auth_required:
                    log(f"[가입] {cname} — 실명인증 필요, 스킵")
                    conn2 = get_conn()
                    conn2.execute("UPDATE cafe_list SET requires_auth=1 WHERE cafe_id=?", (cid,))
                    conn2.commit()
                    conn2.close()
                    page.close()
                    continue

                # 가입 완료 확인
                success = False
                for success_selector in [
                    "text=가입 완료",
                    "text=가입되었습니다",
                    "text=회원이 되셨습니다",
                    ".join-complete",
                ]:
                    try:
                        if page.query_selector(success_selector):
                            success = True
                            break
                    except Exception:
                        continue

                # 확인 버튼이 있으면 클릭
                for confirm_selector in [
                    "button:has-text('확인')",
                    "a:has-text('확인')",
                    ".btn-confirm",
                ]:
                    try:
                        btn = page.query_selector(confirm_selector)
                        if btn:
                            btn.click()
                            rand_delay(page, 1, 2)
                            break
                    except Exception:
                        continue

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                upd_conn = get_conn()
                upd_conn.execute(
                    "UPDATE cafe_list SET joined=1, joined_at=? WHERE cafe_id=?",
                    (now_str, cid),
                )
                upd_conn.commit()
                upd_conn.close()

                log_activity(cid, "join", "카페 가입 완료")
                log(f"[가입] {cname} 가입 완료")

                page.close()
                rand_delay(page, 3, 6)

            except Exception as e:
                log(f"[가입] {cname} 오류: {e}")
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass
                continue

        log("[가입] 전체 완료")

    except Exception as e:
        log(f"[가입] 전체 오류: {e}")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


# ── 3. 페르소나 활동 ──────────────────────────────────────────────────────────

def _update_persona_days():
    """joined_at 기준으로 persona_days 갱신"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT cafe_id, joined_at FROM cafe_list WHERE joined=1 AND joined_at IS NOT NULL"
    ).fetchall()
    now = datetime.now()
    for (cid, joined_at_str) in rows:
        try:
            joined_at = datetime.strptime(joined_at_str, "%Y-%m-%d %H:%M:%S")
            days = (now - joined_at).days
            conn.execute(
                "UPDATE cafe_list SET persona_days=? WHERE cafe_id=?",
                (days, cid),
            )
        except Exception:
            continue
    conn.commit()
    conn.close()


def _do_comment(page, cafe_id, cafe_name, on_log=None):
    """열린 카페 페이지에서 글 하나에 공감+댓글"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg)

    try:
        # 카페 게시글 목록에서 첫 번째 글 클릭
        post_link = None
        for selector in [
            ".article-board tbody tr td.td_article a",
            ".board-list .item a.article",
            "a.article",
            ".cF-list__item a",
        ]:
            try:
                post_link = page.query_selector(selector)
                if post_link:
                    break
            except Exception:
                continue

        if not post_link:
            log(f"[댓글] {cafe_name} — 게시글 링크 없음")
            return

        post_link.click()
        rand_delay(page, 2, 4)

        # iframe 내 컨텐츠 처리 (카페 게시글은 iframe에 있을 수 있음)
        frame = page
        try:
            iframe = page.frame_locator("#cafe_main")
            if iframe:
                frame = iframe
        except Exception:
            pass

        # 공감 버튼 클릭
        for like_selector in [
            "a.on_sympathy",
            ".btn_sympathy",
            "button:has-text('공감')",
            ".sympathy_area a",
        ]:
            try:
                like_btn = frame.locator(like_selector).first
                if like_btn:
                    like_btn.click()
                    rand_delay(page, 1, 2)
                    log_activity(cafe_id, "like", "공감 클릭")
                    break
            except Exception:
                continue

        # 댓글 작성
        comment_text = random.choice(COMMENTS)
        for comment_selector in [
            "textarea.comment_textarea",
            "#clfix textarea",
            ".comment_write textarea",
            "textarea[placeholder*='댓글']",
        ]:
            try:
                textarea = frame.locator(comment_selector).first
                if textarea:
                    textarea.click()
                    rand_delay(page, 1, 2)
                    textarea.fill(comment_text)
                    rand_delay(page, 1, 2)

                    # 댓글 등록 버튼
                    for submit_selector in [
                        "button.btn_register",
                        "button:has-text('등록')",
                        ".comment_write button[type='submit']",
                    ]:
                        try:
                            submit = frame.locator(submit_selector).first
                            if submit:
                                submit.click()
                                rand_delay(page, 2, 4)
                                log_activity(cafe_id, "comment", comment_text)
                                log(f"[댓글] {cafe_name} — '{comment_text}' 등록")
                                break
                        except Exception:
                            continue
                    break
            except Exception:
                continue

    except Exception as e:
        log(f"[댓글] {cafe_name} 오류: {e}")


def _do_post(page, cafe_id, cafe_name, category, on_log=None):
    """카페에 카테고리에 맞는 일상글 게시"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg)

    DAILY_POSTS = {
        "여행": [
            ("주말에 다녀온 근교 여행 후기", "지난 주말에 가까운 곳으로 짧은 여행을 다녀왔어요. 날씨도 좋고 분위기도 좋아서 힐링이 됐답니다. 혹시 비슷한 경험 있으신 분들 계세요?"),
            ("혼자 떠나는 여행, 어디가 좋을까요?", "요즘 혼자 여행을 계획 중인데요, 추천해주실 만한 국내 여행지 있으신가요? 조용하고 아늑한 곳이면 좋겠어요."),
        ],
        "IT/기술": [
            ("요즘 쓰는 앱 공유해요", "최근에 유용하게 쓰고 있는 앱이 생겼어요. 일상 정리하는 데 정말 도움이 많이 되더라고요. 다들 어떤 앱 즐겨 쓰시나요?"),
            ("스마트폰 배터리 오래 쓰는 법", "스마트폰 배터리가 너무 빨리 닳아서 여러 방법을 찾아봤어요. 밝기 조절이랑 백그라운드 앱 정리가 제일 효과가 좋더라고요."),
        ],
        "정부지원금/복지": [
            ("이번에 알게 된 정부 지원 정보 공유", "우연히 알게 된 지원금 정보인데 생각보다 혜택이 꽤 좋더라고요. 신청 조건이 그리 까다롭지 않아서 한번 알아보시면 좋을 것 같아요."),
            ("복지 혜택 놓치지 마세요!", "최근에 복지로 사이트 돌아다니다가 몰랐던 혜택들을 발견했어요. 생각보다 받을 수 있는 지원이 많더라고요."),
        ],
        "살림/가계": [
            ("이번 달 장보기 절약 후기", "마트 할인 행사 잘 활용하면 생각보다 많이 아낄 수 있어요. 이번 달은 식비를 꽤 줄였는데 뿌듯하네요."),
            ("주방 정리 전후 후기", "오래 미뤄뒀던 주방 정리를 드디어 했어요. 수납 용기 통일하니까 훨씬 깔끔해 보이고 요리하기도 편해졌답니다."),
        ],
    }

    posts = DAILY_POSTS.get(category, DAILY_POSTS["살림/가계"])
    title, content = random.choice(posts)

    try:
        # 글쓰기 버튼 탐색
        write_url = f"https://cafe.naver.com/{cafe_id}?iframe_url=/ArticleWrite.nhn%3Fcafeid={cafe_id}"
        page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
        rand_delay(page, 2, 4)

        frame = page
        try:
            iframe = page.frame_locator("#cafe_main")
            if iframe:
                frame = iframe
        except Exception:
            pass

        # 제목 입력
        for title_selector in [
            "input[name='subject']",
            "#subject",
            "input[placeholder*='제목']",
        ]:
            try:
                title_input = frame.locator(title_selector).first
                if title_input:
                    title_input.click()
                    rand_delay(page, 1, 2)
                    title_input.fill(title)
                    rand_delay(page, 1, 2)
                    break
            except Exception:
                continue

        # 내용 입력
        for content_selector in [
            "iframe.se-iframe",
            ".se-editor",
            "div[contenteditable='true']",
            "#content",
        ]:
            try:
                content_area = frame.locator(content_selector).first
                if content_area:
                    content_area.click()
                    rand_delay(page, 1, 2)
                    page.keyboard.type(content, delay=50)
                    rand_delay(page, 1, 2)
                    break
            except Exception:
                continue

        # 등록 버튼 클릭
        for submit_selector in [
            "button:has-text('등록')",
            "input[value='등록']",
            ".btn_upload",
        ]:
            try:
                submit = frame.locator(submit_selector).first
                if submit:
                    submit.click()
                    rand_delay(page, 2, 4)
                    log_activity(cafe_id, "post", title)
                    log(f"[일상글] {cafe_name} — '{title}' 게시 완료")

                    # 마지막 활동 시간 갱신
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    upd_conn = get_conn()
                    upd_conn.execute(
                        "UPDATE cafe_list SET last_activity=? WHERE cafe_id=?",
                        (now_str, cafe_id),
                    )
                    upd_conn.commit()
                    upd_conn.close()
                    break
            except Exception:
                continue

    except Exception as e:
        log(f"[일상글] {cafe_name} 오류: {e}")


def do_persona_activity(on_log=None):
    """가입 카페에서 공감/댓글 + 7일 후부터 일상글 게시"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg)

    init_db()
    _update_persona_days()

    conn = get_conn()
    rows = conn.execute(
        "SELECT cafe_id, cafe_name, category, url, persona_days FROM cafe_list WHERE joined=1"
    ).fetchall()
    conn.close()

    if not rows:
        log("[페르소나] 가입된 카페 없음")
        return

    login_blog(BLOG_ID, on_log)
    pw, browser = connect_cdp(on_log)
    try:
        context = browser.contexts[0]

        for (cid, cname, category, curl, persona_days) in rows:
            page = None
            try:
                log(f"[페르소나] {cname} (D+{persona_days}) 활동 시작")
                page = context.new_page()
                page.goto(curl, wait_until="domcontentloaded", timeout=30000)
                rand_delay(page, 2, 4)

                # 공감/댓글 (30일간 매 실행)
                _do_comment(page, cid, cname, on_log)

                # 일상글 (7일 후부터 주 1회)
                if persona_days >= 7:
                    # 마지막 일상글 게시 시점 확인
                    act_conn = get_conn()
                    last_post = act_conn.execute(
                        """SELECT created_at FROM cafe_activity_log
                           WHERE cafe_id=? AND activity_type='post'
                           ORDER BY created_at DESC LIMIT 1""",
                        (cid,),
                    ).fetchone()
                    act_conn.close()

                    should_post = True
                    if last_post:
                        try:
                            last_dt = datetime.strptime(last_post[0], "%Y-%m-%d %H:%M:%S")
                            if (datetime.now() - last_dt).days < 7:
                                should_post = False
                                log(f"[페르소나] {cname} — 최근 7일 내 일상글 있음, 스킵")
                        except Exception:
                            pass

                    if should_post:
                        _do_post(page, cid, cname, category, on_log)

                # 마지막 활동 시간 갱신
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                upd_conn = get_conn()
                upd_conn.execute(
                    "UPDATE cafe_list SET last_activity=? WHERE cafe_id=?",
                    (now_str, cid),
                )
                upd_conn.commit()
                upd_conn.close()

                page.close()

                # 글마다 30초~3분 간격
                wait_sec = random.randint(30, 180)
                log(f"[페르소나] 다음 카페까지 {wait_sec}초 대기...")
                time.sleep(wait_sec)

            except Exception as e:
                log(f"[페르소나] {cname} 오류: {e}")
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass
                continue

        log("[페르소나] 전체 완료")

    except Exception as e:
        log(f"[페르소나] 전체 오류: {e}")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


# ── 4. 블로그 공유 ────────────────────────────────────────────────────────────

def share_blog_post(blog_url=None, blog_title=None, blog_excerpt=None, on_log=None):
    """persona_days >= 30인 카페에 블로그 글 공유 (하루 카페당 1회, 최대 3~5개)"""
    def log(msg):
        if on_log:
            on_log(msg)
        print(msg)

    init_db()
    _update_persona_days()

    # 기본값 예시
    if not blog_url:
        blog_url = "https://blog.naver.com/salim1su"
    if not blog_title:
        blog_title = "오늘의 살림 팁"
    if not blog_excerpt:
        blog_excerpt = "오늘은 알아두면 유용한 생활 꿀팁을 정리해봤어요. 주방에서 자주 쓰는 재료들을 효율적으로 보관하는 방법인데요, 생각보다 간단해서 바로 따라 해볼 수 있답니다."

    conn = get_conn()
    eligible = conn.execute(
        "SELECT cafe_id, cafe_name, category, url FROM cafe_list WHERE joined=1 AND persona_days >= 30"
    ).fetchall()
    conn.close()

    if not eligible:
        log("[공유] persona_days >= 30 카페 없음")
        return

    # 오늘 이미 공유한 카페 제외
    today_str = datetime.now().strftime("%Y-%m-%d")
    act_conn = get_conn()
    already_shared = set(
        row[0]
        for row in act_conn.execute(
            """SELECT DISTINCT cafe_id FROM cafe_activity_log
               WHERE activity_type='share'
               AND created_at >= ?""",
            (today_str + " 00:00:00",),
        ).fetchall()
    )
    act_conn.close()

    targets = [r for r in eligible if r[0] not in already_shared]
    max_share = random.randint(3, 5)
    targets = targets[:max_share]

    if not targets:
        log("[공유] 오늘 공유할 카페 없음 (이미 전부 공유 완료)")
        return

    log(f"[공유] 대상 카페 {len(targets)}개")

    post_text = f"{blog_title}\n\n{blog_excerpt}\n\n▶ 자세히 보기: {blog_url}"

    login_blog(BLOG_ID, on_log)
    pw, browser = connect_cdp(on_log)
    try:
        context = browser.contexts[0]

        for (cid, cname, category, curl) in targets:
            page = None
            try:
                log(f"[공유] {cname} ({cid}) 공유 시작...")
                page = context.new_page()

                write_url = f"https://cafe.naver.com/{cid}?iframe_url=/ArticleWrite.nhn%3Fcafeid={cid}"
                page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
                rand_delay(page, 2, 4)

                frame = page
                try:
                    iframe = page.frame_locator("#cafe_main")
                    if iframe:
                        frame = iframe
                except Exception:
                    pass

                # 제목 입력
                for title_selector in [
                    "input[name='subject']",
                    "#subject",
                    "input[placeholder*='제목']",
                ]:
                    try:
                        title_input = frame.locator(title_selector).first
                        if title_input:
                            title_input.click()
                            rand_delay(page, 1, 2)
                            title_input.fill(blog_title)
                            rand_delay(page, 1, 2)
                            break
                    except Exception:
                        continue

                # 내용 입력
                for content_selector in [
                    "iframe.se-iframe",
                    ".se-editor",
                    "div[contenteditable='true']",
                    "#content",
                ]:
                    try:
                        content_area = frame.locator(content_selector).first
                        if content_area:
                            content_area.click()
                            rand_delay(page, 1, 2)
                            page.keyboard.type(post_text, delay=50)
                            rand_delay(page, 1, 2)
                            break
                    except Exception:
                        continue

                # 등록 버튼
                for submit_selector in [
                    "button:has-text('등록')",
                    "input[value='등록']",
                    ".btn_upload",
                ]:
                    try:
                        submit = frame.locator(submit_selector).first
                        if submit:
                            submit.click()
                            rand_delay(page, 2, 4)
                            log_activity(cid, "share", blog_url)
                            log(f"[공유] {cname} — 공유 완료")
                            break
                    except Exception:
                        continue

                page.close()
                rand_delay(page, 3, 8)

            except Exception as e:
                log(f"[공유] {cname} 오류: {e}")
                if page:
                    try:
                        page.close()
                    except Exception:
                        pass
                continue

        log("[공유] 전체 완료")

    except Exception as e:
        log(f"[공유] 전체 오류: {e}")
    finally:
        try:
            pw.stop()
        except Exception:
            pass


# ── 메인 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="네이버 카페 자동화 봇")
    parser.add_argument(
        "--mode",
        choices=["find", "join", "persona", "share"],
        required=True,
        help="실행 모드: find=카페탐색 | join=카페가입 | persona=페르소나활동 | share=블로그공유",
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
