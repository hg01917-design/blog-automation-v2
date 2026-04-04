"""야간 자동 실행 — 키워드 수집 → 글 생성 → 포스팅"""
import os
import re
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "overnight_result.txt"

# .env 로드
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

logs = []


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    logs.append(line)


def save_log():
    LOG_FILE.write_text("\n".join(logs), encoding="utf-8")
    log(f"로그 저장: {LOG_FILE}")


def _send_telegram(msg: str):
    """Telegram 메시지 전송 (.env의 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 사용)"""
    try:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not bot_token or not chat_id:
            return
        payload = json.dumps({"chat_id": chat_id, "text": msg}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"[Telegram] 전송 실패: {e}")


# ─── Notion 키워드 큐에서 대기 키워드 가져오기 ───
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_API = "https://api.notion.com/v1"
KEYWORD_DB_ID = "d6bb5b753f1b4963891de02427411276"


def _notion_headers():
    token = os.environ.get("NOTION_TOKEN") or NOTION_TOKEN
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def fetch_next_keyword(blog_id):
    """Notion 키워드 큐에서 blog_id의 '대기' 상태 키워드 1개 가져오기"""
    body = {
        "filter": {
            "and": [
                {"property": "블로그", "select": {"equals": blog_id}},
                {"property": "상태", "select": {"equals": "대기"}},
            ]
        },
        "sorts": [{"property": "검색량", "direction": "descending"}],
        "page_size": 1,
    }
    req = urllib.request.Request(
        f"{NOTION_API}/databases/{KEYWORD_DB_ID}/query",
        data=json.dumps(body).encode(),
        headers=_notion_headers(),
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return None, None
        page = results[0]
        page_id = page["id"]
        props = page.get("properties", {})
        for prop_name in ["키워드", "Name", "name", "제목"]:
            prop = props.get(prop_name, {})
            if prop.get("type") == "title":
                texts = prop.get("title", [])
                if texts:
                    return texts[0].get("plain_text", ""), page_id
        return None, None
    except Exception as e:
        log(f"[Notion] 키워드 가져오기 실패: {e}")
        return None, None


def fetch_failed_keywords(blog_id):
    """Notion 키워드 큐에서 blog_id의 '실패' 상태 키워드 전체 가져오기.

    Returns: list of (keyword: str, page_id: str)
    """
    body = {
        "filter": {
            "and": [
                {"property": "블로그", "select": {"equals": blog_id}},
                {"property": "상태", "select": {"equals": "실패"}},
            ]
        },
        "sorts": [{"property": "검색량", "direction": "descending"}],
        "page_size": 50,
    }
    req = urllib.request.Request(
        f"{NOTION_API}/databases/{KEYWORD_DB_ID}/query",
        data=json.dumps(body).encode(),
        headers=_notion_headers(),
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        results = data.get("results", [])
        keywords = []
        for page in results:
            page_id = page["id"]
            props = page.get("properties", {})
            for prop_name in ["키워드", "Name", "name", "제목"]:
                prop = props.get(prop_name, {})
                if prop.get("type") == "title":
                    texts = prop.get("title", [])
                    if texts:
                        keywords.append((texts[0].get("plain_text", ""), page_id))
                        break
        return keywords
    except Exception as e:
        log(f"[Notion] 실패 키워드 조회 실패: {e}")
        return []


# ─── 블로그 테마 적합성 검사 ───
_BLOG_THEMES = {
    "nolja100": ["여행", "관광", "숙소", "맛집", "코스", "캠핑", "펜션", "호텔", "드라이브",
                 "당일치기", "트레킹", "등산", "해수욕", "바다", "산", "계곡", "레저", "축제",
                 "케이블카", "한옥", "올레길", "둘레길", "차박", "글램핑", "리조트"],
    "salim1su": ["살림", "절약", "가스", "전기", "요금", "주방", "청소", "정리", "수납",
                 "가계", "생활비", "난방", "냉방", "가전", "요리", "레시피", "기름때",
                 "세탁", "빨래", "냉장고", "에어컨", "보일러", "다이소",
                 "화장실", "욕실", "물때", "곰팡이", "집안", "먼지", "바닥", "베란다",
                 "주부", "신혼", "인테리어", "수납", "정돈", "소독", "탈취", "제거",
                 "관리비", "수도", "가습기", "건조기", "식기", "행주", "찌든"],
    "baremi542": ["지원금", "보조금", "지원사업", "복지", "수당", "혜택", "신청", "환급",
                  "정부", "공공", "보험", "연금", "청년", "취업", "바우처", "감면"],
    "triplog": ["호텔", "항공", "맛집", "국내여행", "해외여행", "여행", "숙소", "리조트",
                "투어", "관광", "비행기", "티켓", "패키지", "배낭여행", "자유여행",
                "가볼만한", "여행지", "추천", "코스", "일정", "경비", "항공권", "렌터카"],
}


def is_keyword_suitable(blog_id: str, keyword: str) -> bool:
    """키워드가 블로그 테마에 적합한지 확인"""
    theme_words = _BLOG_THEMES.get(blog_id)
    if not theme_words:
        return True
    return any(w in keyword for w in theme_words)


def update_keyword_status(page_id, status, memo=None):
    """Notion 키워드 상태 업데이트 (메모 옵션)"""
    props = {"상태": {"select": {"name": status}}}
    if memo:
        props["메모"] = {"rich_text": [{"text": {"content": memo}}]}
    body = {"properties": props}
    req = urllib.request.Request(
        f"{NOTION_API}/pages/{page_id}",
        data=json.dumps(body).encode(),
        headers=_notion_headers(),
        method="PATCH",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"[Notion] 상태 업데이트 실패: {e}")


def _extract_core_words(keyword):
    """키워드에서 핵심 단어를 추출한다.

    예: "도시가스 요금 절약" → ["도시가스", "요금", "절약"]
    1글자 단어, 조사, 일반 접속사는 제외.
    """
    STOP_WORDS = {
        '방법', '추천', '정리', '비교', '후기', '종류', '가이드',
        '및', '또는', '그리고', '하는', '위한', '대한', '좋은', '최고',
        '가장', '진짜', '완벽', '꿀팁', '팁', '꿀',
    }
    words = keyword.split()
    core = [w for w in words if len(w) >= 2 and w not in STOP_WORDS]
    return core if core else words[:2]


def check_keyword_duplicate_in_notion(blog_id, keyword):
    """노션 큐에서 이미 완료된 유사 키워드가 있는지 확인한다.

    한 키워드가 다른 키워드를 포함하거나(부분 문자열) 핵심 단어가 겹치면 중복으로 판단.
    예: "실업급여" ↔ "실업급여 계산기" → 중복
    """
    body = {
        "filter": {
            "and": [
                {"property": "블로그", "select": {"equals": blog_id}},
                {"property": "상태", "select": {"equals": "완료"}},
            ]
        },
        "page_size": 100,
    }
    req = urllib.request.Request(
        f"{NOTION_API}/databases/{KEYWORD_DB_ID}/query",
        data=json.dumps(body).encode(),
        headers=_notion_headers(),
        method="POST",
    )
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        done_keywords = []
        for page in data.get("results", []):
            props = page.get("properties", {})
            for prop_name in ["키워드", "Name", "name", "제목"]:
                prop = props.get(prop_name, {})
                if prop.get("type") == "title":
                    texts = prop.get("title", [])
                    if texts:
                        done_keywords.append(texts[0].get("plain_text", ""))
                        break

        kw_words = set(keyword.split())
        for done in done_keywords:
            done_words = set(done.split())
            # 공백 제거 후 완전 동일 (예: "실업급여계산기" == "실업급여 계산기")
            if keyword.replace(" ", "") == done.replace(" ", ""):
                return True, done
            # 단어 단위로 한 쪽이 다른 쪽의 완전한 부분집합 (예: {"실업급여"} ⊂ {"실업급여","계산기"})
            # 단, 단어가 1개짜리 키워드는 제외 (너무 광범위한 차단 방지)
            if len(kw_words) >= 2 and kw_words <= done_words:
                return True, done
            if len(done_words) >= 2 and done_words <= kw_words:
                return True, done
        return False, None
    except Exception:
        return False, None


def check_duplicate_post(blog_id, keyword, on_log=None):
    """네이버 블로그에서 유사 주제 글이 이미 있는지 확인한다.

    핵심 단어로 블로그 내 검색 → 기존 글 제목에 핵심 단어가 포함되면 중복.
    Returns: (is_duplicate: bool, matched_title: str or None)
    """
    def _log(msg):
        if on_log:
            on_log(msg)

    core_words = _extract_core_words(keyword)
    _log(f"[유사문서] 핵심 단어: {core_words}")

    # 네이버 블로그 검색 API (RSS)
    search_query = "+".join(core_words)
    search_url = (
        f"https://blog.naver.com/PostSearchList.naver?"
        f"blogId={blog_id}&searchText={urllib.parse.quote(search_query)}"
        f"&orderType=sim&directAccess=false"
    )

    try:
        req = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="ignore")

        # 글 제목 추출 (네이버 블로그 검색 결과 HTML에서)
        titles = re.findall(r'<span class="ell">(.*?)</span>', html)
        if not titles:
            titles = re.findall(r'class="pcol2"[^>]*>(.*?)</a>', html)
        if not titles:
            titles = re.findall(r'title="([^"]+)"', html)

        # HTML 태그 제거
        clean_titles = [re.sub(r'<[^>]+>', '', t).strip() for t in titles]
        clean_titles = [t for t in clean_titles if len(t) > 5]

        _log(f"[유사문서] {blog_id} 검색 결과: {len(clean_titles)}개 글")

        # 핵심 단어 2개 이상 포함된 제목이 있으면 중복
        for t in clean_titles[:10]:
            match_count = sum(1 for w in core_words if w in t)
            if match_count >= 2 or (len(core_words) == 1 and match_count >= 1):
                _log(f"[유사문서] ⚠ 유사 글 발견: \"{t}\"")
                _log(f"[유사문서] 매칭 단어: {[w for w in core_words if w in t]}")
                return True, t

        _log(f"[유사문서] 유사 글 없음 — 진행 가능")
        return False, None

    except Exception as e:
        _log(f"[유사문서] 검색 실패: {e} — 안전하게 진행")
        return False, None


def _truncate_title(title, max_len=40):
    """제목을 max_len자(기본 40자) 이내로 자른다.

    40자 초과 시:
    1. 구두점(.?!)에서 자르기 (20~40자 범위)
    2. 공백(띄어쓰기)에서 자르기 — 명사 뒤 단어 경계
    3. 조사/접속사 뒤면 한 단어 더 앞으로 (은/는/이/가/을/를/에/의/로/와/과/도/만)
    4. 그래도 없으면 max_len자 강제 자르기
    """
    # 본문 혼입 방지: 줄바꿈이 있으면 첫 줄만
    title = title.split('\n')[0].strip()

    if len(title) <= max_len:
        return title

    # 1. 20~max_len 범위에서 마지막 구두점 찾기
    for i in range(min(max_len, len(title)) - 1, 19, -1):
        if title[i] in '.?!。？！':
            return title[:i + 1]

    # 2. 공백(단어 경계)에서 자르기 — 조사 뒤 자르기 방지
    # 한국어 조사 패턴: 1~2글자 (은,는,이,가,을,를,에,의,로,와,과,도,만,에서,으로,까지,부터)
    JOSA = {'은', '는', '이', '가', '을', '를', '에', '의', '로', '와', '과',
            '도', '만', '에서', '으로', '까지', '부터', '에게', '한테', '처럼'}

    # max_len 이내에서 마지막 공백 위치들 (뒤에서부터)
    for i in range(min(max_len, len(title)) - 1, 14, -1):
        if title[i] == ' ':
            # 공백 앞 단어가 조사인지 확인
            before_space = title[:i]
            last_word = before_space.split()[-1] if before_space.split() else ""
            if last_word in JOSA:
                continue  # 조사 뒤에서 자르면 어색 → 건너뜀
            return title[:i]

    # 3. 강제 자르기
    return title[:max_len]


# ─── 전체 포스팅 파이프라인 ───
def run_posting_pipeline(blog_id, keyword, page_id=None):
    """유사문서 체크 → 글 생성 → 이미지 → 포스팅 전체 파이프라인

    page_id가 주어지면 유사문서 발견 시 Notion 상태를 '실패'로 변경.
    """
    from claude_playwright import generate_text
    from gemini_image import generate_images
    from poster import post_single

    # 0-2. 유사문서 체크 (블로그 내 기존 글)
    log(f"[파이프라인] {blog_id} / '{keyword}' — 유사문서 체크")
    is_dup, matched = check_duplicate_post(blog_id, keyword, on_log=log)
    if is_dup:
        log(f"[파이프라인] ⚠ 유사문서 발견 — 키워드 '{keyword}' 건너뜀")
        if page_id:
            update_keyword_status(page_id, "실패", memo=f"유사문서: {matched[:30]}")
        return False

    # 1. Claude.ai 글 생성
    log(f"[파이프라인] {blog_id} / '{keyword}' — Claude.ai 글 생성 시작")
    raw = generate_text("", blog_id=blog_id, keyword=keyword, on_log=log)

    if not raw or "추출 실패" in raw:
        log(f"[파이프라인] 글 생성 실패")
        return False

    # 2. 파싱 — 각 섹션 정확히 분리
    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)

    # 제목: ===제목===~===제목끝=== 사이에서 첫 줄만 추출 + 40자 제한
    if title_m:
        title_block = title_m.group(1).strip()
        raw_title = title_block.split('\n')[0].strip()
    else:
        raw_title = keyword
    title = _truncate_title(raw_title, max_len=40)

    body = body_m.group(1).strip() if body_m else raw

    # 품질 검수 체크리스트가 본문에 포함된 경우 제거
    body = re.sub(
        r'\n*항목기준충족.*$', '', body,
        flags=re.DOTALL
    ).strip()
    # ===검수=== 섹션이 본문 내 포함된 경우 제거
    body = re.sub(r'\n*===검수===.*?(?:===검수끝===|$)', '', body, flags=re.DOTALL).strip()
    # ✅/❌ 로 시작하는 체크리스트 줄 제거
    body = re.sub(r'\n[✅❌☑️].{0,60}(?:\n[✅❌☑️].{0,60}){2,}', '', body).strip()
    # [검증 필요], [출처 필요], [사실 확인] 등 내부 마커 제거
    body = re.sub(r'\[검증\s*필요\]|\[출처\s*필요\]|\[사실\s*확인\]|\[확인\s*필요\]', '', body).strip()

    # 태그: 첫 줄만 (여러 줄이면 첫 줄의 쉼표 구분)
    if tag_m:
        tag_line = tag_m.group(1).strip().split('\n')[0].strip()
        tags = [t.strip() for t in tag_line.split(",") if t.strip()]
    else:
        tags = [keyword]

    images = []
    # 이미지 섹션 미발견 시 raw에서 직접 탐색 (===본문=== 내부에 포함된 경우 대응)
    if not img_m:
        img_m = re.search(r"===이미지===\s*(.*?)\s*===이미지끝===", raw, re.DOTALL)
    if not img_m:
        # 디버그: raw에 ===이미지=== 텍스트가 있는지 확인
        if "이미지" in raw:
            idx = raw.find("이미지")
            log(f"[파싱] ⚠ ===이미지=== 섹션 불일치. 'raw' 내 '이미지' 주변: {repr(raw[max(0,idx-10):idx+80])}")
        else:
            log(f"[파싱] ⚠ raw에 '이미지' 텍스트 없음. raw 끝 200자: {repr(raw[-200:])}")
    if img_m:
        img_text = img_m.group(1)
        log(f"[파싱] 이미지 섹션 발견 (길이={len(img_text)}자), 내용: {repr(img_text[:300])}")
        for m in re.finditer(
            r"\[이미지\s*(\d+)\]\s*[-\n]*\s*(?:Gemini\s*)?프롬프트:\s*(.+?)[\n\r]+-\s*파일명:\s*(.+?)[\n\r]+-\s*alt:\s*(.+?)(?=\[이미지|\Z)",
            img_text,
            re.DOTALL,
        ):
            images.append({
                "index": int(m.group(1)),
                "prompt": m.group(2).strip(),
                "filename": m.group(3).strip(),
                "alt": m.group(4).strip(),
            })
        if not images:
            # 더 단순한 fallback 파싱: 각 [이미지N] 블록을 찾아 필드 추출
            for block in re.findall(r"\[이미지\s*\d+\][^\[]+", img_text, re.DOTALL):
                n_m = re.search(r"\[이미지\s*(\d+)\]", block)
                p_m = re.search(r"프롬프트:\s*(.+)", block)
                f_m = re.search(r"파일명:\s*(.+)", block)
                a_m = re.search(r"alt:\s*(.+)", block)
                if n_m and p_m:
                    images.append({
                        "index": int(n_m.group(1)),
                        "prompt": p_m.group(1).strip(),
                        "filename": f_m.group(1).strip() if f_m else f"image-{n_m.group(1)}.jpg",
                        "alt": a_m.group(1).strip() if a_m else "",
                    })

    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
    char_count = len(re.sub(r"\s+", "", plain))

    # 파싱 결과 검증 로그
    log(f"[파싱] 제목: \"{title}\" ({len(title)}자)")
    log(f"[파싱] 본문: {char_count}자")
    log(f"[파싱] 태그: {tags} ({len(tags)}개)")
    log(f"[파싱] 이미지: {len(images)}개")
    if len(title) == 0:
        log("[파싱] ⚠ 제목이 비어있음 — 키워드로 대체")
        title = keyword
    if char_count < 100:
        log(f"[파싱] ⚠ 본문이 너무 짧음 ({char_count}자)")
    log(f"[파싱] 본문 미리보기: {body[:80]}...")

    MIN_IMAGES = 3

    # 3. 글 품질 검수 (이미지 생성 전에 먼저 — Gemini 쿼터 낭비 방지)
    quality_ok = True
    if char_count < 1700:
        log(f"[검수] ❌ 본문 너무 짧음 ({char_count}자 < 1700자) — 발행 중단")
        quality_ok = False
    if not tags:
        log(f"[검수] ❌ 태그 없음 — 발행 중단")
        quality_ok = False
    if not quality_ok:
        return False
    log(f"[검수] ✅ 글 품질 통과 — 본문 {char_count}자, 태그 {len(tags)}개")

    # 4. Gemini 이미지 생성 (검수 통과 후에만 실행)
    image_paths = {}
    if images:
        log(f"[파이프라인] Gemini 이미지 생성 시작")
        image_paths = generate_images(images, on_log=log)
        log(f"[파이프라인] 이미지 {len(image_paths)}개 생성 완료")

    # 4-1. 이미지 최소 3장 보장 — 부족하면 loremflickr 폴백 보충
    if len(image_paths) < MIN_IMAGES:
        log(f"[파이프라인] ⚠ 이미지 {len(image_paths)}개 < 최소 {MIN_IMAGES}개 — loremflickr 폴백 보충")
        from gemini_image import _generate_via_fallback
        extra_prompts = [keyword, f"{keyword} 관련 정보", f"{keyword} 생활 팁"]
        for i in range(len(image_paths), MIN_IMAGES):
            kw_fb = extra_prompts[i % len(extra_prompts)]
            fname = f"fallback_{blog_id}_{i+1}.jpg"
            fp = _generate_via_fallback(kw_fb, fname, on_log=log)
            if fp:
                images.append({"index": len(images)+1, "prompt": kw_fb, "filename": fname, "alt": kw_fb})
                image_paths[fname] = fp
        log(f"[파이프라인] 이미지 보충 후 총 {len(image_paths)}개")

    if len(image_paths) < MIN_IMAGES:
        log(f"[검수] ❌ 이미지 부족 ({len(image_paths)}개 < {MIN_IMAGES}개) — 발행 중단")
        return False
    log(f"[검수] ✅ 이미지 {len(image_paths)}개 확인")

    # 4. 포스팅
    log(f"[파이프라인] 포스팅 시작: {blog_id}")
    ok = post_single(
        blog_id=blog_id,
        title=title,
        content=body,
        tags=tags,
        image_paths=image_paths,
        image_infos=images,
        on_log=log,
    )

    if ok:
        log(f"[파이프라인] {blog_id} / '{keyword}' 임시저장완료 ✅")
        _send_telegram(
            f"[{blog_id}] 임시저장완료했습니다 ✅\n"
            f"키워드: {keyword}\n"
            f"클로드코드는 검수후 발행해주세요."
        )
    else:
        log(f"[파이프라인] {blog_id} / '{keyword}' 포스팅 실패 ⚠")
    return ok


