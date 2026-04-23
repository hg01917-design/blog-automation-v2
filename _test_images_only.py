"""이미지 생성만 테스트 (Naver 포스팅 없음)"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)

prompts = [
    {"index": 1, "prompt": "Dirty gray air conditioner filter covered in thick dust and lint, removed and held up against bright white bathroom tiles, showing how filthy the filter has become after months of use, close-up realistic photo", "alt": "먼지가 두껍게 쌓인 에어컨 필터", "filename": "test_aircon_1.webp"},
    {"index": 2, "prompt": "Air conditioner filter being rinsed under running tap water in a bathroom, brown dirty water draining away, clean white bathtub background, realistic close-up photo showing the cleaning process", "alt": "에어컨 필터를 물로 헹구는 모습", "filename": "test_aircon_2.webp"},
    {"index": 3, "prompt": "Clean white air conditioner filter drying on a towel near a sunny window, next to a small bottle of neutral detergent and a soft brush, bright Korean apartment interior, product-style realistic photo", "alt": "에어컨 필터 건조 중인 모습", "filename": "test_aircon_3.webp"},
    {"index": 4, "prompt": "Korean apartment living room showing a wall-mounted air conditioner with its cover open, revealing the internal fins and drip pan, with a small spray bottle of fin cleaner nearby on the floor, realistic interior photo", "alt": "에어컨 내부 핀과 드레인 팬 위치 확인", "filename": "test_aircon_4.webp"},
    {"index": 5, "prompt": "A simple handwritten checklist on white paper showing air conditioner maintenance schedule with dates marked every two weeks, placed on a Korean kitchen counter next to a coffee mug, warm natural lighting, realistic lifestyle photo", "alt": "에어컨 필터 청소 주기 달력 체크리스트", "filename": "test_aircon_5.webp"},
]

from image_router import generate_images_for_blog

def log(msg):
    print(msg, flush=True)

print(f"[테스트] {len(prompts)}장 생성 시작...")
paths = generate_images_for_blog(
    image_infos=prompts,
    blog_id="salim1su",
    on_log=log,
)

print(f"\n=== 결과 ===")
for idx, path in paths.items():
    p = Path(path)
    print(f"이미지 {idx}: {p.name} ({p.stat().st_size // 1024}KB)")

import hashlib
print("\n=== MD5 ===")
for idx, path in paths.items():
    h = hashlib.md5(Path(path).read_bytes()).hexdigest()
    print(f"이미지 {idx}: {h}")
