"""포스팅 에이전트 — 검수 통과한 글을 블로그에 발행"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from poster import post_single
from keyword_engine import db_handler


def run(result: dict, blog_id: str, keyword: str, page_id: str,
        on_log=None, on_status=None):
    """블로그에 글을 발행하고 Notion 상태를 업데이트한다.

    Returns:
        dict: {"posted": bool, "blog_id": str, "title": str}
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if on_status:
        on_status("poster", "working")

    title = result["title"]
    body = result["body"]
    tags = result["tags"]
    image_paths = result.get("image_paths", {})
    images = result.get("images", [])
    # index 0 = 썸네일 (generate_thumbnail이 저장하는 위치)
    thumbnail_path = image_paths.get(0) if image_paths else None

    log(f"[포스팅] {blog_id} 발행 시작: \"{title}\"")

    posts_dir = Path(__file__).parent.parent / "posts"
    done_dir = Path(__file__).parent.parent / "done"
    posts_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:60]
    post_file = posts_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_title}.txt"
    post_file.write_text(body, encoding="utf-8")
    body = post_file.read_text(encoding="utf-8")
    log(f"[포스팅] 본문 파일 저장: {post_file}")
    if thumbnail_path:
        log(f"[포스팅] 썸네일: {thumbnail_path}")

    try:
        ok = post_single(
            blog_id=blog_id,
            title=title,
            content=body,
            tags=tags,
            image_paths=image_paths,
            image_infos=images,
            keyword=keyword,
            thumbnail_path=thumbnail_path,
            on_log=log,
        )
    except Exception as e:
        log(f"[포스팅] 발행 오류: {e}")
        ok = False

    if ok:
        log(f"[포스팅] ✓ 발행 성공: \"{title}\" ({blog_id})")
        db_handler.set_keyword_status(keyword, "published", blog_id)
        done_file = done_dir / post_file.name
        post_file.replace(done_file)
        log(f"[포스팅] 완료 파일 이동: {done_file}")
    else:
        log(f"[포스팅] ⚠ 발행 실패: \"{title}\" ({blog_id})")
        db_handler.set_keyword_status(keyword, "failed", blog_id)

    if on_status:
        on_status("poster", "done" if ok else "failed")

    return {
        "posted": ok,
        "blog_id": blog_id,
        "title": title,
        "post_url": _find_latest_post_url(blog_id) if ok else "",
    }


def _find_latest_post_url(blog_id: str) -> str:
    """블로그 홈에서 가장 최근 게시물 URL을 반환한다. 실패 시 "" 반환."""
    home_urls = {
        "goodisak":  "https://goodisak.tistory.com",
        "nolja100":  "https://nolja100.tistory.com",
        "salim1su":  "https://blog.naver.com/salim1su",
        "baremi542": "https://baremi542.com",
    }
    home = home_urls.get(blog_id, "")
    if not home:
        return ""

    try:
        import re
        from browser import connect_cdp

        pw, browser = connect_cdp()
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.new_page()
            page.goto(home, timeout=30000)
            page.wait_for_load_state("domcontentloaded", timeout=15000)

            if blog_id in ("goodisak", "nolja100"):
                # tistory: first <a> href ending with /\d+
                links = page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.getAttribute('href'))",
                )
                for href in links:
                    if href and re.search(r"/\d+$", href):
                        url = href if href.startswith("http") else home + href
                        return url

            elif blog_id == "salim1su":
                # naver: first <a> href containing blog.naver.com/salim1su/\d+
                links = page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.getAttribute('href'))",
                )
                for href in links:
                    if href and re.search(r"blog\.naver\.com/salim1su/\d+", href):
                        return href if href.startswith("http") else "https:" + href

            elif blog_id == "baremi542":
                # wordpress: first <a> inside h1, h2, or .entry-title
                href = page.eval_on_selector(
                    "h1 a, h2 a, .entry-title a",
                    "el => el.getAttribute('href')",
                )
                if href:
                    return href

        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                pw.stop()
            except Exception:
                pass

    except Exception:
        pass

    return ""


def _update_publish_date(page_id):
    """Notion 페이지에 발행일 기록"""
    import json
    import urllib.request
    import os

    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    body = {
        "properties": {
            "발행일": {"date": {"start": today}},
        }
    }
    req = urllib.request.Request(
        f"https://api.notion.com/v1/pages/{page_id}",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass
