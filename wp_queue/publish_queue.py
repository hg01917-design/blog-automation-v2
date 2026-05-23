"""
wp_queue/publish_queue.py
wp_queue/*.json 파일을 읽어 WordPress REST API로 발행한다.

사용법:
    python3 wp_queue/publish_queue.py          # 전체 pending_publish 항목
    python3 wp_queue/publish_queue.py baremi542 # 특정 블로그만

.env 필요:
    WP_USER=<워드프레스 사용자명>
    WP_APP_PASSWORD=<애플리케이션 비밀번호>
"""
import os
import sys
import json
import base64
import ssl
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
QUEUE_DIR = Path(__file__).parent

# .env 로드
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

BLOG_SITES = {
    "baremi542": "https://baremi542.com",
    "triplog": "https://app.baremi542.com",
}

BLOG_CREDENTIALS = {
    "baremi542": ("WP_USER", "WP_APP_PASSWORD"),
    "triplog": ("TRIPLOG_WP_USER", "TRIPLOG_WP_APP_PASSWORD"),
}


def urlopen(req, timeout=20):
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_ctx)


def get_or_create_category(site_url, auth_header, cat_name):
    encoded = urllib.parse.quote(cat_name)
    req = urllib.request.Request(
        f"{site_url}/wp-json/wp/v2/categories?search={encoded}&per_page=5",
        headers={"Authorization": auth_header},
    )
    try:
        resp = json.loads(urlopen(req).read())
        for cat in resp:
            if cat.get("name") == cat_name:
                return cat["id"]
    except Exception as e:
        print(f"  [카테고리 조회 오류] {e}")

    req2 = urllib.request.Request(
        f"{site_url}/wp-json/wp/v2/categories",
        data=json.dumps({"name": cat_name}).encode(),
        headers={"Authorization": auth_header, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp2 = json.loads(urlopen(req2).read())
        return resp2.get("id")
    except Exception as e:
        print(f"  [카테고리 생성 오류] {e}")
        return None


def publish_item(item, dry_run=False):
    blog = item.get("blog", "baremi542")
    site_url = item.get("site_url") or BLOG_SITES.get(blog, "")
    title = item.get("title", "")
    content = item.get("content", "")
    category_name = item.get("category", "")

    user_env, pass_env = BLOG_CREDENTIALS.get(blog, ("WP_USER", "WP_APP_PASSWORD"))
    wp_user = os.environ.get(user_env, "")
    wp_pass = os.environ.get(pass_env, "").replace(" ", "")

    if not wp_user or not wp_pass:
        print(f"  [오류] {user_env}/{pass_env} 환경변수 미설정 — 스킵")
        return False

    token = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
    auth_header = f"Basic {token}"
    headers = {"Authorization": auth_header, "Content-Type": "application/json"}

    if dry_run:
        print(f"  [DRY RUN] 발행 예정: {title[:50]}")
        return True

    cat_id = None
    if category_name:
        cat_id = get_or_create_category(site_url, auth_header, category_name)

    payload = {"title": title, "content": content, "status": "publish"}
    if cat_id:
        payload["categories"] = [cat_id]

    req = urllib.request.Request(
        f"{site_url}/wp-json/wp/v2/posts",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        resp = json.loads(urlopen(req, timeout=30).read())
        post_id = resp.get("id")
        post_url = resp.get("link", "")
        print(f"  [발행 완료] ID={post_id} URL={post_url}")
        return True
    except Exception as e:
        print(f"  [발행 오류] {e}")
        return False


def main():
    target_blog = sys.argv[1] if len(sys.argv) > 1 else None
    dry_run = "--dry-run" in sys.argv

    queue_files = sorted(QUEUE_DIR.glob("*.json"))
    processed = 0

    for fpath in queue_files:
        try:
            item = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[파일 읽기 오류] {fpath.name}: {e}")
            continue

        if item.get("status") != "pending_publish":
            continue
        if target_blog and item.get("blog") != target_blog:
            continue

        print(f"\n처리 중: {fpath.name}")
        print(f"  키워드: {item.get('keyword')}")
        print(f"  제목: {item.get('title', '')[:60]}")

        ok = publish_item(item, dry_run=dry_run)
        if ok and not dry_run:
            item["status"] = "published"
            item["published_at"] = datetime.now().isoformat()
            fpath.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
            processed += 1

    print(f"\n완료: {processed}건 발행")


if __name__ == "__main__":
    main()
