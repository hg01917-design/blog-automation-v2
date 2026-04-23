#!/usr/bin/env python3
"""Picasa API로 이미지 업로드 후 Blogger 포스트에 삽입"""
import sys, json, subprocess, urllib.request, urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

BLOGGER_BLOG_ID = "5956656339719895415"
POST_ID = "7327638874699086892"
IMAGES = [
    BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-1.webp",
    BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-2.webp",
    BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-3.webp",
    BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-4.webp",
    BASE_DIR / "images/blogspot_it/blogspot_it-카카오맵과-네이버지도-기본-기능-비교-화면-5.webp",
]

def get_token():
    from gsc_indexing import _get_access_token
    return _get_access_token()

def webp_to_jpeg(webp_path: Path, max_size: int = 1200, quality: int = 75) -> bytes:
    """webp를 jpeg bytes로 변환 (pillow 사용), 최대 max_size px로 리사이즈"""
    try:
        from PIL import Image
        import io
        img = Image.open(webp_path).convert("RGB")
        # 리사이즈 (비율 유지)
        w, h = img.size
        if w > max_size or h > max_size:
            ratio = min(max_size / w, max_size / h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except ImportError:
        # pillow 없으면 sips (macOS) 사용
        import tempfile, subprocess
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        subprocess.run(["sips", "-s", "format", "jpeg", "-z", "800", "800",
                        str(webp_path), "--out", tmp_path],
                       capture_output=True, check=True)
        data = open(tmp_path, "rb").read()
        Path(tmp_path).unlink(missing_ok=True)
        return data

def upload_to_picasa(token: str, img_data: bytes, filename: str) -> str:
    """Picasa API로 이미지 업로드, URL 반환"""
    # Blogger dropbox album에 업로드
    url = "https://picasaweb.google.com/data/feed/api/user/default/albumid/default"
    # Slug 헤더는 ASCII만 허용 - 한글 파일명이면 영문으로 대체
    import re as _re
    safe_filename = _re.sub(r'[^\x00-\x7F]', '', filename) or "image.jpg"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "image/jpeg",
        "Slug": safe_filename,
        "GData-Version": "2",
    }
    req = urllib.request.Request(url, data=img_data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            # XML 응답에서 media URL 추출
            import re
            urls = re.findall(r'<media:content url="([^"]+)"', body)
            if urls:
                return urls[0]
            # 다른 패턴 시도
            urls = re.findall(r'url="([^"]+\.jpg[^"]*)"', body)
            if urls:
                return urls[0]
            print(f"응답 (첫 500자): {body[:500]}")
            return ""
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"Picasa 업로드 오류 {e.code}: {body[:300]}")
        return ""

def get_post_content(token: str) -> dict:
    """현재 포스트 내용 가져오기"""
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{POST_ID}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def update_post_with_images(token: str, post: dict, image_urls: list) -> dict:
    """포스트 내용에 이미지 삽입 후 업데이트"""
    content = post.get("content", "")

    # H2 요소 뒤에 이미지 삽입
    import re
    h2_pattern = re.compile(r'(<h2[^>]*>.*?</h2>)', re.DOTALL)
    h2_matches = list(h2_pattern.finditer(content))
    print(f"H2 요소: {len(h2_matches)}개")

    # 역순으로 삽입 (앞에서 삽입하면 위치가 틀어짐)
    for i, url in reversed(list(enumerate(image_urls))):
        if i < len(h2_matches):
            m = h2_matches[i]
            img_tag = f'<figure><img src="{url}" alt="이미지{i+1}" style="max-width:100%;height:auto;" /></figure>'
            content = content[:m.end()] + "\n" + img_tag + content[m.end():]
            print(f"이미지{i+1} H2[{i}] 다음에 삽입")
        else:
            # H2가 부족하면 맨 앞에 삽입
            img_tag = f'<figure><img src="{url}" alt="이미지{i+1}" style="max-width:100%;height:auto;" /></figure>\n'
            content = img_tag + content
            print(f"이미지{i+1} 본문 앞에 삽입")

    # API로 업데이트
    update_url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{POST_ID}"
    body = json.dumps({"content": content}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(update_url, data=body, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        print(f"업데이트 오류 {e.code}: {err[:300]}")
        return {}

def main():
    print("=== Blogger 이미지 삽입 (Picasa API 방식) ===\n")

    token = get_token()
    print(f"토큰 획득: {token[:20]}...\n")

    # 이미지 업로드
    image_urls = []
    for img_path in IMAGES:
        if not img_path.exists():
            print(f"파일 없음: {img_path}")
            continue
        print(f"업로드 중: {img_path.name}")
        try:
            img_data = webp_to_jpeg(img_path)
            print(f"  변환 완료: {len(img_data)//1024}KB")
            url = upload_to_picasa(token, img_data, img_path.stem + ".jpg")
            if url:
                image_urls.append(url)
                print(f"  ✅ URL: {url[:80]}")
            else:
                print(f"  ❌ URL 없음")
        except Exception as e:
            print(f"  오류: {e}")

    print(f"\n업로드된 이미지: {len(image_urls)}개")

    if not image_urls:
        print("업로드된 이미지 없음, 종료")
        return

    # 포스트 업데이트
    print("\n포스트 내용 가져오기...")
    post = get_post_content(token)
    print(f"포스트 제목: {post.get('title', '')}")
    print(f"포스트 내용: {len(post.get('content', ''))}자")

    print("\n이미지 삽입 후 업데이트 중...")
    result = update_post_with_images(token, post, image_urls)
    if result:
        print(f"✅ 업데이트 완료: {result.get('url', '')}")
    else:
        print("❌ 업데이트 실패")

if __name__ == "__main__":
    main()
