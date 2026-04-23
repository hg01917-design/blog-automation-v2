"""Escape → Ctrl+S → 스크린샷 → 텔레그램"""
import sys, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp
from pathlib import Path

img_dir = Path('/Users/hana/Downloads/blog-automation-v2/images')
pw, browser = connect_cdp()

tistory_page = None
for ctx in browser.contexts:
    for p in ctx.pages:
        if 'goodisak.tistory.com' in p.url:
            tistory_page = p
            print(f"에디터 탭: {p.url}")
            break

if not tistory_page:
    print("에디터 탭 없음")
    pw.stop()
    exit()

# 1. Escape로 열린 다이얼로그/팝업 닫기
print("Escape 키 전송")
tistory_page.keyboard.press('Escape')
tistory_page.wait_for_timeout(1000)

# 2. Ctrl+S 임시저장
print("Ctrl+S 전송")
tistory_page.keyboard.press('Control+s')
tistory_page.wait_for_timeout(2000)

# 3. 스크린샷
ss = str(img_dir / 'gaming_saved.png')
tistory_page.screenshot(path=ss)
print(f"스크린샷: {ss}")

# 4. 텔레그램 전송
result = subprocess.run(
    ['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
     '--photo', ss,
     '게이밍노트북 임시저장 완료. 확인 후 발행해주세요.'],
    capture_output=True, text=True
)
print(f"텔레그램 발송: returncode={result.returncode}")

pw.stop()
print("완료")
