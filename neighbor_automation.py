"""
네이버 블로그 서로이웃 + 댓글 자동화 v4 (최종)
- 서로이웃: _addBuddyPop 클릭 → BuddyAdd 팝업 → 서로이웃 선택 → 메시지 → 신청
- 댓글: floating 버튼 JS 클릭 → contenteditable 입력 → 등록
- 계정: python3 neighbor_automation.py [salim1su|me1091]  (기본값: salim1su)
"""
import sys
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp
import re, random, time, json, os
from datetime import date

# 실행 계정 결정 (인수 없으면 salim1su)
ACCOUNT = sys.argv[1] if len(sys.argv) > 1 else "salim1su"
assert ACCOUNT in ("salim1su", "me1091"), f"알 수 없는 계정: {ACCOUNT}"
print(f"[이웃추가] 계정: {ACCOUNT}")

DAILY_LIMIT = 5
_base = os.path.dirname(__file__)
VISITED_FILE    = os.path.join(_base, f'visited_blogs_{ACCOUNT}.json')
DISCOVERED_FILE = os.path.join(_base, f'discovered_blogs_{ACCOUNT}.json')

# salim1su: 살림/절약 관련 블로거
SEARCH_KEYWORDS = ["살림 노하우", "절약 생활", "가계부 공유", "주부 일상", "국내 여행 후기", "정부지원금 정보"]

# me1091: 제품 리뷰 관련 블로거
SEARCH_KEYWORDS_ME1091 = [
    "쿠팡 제품 후기", "생활용품 리뷰", "가성비 추천", "육아용품 후기",
    "주방용품 추천", "인테리어 소품 리뷰", "다이소 추천", "생필품 추천"
]


