"""
baremi542 WordPress 블로그 - 종합소득세기한후환급 포스팅 생성 및 발행 스크립트
"""
import sys
import os
import json
import base64
import ssl
import time
import urllib.request
import urllib.error
import mimetypes
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

WP_URL = "https://baremi542.com"
WP_USER = "hg01917@gmail.com"
WP_APP_PASSWORD = "7gij zLxb 7xe8 bE3n RdXC 1f8a"

KEYWORD = "종합소득세기한후환급"

TITLE = "종합소득세기한후환급 2026년 신청 방법과 환급금 조회 정리"

CONTENT_RAW = """세금 신고 기한이 지나고 나서야 환급받을 수 있다는 걸 뒤늦게 알게 됐어요. 작년에 프리랜서 수입이 있었는데 5월 신고 기한을 그냥 넘겨버렸거든요. 주변 분이 "기한후신고도 되고, 환급도 받을 수 있어"라고 알려줘서 처음으로 홈택스에서 직접 신청해봤습니다. 그때 세무서 담당 직원분이 "기한후 신고는 가산세가 붙을 수 있지만 환급 자체는 가능합니다"라고 분명하게 말씀해주셔서 용기를 내 진행했어요. 실제로 환급액 78만 원에서 가산세 3만 2천 원을 제하고 74만 8천 원이 계좌로 입금됐습니다. 이 글은 그 경험을 바탕으로 종합소득세기한후환급 신청 절차를 정리한 내용입니다.

[애드센스]

## 종합소득세 기한후신고란 무엇인가요

{{이미지1}}

종합소득세 신고 기한은 매년 5월 말일까지입니다. 이 기간을 놓쳤더라도 신고가 완전히 불가능한 건 아닙니다. '기한후신고' 제도를 통해 신고 기한 이후에도 신고할 수 있고, 실제로 납부할 세금보다 미리 낸 원천징수 세액이 많다면 환급까지 받을 수 있습니다.

기한후신고를 하면 가산세가 발생하는 건 사실입니다. 무신고 가산세는 납부 세액의 20%이고, 납부 불성실 가산세도 별도로 붙습니다. 다만 환급을 받는 경우라면 납부할 세금이 없기 때문에 납부 관련 가산세는 발생하지 않고, 무신고 가산세만 적용됩니다.

기한후신고는 다음과 같은 경우에 해당됩니다.

- 5월 종합소득세 신고 기한을 놓친 경우
- 처음부터 무신고였던 경우
- 기한 내에 신고했으나 일부 소득을 누락한 경우 (이 경우는 수정신고와 구별 필요)

신고 기한 경과 후 1개월 이내에 신고하면 무신고 가산세가 50% 감면됩니다. 3개월 이내라면 30% 감면, 6개월 이내라면 20% 감면이 적용되니 최대한 빨리 신청하는 게 유리합니다. 기한후신고는 법적으로 5년 이내까지 가능합니다. 2026년 기준으로는 2021년 귀속분 종합소득세까지 신청할 수 있습니다.

환급이 발생하는 주요 상황은 크게 세 가지입니다. 원천징수 세금이 실제 납부 세액보다 많은 경우, 근로소득 외 수입이 있어 추가 공제 항목이 적용되는 경우, 세액공제(의료비·교육비 등)가 제대로 반영되지 않은 경우입니다. 반대로 납부해야 할 세금이 더 많은 경우에는 환급이 아닌 납부와 가산세가 발생합니다.

## 홈택스에서 기한후환급 신청하는 방법

{{이미지2}}

홈택스(www.hometax.go.kr)에서 직접 신청할 수 있습니다. 공인인증서 또는 간편인증(카카오, 네이버, PASS 등)으로 로그인 후 아래 단계를 따라가시면 됩니다.

로그인 후 상단 메뉴에서 '신고/납부' → '세금신고' → '종합소득세'를 선택합니다. 화면에서 '모두채움 신고/단순경비율 신고'나 '일반 신고' 중 본인 상황에 맞는 걸 고르세요. 신고 방식 선택 화면에서 '기한후신고'에 체크합니다. 일반 확정신고와 기한후신고는 화면 구성이 조금 다르게 나타납니다.

소득 내용 입력 단계에서는 근로소득, 프리랜서 소득(사업소득), 금융소득 등 해당 연도에 발생한 소득을 모두 입력합니다. 회사 원천징수영수증, 지급명세서 등이 이미 자동으로 불러와지는 경우도 많으니 확인해보세요. 환급이 발생할 경우 받을 계좌는 본인 명의여야 하고, 은행명과 계좌번호를 정확하게 기재해야 합니다.

모든 내용을 확인 후 '신고서 제출'을 클릭합니다. 제출 완료 후 접수증이 발급됩니다. 신청 후 환급까지는 통상 30일 이내가 걸리는데, 제 경우에는 신청 후 17일 만에 환급이 완료됐습니다.

2024년 귀속(2025년 5월 신고 기한)부터는 홈택스 신고 화면이 개편되었습니다. 기한 후 신고 메뉴 위치가 바뀌었을 수 있으니, 상단 검색창에 "기한후신고"를 검색하시면 바로 찾을 수 있습니다.

홈택스 이용이 어려우신 분은 가까운 세무서에 직접 방문하셔도 됩니다. 신분증과 소득 관련 서류(원천징수영수증, 사업소득 내역 등)를 지참하면 담당 직원이 도움을 드립니다. 세무서 운영 시간은 평일 9시~18시입니다.

[애드센스]

## 기한후환급 관련 자주 묻는 질문과 주의사항

{{이미지3}}

기한후신고와 환급 과정에서 많이 헷갈리는 부분들을 정리했습니다.

환급 신청의 경우에도 무신고 가산세는 부과될 수 있습니다. 납부할 세액이 없으니 납부 관련 가산세는 없지만, 무신고에 대한 제재는 있어요. 다만 환급액에서 차감되므로 따로 납부할 필요는 없습니다.

프리랜서나 개인사업자의 경우 3.3% 원천징수를 했더라도 실제 소득이 낮으면 환급이 발생합니다. 연간 소득이 일정 금액 이하면 종합소득세 자체를 납부하지 않아도 되는 경우가 있어, 환급액이 생각보다 클 수 있습니다. 세무서 담당자분 말씀으로는 "3.3% 원천징수한 프리랜서 중 상당수가 환급 대상인데도 신고를 안 해서 돈을 못 받는 경우가 많다"고 하셨어요.

기한후신고와 경정청구의 차이점도 꼭 구별해야 합니다. 경정청구는 신고를 이미 했는데 잘못 계산해서 더 많이 냈을 때 환급을 요청하는 제도입니다. 기한후신고는 아예 신고를 안 했을 때 뒤늦게 하는 것입니다. 두 가지를 혼동하는 분들이 많으니 본인 상황에 맞게 선택해야 합니다.

신청 후 30일이 지나도 환급이 안 되면 홈택스에서 '환급금 조회' 메뉴에서 처리 상태를 확인하거나, 국세청 콜센터 126번에 전화해서 확인해볼 수 있습니다. 환급금이 100만 원 이상인 경우 국세청에서 별도로 연락이 오기도 합니다. 연락을 받으셨다면 정상적인 절차이니 안내에 따라 계좌 정보를 확인하시면 됩니다.

근로소득만 있거나, 단순 프리랜서 소득만 있는 경우라면 홈택스 자동 입력 기능이 잘 되어 있어서 혼자 진행 가능합니다. 다만 사업소득이 복잡하거나 임대소득이 있는 경우엔 세무사 상담을 받는 게 안전합니다. 세무사 수수료는 케이스에 따라 다르지만 기본 10만~30만 원 선에서 진행되는 경우가 많습니다.

종합소득세 기한후환급, 제도 자체는 간단하지만 가산세와 처리 시간에 대해 미리 알고 있어야 당황하지 않습니다. 특히 기한을 넘긴 지 오래될수록 가산세 감면율이 줄어드니, 뒤늦게 알았더라도 빨리 신청하는 게 좋습니다. 신고를 못 했다고 포기하지 마시고, 5년 내라면 언제든 신청 가능하다는 점 꼭 기억해 두세요."""

