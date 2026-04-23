"""salim1su 오리털이불 건조기 포스팅 — Gemini 이미지 + 네이버 임시저장"""
import re, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

DRAFT_PATH = "/tmp/salim1su_draft2.txt"
KEYWORD = "오리털이불 건조기 돌려도 되는지"

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

def extract_image_infos(body_text):
    infos = []
    for m in re.finditer(r'\[이미지(\d+)\][\s\S]*?프롬프트:\s*(.*?)\nalt:\s*(.*?)\n\[/이미지\1\]', body_text):
        infos.append({"index": int(m.group(1)), "prompt": m.group(2).strip(), "alt": m.group(3).strip()})
    return sorted(infos, key=lambda x: x["index"])

title, body, tags = parse_draft(DRAFT_PATH)
print(f"제목: {title}")
print(f"태그: {tags[:3]}...")

image_infos = extract_image_infos(body)
print(f"이미지 슬롯: {[i['index'] for i in image_infos]}")

from image_router import generate_images_for_blog

def log(msg):
    print(msg, flush=True)

bing_infos = [
    {"index": info["index"], "prompt": info["prompt"],
     "filename": f"salim1su_comforter_{info['index']}.jpg", "alt": info["alt"]}
    for info in image_infos
]

print(f"[Gemini] {len(bing_infos)}장 생성 중...")
image_paths = generate_images_for_blog(
    image_infos=bing_infos,
    blog_id="salim1su",
    on_log=log,
)

if not image_paths:
    print("[ERROR] 이미지 생성 전체 실패")
    sys.exit(1)

print(f"\n생성된 이미지: {list(image_paths.values())}")

from config import ACCOUNT_MAP
account = ACCOUNT_MAP.get("salim1su")
if not account:
    print("[ERROR] salim1su 계정 없음")
    sys.exit(1)

from poster import _post_naver

post_image_infos = [{"index": i["index"], "alt": i["alt"]} for i in image_infos]

print(f"\n[포스팅] salim1su 임시저장 시작...")
result = _post_naver(
    account=account,
    title=title,
    content=body,
    tags=tags,
    image_paths=image_paths,
    image_infos=post_image_infos,
    keyword=KEYWORD,
    on_log=log,
)
print(f"\n[결과] {'성공' if result else '실패'}")
