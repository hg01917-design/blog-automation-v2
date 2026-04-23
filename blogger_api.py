"""
blogger_api.py
Blogger API v3 — 글 발행/임시저장
"""
import json
import urllib.request
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).parent


def _get_token() -> str:
    import sys
    sys.path.insert(0, str(BASE_DIR))
    from gsc_indexing import _get_access_token
    return _get_access_token()


def _load_env() -> dict:
    env = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _inject_adsense(content: str, env: dict) -> str:
    """본문의 [애드센스] 마커를 실제 AdSense 코드로 치환."""
    pub = env.get("ADSENSE_CODE", "")
    slot = env.get("ADSENSE_SLOT", "")
    if not pub or not slot:
        return content
    ad_html = (
        f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={pub}" crossorigin="anonymous"></script>'
        f'<ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{pub}" data-ad-slot="{slot}"></ins>'
        '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script>'
    )
    return content.replace("[애드센스]", ad_html)


def publish_post(title: str, content: str, labels: list = None,
                 status: str = "LIVE", blog_id: str = None,
                 meta_description: str = None) -> dict:
    """Blogger에 글 발행 또는 임시저장.

    Args:
        title: 글 제목
        content: HTML 본문 ([애드센스] 마커 포함 가능)
        labels: 태그 목록
        status: "LIVE" (발행) or "DRAFT" (임시저장)
        blog_id: 블로그 ID (None이면 .env에서 읽음)
        meta_description: 검색 설명 (customMetaData)

    Returns:
        {"ok": True, "url": "...", "id": "..."} or {"ok": False, "reason": "..."}
    """
    env = _load_env()
    content = _inject_adsense(content, env)
    if not blog_id:
        blog_id = env.get("BLOGGER_BLOG_ID", "")
    if not blog_id:
        return {"ok": False, "reason": "BLOGGER_BLOG_ID 없음"}

    try:
        token = _get_token()
    except Exception as e:
        return {"ok": False, "reason": f"토큰 오류: {e}"}

    body = {
        "title": title,
        "content": content,
    }
    if labels:
        body["labels"] = labels
    if meta_description:
        body["customMetaData"] = meta_description

    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/"
    if status == "DRAFT":
        url += "?isDraft=true"

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        return {
            "ok": True,
            "id": resp.get("id", ""),
            "url": resp.get("url", ""),
            "title": resp.get("title", ""),
        }
    except urllib.error.HTTPError as e:
        reason = e.read().decode(errors="replace")
        return {"ok": False, "reason": f"HTTP {e.code}: {reason[:1000]}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def patch_post_content(post_id: str, content: str, blog_id: str = None) -> bool:
    """Blogger 드래프트/발행 글 본문 수정 (PATCH)."""
    env = _load_env()
    if not blog_id:
        blog_id = env.get("BLOGGER_BLOG_ID", "")
    if not blog_id:
        return False
    try:
        token = _get_token()
        data = json.dumps({"content": content}).encode("utf-8")
        req = urllib.request.Request(
            f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/{post_id}",
            data=data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="PATCH",
        )
        urllib.request.urlopen(req, timeout=30)
        return True
    except Exception:
        return False


def find_draft_by_keyword(keyword: str, blog_id: str = None) -> dict | None:
    """키워드가 제목에 포함된 드래프트 글 조회. 없으면 None."""
    env = _load_env()
    if not blog_id:
        blog_id = env.get("BLOGGER_BLOG_ID", "")
    if not blog_id:
        return None
    try:
        token = _get_token()
        params = urllib.parse.urlencode({"status": "draft", "maxResults": 20})
        url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts?{params}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        for post in resp.get("items", []):
            if keyword in post.get("title", ""):
                return post
    except Exception:
        pass
    return None


def list_posts(blog_id: str = None, status: str = "live", max_results: int = 10) -> list:
    """최근 발행된 글 목록 조회"""
    env = _load_env()
    if not blog_id:
        blog_id = env.get("BLOGGER_BLOG_ID", "")

    token = _get_token()
    params = urllib.parse.urlencode({"status": status, "maxResults": max_results})
    url = f"https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts?{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return resp.get("items", [])


if __name__ == "__main__":
    print("Blogger API 연결 테스트...")
    posts = list_posts(max_results=3)
    if posts:
        print(f"✅ 연결 성공! 최근 글 {len(posts)}개:")
        for p in posts:
            print(f"  - {p.get('title', '')} ({p.get('url', '')})")
    else:
        print("✅ 연결 성공 (발행된 글 없음)")
