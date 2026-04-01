"""
네이버 블로그 서로이웃 + 댓글 자동화 v4 (최종)
- 서로이웃: _addBuddyPop 클릭 → BuddyAdd 팝업 → 서로이웃 선택 → 메시지 → 신청
- 댓글: floating 버튼 JS 클릭 → contenteditable 입력 → 등록
"""
import sys
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')

from browser import connect_cdp
import re, random, time, json

TARGET_BLOGS = [
    {"blog_id": "planwithme",      "name": "가계부 쓰는 독립여정",    "keyword": "가계부/절약",    "done": False},
    {"blog_id": "cash_victo",      "name": "캐시빅토",               "keyword": "가계부/절약",    "done": False},
    {"blog_id": "joiie",           "name": "치치피의 짠순재테크",     "keyword": "재테크/절약",    "done": False},
    {"blog_id": "bokdaeng_living", "name": "bokdaeng_living",        "keyword": "살림/신혼",      "done": False},
]

def gen_comment(post_title, body, name):
    lines = [l.strip() for l in body.split('\n') if 15 < len(l.strip()) < 70]
    key1 = lines[0] if len(lines) > 0 else post_title[:30]
    key2 = lines[1] if len(lines) > 1 else key1
    nums = re.findall(r'\d+(?:만|천|원|%|개|가지|번|분|시간)', body)
    num_str = nums[0] if nums else ""

    reactions = ["아 진짜요?", "맞아요ㅠㅠ", "저도 그랬는데", "완전 공감이에요", "헉 이거 몰랐어요"]
    endings = [
        "저도 써봐야겠어요. 좋은 글 감사해요!",
        "저한테 딱 필요한 정보였어요 감사합니다 :)",
        "이렇게 자세히 써주셔서 너무 도움됐어요!",
        "다음 글도 기대할게요~",
        "북마크 해뒀어요 ㅎㅎ",
    ]

    options = [
        # 본문 첫 문장 인용 + 공감
        f'"{key1[:38]}" — 이 부분에서 멈춰서 두 번 읽었어요. {random.choice(reactions)} {num_str + "이라는 수치도 놀랍고요. " if num_str else ""}{random.choice(endings)}',
        # 두 번째 문장 언급 + 질문 느낌
        f'{key1[:30]} 이야기 읽으면서 저도 비슷한 상황이었던 게 생각났어요. 특히 {key2[:28]} 부분이 현실적이어서 더 와닿았어요. {random.choice(endings)}',
        # 구체적 수치/내용 언급
        f'글 읽다가 {key1[:32]} 이 대목에서 완전 공감했어요. {"" + num_str + " " if num_str else ""}{"이 부분 특히 유용했고요. " if num_str else ""}{random.choice(endings)}',
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

def do_neighbor(page, blog_id, blog_name, keyword, post_title="", body_snippet=""):
    """서로이웃 신청"""
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

    if not src_frame:
        print("  이웃추가 버튼이 있는 프레임 없음")
        return False

    print(f"  프레임: {src_frame.url[:60]}")

    # _addBuddyPop 클릭 → 새 탭 열림
    new_pages = []
    page.context.on("page", lambda p: new_pages.append(p))

    src_frame.locator('a._addBuddyPop').first.click(timeout=8000)

    # BuddyAdd 페이지 대기 (최대 15초)
    buddy_page = None
    for _ in range(30):
        time.sleep(0.5)
        for p in page.context.pages:
            if 'BuddyAdd' in p.url:
                buddy_page = p
                break
        if buddy_page:
            break

    if not buddy_page:
        print("  BuddyAdd 페이지 없음")
        return False

    buddy_page.wait_for_load_state('domcontentloaded')
    time.sleep(2)

    # Step 1: 서로이웃 선택 → 다음 (disabled이면 이웃으로 폴백)
    each_label = buddy_page.locator('label[for="each_buddy_add"]')
    each_radio = buddy_page.locator('#each_buddy_add')
    is_disabled = each_radio.count() > 0 and each_radio.first.is_disabled()
    if not is_disabled:
        each_label.click()
    else:
        print("  서로이웃 disabled — 이웃으로 신청")
    time.sleep(0.3)
    buddy_page.locator('a._buddyAddNext').click()
    time.sleep(3)

    # Step 2: 메시지 입력 → 다음
    ta = buddy_page.locator('textarea#message')
    if ta.count() == 0:
        print("  메시지 textarea 없음")
        buddy_page.close()
        return False
    ta.first.fill(msg)
    time.sleep(0.5)

    buddy_page.locator('a._addBothBuddy').click()
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
pw, browser = connect_cdp()
ctx = browser.contexts[0]
page = ctx.new_page()
page.goto('https://blog.naver.com', wait_until='domcontentloaded', timeout=10000)
time.sleep(1)

results = []

try:
    for blog in TARGET_BLOGS:
        if blog.get("done"):
            print(f"\n[스킵] {blog['name']} — 이미 처리됨")
            continue

        print(f"\n{'='*55}")
        print(f"처리: {blog['name']} ({blog['blog_id']})")
        r = {"blog": blog['name'], "blog_id": blog['blog_id'], "comment_ok": False, "neighbor_ok": False,
             "post_title": "", "body": ""}

        # 1. 최신 글 ID 가져오기
        log_no = get_latest_post_id(page, blog['blog_id'])
        post_title, body = "", ""
        if log_no:
            # 2. 댓글 작성
            comment_text = gen_comment("", "", "")  # 임시, 아래서 실제 내용으로 교체
            title, body, _ = get_post_info(page, blog['blog_id'], log_no)
            comment_text = gen_comment(title, body, blog['name'])
            print(f"  댓글: {comment_text[:60]}...")
            try:
                comment_ok, post_title, body = do_comment(page, blog['blog_id'], log_no, comment_text)
            except Exception as e:
                print(f"  댓글 오류: {e}")
                comment_ok = False
            r['comment_ok'] = comment_ok
            r['post_title'] = post_title
            r['body'] = body[:200]

        # 3. 서로이웃 신청 (댓글에서 읽은 본문 내용 전달)
        try:
            neighbor_ok = do_neighbor(page, blog['blog_id'], blog['name'], blog['keyword'],
                                      post_title=post_title, body_snippet=body)
        except Exception as e:
            print(f"  서로이웃 오류: {e}")
            neighbor_ok = False
        r['neighbor_ok'] = neighbor_ok

        results.append(r)
        print(f"\n  → 댓글:{r['comment_ok']} / 서로이웃:{neighbor_ok}")
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
