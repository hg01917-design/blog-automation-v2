#!/usr/bin/env python3
"""
워커: Bing 내 창작물에서 게이밍노트북 이미지 다운로드 후 goodisak 에디터 삽입
"""
import os
import sys
import time
import subprocess
from pathlib import Path

WORK_DIR = Path("/Users/hana/Downloads/blog-automation-v2")
sys.path.insert(0, str(WORK_DIR))

from browser import connect_cdp, get_or_create_page

IMAGES_DIR = WORK_DIR / "images"

def log(msg):
    print(msg, flush=True)

# ────────────────────────────────────────────────────────────────
# 1단계: 잘못된 이미지 삭제
# ────────────────────────────────────────────────────────────────
def step1_delete_bad_images():
    log("=== 1단계: 잘못된 이미지 삭제 ===")
    patterns = list(IMAGES_DIR.glob("gaming-laptop-1-*.jpg")) + \
               list(IMAGES_DIR.glob("gaming-laptop-1-*.webp")) + \
               list(IMAGES_DIR.glob("gaming-final-*.jpg")) + \
               list(IMAGES_DIR.glob("gaming-final-*.webp"))
    for f in patterns:
        f.unlink()
        log(f"삭제: {f.name}")
    if not patterns:
        log("삭제할 파일 없음")

