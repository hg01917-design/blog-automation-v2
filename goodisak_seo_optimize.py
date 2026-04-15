"""
goodisak_seo_optimize.py
GSC 노출은 있으나 클릭이 없는 글들의 제목 + 메타 디스크립션 최적화
대상: 순위 8~11위 글 4개
"""
import sys
import time
import random
sys.path.insert(0, "/Users/hana/Downloads/blog-automation-v2")

from browser import connect_cdp, get_or_create_page
from publish_drafts import _tistory_ensure_login

# 최적화 대상 (slug → 새 제목 + 메타)
TARGETS = [
    {
        "slug": "아이폰-구독-자동결제-환불-되나요",
        "new_title": "아이폰 구독 자동결제 환불 방법 총정리 (2026 앱스토어 최신)",
        "meta": "앱스토어 구독 자동결제가 실수로 결제됐다면? 환불 신청 방법부터 거절 시 대처법까지 단계별로 안내합니다. 구독 해지·환불 성공률 높이는 팁 포함.",
    },
    {
        "slug": "Z플립3-충전-안될때-케이블-확인-해결법",
        "new_title": "갤럭시 Z플립3 충전 안될 때 해결법 5가지 (케이블·포트 점검)",
        "meta": "Z플립3 충전이 갑자기 안 된다면? 케이블 불량부터 소프트웨어 오류까지 원인별 해결법 정리. 대부분 집에서 5분 안에 해결 가능합니다.",
    },
    {
        "slug": "응용프로그램-오류-막막하죠-이렇게-해결하세요",
        "new_title": "응용 프로그램을 올바르게 시작하지 못했습니다 오류 해결법 (0xc000007b 포함)",
        "meta": "윈도우 응용프로그램 오류 0xc000007b, 0xc0000142 원인과 해결법. Visual C++ 재배포 패키지 설치부터 DLL 수정까지 단계별로 안내합니다.",
    },
    {
        "slug": "구글-포토-용량-부족할-때-네이버-마이박스로-바꿔야-할까",
        "new_title": "구글 포토 용량 부족 해결법과 네이버 마이박스 이전 장단점 비교 (2026)",
        "meta": "구글 포토 15GB 꽉 찼다면? 용량 늘리는 방법부터 네이버 마이박스·iCloud 등 대안까지 비교 정리. 무료로 해결하는 방법도 안내합니다.",
    },
]

BLOG_ID = "goodisak"


def log(msg):
    print(f"[SEO] {msg}")


def find_post_id(page, slug):
    """manage/posts 페이지에서 슬러그로 글 ID 찾기"""
    # 검색어: 슬러그의 핵심 단어들
    keyword = slug.replace("-", " ").split()[0]  # 첫 단어로 검색
    search_url = f"https://{BLOG_ID}.tistory.com/manage/posts?type=post&status=&tag=&search={keyword}"
    page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(2000)

    # 글 목록에서 해당 slug 포함 링크 찾기
    links = page.locator("a[href*='/manage/newpost/']").all()
    for link in links:
        href = link.get_attribute("href") or ""
        # 제목 텍스트 확인
        try:
            row = link.locator("xpath=ancestor::tr").first
            title_cell = row.locator("td.title").first
            title_text = title_cell.inner_text() if title_cell else ""
        except Exception:
            title_text = ""

        if slug[:10].replace("-", "") in href.replace("/", "") or slug[:5] in title_text:
            post_id = href.split("/manage/newpost/")[-1].strip("/")
            log(f"  글 ID 발견: {post_id} (href={href})")
            return post_id

    # 목록 전체 스캔
    rows = page.locator("table.list-manage tbody tr").all()
    for row in rows:
        try:
            title_el = row.locator("td.title a, td.title span").first
            title_text = title_el.inner_text() if title_el else ""
            edit_link = row.locator("a[href*='/manage/newpost/']").first
            href = edit_link.get_attribute("href") or ""
            if any(word in title_text for word in slug.split("-")[:3]):
                post_id = href.split("/manage/newpost/")[-1].strip("/")
                log(f"  글 ID 발견(제목매칭): {post_id}, 제목: {title_text[:30]}")
                return post_id
        except Exception:
            continue

    return None


