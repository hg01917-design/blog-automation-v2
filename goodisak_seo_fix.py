"""
goodisak_seo_fix.py
1) 노출 있는 4개 글 → 제목 SEO 최적화
2) 중복 2개 글 → 비공개 처리
"""
import sys, time, random, re
sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")
from browser import connect_cdp, get_or_create_page
from publish_drafts import _tistory_ensure_login

BLOG_ID = "goodisak"

# ── 1. 제목 최적화 대상 ────────────────────────────────────────────────────
TITLE_FIXES = [
    {
        "slug_keyword": "아이폰-구독-자동결제-환불",
        "new_title": "아이폰 구독 자동결제 환불 방법 총정리 (2026 앱스토어 최신)",
        "meta": "앱스토어 구독 자동결제가 실수로 결제됐다면? 환불 신청 방법부터 거절 시 대처법까지 단계별로 안내합니다. 구독 해지·환불 성공률 높이는 팁 포함.",
    },
    {
        "slug_keyword": "Z플립3-충전-안될때",
        "new_title": "갤럭시 Z플립3 충전 안될 때 해결법 5가지 (케이블·포트 점검)",
        "meta": "Z플립3 충전이 갑자기 안 된다면? 케이블 불량부터 소프트웨어 오류까지 원인별 해결법 정리. 대부분 집에서 5분 안에 해결 가능합니다.",
    },
    {
        "slug_keyword": "응용프로그램-오류-막막",
        "new_title": "응용 프로그램을 올바르게 시작하지 못했습니다 오류 해결법 (0xc000007b 포함)",
        "meta": "윈도우 응용프로그램 오류 0xc000007b, 0xc0000142 원인과 해결법. Visual C++ 재배포 패키지 설치부터 DLL 수정까지 단계별로 안내합니다.",
    },
    {
        "slug_keyword": "구글-포토-용량-부족",
        "new_title": "구글 포토 용량 부족 해결법과 네이버 마이박스 이전 장단점 비교 (2026)",
        "meta": "구글 포토 15GB 꽉 찼다면? 용량 늘리는 방법부터 네이버 마이박스·iCloud 등 대안까지 비교 정리. 무료로 해결하는 방법도 안내합니다.",
    },
]

# ── 2. 비공개 처리 대상 ────────────────────────────────────────────────────
MAKE_PRIVATE = [
    "갤럭시A시리즈-순서-읽는-법과-2025년",   # 2025버전 (2026버전으로 대체)
    "윈도우-11-갑자기-느려졌을-때-바로-해결",  # 일반적 버전 (원인별 버전 유지)
]


def log(msg):
    print(f"[goodisak_seo] {msg}")


def get_all_post_ids(page):
    """manage/posts 전체 목록 수집 → {slug_key: post_id}"""
    mapping = {}
    page_num = 1
    while True:
        url = f"https://{BLOG_ID}.tistory.com/manage/posts?page={page_num}&type=post"
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)

        rows = page.locator("table tbody tr").all()
        if not rows:
            break

        found_any = False
        for row in rows:
            try:
                edit_link = row.locator("a[href*='/manage/newpost/']").first
                href = edit_link.get_attribute("href") or ""
                post_id = href.split("/manage/newpost/")[-1].strip("/").split("?")[0]
                title_el = row.locator("a.title, td.title a, .list-title a").first
                title_text = title_el.inner_text().strip() if title_el else ""
                if post_id and post_id.isdigit():
                    mapping[post_id] = title_text
                    found_any = True
            except Exception:
                continue

        if not found_any:
            break

        # 다음 페이지 있는지 확인
        next_btn = page.locator("a.next, a[rel='next'], .pagination a:has-text('다음')").first
        if not next_btn or not next_btn.is_visible(timeout=1000):
            break
        page_num += 1

    log(f"전체 글 {len(mapping)}개 ID 수집 완료")
    return mapping


def find_post_id_by_keyword(mapping, keyword):
    """제목에서 keyword 포함 post_id 반환"""
    keyword_clean = keyword.replace("-", "").replace(" ", "").lower()
    for pid, title in mapping.items():
        title_clean = title.replace(" ", "").replace("-", "").lower()
        if keyword_clean[:8] in title_clean:
            return pid, title
    return None, None


