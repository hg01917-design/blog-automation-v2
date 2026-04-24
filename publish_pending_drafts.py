"""
publish_pending_drafts.py
drafts/ 폴더의 pending_publish 상태 JSON을 읽어 WordPress REST API로 발행.
remote Claude Code 세션에서 생성된 콘텐츠를 로컬에서 발행할 때 사용.

사용:
    python publish_pending_drafts.py
    python publish_pending_drafts.py baremi542   # 특정 블로그만
"""
import sys
import json
import re
import base64
import ssl
import time
import os
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
DRAFTS_DIR = ROOT / "drafts"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

# WP 설정
BLOGS = {
    "baremi542": {
        "url": "https://baremi542.com",
        "user_key": "WP_USER",
        "pass_key": "WP_APP_PASSWORD",
    },
    "triplog": {
        "url": "https://app.baremi542.com",
        "user_key": "TRIPLOG_WP_USER",
        "pass_key": "TRIPLOG_WP_APP_PASSWORD",
    },
}

# 정부지원 카테고리 슬러그 (baremi542)
BAREMI542_CAT_SLUG = "정부지원금"


def _load_secrets():
    p = ROOT / "remote_secrets.json"
    if p.exists():
        s = json.loads(p.read_text())
        import os
        for k, v in s.items():
            os.environ.setdefault(k, v)
    import os
    return os.environ


def _auth_header(blog_id: str, env) -> str:
    cfg = BLOGS[blog_id]
    user = env.get(cfg["user_key"], "")
    pw = env.get(cfg["pass_key"], "").replace(" ", "")
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {token}"


def _wp_get(url: str, auth: str):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={
        "Authorization": auth,
        "Content-Type": "application/json",
    })
    resp = urllib.request.urlopen(req, timeout=20, context=ctx)
    return json.loads(resp.read())


def _wp_post(url: str, auth: str, data: dict) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": auth,
        "Content-Type": "application/json",
    }, method="POST")
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    return json.loads(resp.read())


def _get_category_id(wp_url: str, auth: str, slug: str) -> int:
    try:
        cats = _wp_get(f"{wp_url}/wp-json/wp/v2/categories?per_page=50", auth)
        for c in cats:
            if c.get("slug") == slug or c.get("name") == slug:
                return c["id"]
    except Exception:
        pass
    return 1  # fallback to default


def _get_or_create_tag_id(wp_url: str, auth: str, tag_name: str) -> int | None:
    try:
        res = _wp_get(f"{wp_url}/wp-json/wp/v2/tags?search={urllib.parse.quote(tag_name)}", auth)
        if res:
            return res[0]["id"]
        # 없으면 생성
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        body = json.dumps({"name": tag_name}).encode()
        req = urllib.request.Request(
            f"{wp_url}/wp-json/wp/v2/tags",
            data=body,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            method="POST",
        )
        created = json.loads(urllib.request.urlopen(req, timeout=10, context=ctx).read())
        return created["id"]
    except Exception:
        return None


def _clean_content(content: str) -> str:
    """[이미지N] 잔재 태그 및 [애드센스] 리터럴 제거"""
    # [이미지N] / [/이미지N] 잔재 제거
    content = re.sub(r'\[/?이미지\s*\d+\]', '', content)
    # <p>[애드센스]</p> 리터럴 제거 (WP에 텍스트로 노출 방지)
    content = re.sub(r'<p>\s*\[애드센스\]\s*</p>', '', content)
    content = re.sub(r'\[애드센스\]', '', content)
    # 빈 <p></p> 정리
    content = re.sub(r'<p>\s*</p>', '', content)
    return content


def _count_img_tags(html: str) -> int:
    return len(re.findall(r'<img\b', html, re.IGNORECASE))