# ─── 블로그 1편 포스팅 ───
MIN_POST_GAP_HOURS = 3  # 같은 블로그 포스팅 최소 간격


def _hours_since_last_post(blog_id: str) -> float:
    """마지막 published 이후 경과 시간(시간). 발행 이력 없으면 999 반환."""
    from keyword_engine.db_handler import _conn
    with _conn() as db:
        row = db.execute(
            """SELECT updated_at FROM keyword_blog_status
               WHERE blog_id = ? AND status IN ('published', 'draft_saved')
               ORDER BY updated_at DESC LIMIT 1""",
            (blog_id,),
        ).fetchone()
    if not row:
        return 999.0
    from datetime import datetime as _dt
    try:
        last_time = _dt.fromisoformat(row[0])
        return (_dt.now() - last_time).total_seconds() / 3600
    except Exception:
        return 999.0


def post_one_blog(blog_id):
    """한 블로그에 키워드 1개 선택 → 포스팅 (SQLite 키워드 엔진만 사용)"""
    from keyword_engine.db_handler import fetch_next_pending, set_keyword_status as _db_set

    # 최소 포스팅 간격 체크 (같은 블로그 3시간 이상 텀)
    elapsed = _hours_since_last_post(blog_id)
    if elapsed < MIN_POST_GAP_HOURS:
        log(f"[{blog_id}] 마지막 포스팅 {elapsed:.1f}시간 전 — 최소 {MIN_POST_GAP_HOURS}시간 필요, 스킵")
        return False

    kw = fetch_next_pending(blog_id)
    if kw and not is_keyword_suitable(blog_id, kw):
        log(f"[{blog_id}] ⚠ 테마 부적합 '{kw}' → 스킵")
        _db_set(kw, "failed", blog_id=blog_id)
        kw = None
    if not kw:
        log(f"[{blog_id}] 대기 키워드 없음 — 스킵")
        return False
    log(f"[{blog_id}] 키워드: {kw}")
    _db_set(kw, "in_progress", blog_id=blog_id)
    try:
        ok = run_posting_pipeline(blog_id, kw, page_id=None)
        if ok:
            _db_set(kw, "draft_saved", blog_id=blog_id)
        else:
            _db_set(kw, "failed", blog_id=blog_id)
        return ok
    except Exception as e:
        log(f"[{blog_id}] 오류: {e}")
        _db_set(kw, "failed", blog_id=blog_id)
        return False


