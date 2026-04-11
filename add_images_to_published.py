"""
add_images_to_published.py
방금 발행된 글에 Unsplash 이미지 3개를 삽입하고 재저장
- goodisak: "아이패드 프로 M4 실사용 반년, 탠덤 OLED 체감과 iPadOS 한계"
- nolja100: "강릉 숙소 추천 바다뷰 호텔 펜션 가성비 비교"

사용법:
    python3 add_images_to_published.py             # 둘 다
    python3 add_images_to_published.py goodisak    # 특정 블로그만
"""
import sys
import time
import re
import urllib.request
import urllib.parse
import ssl
import os
from pathlib import Path

sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp, get_or_create_page
from config import ACCOUNT_MAP
from poster import _tistory_upload_image, _tistory_set_thumbnail

IMAGES_DIR = Path('/Users/hana/Downloads/blog-automation-v2/images')
TARGET_BLOG = sys.argv[1] if len(sys.argv) > 1 else None


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def download_stock_image(keyword: str, filename: str) -> str | None:
    """스톡 이미지 다운로드 (picsum 우선, 실패 시 loremflickr 폴백)
    → images/ 저장 후 경로 반환"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # picsum.photos (무료, 신뢰성 높음)
    import hashlib
    seed = int(hashlib.md5(keyword.encode()).hexdigest()[:8], 16) % 1000
    urls_to_try = [
        f"https://picsum.photos/seed/{seed}/1200/800",
        f"https://loremflickr.com/1200/800/{urllib.parse.quote(keyword.replace(' ', ','))}",
    ]

    for url in urls_to_try:
        log(f"[이미지] 다운로드 시도: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, timeout=30, context=ctx)
            data = resp.read()
            if len(data) < 5000:
                log(f"[이미지] 응답 너무 작음 ({len(data)}bytes) — 다음 URL 시도")
                continue
            out = IMAGES_DIR / filename
            out.write_bytes(data)
            log(f"[이미지] 저장: {filename} ({len(data)//1024}KB)")
            return str(out)
        except Exception as e:
            log(f"[이미지] 실패 ({url}): {e}")
            continue

    log(f"[이미지] 모든 URL 실패: {keyword}")
    return None


def get_entry_id_from_posts_page(page, blog_id: str) -> str | None:
    """manage/posts 통계 링크에서 최신 entry ID 추출"""
    posts_url = f"https://{blog_id}.tistory.com/manage/posts"
    try:
        page.evaluate("window.onbeforeunload = null")
    except Exception:
        pass
    page.goto(posts_url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    if "/manage" not in page.url:
        log(f"[{blog_id}] manage/posts 접근 불가: {page.url}")
        return None

    # 통계 링크에서 entry ID 추출
    stats_links = page.evaluate("""() => {
        return [...document.querySelectorAll('a')]
            .filter(a => a.href.includes('statistics/entry/'))
            .map(a => a.href)
            .slice(0, 3);
    }""")
    log(f"[{blog_id}] 통계 링크: {stats_links}")

    if stats_links:
        m = re.search(r'/entry/(\d+)', stats_links[0])
        if m:
            return m.group(1)

    return None


def wait_for_tinymce(page, timeout_sec=25) -> bool:
    """TinyMCE 에디터 로드 대기"""
    for i in range(timeout_sec):
        ready = page.evaluate("""() =>
            !!(window.tinymce && tinymce.activeEditor &&
               tinymce.activeEditor.getContent)
        """)
        if ready:
            log(f"TinyMCE 로드 완료 ({i+1}초)")
            return True
        time.sleep(1)
    return False


def delete_existing_images(page, blog_id: str) -> int:
    """TinyMCE 에디터에서 기존 이미지 전체 삭제. 삭제된 개수 반환."""
    deleted = page.evaluate("""() => {
        const ed = tinymce.activeEditor;
        const body = ed.getBody();
        // Tistory 이미지 블록: figure.imageblock, p>img, div.img_block 등
        const containers = [
            ...body.querySelectorAll('figure[class*="image"], figure[class*="img"]'),
            ...body.querySelectorAll('p > img'),
            ...body.querySelectorAll('div[class*="img"]'),
        ];
        // 중복 제거 (img 자체가 포함된 경우 부모 우선)
        const toRemove = new Set();
        containers.forEach(el => {
            // img 태그면 부모 figure/p로 올라가서 제거
            if (el.tagName === 'IMG') {
                const parent = el.closest('figure') || el.parentElement;
                toRemove.add(parent || el);
            } else {
                toRemove.add(el);
            }
        });
        // figure/p 없이 body 직속 img도 제거
        body.querySelectorAll(':scope > img').forEach(el => toRemove.add(el));
        toRemove.forEach(el => { try { el.remove(); } catch(e) {} });
        ed.fire('change');
        ed.save();
        return toRemove.size;
    }""")
    log(f"[{blog_id}] 기존 이미지 {deleted}개 삭제")
    return deleted


def insert_images_at_positions(page, blog_id: str, image_files: list) -> int:
    """TinyMCE 에디터에서 기존 이미지 전부 삭제 후 H2 소제목 아래에 새 이미지 삽입.
    삽입 위치를 매번 DOM에서 새로 조회해 DOM 변화에 강건하게 처리.
    삽입 후 실제 img 수 증가 여부로 성공 검증.
    """
    # ── 먼저 기존 이미지 전체 삭제 ──
    delete_existing_images(page, blog_id)
    time.sleep(1)

    inserted = 0

    # 현재 H2/H3 개수 파악 → 삽입 가능한 최대 이미지 수 결정
    h2_count = page.evaluate("""() => {
        const ed = tinymce.activeEditor;
        return ed.getBody().querySelectorAll('h2, h3').length;
    }""")
    n = min(len(image_files), max(h2_count, 1))
    log(f"[{blog_id}] H2/H3 {h2_count}개 감지 → 이미지 {n}개 삽입 예정")

    for i in range(n):
        fp = image_files[i] if i < len(image_files) else None
        if not fp or not os.path.exists(fp):
            log(f"[{blog_id}] 이미지 파일 없음: {fp}")
            continue

        # 삽입 전 img 수 기록
        before_count = page.evaluate("""() => {
            return tinymce.activeEditor.getBody().querySelectorAll('img').length;
        }""")

        # H2/H3 i번째 바로 아래 단락에 커서 (DOM 매번 새로 조회)
        page.evaluate(f"""() => {{
            const ed = tinymce.activeEditor;
            const body = ed.getBody();
            const h2s = [...body.querySelectorAll('h2, h3')];
            const target = h2s[{i}];
            if (target) {{
                const next = target.nextElementSibling;
                if (next) {{
                    ed.selection.setCursorLocation(next, 0);
                }} else {{
                    // H2 다음 형제 없으면 H2 맨 끝
                    ed.selection.setCursorLocation(target, target.childNodes.length);
                }}
            }} else {{
                // H2 없으면 본문 맨 앞
                const first = body.firstElementChild;
                if (first) ed.selection.setCursorLocation(first, 0);
                else {{ ed.selection.select(body, true); ed.selection.collapse(true); }}
            }}
            ed.focus();
        }}""")
        time.sleep(0.3)

        _tistory_upload_image(page, fp, alt=f"image-{i+1}", on_log=log)
        time.sleep(2)

        # 삽입 검증: img 수 증가 여부
        after_count = page.evaluate("""() => {
            return tinymce.activeEditor.getBody().querySelectorAll('img').length;
        }""")
        if after_count > before_count:
            inserted += 1
            log(f"[{blog_id}] 이미지 {i+1} 삽입 확인 ✅ ({before_count} → {after_count}개)")
        else:
            log(f"[{blog_id}] 이미지 {i+1} 삽입 미확인 ⚠ (before={before_count}, after={after_count})")

    # 썸네일(대표이미지) 설정 — 삽입된 첫 번째 이미지 기준
    if inserted > 0:
        time.sleep(1)
        _tistory_set_thumbnail(page, log_fn=log)

    return inserted


def save_published_post(page, blog_id: str) -> bool:
    """이미 발행된 글 업데이트 (완료 → 공개 발행)"""
    log(f"[{blog_id}] 저장 시작...")

    clicked = page.evaluate("""() => {
        const candidates = [
            document.querySelector('#publish-layer-btn'),
            document.querySelector('#btn-submit'),
            document.querySelector('#publish-btn'),
            document.querySelector('.btn_publish'),
            ...[...document.querySelectorAll('button, a')]
                .filter(el => ['완료', '발행', '게시'].includes(el.textContent.trim()))
        ];
        for (const el of candidates) {
            if (el) { el.click(); return el.textContent.trim(); }
        }
        return null;
    }""")
    if not clicked:
        log(f"[{blog_id}] 발행 버튼 없음")
        return False
    log(f"[{blog_id}] '{clicked}' 클릭")
    time.sleep(2)

    # 공개 라디오 선택
    page.evaluate("""() => {
        const r = document.getElementById('open20');
        if (r) { r.click(); r.checked = true; return; }
        const labels = [...document.querySelectorAll('label')];
        const pub = labels.find(l => l.textContent.trim() === '공개');
        if (pub) pub.click();
    }""")
    time.sleep(1)

    confirmed = page.evaluate("""() => {
        const labels = ['공개 발행', '발행하기', '발행', '확인', '게시'];
        const btns = [...document.querySelectorAll('button')];
        for (const lbl of labels) {
            const btn = btns.find(b => b.textContent.trim() === lbl && !b.disabled);
            if (btn) { btn.click(); return lbl; }
        }
        return null;
    }""")
    if confirmed:
        log(f"[{blog_id}] 발행 확인: '{confirmed}'")
        time.sleep(3)
        return True
    log(f"[{blog_id}] 발행 확인 버튼 없음")
    return False


def process_blog(pw_browser_tuple, blog_id: str, entry_id_hint: str,
                 image_keywords: list) -> dict:
    """한 블로그 처리. pw_browser_tuple = (pw, browser) 또는 None이면 새로 연결."""
    result = {
        "blog_id": blog_id,
        "entry_id": None,
        "images_downloaded": 0,
        "images_inserted": 0,
        "saved": False,
        "error": None,
    }

    pw, browser = pw_browser_tuple
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.new_page()

    try:
        # 1. manage 세션 확인
        log(f"[{blog_id}] manage 접근 확인...")
        try:
            page.evaluate("window.onbeforeunload = null")
        except Exception:
            pass
        page.goto(f"https://{blog_id}.tistory.com/manage/", wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)

        if "/manage" not in page.url:
            log(f"[{blog_id}] 로그인 필요 — login_blog 호출...")
            # login_blog는 자체 pw 인스턴스를 생성하므로 현재 탭 닫고 별도 실행
            page.close()
            from login_playwright import login_blog as _login
            login_ok = _login(blog_id, on_log=log)
            if not login_ok:
                result["error"] = f"{blog_id} 로그인 실패"
                return result
            time.sleep(2)
            # 로그인 후 새 페이지 열어서 재접속
            ctx2 = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx2.new_page()
            page.goto(f"https://{blog_id}.tistory.com/manage/", wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            if "/manage" not in page.url:
                result["error"] = f"{blog_id} manage 재접근 실패"
                return result

        log(f"[{blog_id}] manage 접근 성공")

        # 2. entry ID 확인
        entry_id = entry_id_hint
        if not entry_id:
            entry_id = get_entry_id_from_posts_page(page, blog_id)
        if not entry_id:
            result["error"] = "entry_id 확인 실패"
            return result

        result["entry_id"] = entry_id
        edit_url = f"https://{blog_id}.tistory.com/manage/newpost/{entry_id}"
        log(f"[{blog_id}] 편집 URL: {edit_url}")

        # 3. 편집 페이지 이동
        try:
            page.evaluate("window.onbeforeunload = null")
        except Exception:
            pass
        page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(4)
        log(f"[{blog_id}] 현재 URL: {page.url}")

        # 4. TinyMCE 대기
        if not wait_for_tinymce(page):
            result["error"] = "TinyMCE 로드 실패"
            return result

        # 현재 콘텐츠 이미지 확인
        current_content = page.evaluate("() => tinymce.activeEditor.getContent()")
        existing_imgs = len(re.findall(r'<img\s', current_content))
        log(f"[{blog_id}] 기존 이미지: {existing_imgs}개, 콘텐츠 길이: {len(current_content)}")

        # 5. 이미지 다운로드
        image_files = []
        for j, kw in enumerate(image_keywords):
            fname = f"{blog_id}-stock-{re.sub(r'[^a-z0-9]', '-', kw.lower())}-{j+1}.jpg"
            fp = download_stock_image(kw, fname)
            image_files.append(fp)

        valid = [f for f in image_files if f]
        result["images_downloaded"] = len(valid)
        log(f"[{blog_id}] 다운로드 성공: {len(valid)}/{len(image_files)}")

        if not valid:
            result["error"] = "이미지 다운로드 모두 실패"
            return result

        # 6. 이미지 삽입
        inserted = insert_images_at_positions(page, blog_id, valid)
        result["images_inserted"] = inserted

        if inserted == 0:
            result["error"] = "이미지 삽입 실패"
            return result

        # 7. 저장
        saved = save_published_post(page, blog_id)
        result["saved"] = saved

    except Exception as e:
        result["error"] = str(e)
        log(f"[{blog_id}] 예외: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            page.close()
        except Exception:
            pass

    return result


# ─── 작업 정의 ────────────────────────────────────
# entry_id: None이면 manage/posts 통계 링크에서 자동 탐지
TASKS = [
    {
        "blog_id": "goodisak",
        "entry_id": "44",   # 아이패드 프로 M4 글 (최신)
        "image_keywords": ["ipad tablet", "apple technology", "digital device"],
    },
    {
        "blog_id": "nolja100",
        "entry_id": "201",  # 통계 링크에서 확인
        "image_keywords": ["gangneung beach", "korea hotel", "ocean view"],
    },
]

if TARGET_BLOG:
    TASKS = [t for t in TASKS if t["blog_id"] == TARGET_BLOG]
    if not TASKS:
        print(f"[오류] 알 수 없는 블로그: {TARGET_BLOG}")
        sys.exit(1)

# ─── 실행 ─────────────────────────────────────────
pw, browser = connect_cdp(log)
results = []

try:
    for task in TASKS:
        log(f"\n{'='*55}")
        log(f"=== {task['blog_id']} 이미지 보완 시작 ===")
        log(f"{'='*55}")
        r = process_blog(
            (pw, browser),
            task["blog_id"],
            task.get("entry_id"),
            task["image_keywords"],
        )
        results.append(r)
        log(f"[결과] {r}")
        time.sleep(3)
finally:
    try:
        pw.stop()
    except Exception:
        pass

# ─── 최종 요약 ────────────────────────────────────
print("\n" + "="*55)
print("최종 결과 요약")
print("="*55)
for r in results:
    if r["saved"]:
        status = "성공"
    elif r["images_inserted"] > 0:
        status = "이미지삽입완료(저장실패)"
    else:
        status = "실패"
    print(f"[{r['blog_id']}] {status}")
    print(f"  entry_id : {r['entry_id']}")
    print(f"  다운로드 : {r['images_downloaded']}개")
    print(f"  삽입     : {r['images_inserted']}개")
    print(f"  저장     : {r['saved']}")
    if r.get("error"):
        print(f"  오류     : {r['error']}")
