"""에디터 전체 스크롤 스크린샷 확인"""
import sys, subprocess
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp, get_or_create_page
from pathlib import Path

img_dir = Path('/Users/hana/Downloads/blog-automation-v2/images')
pw, browser = connect_cdp()

tistory_page = None
for ctx in browser.contexts:
    for p in ctx.pages:
        if 'goodisak.tistory.com' in p.url:
            tistory_page = p
            break

if not tistory_page:
    print("에디터 탭 없음")
    pw.stop()
    exit()

# 전체 페이지 스크린샷 (full_page=True)
ss = str(img_dir / 'editor_full.png')
tistory_page.screenshot(path=ss, full_page=True)
print(f"전체 스크린샷: {ss}")

# H2 수와 이미지 위치 확인
structure = tistory_page.evaluate("""() => {
    const ed = window.tinymce && (tinymce.get('content') || tinymce.activeEditor);
    if (!ed) return null;
    const body = ed.getBody();
    const h2s = [...body.querySelectorAll('h2')].map(h => h.textContent.trim().substring(0, 50));
    const imgs = [...body.querySelectorAll('img')].map(img => img.src.substring(0, 80));
    const total_len = body.textContent.length;
    return {h2s, imgs, total_len};
}""")

if structure:
    print(f"글자 수: {structure['total_len']}")
    print(f"H2 제목 ({len(structure['h2s'])}개):")
    for h in structure['h2s']:
        print(f"  - {h}")
    print(f"이미지 ({len(structure['imgs'])}개):")
    for img in structure['imgs']:
        print(f"  {img}")

subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
                '--photo', ss,
                f"goodisak 게이밍노트북 이미지 교체 완료\n이미지 {len(structure['imgs']) if structure else '?'}장 / H2 {len(structure['h2s']) if structure else '?'}개\n임시저장 완료. 발행 전 확인해주세요."])

pw.stop()