def run_one_round(round_num):
    """모든 블로그에 1편씩 포스팅 (1라운드) — 순서 랜덤. 실패 블로그는 1회 재시도."""
    import time as _time
    import random as _rand
    BLOGS = ["nolja100", "salim1su", "baremi542", "goodisak", "triplog"]
    _rand.shuffle(BLOGS)  # 매 라운드 랜덤 순서 (한 블로그 연달아 3개 방지)
    log(f"\n{'='*60}")
    log(f"[라운드 {round_num}] 시작 ({datetime.now().strftime('%H:%M')})")
    log(f"{'='*60}")
    results = {}
    for blog_id in BLOGS:
        ok = post_one_blog(blog_id)
        results[blog_id] = "✅" if ok else "⚠"
        # 블로그 간 1-3분 랜덤 대기 (사람처럼)
        _time.sleep(_rand.uniform(60, 180))
    log(f"[라운드 {round_num}] 완료: " + " / ".join(f"{k}:{v}" for k, v in results.items()))
    save_log()

    # ── 실패 블로그 즉시 재시도 (1회) ──
    failed = [b for b, s in results.items() if s == "⚠"]
    if failed:
        log(f"[라운드 {round_num}] 실패 블로그 재시도: {failed}")
        _time.sleep(_rand.uniform(60, 120))  # 1-2분 후 재시도
        for blog_id in failed:
            ok = post_one_blog(blog_id)
            results[blog_id] = "✅" if ok else "⚠"
            _time.sleep(_rand.uniform(30, 90))
        log(f"[라운드 {round_num}] 재시도 결과: " + " / ".join(f"{b}:{results[b]}" for b in failed))
        save_log()


# ─── 메인 실행 ───
if __name__ == "__main__":
    import time as _time
    import random as _random

    log("=" * 60)
    log(f"자동 실행 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 60)

    # ── 화면 잠금/슬립 방지 (macOS caffeinate) ──
    import subprocess as _sub
    try:
        _caffeinate = _sub.Popen(["caffeinate", "-d", "-i", "-s"],
                                 stdout=_sub.DEVNULL, stderr=_sub.DEVNULL)
        log("[시스템] caffeinate 시작 (화면 잠금/슬립 방지)")
    except Exception as _e:
        _caffeinate = None
        log(f"[시스템] caffeinate 실패: {_e}")

    # ── 키워드 크롤링 (1회) ──
    log("[크롤링] salim1su, baremi542 키워드 수집")
    from keyword_crawler import crawl_keywords
    for bid in ["salim1su", "baremi542"]:
        try:
            result = crawl_keywords(blog_id=bid, on_log=log)
            log(f"[크롤링] {bid}: {result.get(bid, 0)}개 저장")
        except Exception as e:
            log(f"[크롤링] {bid} 오류: {e}")
    save_log()

    # ── 경쟁 사이트 모니터링 (월/수/금 실행) ──
    _today_wd = datetime.now().weekday()  # 0=월, 2=수, 4=금
    if _today_wd in (0, 2, 4):
        log("[경쟁모니터] 경쟁 사이트 신규 포스트 감지 시작")
        try:
            from keyword_engine.competitor_monitor import monitor_competitors
            _added = monitor_competitors(on_log=log)
            log(f"[경쟁모니터] 신규 키워드 {_added}개 추가 완료")
        except Exception as _e:
            log(f"[경쟁모니터] 오류: {_e}")
        save_log()

    # ── 라운드 1: 0~30분 랜덤 지연 후 시작 ──
    delay1 = _random.uniform(0, 30 * 60)
    log(f"[라운드 1] {int(delay1/60)}분 후 시작 예정")
    _time.sleep(delay1)
    run_one_round(1)

    # ── 라운드 2: 3~6시간 랜덤 대기 ──
    delay2 = _random.uniform(3 * 3600, 6 * 3600)
    log(f"[라운드 2] {int(delay2/3600)}시간 {int((delay2%3600)/60)}분 후 시작 예정")
    _time.sleep(delay2)
    run_one_round(2)

    # ── 라운드 3: 3~6시간 랜덤 대기 ──
    delay3 = _random.uniform(3 * 3600, 6 * 3600)
    log(f"[라운드 3] {int(delay3/3600)}시간 {int((delay3%3600)/60)}분 후 시작 예정")
    _time.sleep(delay3)
    run_one_round(3)

    log("\n" + "=" * 60)
    log("전체 완료")
    log("=" * 60)
    save_log()

    # ── caffeinate 종료 ──
    if _caffeinate:
        try:
            _caffeinate.terminate()
            log("[시스템] caffeinate 종료")
        except Exception:
            pass