def _add_images_to_wp(wp_url: str, auth: str, content: str, title: str, blog_id: str) -> str:
    """이미지가 3개 미만이면 image_router로 생성 후 WP 미디어에 업로드하여 삽입."""
    img_count = _count_img_tags(content)
    if img_count >= 3:
        return content
    need = 3 - img_count
    print(f"[{blog_id}] 이미지 {img_count}개 < 3개 → {need}개 생성 중...")
    try:
        from image_router import generate_images_for_blog
        from poster import _wp_upload_image_with_id
        slug = re.sub(r'[^\w가-힣]', '-', title.strip()).strip('-')[:40]
        for i in range(1, need + 1):
            results = generate_images_for_blog(
                blog_id=blog_id,
                image_infos=[{"index": i, "prompt": f"{title} travel photo", "filename": f"{slug}-img{i}.jpg"}],
                skip_webp=False,
                on_log=print,
            )
            fp = results.get(i, "")
            if fp:
                img_url, _ = _wp_upload_image_with_id(wp_url, auth, fp, alt=title, on_log=print)
                if img_url:
                    fig = f'<figure class="wp-block-image"><img src="{img_url}" alt="{title}"/></figure>\n'
                    if i == 1:
                        content = re.sub(r'(</p>)', r'\1' + fig, content, count=1)
                    else:
                        mid = len(content) // 2
                        ins = content.find('</p>', mid)
                        if ins > 0:
                            content = content[:ins + 4] + fig + content[ins + 4:]
    except Exception as e:
        print(f"[{blog_id}] 이미지 생성 실패 (무시): {e}")
    return content


def publish_draft(draft_path: Path, env) -> dict:
    data = json.loads(draft_path.read_text())
    blog_id = data.get("blog") or data.get("blog_id")
    if not blog_id or blog_id not in BLOGS:
        return {"ok": False, "reason": f"unknown blog_id: {blog_id}"}

    cfg = BLOGS[blog_id]
    wp_url = cfg["url"]
    auth = _auth_header(blog_id, env)
    title = data["title"]
    content = _clean_content(data["content"])
    keyword = data.get("keyword", "")

    # 이미지 보완 (3개 미만이면 생성 후 삽입)
    content = _add_images_to_wp(wp_url, auth, content, title, blog_id)

    # 카테고리 ID 결정 (baremi542만)
    categories = []
    if blog_id == "baremi542":
        cat_id = _get_category_id(wp_url, auth, BAREMI542_CAT_SLUG)
        categories = [cat_id]

    post_body = {
        "title": title,
        "content": content,
        "status": "publish",
    }
    if categories:
        post_body["categories"] = categories
    if keyword:
        tag_id = _get_or_create_tag_id(wp_url, auth, keyword)
        if tag_id:
            post_body["tags"] = [tag_id]

    try:
        result = _wp_post(f"{wp_url}/wp-json/wp/v2/posts", auth, post_body)
        post_id = result.get("id")
        post_url = result.get("link", "")
        print(f"[OK] {blog_id} 발행 완료: {title}")
        print(f"     URL: {post_url}")

        # 상태 파일 업데이트
        data["status"] = "published"
        data["published_at"] = datetime.now().isoformat()
        data["post_id"] = post_id
        data["post_url"] = post_url
        draft_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

        return {"ok": True, "blog_id": blog_id, "title": title, "url": post_url}

    except urllib.error.HTTPError as e:
        reason = e.read().decode(errors="replace")
        print(f"[FAIL] {blog_id} HTTP {e.code}: {reason[:200]}")
        return {"ok": False, "blog_id": blog_id, "reason": reason[:200]}
    except Exception as e:
        print(f"[FAIL] {blog_id}: {e}")
        return {"ok": False, "blog_id": blog_id, "reason": str(e)}


def main(filter_blog=None):
    env = _load_secrets()
    results = []

    drafts = sorted(DRAFTS_DIR.glob("*.json"))
    pending = [d for d in drafts if json.loads(d.read_text()).get("status") == "pending_publish"]

    if filter_blog:
        pending = [d for d in pending if (lambda x: x.get("blog") or x.get("blog_id"))(json.loads(d.read_text())) == filter_blog]

    print(f"발행 대기 드래프트: {len(pending)}개")

    for i, draft_path in enumerate(pending):
        if i > 0:
            print("  [3.5시간 간격 체크 생략 — 수동 실행 모드]")
        r = publish_draft(draft_path, env)
        results.append(r)
        time.sleep(2)

    # 로그 기록
    log_file = LOG_DIR / f"publish_pending_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\n로그 저장: {log_file}")
    return results


if __name__ == "__main__":
    blog_filter = sys.argv[1] if len(sys.argv) > 1 else None
    main(blog_filter)