def find_post_by_manage_list(page, slug):
    """manage/posts 전체 목록 순회해서 slug로 글 찾기"""
    # entry URL로 글 접근 후 편집 링크 추출
    entry_url = f"https://{BLOG_ID}.tistory.com/entry/{slug}"
    page.goto(entry_url, wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(1500)

    # 관리자용 편집 버튼이 있는지 확인
    edit_btns = page.locator("a[href*='/manage/newpost/']").all()
    for btn in edit_btns:
        href = btn.get_attribute("href") or ""
        if "/manage/newpost/" in href:
            post_id = href.split("/manage/newpost/")[-1].strip("/")
            log(f"  편집 링크에서 ID 추출: {post_id}")
            return post_id

    # URL에서 숫자 ID 추출 시도 (리다이렉트된 경우)
    current_url = page.url
    if "/entry/" not in current_url:
        # 숫자 URL이면 바로 ID
        parts = current_url.rstrip("/").split("/")
        for part in reversed(parts):
            if part.isdigit():
                return part

    return None


def edit_post_seo(page, post_id, target):
    """Tistory 편집기에서 제목·메타 수정"""
    edit_url = f"https://{BLOG_ID}.tistory.com/manage/newpost/{post_id}"
    log(f"  편집 페이지 이동: {edit_url}")
    page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # 제목 수정
    title_input = page.locator("#post-title-inp, input[name='title'], #title").first
    try:
        title_input.wait_for(state="visible", timeout=8000)
        title_input.click(click_count=3)
        page.wait_for_timeout(300)
        title_input.fill(target["new_title"])
        page.wait_for_timeout(500)
        log(f"  제목 수정 완료: {target['new_title']}")
    except Exception as e:
        log(f"  제목 입력 실패: {e}")
        return False

    # 메타 디스크립션 — Tistory 설정 패널에서 처리
    # "발행 설정" 버튼 클릭
    try:
        publish_btn = page.locator(
            "button:has-text('발행설정'), button:has-text('발행 설정'), "
            "#publish-layer-btn, .btn-publish-setting"
        ).first
        if publish_btn.is_visible(timeout=3000):
            publish_btn.click()
            page.wait_for_timeout(1500)
            log("  발행설정 패널 열기 완료")
    except Exception:
        log("  발행설정 버튼 없음 — 우측 패널 탐색")

    # 메타 디스크립션 입력창 탐색
    meta_selectors = [
        "textarea[name='metaDescription']",
        "textarea[placeholder*='요약']",
        "textarea[placeholder*='설명']",
        "#meta-description",
        ".meta-description textarea",
        "textarea[name='summary']",
    ]
    meta_filled = False
    for sel in meta_selectors:
        try:
            meta_el = page.locator(sel).first
            if meta_el.is_visible(timeout=2000):
                meta_el.click()
                page.wait_for_timeout(200)
                meta_el.fill(target["meta"])
                page.wait_for_timeout(300)
                log(f"  메타 디스크립션 입력 완료 ({sel})")
                meta_filled = True
                break
        except Exception:
            continue

    if not meta_filled:
        log("  메타 디스크립션 입력창 없음 — 스킵")

    # 저장 (임시저장)
    try:
        save_btn = page.locator(
            "button:has-text('저장'), button:has-text('임시저장'), "
            "#btn-save, .btn-save"
        ).first
        save_btn.wait_for(state="visible", timeout=5000)
        save_btn.click()
        page.wait_for_timeout(2000)
        log("  저장 완료")
    except Exception as e:
        log(f"  저장 버튼 클릭 실패: {e}")

    # 발행 버튼
    try:
        pub_btn = page.locator(
            "button:has-text('발행'), button:has-text('공개'), "
            "#publish-btn, .btn-publish"
        ).first
        if pub_btn.is_visible(timeout=3000):
            pub_btn.click()
            page.wait_for_timeout(2000)
            log("  발행 완료")
    except Exception:
        log("  발행 버튼 없음 — 저장만 처리됨")

    return True


def main():
    log("Chrome CDP 연결 중...")
    pw, browser = connect_cdp(on_log=log)
    try:
        page = get_or_create_page(browser)

        log("goodisak 로그인 확인...")
        if not _tistory_ensure_login(page, BLOG_ID):
            log("로그인 실패 — 종료")
            return

        results = []
        for target in TARGETS:
            slug = target["slug"]
            log(f"\n처리 중: {slug}")

            # 글 ID 찾기
            post_id = find_post_by_manage_list(page, slug)
            if not post_id:
                post_id = find_post_id(page, slug)

            if not post_id:
                log(f"  글 ID 못 찾음 — 스킵: {slug}")
                results.append({"slug": slug, "status": "not_found"})
                continue

            # 편집
            ok = edit_post_seo(page, post_id, target)
            results.append({"slug": slug, "post_id": post_id, "status": "ok" if ok else "failed"})
            time.sleep(random.uniform(2, 3))

        # 결과 요약
        log("\n=== 결과 요약 ===")
        for r in results:
            log(f"  {r['slug'][:30]}: {r['status']}")

        return results

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