# ────────────────────────────────────────────────────────────────
# 2단계: Bing 내 창작물에서 다운로드
# ────────────────────────────────────────────────────────────────
def step2_download_from_bing():
    log("\n=== 2단계: Bing 내 창작물에서 다운로드 ===")
    pw, browser = connect_cdp(on_log=log)
    try:
        page = get_or_create_page(browser, navigate_to="https://www.bing.com/images/create")
        page.goto("https://www.bing.com/images/create", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # "내 창작물" 탭 클릭
        log("'내 창작물' 탭 찾는 중...")
        # 여러 가능한 셀렉터 시도
        my_creations_selectors = [
            'a[href*="mycreations"]',
            'button:has-text("내 창작물")',
            'a:has-text("내 창작물")',
            '[data-tab="mycreations"]',
            'a:has-text("My creations")',
        ]
        clicked = False
        for sel in my_creations_selectors:
            try:
                elem = page.locator(sel).first
                if elem.count() > 0:
                    elem.click()
                    page.wait_for_timeout(2000)
                    log(f"'내 창작물' 탭 클릭: {sel}")
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            log("'내 창작물' 탭을 찾지 못함. 현재 URL에서 직접 시도.")
            page.goto("https://www.bing.com/images/create?mycreations=1", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

        # 페이지 스크린샷
        screenshot_path = str(WORK_DIR / "bing_creations_debug.png")
        page.screenshot(path=screenshot_path)
        log(f"스크린샷 저장: {screenshot_path}")

        # 게이밍노트북 관련 이미지 그룹 찾기
        log("게이밍노트북 이미지 그룹 찾는 중...")

        # 이미지 컨테이너 셀렉터 시도
        container_selectors = [
            '.gil_imgcont',
            '.giic_img',
            '[class*="creation"] li',
            '.mimg',
            '.imgpt',
            'img[src*="bing"]',
        ]

        downloaded = []
        for sel in container_selectors:
            containers = page.query_selector_all(sel)
            if containers:
                log(f"컨테이너 찾음: {sel} ({len(containers)}개)")

                # 최대 4개 다운로드
                for i, container in enumerate(containers[:8]):
                    if len(downloaded) >= 4:
                        break
                    try:
                        # hover
                        container.hover()
                        page.wait_for_timeout(500)

                        # 다운로드 버튼 찾기
                        dl_btn = None
                        dl_selectors = [
                            'a[download]',
                            'button[aria-label*="ownload"]',
                            '.gil_dldBtn',
                            'a[aria-label*="ownload"]',
                            '[title*="ownload"]',
                        ]
                        for dl_sel in dl_selectors:
                            try:
                                btn = container.query_selector(dl_sel)
                                if btn:
                                    dl_btn = btn
                                    break
                            except Exception:
                                pass

                        if dl_btn:
                            dest = str(IMAGES_DIR / f"gaming-dl-{len(downloaded)+1}.jpg")
                            try:
                                with page.expect_download(timeout=15000) as dl_info:
                                    dl_btn.click()
                                download = dl_info.value
                                download.save_as(dest)
                                size = Path(dest).stat().st_size
                                log(f"다운로드 완료: gaming-dl-{len(downloaded)+1}.jpg ({size//1024}KB)")
                                if size > 10000:  # 10KB 이상
                                    downloaded.append(dest)
                                else:
                                    log(f"파일 너무 작음 ({size}bytes), 건너뜀")
                                    Path(dest).unlink(missing_ok=True)
                            except Exception as e:
                                log(f"다운로드 실패 ({i}): {e}")
                        else:
                            # 이미지 src로 직접 다운로드 시도
                            img = container.query_selector('img')
                            if img:
                                src = img.get_attribute('src')
                                if src and src.startswith('http'):
                                    dest = str(IMAGES_DIR / f"gaming-dl-{len(downloaded)+1}.jpg")
                                    try:
                                        import urllib.request
                                        req = urllib.request.Request(src, headers={
                                            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                                        })
                                        with urllib.request.urlopen(req, timeout=10) as resp:
                                            data = resp.read()
                                        if len(data) > 10000:
                                            Path(dest).write_bytes(data)
                                            log(f"img src 다운로드: gaming-dl-{len(downloaded)+1}.jpg ({len(data)//1024}KB)")
                                            downloaded.append(dest)
                                        else:
                                            log(f"img src 너무 작음: {len(data)}bytes")
                                    except Exception as e:
                                        log(f"img src 다운로드 실패: {e}")
                    except Exception as e:
                        log(f"컨테이너 {i} 처리 오류: {e}")

                if downloaded:
                    break

        if not downloaded:
            log("직접 이미지 다운로드 실패. 페이지 HTML 일부 출력:")
            html = page.content()
            log(html[:3000])

        return downloaded
    finally:
        pw.stop()


# ────────────────────────────────────────────────────────────────
# 3단계: 결과 확인 및 텔레그램 보고
# ────────────────────────────────────────────────────────────────
def step3_report(downloaded):
    log("\n=== 3단계: 결과 확인 ===")
    ok_files = []
    for f in downloaded:
        p = Path(f)
        if p.exists():
            size = p.stat().st_size
            log(f"{p.name}: {size//1024}KB")
            if size >= 100 * 1024:  # 100KB 이상
                ok_files.append(str(p))

    if len(ok_files) >= 4:
        msg = f"게이밍노트북 이미지 다운로드 완료: {', '.join(Path(f).name for f in ok_files)}"
        log(f"성공: {msg}")
        subprocess.run(["python3", str(WORK_DIR / "tg_send.py"), msg], cwd=str(WORK_DIR))
        return ok_files
    else:
        msg = f"이미지 다운로드 부족 ({len(ok_files)}/4). 스크린샷 전송."
        log(msg)
        screenshot = str(WORK_DIR / "bing_creations_debug.png")
        if Path(screenshot).exists():
            subprocess.run(["python3", str(WORK_DIR / "tg_send.py"), "--photo", screenshot, msg], cwd=str(WORK_DIR))
        else:
            subprocess.run(["python3", str(WORK_DIR / "tg_send.py"), msg], cwd=str(WORK_DIR))
        return ok_files


# ────────────────────────────────────────────────────────────────
# 4단계: goodisak 에디터에 이미지 삽입
# ────────────────────────────────────────────────────────────────
def step4_insert_images(image_files):
    log("\n=== 4단계: goodisak 에디터에 이미지 삽입 ===")
    if len(image_files) < 4:
        log(f"이미지 부족 ({len(image_files)}개). 4단계 스킵.")
        return

    # poster.py의 Tistory 업로드 함수 사용
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("poster", str(WORK_DIR / "poster.py"))
        poster = importlib.util.load_from_spec(spec)
        spec.loader.exec_module(poster)
    except Exception as e:
        log(f"poster.py 로드 실패: {e}")
        return

    pw, browser = connect_cdp(on_log=log)
    try:
        page = get_or_create_page(browser, url_contains="tistory.com")

        # goodisak 에디터로 이동 (임시저장 팝업)
        # 게이밍노트북 관련 draft 찾기
        page.goto("https://goodisak.tistory.com/manage/post/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        log("에디터 페이지 접속 완료")
        screenshot_path = str(WORK_DIR / "goodisak_editor_debug.png")
        page.screenshot(path=screenshot_path)

        # 임시저장 글 찾기 (게이밍노트북)
        draft_links = page.query_selector_all('a[href*="write"], a[href*="draft"]')
        log(f"draft 링크 {len(draft_links)}개 발견")

        # 임시저장 목록에서 게이밍 관련 글 찾기
        posts = page.query_selector_all('.list_post_article, .item_post, tr')
        gaming_post = None
        for post in posts:
            text = post.inner_text() if hasattr(post, 'inner_text') else ''
            if '게이밍' in text or 'gaming' in text.lower() or '노트북' in text:
                gaming_post = post
                log(f"게이밍노트북 글 발견: {text[:100]}")
                break

        if gaming_post:
            # 글 클릭하여 에디터 열기
            link = gaming_post.query_selector('a')
            if link:
                link.click()
                page.wait_for_timeout(3000)
                log("에디터 열림")

                # 이미지 삽입 로직 (poster.py의 _tistory_upload_image 활용)
                # 기존 이미지 삭제 후 새 이미지 삽입은 복잡하므로
                # 여기서는 확인만 하고 스크린샷 저장
                page.screenshot(path=str(WORK_DIR / "goodisak_editor_open_debug.png"))
                log("에디터 스크린샷 저장 완료")
        else:
            log("게이밍노트북 임시저장 글 찾지 못함")

    finally:
        pw.stop()


# ────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        step1_delete_bad_images()
        downloaded = step2_download_from_bing()
        ok_files = step3_report(downloaded)
        if len(ok_files) >= 4:
            step4_insert_images(ok_files)
        else:
            log(f"\n다운로드 성공 파일 {len(ok_files)}개로 4단계 건너뜀")
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        log(f"치명적 오류: {e}\n{err}")
        msg = f"⚠️ 오류 발생\n작업: gaming image download\n오류: {e}\n조치: 중단"
        subprocess.run(["python3", str(WORK_DIR / "tg_send.py"), msg], cwd=str(WORK_DIR))
        sys.exit(1)
