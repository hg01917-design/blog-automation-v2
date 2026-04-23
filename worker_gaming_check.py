"""goodisak 에디터 상태 확인 + 임시저장 팝업 닫기 + 본문 스크린샷"""
import sys, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp, get_or_create_page
from pathlib import Path

img_dir = Path('/Users/hana/Downloads/blog-automation-v2/images')
pw, browser = connect_cdp()

# 에디터 탭 찾기
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

# 임시저장 팝업이 열려있으면 "임시저장하기" 클릭
overlay = tistory_page.evaluate("""() => !!document.querySelector('.ReactModal__Overlay')""")
print(f"임시저장 팝업: {overlay}")

if overlay:
    # "임시저장하기" 버튼 클릭
    clicked = tistory_page.evaluate("""() => {
        const btns = [...document.querySelectorAll('button')];
        const save = btns.find(b => b.textContent.includes('임시저장하기'));
        if (save) { save.click(); return true; }
        // 취소로 팝업 닫기
        const cancel = btns.find(b => b.textContent.includes('취소'));
        if (cancel) { cancel.click(); return 'cancel'; }
        return false;
    }""")
    print(f"임시저장하기 클릭: {clicked}")
    tistory_page.wait_for_timeout(2000)

# 이미지 수 확인
img_count = tistory_page.evaluate("""() => {
    const ed = window.tinymce && (tinymce.get('content') || tinymce.activeEditor);
    if (!ed) return -1;
    return ed.getBody().querySelectorAll('img').length;
}""")
print(f"에디터 이미지 수: {img_count}")

# 이미지 src 확인
img_srcs = tistory_page.evaluate("""() => {
    const ed = window.tinymce && (tinymce.get('content') || tinymce.activeEditor);
    if (!ed) return [];
    return [...ed.getBody().querySelectorAll('img')].map(img => img.src.substring(0, 100));
}""")
print("이미지 src 목록:")
for s in img_srcs:
    print(f"  {s}")

# 본문 스크린샷
ss = str(img_dir / 'editor_check.png')
tistory_page.screenshot(path=ss)
print(f"스크린샷: {ss}")

# 텔레그램으로 스크린샷 전송
subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
                '--photo', ss,
                f'게이밍노트북 에디터 확인 — 이미지 {img_count}장 삽입됨'])

pw.stop()
