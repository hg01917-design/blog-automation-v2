"""goodisak 카카오톡 알림 포스팅 — 이미지 4장(Bing 1배치) + 임시저장"""
import re
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

DRAFT_PATH = "/tmp/goodisak_draft_clean.txt"

# ── 드래프트 파싱 ──────────────────────────────────
def parse_draft(path):
    text = Path(path).read_text(encoding="utf-8")
    title = re.search(r'===제목===\n(.*?)\n===제목끝===', text, re.DOTALL)
    body  = re.search(r'===본문===\n(.*?)\n===본문끝===', text, re.DOTALL)
    tags  = re.search(r'===태그===\n(.*?)\n===태그끝===', text, re.DOTALL)
    return (
        title.group(1).strip() if title else "",
        body.group(1).strip()  if body  else "",
        [t.strip() for t in tags.group(1).split(",")] if tags else [],
    )

# ── 이미지 정보 추출 ────────────────────────────────
def extract_image_infos(body_text):
    infos = []
    for m in re.finditer(r'\[이미지(\d+)\]\s*\nprompt:\s*(.*?)\nalt:\s*(.*?)\n\[/이미지\1\]', body_text, re.DOTALL):
        infos.append({"index": int(m.group(1)), "prompt": m.group(2).strip(), "alt": m.group(3).strip()})
    # 한국어 레이블도 처리
    if not infos:
        for m in re.finditer(r'\[이미지(\d+)\][\s\S]*?프롬프트:\s*(.*?)\nalt:\s*(.*?)\n\[/이미지\1\]', body_text):
            infos.append({"index": int(m.group(1)), "prompt": m.group(2).strip(), "alt": m.group(3).strip()})
    return sorted(infos, key=lambda x: x["index"])

title, body, tags = parse_draft(DRAFT_PATH)
print(f"제목: {title}")
print(f"태그: {tags}")

image_infos = extract_image_infos(body)
print(f"이미지 슬롯: {[i['index'] for i in image_infos]}")

# ── Bing 이미지 생성 ────────────────────────────────
from bing_image import generate_images_bing

def log(msg):
    print(msg, flush=True)

# Bing 요청용: index + prompt + filename
bing_infos = [
    {"index": info["index"], "prompt": info["prompt"], "filename": f"goodisak_kakao_{info['index']}.jpg"}
    for info in image_infos
]

print(f"\n[Bing] {len(bing_infos)}장 생성 시작 (1배치)...")
image_paths = generate_images_bing(bing_infos, on_log=log)
print(f"[Bing] 완료: {image_paths}")

if not image_paths:
    print("[ERROR] 이미지 생성 실패")
    sys.exit(1)

# ── 썸네일: 이미지1 복사본 사용 (원본은 본문용으로 보존) ──
import shutil as _shutil
_orig_thumb = image_paths.get(1) or list(image_paths.values())[0]
thumbnail_path = _orig_thumb.replace(".webp", "_thumb.webp").replace(".jpg", "_thumb.jpg")
_shutil.copy2(_orig_thumb, thumbnail_path)
print(f"[썸네일] 복사본: {thumbnail_path}")

# ── goodisak 계정 ──────────────────────────────────
from config import ACCOUNT_MAP
account = ACCOUNT_MAP.get("goodisak")
if not account:
    print("[ERROR] goodisak 계정 없음")
    sys.exit(1)

# ── 포스팅 ──────────────────────────────────────────
from poster import _post_tistory

# image_infos에 section 필드 추가 (alt 기반)
post_image_infos = [{"index": i["index"], "section": i["alt"], "alt": i["alt"]} for i in image_infos]

print(f"\n[포스팅] goodisak 임시저장 시작...")
result = _post_tistory(
    account=account,
    title=title,
    body_html=body,
    tags=tags,
    image_paths=image_paths,
    image_infos=post_image_infos,
    keyword="카카오톡 알림 안 올 때",
    thumbnail_path=thumbnail_path,
    on_log=log,
)
print(f"\n[결과] {'성공' if result else '실패'}")