def edit_title_and_meta(page, post_id, new_title, meta):
    """편집기에서 제목·메타 수정 후 발행"""
    edit_url = f"https://{BLOG_ID}.tistory.com/manage/newpost/{post_id}"
    page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # 제목 수정
    title_sel = "#post-title-inp, input[name='title'], #title"
    try:
        title_el = page.locator(title_sel).first
        title_el.wait_for(state="visible", timeout=8000)
        title_el.click(click_count=3)
        page.wait_for_timeout(300)
        title_el.fill(new_title)
        page.wait_for_timeout(500)
        log(f"  제목 수정: {new_title[:40]}")
    except Exception as e:
        log(f"  제목 수정 실패: {e}")
        return False

    # 메타 디스크립션 (Tistory 우측 패널)
    meta_sels = [
        "textarea[name='metaDescription']",
        "textarea[placeholder*='요약']",
        "textarea[placeholder*='설명']",
        "#meta-description",
        ".layer-publish textarea",
    ]
    for sel in meta_sels:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click()
                page.wait_for_timeout(200)
                el.fill(meta)
                log(f"  메타 입력 완료")
                break
        except Exception:
            continue

    # 발행 버튼
    try:
        pub_btn = page.locator(
            "button#publish-layer-btn, button.btn-publish, button:has-text('완료'), button:has-text('발행')"
        ).first
        pub_btn.wait_for(state="visible", timeout=5000)
        pub_btn.click()
        page.wait_for_timeout(2000)

        # 공개 발행 확인
        confirm = page.locator(
            "button:has-text('발행'), button:has-text('확인'), button.btn-confirm"
        ).first
        if confirm.is_visible(timeout=2000):
            confirm.click()
            page.wait_for_timeout(2000)
        log(f"  발행 완료")
        return True
    except Exception as e:
        log(f"  발행 실패: {e}")
        # 저장만이라도
        try:
            save = page.locator("button:has-text('저장'), button:has-text('임시저장')").first
            save.click()
            page.wait_for_timeout(1500)
            log("  임시저장으로 대체")
        except Exception:
            pass
        return False


def make_post_private(page, post_id, title):
    """편집기에서 비공개로 변경 후 저장"""
    edit_url = f"https://{BLOG_ID}.tistory.com/manage/newpost/{post_id}"
    page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # 발행 설정 패널 열기
    try:
        pub_btn = page.locator(
            "button#publish-layer-btn, button.btn-publish-setting, button:has-text('발행설정')"
        ).first
        pub_btn.wait_for(state="visible", timeout=5000)
        pub_btn.click()
        page.wait_for_timeout(1500)
    except Exception as e:
        log(f"  발행설정 버튼 실패: {e}")

    # 비공개 라디오 선택
    private_sels = [
        "input[value='3']",               # Tistory 비공개 value
        "input[name='visibility'][value='0']",
        "label:has-text('비공개') input",
        "input#visibility3",
    ]
    selected = False
    for sel in private_sels:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                el.click(force=True)
                page.wait_for_timeout(500)
                log(f"  비공개 선택 완료 ({sel})")
                selected = True
                break
        except Exception:
            continue

    if not selected:
        log(f"  비공개 옵션 못 찾음 — 스킵: {title[:30]}")
        return False

    # 완료/발행 클릭
    try:
        confirm = page.locator(
            "button:has-text('완료'), button:has-text('발행'), button.btn-confirm"
        ).first
        if confirm.is_visible(timeout=2000):
            confirm.click()
            page.wait_for_timeout(2000)
        log(f"  비공개 저장 완료: {title[:40]}")
        return True
    except Exception as e:
        log(f"  비공개 저장 실패: {e}")
        return False


def main():
    log("Chrome CDP 연결...")
    pw, browser = connect_cdp(on_log=log)
    try:
        page = get_or_create_page(browser)

        log("goodisak 로그인 확인...")
        if not _tistory_ensure_login(page, BLOG_ID):
            log("로그인 실패")
            return

        # 전체 글 ID 수집
        log("글 목록 수집 중...")
        mapping = get_all_post_ids(page)

        results = []

        # ── 제목 최적화 ──────────────────────────────────────────────────
        log("\n=== 제목 SEO 최적화 ===")
        for fix in TITLE_FIXES:
            kw = fix["slug_keyword"]
            pid, old_title = find_post_id_by_keyword(mapping, kw)
            if not pid:
                log(f"글 못 찾음: {kw}")
                results.append({"action": "title", "keyword": kw, "status": "not_found"})
                continue
            log(f"처리: [{pid}] {old_title[:40]}")
            ok = edit_title_and_meta(page, pid, fix["new_title"], fix["meta"])
            results.append({
                "action": "title",
                "old": old_title,
                "new": fix["new_title"],
                "status": "ok" if ok else "failed",
            })
            time.sleep(random.uniform(2, 3))

        # ── 비공개 처리 ──────────────────────────────────────────────────
        log("\n=== 중복 글 비공개 처리 ===")
        for kw in MAKE_PRIVATE:
            pid, old_title = find_post_id_by_keyword(mapping, kw)
            if not pid:
                log(f"글 못 찾음: {kw}")
                results.append({"action": "private", "keyword": kw, "status": "not_found"})
                continue
            log(f"비공개 처리: [{pid}] {old_title[:40]}")
            ok = make_post_private(page, pid, old_title)
            results.append({
                "action": "private",
                "title": old_title,
                "status": "ok" if ok else "failed",
            })
            time.sleep(random.uniform(2, 3))

        # 결과 출력
        log("\n=== 최종 결과 ===")
        for r in results:
            if r["action"] == "title":
                log(f"[제목최적화] {r.get('old','?')[:30]} → {r['status']}")
            else:
                log(f"[비공개] {r.get('title','?')[:30]} → {r['status']}")

        return results

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
