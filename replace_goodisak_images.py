"""goodisak 게이밍노트북 draft 이미지 교체 스크립트
Bing Image Creator에서 4장 체크 후 일괄 다운로드 → 티스토리 업로드
"""
import sys, time, subprocess, json, re
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from browser import connect_cdp
from bing_image import generate_images_bing
from poster import _tistory_upload_image

def log(msg):
    print(msg, flush=True)

# 1. 열린 draft 탭 찾기
pw, browser = connect_cdp()
ctx = browser.contexts[0]

page = None
for p in ctx.pages:
    if 'newpost' in p.url:
        page = p
        break
if not page:
    log("ERROR: newpost 탭 없음")
    pw.stop()
    sys.exit(1)
log(f"탭 확인: {page.url}")

# 2. 기존 이미지 삭제
result = page.evaluate("""() => {
    const ed = tinymce.get('editor-tistory') || tinymce.activeEditor;
    if (!ed) return 'no editor';
    const imgs = ed.getBody().querySelectorAll('img');
    const count = imgs.length;
    imgs.forEach(img => img.remove());
    return 'deleted ' + count;
}""")
log(f"기존 이미지 삭제: {result}")
time.sleep(1)

# 3. Bing으로 이미지 3장 생성 (subprocess 분리 — Playwright 인스턴스 충돌 방지)
bing_script = """
import sys, json
sys.path.insert(0, '/Users/hana/Downloads/blog-automation-v2')
from bing_image import generate_images_bing
result = generate_images_bing([
    {"index": 1, "prompt": "gaming laptop computer RGB backlit keyboard on desk product photo", "filename": "gaming-notebook-1.jpg"},
    {"index": 2, "prompt": "gaming laptop screen showing video game portable computer product", "filename": "gaming-notebook-2.jpg"},
    {"index": 3, "prompt": "gaming notebook PC hardware specs comparison review 2024", "filename": "gaming-notebook-3.jpg"},
], skip_webp=True, on_log=print)
print("RESULT:" + json.dumps(result))
"""
with open('/tmp/bing_gen.py', 'w') as f:
    f.write(bing_script)

log("Bing 이미지 생성 시작 (subprocess)...")
out = subprocess.run(['python3', '/tmp/bing_gen.py'], capture_output=True, text=True, timeout=300)
log(out.stdout[-2000:])
if out.stderr:
    log("stderr: " + out.stderr[-300:])

m = re.search(r'RESULT:(\{.*\})', out.stdout)
paths = {}
if m:
    raw = json.loads(m.group(1))
    paths = {int(k): v for k, v in raw.items()}
log(f"생성 결과: {paths}")

if not paths:
    subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
        '⚠️ 오류 발생\n작업: goodisak Bing 이미지 생성\n오류: 이미지 생성 실패\n조치: 중단'])
    pw.stop()
    sys.exit(1)

# 4. 티스토리에 업로드 (업로드 성공 시 로컬 파일 자동 삭제)
for idx in sorted(paths.keys()):
    ok = _tistory_upload_image(page, paths[idx], alt='게이밍노트북추천', on_log=log)
    log(f"[{idx}] {'✅ 업로드 성공' if ok else '❌ 업로드 실패'}")
    time.sleep(2)

# 5. 완료 보고
subprocess.run(['python3', '/Users/hana/Downloads/blog-automation-v2/tg_send.py',
    f'🖼️ 이미지 교체 완료\n블로그: goodisak\n글: 게이밍노트북추천 2026\n새 이미지 {len(paths)}장 업로드\n확인 부탁드립니다'])

pw.stop()
log("완료")