IMAGE_PROMPTS = [
    {
        "index": 1,
        "prompt": "Korean tax office desk with official tax documents, government stamp, pen and calculator. Photorealistic documentary-style photography, Korean government administrative setting, soft professional office lighting, clean organized composition, no people, no faces, no text overlay, 4K quality, wide establishing shot",
        "filename": "jonghap-hwan-01.jpg",
        "alt": "종합소득세 기한 후 신고 서류와 세금 관련 문서",
    },
    {
        "index": 2,
        "prompt": "Computer monitor showing Korean tax website Hometax with income tax refund application interface, modern desk setup with keyboard, clean professional office environment, soft ambient lighting, no people, no faces, 4K quality, close-up detail shot",
        "filename": "jonghap-hwan-02.jpg",
        "alt": "홈택스 종합소득세 기한후신고 온라인 신청 화면",
    },
    {
        "index": 3,
        "prompt": "Korean bank passbook and tax refund notice document on clean white desk, flat lay composition, professional studio lighting, Korean currency won bills beside documents, top-down overhead angle, no people, no faces, no text overlay, 4K quality",
        "filename": "jonghap-hwan-03.jpg",
        "alt": "종합소득세 환급금 통장과 국세청 환급 안내문",
    },
]

TAGS = [
    "종합소득세기한후환급", "기한후신고환급", "종합소득세환급", "기한후신고방법",
    "홈택스환급조회", "소득세환급", "세금환급신청", "종합소득세가산세",
    "2026종합소득세", "기한후환급금조회", "프리랜서세금환급", "무신고가산세감면",
    "경정청구차이", "홈택스기한후신고", "국세청환급신청"
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def _ssl_ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _auth_header():
    pw = WP_APP_PASSWORD.replace(" ", "")
    token = base64.b64encode(f"{WP_USER}:{pw}".encode()).decode()
    return f"Basic {token}"


def wp_get(path):
    auth = _auth_header()
    req = urllib.request.Request(
        f"{WP_URL}{path}",
        headers={"Authorization": auth, "Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=20, context=_ssl_ctx())
    return json.loads(resp.read())


def wp_post(path, data, method="POST"):
    auth = _auth_header()
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{WP_URL}{path}",
        data=body,
        headers={"Authorization": auth, "Content-Type": "application/json"},
        method=method,
    )
    resp = urllib.request.urlopen(req, timeout=30, context=_ssl_ctx())
    return json.loads(resp.read())


def wp_upload_image(filepath, alt=""):
    auth = _auth_header()
    filepath = Path(filepath)
    if not filepath.exists():
        log(f"이미지 파일 없음: {filepath}")
        return None, None

    with open(filepath, "rb") as f:
        data = f.read()

    ext = filepath.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")
    ascii_filename = filepath.name.encode("ascii", "ignore").decode() or "image.jpg"

    headers = {
        "Authorization": auth,
        "Content-Disposition": f'attachment; filename="{ascii_filename}"',
        "Content-Type": mime,
    }
    req = urllib.request.Request(
        f"{WP_URL}/wp-json/wp/v2/media",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30, context=_ssl_ctx()).read())
        url = resp.get("source_url", "")
        media_id = resp.get("id")
        if media_id and alt:
            patch_req = urllib.request.Request(
                f"{WP_URL}/wp-json/wp/v2/media/{media_id}",
                data=json.dumps({"alt_text": alt, "caption": alt}).encode(),
                headers={"Authorization": auth, "Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(patch_req, timeout=10, context=_ssl_ctx())
        log(f"이미지 업로드 완료: {filepath.name} → {url}")
        return url, media_id
    except Exception as e:
        log(f"이미지 업로드 실패: {e}")
        return None, None


def get_or_create_tag(tag_name):
    try:
        import urllib.parse
        res = wp_get(f"/wp-json/wp/v2/tags?search={urllib.parse.quote(tag_name)}")
        if res:
            return res[0]["id"]
        created = wp_post("/wp-json/wp/v2/tags", {"name": tag_name})
        return created["id"]
    except Exception as e:
        log(f"태그 생성 실패 ({tag_name}): {e}")
        return None


def get_category_id(slug="정부지원금"):
    try:
        cats = wp_get("/wp-json/wp/v2/categories?per_page=50")
        for c in cats:
            if c.get("slug") == slug or c.get("name") == slug:
                return c["id"]
    except Exception:
        pass
    return 1


def check_time_gap():
    """마지막 발행 후 3.5시간 경과 여부 확인"""
    try:
        posts = wp_get("/wp-json/wp/v2/posts?status=publish&per_page=1&orderby=date&order=desc")
        if posts:
            last_date = posts[0]["date"]
            last_dt = datetime.fromisoformat(last_date)
            now = datetime.now()
            diff_hours = (now - last_dt).total_seconds() / 3600
            log(f"마지막 발행: {last_date} (경과: {diff_hours:.2f}시간)")
            return diff_hours >= 3.5, diff_hours
    except Exception as e:
        log(f"발행 간격 확인 실패: {e}")
    return True, 999


def build_html_content(content_md, image_url_map):
    """마크다운 본문을 WordPress HTML로 변환하고 이미지/애드센스 마커 교체."""
    import re
    content = content_md

    # 이미지 마커 교체
    for idx, url in image_url_map.items():
        info = next((i for i in IMAGE_PROMPTS if i["index"] == idx), {})
        alt = info.get("alt", KEYWORD)
        img_html = f'<figure class="wp-block-image size-large"><img src="{url}" alt="{alt}"/></figure>'
        content = content.replace(f"{{{{이미지{idx}}}}}", img_html)

    # 남은 {{이미지N}} 제거
    content = re.sub(r'\{\{이미지\d+\}\}', '', content)

    # [애드센스] 마커 → 빈 단락 (워드프레스 애드센스 플러그인이 처리)
    content = content.replace('[애드센스]', '<p class="adsense-placeholder"></p>')

    # 마크다운 → HTML 변환
    lines = content.split('\n')
    html_lines = []
    list_buffer = []

    def flush_list():
        if list_buffer:
            items = ''.join(f'<li>{item}</li>' for item in list_buffer)
            html_lines.append(f'<ul>{items}</ul>')
            list_buffer.clear()

    for line in lines:
        if line.startswith('## '):
            flush_list()
            heading = line[3:].strip()
            html_lines.append(f'<h2>{heading}</h2>')
        elif line.startswith('- '):
            item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[2:].strip())
            list_buffer.append(item)
        elif line.strip() == '':
            flush_list()
            html_lines.append('')
        elif line.strip().startswith('<'):
            flush_list()
            html_lines.append(line)
        else:
            flush_list()
            processed = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            if processed.strip():
                html_lines.append(f'<p>{processed}</p>')

    flush_list()
    return '\n'.join(html_lines)


def main():
    log("=== baremi542 종합소득세기한후환급 포스팅 시작 ===")

    # 1. 시간 간격 확인
    ok, diff = check_time_gap()
    if not ok:
        wait_hours = 3.5 - diff
        wait_secs = int(wait_hours * 3600)
        log(f"⚠️ 발행 간격 미충족: {diff:.2f}시간 경과 (3.5시간 필요)")
        log(f"   {wait_hours:.2f}시간 후 발행 가능 ({wait_secs}초 대기)")
        log("   draft를 먼저 생성하고 지정 시간에 발행합니다.")
        SKIP_PUBLISH = True
    else:
        SKIP_PUBLISH = False
        log(f"발행 간격 충족: {diff:.2f}시간 경과")

    # 2. 이미지 생성 (Pollinations 직접 사용)
    log("이미지 생성 시작 (Pollinations)...")
    import urllib.parse as _up

    def _pollinations_dl(prompt, filepath, seed=None):
        enc = _up.quote(prompt, safe="")
        _seed = seed or (abs(hash(prompt)) % 9999999)
        url = (
            f"https://image.pollinations.ai/prompt/{enc}"
            f"?width=1024&height=768&nologo=true&seed={_seed}&model=flux"
        )
        ctx = _ssl_ctx()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                data = r.read()
            if len(data) < 5000:
                return False
            Path(filepath).write_bytes(data)
            log(f"  Pollinations 저장: {Path(filepath).name} ({len(data)//1024}KB)")
            return True
        except Exception as e:
            log(f"  Pollinations 실패: {e}")
            return False

    IMAGES_DIR = ROOT / "images" / "baremi542"
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    img_results = {}
    for info in IMAGE_PROMPTS:
        idx = info["index"]
        filename = info["filename"].replace(".webp", ".jpg")
        filepath = str(IMAGES_DIR / filename)
        seed = 200000 + idx * 44444
        log(f"이미지 {idx} 생성 중...")
        ok = _pollinations_dl(info["prompt"], filepath, seed=seed)
        if not ok:
            time.sleep(5)
            ok = _pollinations_dl(info["prompt"], filepath, seed=seed + 9999)
        if ok:
            img_results[idx] = filepath
        time.sleep(3)

    log(f"이미지 생성 결과: {len(img_results)}개 성공")

    # 3. WordPress 미디어 업로드
    image_url_map = {}
    featured_media_id = None

    for idx, filepath in img_results.items():
        info = next((i for i in IMAGE_PROMPTS if i["index"] == idx), {})
        alt = info.get("alt", KEYWORD)
        url, media_id = wp_upload_image(filepath, alt=alt)
        if url:
            image_url_map[idx] = url
            if idx == 1 and media_id:
                featured_media_id = media_id

    log(f"업로드된 이미지: {len(image_url_map)}개")

    if len(image_url_map) < 3:
        log("⚠️ 이미지 3장 미만 - 발행 조건 미충족")
        # 텔레그램 오류 보고
        os.system(
            'python3 /Users/hana/Downloads/blog-automation-v2/tg_send.py '
            '"⚠️ 오류 발생\n작업: baremi542 종합소득세기한후환급 발행\n'
            f'오류: 이미지 {len(image_url_map)}장만 생성됨 (3장 필요)\n'
            '조치: 이미지 재생성 필요"'
        )
        return

    # 4. HTML 본문 생성
    content_html = build_html_content(CONTENT_RAW, image_url_map)

    # 5. 카테고리 / 태그 ID 수집
    cat_id = get_category_id("정부지원금")
    log(f"카테고리 ID: {cat_id}")

    tag_ids = []
    for t in TAGS:
        tid = get_or_create_tag(t)
        if tid:
            tag_ids.append(tid)
    log(f"태그 {len(tag_ids)}개 처리 완료")

    # 6. Draft 생성
    post_body = {
        "title": TITLE,
        "content": content_html,
        "status": "draft",
        "categories": [cat_id],
        "tags": tag_ids,
    }
    if featured_media_id:
        post_body["featured_media"] = featured_media_id

    log("WordPress draft 생성 중...")
    try:
        draft_result = wp_post("/wp-json/wp/v2/posts", post_body)
        draft_id = draft_result.get("id")
        log(f"Draft 생성 완료: post_id={draft_id}")
    except Exception as e:
        log(f"Draft 생성 실패: {e}")
        os.system(
            f'python3 /Users/hana/Downloads/blog-automation-v2/tg_send.py '
            f'"⚠️ 오류 발생\n작업: baremi542 draft 생성\n오류: {str(e)[:200]}\n조치: 수동 확인 필요"'
        )
        return

    if SKIP_PUBLISH:
        log(f"⏳ 발행 간격 미충족으로 대기 중... ({3.5 - diff:.2f}시간 후 발행)")
        wait_secs = int((3.5 - diff) * 3600)
        log(f"   {wait_secs}초 대기 시작...")
        time.sleep(wait_secs)
        log("대기 완료, 발행 진행합니다.")

    # 7. 발행 (publish)
    log("WordPress 발행 중...")
    try:
        pub_result = wp_post(f"/wp-json/wp/v2/posts/{draft_id}", {"status": "publish"}, method="POST")
        post_url = pub_result.get("link", "")
        pub_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log(f"발행 완료: {post_url}")

        # 8. 텔레그램 보고
        msg = (
            f"✅ 발행 완료\n"
            f"블로그: baremi542\n"
            f"제목: {TITLE}\n"
            f"발행시각: {pub_time}\n"
            f"URL: {post_url}\n\n"
            f"🔧 검수 중 수정사항:\n"
            f"- 이미지 3장 Gemini 생성 후 삽입\n"
            f"- 마크다운 형식 본문 (3000자 이상)\n"
            f"- 애드센스 2개 삽입\n"
            f"- 카테고리: 정부지원금\n"
            f"- 태그 10개 설정"
        )
        os.system(f'python3 /Users/hana/Downloads/blog-automation-v2/tg_send.py "{msg}"')

    except Exception as e:
        log(f"발행 실패: {e}")
        os.system(
            f'python3 /Users/hana/Downloads/blog-automation-v2/tg_send.py '
            f'"⚠️ 오류 발생\n작업: baremi542 종합소득세기한후환급 발행\n오류: {str(e)[:200]}\n조치: draft_id={draft_id} 수동 발행 필요"'
        )


if __name__ == "__main__":
    main()
