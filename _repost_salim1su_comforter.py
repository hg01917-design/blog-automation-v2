"""salim1su 오리털이불 건조기 재포스팅 — 기존 이미지 재사용, 태그+카테고리+임시저장"""
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
    for m in re.finditer(r'\[이미지(\d+)\][\s\S]*?alt:\s*(.*?)\n\[/이미지\1\]', body_text):
        infos.append({"index": int(m.group(1)), "alt": m.group(2).strip()})
    return sorted(infos, key=lambda x: x["index"])

title, body, tags = parse_draft(DRAFT_PATH)
print(f"제목: {title}")
print(f"태그: {tags[:3]}...")

image_infos = extract_image_infos(body)
print(f"이미지 슬롯: {[i['index'] for i in image_infos]}")

# 기존 이미지 재사용
BASE = Path(__file__).parent / "images" / "salim1su"
image_paths = {
    1: str(BASE / "salim1su-오리털이불을-건조기에-넣는-모습-1-785641.webp"),
    2: str(BASE / "salim1su-오리털이불을-건조기에-넣는-모습-2-785641.webp"),
    3: str(BASE / "salim1su-오리털이불을-건조기에-넣는-모습-3-785641.webp"),
    4: str(BASE / "salim1su-오리털이불을-건조기에-넣는-모습-4-785641.webp"),
    5: str(BASE / "salim1su-오리털이불을-건조기에-넣는-모습-5-785641.webp"),
}

for idx, path in image_paths.items():
    exists = Path(path).is_file()
    print(f"  이미지{idx}: {'✅' if exists else '❌'} {Path(path).name}")

from config import ACCOUNT_MAP
account = ACCOUNT_MAP.get("salim1su")
if not account:
    print("[ERROR] salim1su 계정 없음")
    sys.exit(1)

from poster import _post_naver

post_image_infos = [{"index": i["index"], "alt": i["alt"]} for i in image_infos]

def log(msg):
    print(msg, flush=True)

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