def load_discovered():
    if os.path.exists(DISCOVERED_FILE):
        with open(DISCOVERED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_discovered(blogs):
    with open(DISCOVERED_FILE, 'w', encoding='utf-8') as f:
        json.dump(blogs, f, ensure_ascii=False, indent=2)


def discover_blogs(page, count=20):
    """네이버 블로그 검색으로 새 블로그 ID 발굴"""
    visited = load_visited()
    discovered = {b['blog_id'] for b in load_discovered()}
    target_list = TARGET_BLOGS_ME1091 if ACCOUNT == "me1091" else TARGET_BLOGS
    hardcoded = {b['blog_id'] for b in target_list}
    already_known = visited.keys() | discovered | hardcoded

    new_blogs = []
    kw_list = SEARCH_KEYWORDS_ME1091 if ACCOUNT == "me1091" else SEARCH_KEYWORDS
    kw = random.choice(kw_list)
    print(f"[발굴] 검색 키워드: {kw}")
    try:
        search_url = f"https://search.naver.com/search.naver?where=blog&query={kw}"
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        blog_ids = page.evaluate("""() => {
            const ids = new Set();
            for (const a of document.querySelectorAll('a[href*="blog.naver.com/"]')) {
                const m = a.href.match(/blog\\.naver\\.com\\/([A-Za-z0-9_]+)/);
                if (m && m[1] && !['PostView', 'PostList', 'search'].includes(m[1])) {
                    ids.add(m[1]);
                }
            }
            return [...ids].slice(0, 30);
        }""")

        for bid in blog_ids:
            if bid not in already_known and len(new_blogs) < count:
                new_blogs.append({"blog_id": bid, "name": bid, "keyword": kw})

        print(f"[발굴] 새 블로그 {len(new_blogs)}개 발굴")
    except Exception as e:
        print(f"[발굴] 오류: {e}")

    existing = load_discovered()
    existing_ids = {b['blog_id'] for b in existing}
    for b in new_blogs:
        if b['blog_id'] not in existing_ids:
            existing.append(b)
    save_discovered(existing)
    return new_blogs

def load_visited():
    if os.path.exists(VISITED_FILE):
        with open(VISITED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_visited(visited):
    with open(VISITED_FILE, 'w', encoding='utf-8') as f:
        json.dump(visited, f, ensure_ascii=False, indent=2)

TARGET_BLOGS = [
    {"blog_id": "planwithme",      "name": "가계부 쓰는 독립여정",    "keyword": "가계부/절약",    "done": True},
    {"blog_id": "cash_victo",      "name": "캐시빅토",               "keyword": "가계부/절약",    "done": True},
    {"blog_id": "joiie",           "name": "치치피의 짠순재테크",     "keyword": "재테크/절약",    "done": True},
    {"blog_id": "bokdaeng_living", "name": "bokdaeng_living",        "keyword": "살림/신혼",      "done": True},
    {"blog_id": "dailyw",          "name": "dailyw",                 "keyword": "가계부/절약",    "done": True},
    {"blog_id": "yh120105",        "name": "yh120105",               "keyword": "가계부/절약",    "done": True},
    {"blog_id": "kurumihodu",      "name": "kurumihodu",             "keyword": "가계부/절약",    "done": True},
    {"blog_id": "justdo100",       "name": "justdo100",              "keyword": "가계부/절약",    "done": True},
    {"blog_id": "ejykorea",        "name": "ejykorea",               "keyword": "가계부/절약",    "done": True},
    {"blog_id": "skyluck314",      "name": "skyluck314",             "keyword": "가계부/절약",    "done": True},
    {"blog_id": "sallim_lumora",   "name": "sallim_lumora",          "keyword": "살림/신혼",      "done": True},
    {"blog_id": "khlovems",        "name": "khlovems",               "keyword": "살림/신혼",      "done": True},
    {"blog_id": "khysh7",          "name": "khysh7",                 "keyword": "살림/신혼",      "done": True},
    {"blog_id": "iamevelyn96",     "name": "iamevelyn96",            "keyword": "살림/신혼",      "done": True},
    {"blog_id": "mykjife",         "name": "mykjife",                "keyword": "살림/신혼",      "done": True},
    # 2026-04-02 추가 (서로이웃 성공 확인된 블로그)
    {"blog_id": "soo_clean",       "name": "수클린 살림일기",         "keyword": "살림/청소",      "done": True},
    {"blog_id": "haeun_life",      "name": "해은의 일상",             "keyword": "살림/일상",      "done": True},
    # 나머지는 discovered_blogs.json에서 자동 공급
]

# me1091: 리뷰 블로그 독자 타깃 (제품 리뷰/가성비/쿠팡 관련 블로거)
TARGET_BLOGS_ME1091 = [
    {"blog_id": "seon0425",        "name": "소소한 리뷰일기",        "keyword": "생활용품/리뷰"},
    {"blog_id": "hyun4236",        "name": "현실 살림 리뷰",          "keyword": "가성비/리뷰"},
    {"blog_id": "reviewking2",     "name": "리뷰킹2",                "keyword": "제품리뷰"},
    {"blog_id": "daily_review99",  "name": "데일리리뷰",              "keyword": "일상리뷰"},
    {"blog_id": "coupang_jjang",   "name": "쿠팡짱",                 "keyword": "쿠팡리뷰"},
    {"blog_id": "lifewithitem",    "name": "아이템으로 사는 삶",      "keyword": "리뷰/추천"},
    {"blog_id": "happyhome24",     "name": "해피홈24",               "keyword": "인테리어/리뷰"},
    {"blog_id": "bestbuy_kr",      "name": "베스트바이코리아",        "keyword": "가성비추천"},
    # 나머지는 discovered_blogs_me1091.json에서 자동 공급
]

def gen_comment(post_title, body, name):
    lines = [l.strip() for l in body.split('\n') if 15 < len(l.strip()) < 70]
    key1 = lines[0] if len(lines) > 0 else post_title[:30]
    key2 = lines[1] if len(lines) > 1 else (lines[0] if lines else post_title[:30])
    nums = re.findall(r'\d+(?:만|천|원|%|개|가지|번|분|시간)', body)
    num_str = nums[0] if nums else ""
    has_num = bool(num_str)

    # 각 템플릿은 구조·어투가 완전히 다르게
    options = [
        # 1. 짧고 솔직한 반응
        f'오늘 우연히 들어왔는데 {key1[:28]} 이 부분 읽으면서 아 나만 이런 거 아니었구나 싶었어요. 공감 가는 글 감사해요!',
        # 2. 정보성 칭찬
        f'{"" + num_str + " " if has_num else ""}{key1[:30]} 덕분에 몰랐던 거 하나 알고 가요. 이런 정보 찾기 힘든데 정리해주셔서 감사합니다 :)',
        # 3. 개인 경험 연결
        f'저도 {key2[:25]} 이런 거 고민했던 적 있는데 글 보고 도움 많이 됐어요. 실용적으로 써주셔서 좋았어요~',
        # 4. 가볍고 친근한 톤
        f'헉 {key1[:28]} 저 이거 진짜 몰랐어요ㅠ {"" + num_str + "이나 " if has_num else ""}이런 팁 알려주셔서 감사해요 ㅎㅎ 잘 보고 갑니다!',
        # 5. 공감 + 저장
        f'{key1[:30]} 부분 공감 100%예요. 스크랩해두고 나중에 다시 봐야겠어요. 좋은 글 써주셔서 감사합니다!',
        # 6. 질문 느낌
        f'글 읽으면서 {key2[:28]} 이 내용이 제 상황이랑 너무 비슷해서 반가웠어요. {"" + num_str + " 부분도 인상적이었고요. " if has_num else ""}다음 글도 기대할게요 :)',
        # 7. 담백한 감사
        f'바쁜데 이렇게 꼼꼼하게 써주셨군요. {key1[:25]} 내용 덕분에 저도 한번 시도해볼 용기가 생겼어요. 감사해요!',
        # 8. 발견한 느낌
        f'검색하다가 우연히 들어왔는데 딱 제가 찾던 내용이었어요. 특히 {key1[:25]} 이 부분이요. 북마크하고 갑니다~',
    ]
    return random.choice(options)

def gen_neighbor_msg(name, keyword, post_title="", body_snippet=""):
    # 본문 내용이 있으면 첫 문장 활용, 없으면 keyword 사용
    content_ref = ""
    if body_snippet:
        lines = [l.strip() for l in body_snippet.split('\n') if 15 < len(l.strip()) < 60]
        if lines:
            content_ref = lines[0][:40]
    if not content_ref and post_title:
        content_ref = post_title[:30]
    if not content_ref:
        content_ref = keyword

    options = [
        f'안녕하세요! 오늘 방문해서 글 읽다가 "{content_ref}" 이 부분에서 저랑 비슷한 고민 하고 계신 것 같아서 반가웠어요. 저도 비슷한 주제로 블로그 하고 있는데 서로이웃 신청해도 될까요? 잘 부탁드려요 😊',
        f'안녕하세요~ 글 읽다가 {content_ref} — 이 내용이 딱 제가 찾던 거라서 저도 모르게 이웃신청 누르게 됐어요 ㅎㅎ 저도 살림/절약 관련 글 쓰는데 앞으로 좋은 정보 나눠요! 잘 부탁드립니다 :)',
        f'오늘 처음 방문했는데 "{content_ref}" 이 글 보고 완전 공감해서 댓글도 남기고 이웃신청도 드려요. 같은 관심사를 가진 분들끼리 소통하면 좋을 것 같아서요. 맞이해주시면 감사해요 💕',
    ]
    return random.choice(options)

def gen_neighbor_msg_me1091(name, keyword, post_title="", body_snippet=""):
    """me1091 리뷰 블로그 계정용 이웃신청 메시지"""
    content_ref = ""
    if body_snippet:
        lines = [l.strip() for l in body_snippet.split('\n') if 15 < len(l.strip()) < 60]
        if lines:
            content_ref = lines[0][:40]
    if not content_ref and post_title:
        content_ref = post_title[:30]
    if not content_ref:
        content_ref = keyword

    options = [
        f'안녕하세요! "{content_ref}" 글 읽다가 저도 비슷한 제품 써봤던 기억이 나서 공감하면서 읽었어요. 저도 일상용품·생활템 위주로 직접 써보고 후기 남기는 블로그 운영 중인데 서로이웃 신청 드려도 될까요? 좋은 리뷰 정보 나눠요 😊',
        f'안녕하세요~ 오늘 우연히 방문했는데 {content_ref} 이 부분에서 딱 멈췄어요. 저도 이 제품 찾아보던 중이었거든요 ㅎㅎ 솔직한 후기 정말 도움됐어요. 저도 리뷰 블로그 운영 중인데 서로이웃 해요! 잘 부탁드려요 :)',
        f'글 읽다가 "{content_ref}" 이 리뷰가 너무 현실적이어서 바로 이웃신청 드려요. 광고 없이 솔직하게 쓰신 거 느껴졌어요. 저도 가성비 제품 위주로 써보고 후기 남기는데, 앞으로 좋은 정보 나눠요 💕',
    ]
    return random.choice(options)

def get_latest_post_id(page, blog_id):
    try:
        result = page.evaluate(
            'async (blogId) => { var r = await fetch("https://blog.naver.com/PostList.naver?blogId=" + blogId + "&widgetTypeCall=true&noTrackingCode=true"); return await r.text(); }',
            blog_id
        )
        ids = re.findall(r'logNo=(\d+)', result)
        return ids[0] if ids else None
    except Exception as e:
        print(f"  글 ID 조회 실패: {e}")
        return None

def get_post_info(page, blog_id, log_no):
    """포스트 제목 + 본문 추출"""
    post_url = f"https://blog.naver.com/{blog_id}/{log_no}"
    page.goto(post_url, wait_until='domcontentloaded', timeout=20000)
    page.wait_for_timeout(4000)

    title = page.evaluate("""() => {
        var m = document.querySelector('meta[property="og:title"]');
        return m ? m.content.replace(/\\s*[:|]\\s*네이버 블로그/, '').trim() : '';
    }""")

    postview = next((f for f in page.frames if 'PostView' in f.url), None)
    body = ""
    if postview:
        try:
            text = postview.evaluate('() => document.body.innerText')
            if '본문 기타 기능' in text:
                body = text.split('본문 기타 기능')[1][:600].strip()
            else:
                lines = [l.strip() for l in text.split('\n') if l.strip()]
                body = '\n'.join(lines[15:35])
        except:
            pass

    return title, body, postview

def do_comment(page, blog_id, log_no, comment_text):
    """댓글 작성"""
    title, body, postview = get_post_info(page, blog_id, log_no)
    if not postview:
        print("  PostView 없음")
        return False, title, body

    # floating 버튼 JS 클릭
    postview.evaluate("() => { var btn = document.querySelector('a._floating_bottom_btn_comment, a._cmtList'); if(btn) btn.click(); }")
    time.sleep(3)

    # contenteditable 확인 및 입력
    input_ok = postview.evaluate("""(comment) => {
        var el = document.querySelector('.u_cbox_text[contenteditable=true]');
        if (!el || el.getBoundingClientRect().width === 0) return false;
        el.focus();
        document.execCommand('selectAll');
        document.execCommand('insertText', false, comment);
        return el.textContent.length > 0;
    }""", comment_text)

    if not input_ok:
        print("  댓글 입력 실패")
        return False, title, body

    time.sleep(1)

    # 등록 버튼 클릭
    submit_ok = postview.evaluate("""() => {
        var btns = document.querySelectorAll('button.u_cbox_btn_upload');
        for (var b of btns) {
            if (b.innerText.trim() === '등록' && !b.disabled) {
                b.click();
                return true;
            }
        }
        return false;
    }""")

    if submit_ok:
        time.sleep(3)
        # 텍스트 지워졌으면 성공
        after = postview.evaluate("() => { var el = document.querySelector('.u_cbox_text'); return el ? el.textContent : ''; }")
        if not after.strip():
            print(f"  댓글 등록 ✅ — {comment_text[:40]}...")
            return True, title, body
        else:
            print("  등록 후 텍스트 남아있음 (등록 실패?)")
            return False, title, body
    else:
        print("  등록 버튼 없음")
        return False, title, body

def do_neighbor(page, blog_id, blog_name, keyword, post_title="", body_snippet="", account="salim1su"):
    """서로이웃 신청"""
    if account == "me1091":
        msg = gen_neighbor_msg_me1091(blog_name, keyword, post_title=post_title, body_snippet=body_snippet)
    else:
        msg = gen_neighbor_msg(blog_name, keyword, post_title=post_title, body_snippet=body_snippet)

    # 기존 BuddyAdd 페이지 닫기
    for p in page.context.pages:
        if 'BuddyAdd' in p.url:
            try: p.close()
            except: pass

    # 블로그 메인으로 이동
    page.goto(f'https://blog.naver.com/{blog_id}', wait_until='domcontentloaded', timeout=20000)
    page.wait_for_timeout(6000)

    # PostList 또는 Prologue 프레임 대기 (최대 15초)
    src_frame = None
    for _ in range(30):
        for f in page.frames:
            if ('PostList' in f.url or 'Prologue' in f.url) and f.url:
                try:
                    if f.locator('a._addBuddyPop').count() > 0:
                        src_frame = f
                        break
                except:
                    pass
        if src_frame:
            break
        time.sleep(0.5)

    # 팝업 열기: 프레임 버튼 클릭 OR 직접 URL 이동 (폴백)
    buddy_page = None

    if src_frame:
        print(f"  프레임: {src_frame.url[:60]}")
        try:
            with page.expect_popup(timeout=10000) as popup_info:
                src_frame.locator('a._addBuddyPop').first.click(timeout=8000)
            buddy_page = popup_info.value
            buddy_page.wait_for_load_state('domcontentloaded', timeout=10000)
        except Exception as e:
            print(f"  팝업 클릭 실패: {e}")
            # context.pages 에서 BuddyAdd 찾기
            for p in page.context.pages:
                if 'BuddyAdd' in p.url:
                    buddy_page = p
                    break
    else:
        print("  이웃추가 버튼 프레임 없음 → 직접 URL 시도")

    # 직접 URL 폴백: 프레임 버튼으로 못 열었을 때
    if not buddy_page:
        try:
            with page.expect_popup(timeout=8000) as popup_info:
                page.evaluate(f"""() => {{
                    window.open('https://buddy.naver.com/BuddyAdd.nhn?blogId={blog_id}',
                        'BuddyAdd', 'width=430,height=580');
                }}""")
            buddy_page = popup_info.value
            buddy_page.wait_for_load_state('domcontentloaded', timeout=10000)
            print("  직접 URL로 BuddyAdd 열기 성공")
        except Exception as e2:
            print(f"  직접 URL도 실패: {e2}")

    if not buddy_page:
        print("  BuddyAdd 페이지 열기 불가 — 스킵")
        return False

    buddy_page.wait_for_load_state('domcontentloaded')
    time.sleep(2)

    # 페이지 상태 확인 (이미 이웃인지, 로그인 필요한지)
    page_text = buddy_page.evaluate("() => document.body.innerText") or ""
    if "이미" in page_text and "이웃" in page_text:
        print(f"  이미 이웃 상태 — 스킵")
        buddy_page.close()
        return False
    if "로그인" in page_text:
        print(f"  로그인 필요 — 스킵")
        buddy_page.close()
        return False

    # Step 1: 서로이웃 선택 → 다음
    each_label = buddy_page.locator('label[for="each_buddy_add"]')
    each_radio = buddy_page.locator('#each_buddy_add')
    if each_label.count() > 0:
        is_disabled = each_radio.count() > 0 and each_radio.first.is_disabled()
        if not is_disabled:
            each_label.click()
        else:
            print("  서로이웃 disabled — 이웃으로 신청")
    else:
        print("  서로이웃 선택 UI 없음 — 기본 진행")

    time.sleep(0.3)
    next_btn = buddy_page.locator('a._buddyAddNext')
    if next_btn.count() == 0:
        print("  다음 버튼 없음")
        buddy_page.close()
        return False
    next_btn.click()
    time.sleep(3)

    # Step 2: 메시지 입력 → 신청
    ta = buddy_page.locator('textarea#message')
    if ta.count() == 0:
        print("  메시지 textarea 없음")
        buddy_page.close()
        return False
    ta.first.fill(msg)
    time.sleep(0.5)

    submit_btn = buddy_page.locator('a._addBothBuddy')
    if submit_btn.count() == 0:
        print("  신청 버튼 없음")
        buddy_page.close()
        return False
    submit_btn.click()
    time.sleep(3)

    # 완료 확인
    done_text = buddy_page.evaluate("""() => {
        var p = document.querySelector('.text_buddy_add');
        return p ? p.innerText : '';
    }""")
    if '신청하였습니다' in done_text:
        print(f"  서로이웃 신청 ✅ — {done_text.strip()}")
        buddy_page.close()
        return True
    else:
        print(f"  서로이웃 결과 불명확: {done_text[:50]}")
        buddy_page.close()
        return False


# ── 메인 ──────────────────────────────────────────────────────────────────────
visited = load_visited()
today = str(date.today())
# 성공(neighbor_ok=True)한 것만 한도에 포함
today_count = sum(1 for v in visited.values() if v.get('date') == today and v.get('neighbor_ok'))
today_total = sum(1 for v in visited.values() if v.get('date') == today)
print(f"오늘({today}) 방문: {today_total}개 (서로이웃 성공: {today_count}개) / 한도: {DAILY_LIMIT}개")

pw, browser = connect_cdp()
ctx = browser.contexts[0]
page = ctx.new_page()

# 계정 로그인 확인 (me1091은 별도 로그인 필요)
if ACCOUNT == "me1091":
    from login_playwright import login_naver
    print("[이웃추가] me1091 네이버 로그인 확인 중...")
    # 기존 page 넘겨서 새 Playwright 세션 충돌 방지
    login_naver(naver_id="me1091", page=page)
    page.goto('https://blog.naver.com/me1091', wait_until='domcontentloaded', timeout=15000)
else:
    page.goto('https://blog.naver.com', wait_until='domcontentloaded', timeout=10000)
time.sleep(1)

# 계정별 타깃 목록 선택
target_list = TARGET_BLOGS_ME1091 if ACCOUNT == "me1091" else TARGET_BLOGS

results = []

try:
    # 타깃 + discovered 블로그 합치기
    discovered_blogs = load_discovered()
    all_blogs = target_list + [b for b in discovered_blogs if b['blog_id'] not in {x['blog_id'] for x in target_list}]

    # 발굴 조건: done=True 제외하고 미방문 남은 개수로 판단
    if today_count < DAILY_LIMIT:
        remaining = [b for b in all_blogs if not b.get('done') and b['blog_id'] not in visited]
        if len(remaining) < (DAILY_LIMIT - today_count) * 2:
            print(f"[발굴] 미방문 후보 {len(remaining)}개 → 새 블로그 탐색 중...")
            discover_blogs(page, count=30)
            discovered_blogs = load_discovered()
            all_blogs = target_list + [b for b in discovered_blogs if b['blog_id'] not in {x['blog_id'] for x in target_list}]

    for blog in all_blogs:
        if today_count >= DAILY_LIMIT:
            print(f"\n[한도도달] 오늘 {DAILY_LIMIT}개 성공 — 중단")
            break

        blog_id = blog['blog_id']
        # 이미 서로이웃 완료된 계정 스킵
        if blog.get('done'):
            continue
        if blog_id in visited:
            print(f"\n[스킵] {blog.get('name', blog_id)} — 이미 방문함 ({visited[blog_id].get('date','')})")
            continue

        print(f"\n{'='*55}")
        print(f"처리: {blog['name']} ({blog_id})")
        r = {"blog": blog['name'], "blog_id": blog_id, "comment_ok": False, "neighbor_ok": False,
             "post_title": "", "body": ""}

        # 1. 최신 글 ID 가져오기
        log_no = get_latest_post_id(page, blog_id)
        post_title, body = "", ""
        if log_no:
            # 2. 댓글 작성
            title, body, _ = get_post_info(page, blog_id, log_no)
            comment_text = gen_comment(title, body, blog['name'])
            print(f"  댓글: {comment_text[:60]}...")
            try:
                comment_ok, post_title, body = do_comment(page, blog_id, log_no, comment_text)
            except Exception as e:
                print(f"  댓글 오류: {e}")
                comment_ok = False
            r['comment_ok'] = comment_ok
            r['post_title'] = post_title
            r['body'] = body[:200]

        # 3. 서로이웃 신청
        try:
            neighbor_ok = do_neighbor(page, blog_id, blog['name'], blog['keyword'],
                                      post_title=post_title, body_snippet=body,
                                      account=ACCOUNT)
        except Exception as e:
            print(f"  서로이웃 오류: {e}")
            neighbor_ok = False
        r['neighbor_ok'] = neighbor_ok

        # 방문 기록 저장
        visited[blog_id] = {"date": today, "comment_ok": r['comment_ok'], "neighbor_ok": neighbor_ok}
        save_visited(visited)
        today_count += 1

        results.append(r)
        print(f"\n  → 댓글:{r['comment_ok']} / 서로이웃:{neighbor_ok} | 오늘 {today_count}/{DAILY_LIMIT}")
        time.sleep(random.uniform(15, 25))

finally:
    page.close()
    pw.stop()

print(f"\n{'='*55}")
print("완료 요약:")
for r in results:
    c = "✅" if r['comment_ok'] else "❌"
    n = "✅" if r['neighbor_ok'] else "❌"
    print(f"  {r['blog']}: 댓글{c} 서로이웃{n}")

with open('/tmp/neighbor_results_v4.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("결과 저장: /tmp/neighbor_results_v4.json")
