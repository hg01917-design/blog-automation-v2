#!/usr/bin/env python3
"""catbox.moe로 이미지 업로드 후 Blogger 포스트에 URL로 삽입"""
import sys, json, urllib.request, io, re
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

def webp_to_jpeg(webp_path: Path, max_px: int = 1200, quality: int = 78) -> bytes:
    from PIL import Image
    img = Image.open(webp_path).convert("RGB")
    w, h = img.size
    if w > max_px or h > max_px:
        r = min(max_px/w, max_px/h)
        img = img.resize((int(w*r), int(h*r)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()

def upload_image(img_data: bytes, filename: str) -> str:
    """여러 무료 호스팅 서비스 순서대로 시도"""
    # 1. 0x0.st
    try:
        boundary = "----Boundary7MA4"
        parts = [
            (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
             f'Content-Type: image/jpeg\r\n\r\n').encode() + img_data,
            f'--{boundary}--'.encode(),
        ]
        body = b'\r\n'.join(parts)
        req = urllib.request.Request(
            "https://0x0.st",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = resp.read().decode("utf-8").strip()
            if result.startswith("https://"):
                return result
    except Exception as e:
        print(f"  0x0.st 오류: {e}")

    # 2. litterbox.catbox.moe (임시 호스팅, 72시간)
    try:
        boundary = "----Boundary7MA5"
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="reqtype"\r\n\r\nfileupload'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="time"\r\n\r\n72h'.encode(),
            (f'--{boundary}\r\nContent-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
             f'Content-Type: image/jpeg\r\n\r\n').encode() + img_data,
            f'--{boundary}--'.encode(),
        ]
        body = b'\r\n'.join(parts)
        req = urllib.request.Request(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                     "User-Agent": "Mozilla/5.0"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = resp.read().decode("utf-8").strip()
            if result.startswith("https://"):
                return result
    except Exception as e:
        print(f"  litterbox 오류: {e}")

    return ""

def get_post(token: str) -> dict:
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{POST_ID}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def insert_images_into_html(content: str, image_urls: list) -> str:
    """H2 요소 다음에 이미지 삽입"""
    h2_pattern = re.compile(r'(<h2[^>]*>.*?</h2>)', re.DOTALL | re.IGNORECASE)
    h2_matches = list(h2_pattern.finditer(content))
    print(f"H2 요소: {len(h2_matches)}개, 이미지: {len(image_urls)}개")

    # 역순으로 삽입
    for i, url in reversed(list(enumerate(image_urls))):
        img_tag = f'\n<figure style="text-align:center;margin:20px 0"><img src="{url}" alt="이미지{i+1}" style="max-width:100%;height:auto;border-radius:8px" /></figure>\n'
        if i < len(h2_matches):
            m = h2_matches[i]
            content = content[:m.end()] + img_tag + content[m.end():]
            print(f"  이미지{i+1} → H2[{i}] 다음 삽입")
        else:
            content = img_tag + content
            print(f"  이미지{i+1} → 본문 앞 삽입")
    return content

def update_post(token: str, content: str) -> dict:
    url = f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/{POST_ID}"
    body = json.dumps({"content": content}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, method="PATCH")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"업데이트 오류 {e.code}: {e.read().decode()[:300]}")
        return {}

def main():
    print("=== Blogger 이미지 삽입 (catbox.moe 호스팅) ===\n")
    token = get_token()

    image_urls = []
    for i, img_path in enumerate(IMAGES):
        if not img_path.exists():
            print(f"파일 없음: {img_path}")
            continue
        print(f"[{i+1}/5] 업로드: {img_path.name}")
        try:
            img_data = webp_to_jpeg(img_path)
            print(f"  JPEG 변환: {len(img_data)//1024}KB")
            url = upload_image(img_data, f"blogger_img_{i+1}.jpg")
            if url:
                image_urls.append(url)
                print(f"  ✅ URL: {url}")
            else:
                print(f"  ❌ 업로드 실패")
        except Exception as e:
            print(f"  오류: {e}")

    print(f"\n업로드 완료: {len(image_urls)}/5개")
    if not image_urls:
        print("이미지 업로드 실패, 종료")
        return

    print("\n포스트 가져오기...")
    post = get_post(token)
    content = post.get("content", "")
    print(f"포스트 제목: {post.get('title', '')}")
    print(f"현재 내용: {len(content)}자")

    print("\n이미지 삽입 중...")
    new_content = insert_images_into_html(content, image_urls)
    print(f"수정 후 내용: {len(new_content)}자")

    print("\nBlogger API 업데이트 중...")
    result = update_post(token, new_content)
    if result.get("id"):
        print(f"✅ 업데이트 완료!")
        print(f"   URL: {result.get('url', '')}")
    else:
        print("❌ 업데이트 실패")

if __name__ == "__main__":
    main()
