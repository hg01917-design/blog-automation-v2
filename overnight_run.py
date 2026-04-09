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


def _notify_draft_saved(blog_id: str, keyword: str):
    """임시저장 완료 후 Claude Code로 검수·발행 — 중복 방지 락 적용"""
    import subprocess as _sp
    import fcntl as _fcntl
    PROJECT_DIR = str(Path(__file__).parent)
    CLAUDE_BIN = "/Users/hana/.local/bin/claude"

    # 이미 claude 검수 실행 중이면 스킵 (락 파일 확인)
    lock_path = "/tmp/publish_drafts.lock"
    try:
        _lfd = open(lock_path, "w")
        _fcntl.flock(_lfd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        _fcntl.flock(_lfd, _fcntl.LOCK_UN)
        _lfd.close()
    except BlockingIOError:
        log(f"[publish] Claude 검수 이미 실행 중 — {blog_id} 스킵")
        return

    prompt = (
        f"blog_id={blog_id} keyword={keyword}\n"
        f"봇이 임시저장 완료했습니다. {blog_id} 블로그의 임시저장 글을 아래 순서로 검수 후 발행해줘.\n\n"
        f"[검수 체크리스트 — 전부 통과해야 발행]\n"
        f"1. 중복 확인: {blog_id} 블로그 최근 발행 글 목록(RSS 또는 관리페이지)과 비교해서 "
        f"제목/주제가 유사한 글이 이미 있으면 임시저장 삭제 후 발행 중단\n"
        f"2. 마크다운 잔재 없는지 (**bold**, ## heading 등 텍스트 그대로 노출)\n"
        f"3. 이미지 3장 이상 (부족하면 Gemini로 생성 후 삽입)\n"
        f"4. [검증 필요][출처 필요] 등 내부 마커 없는지\n"
        f"5. 블로그 테마와 주제 일치 여부\n"
        f"6. 1700자 이상 (미달이면 보완 후 발행)\n"
        f"7. 같은 블로그 마지막 발행 후 3.5시간 이상 경과 여부 (미달이면 대기)\n\n"
        f"발행 완료 또는 중단 후 텔레그램(chat_id=8674424194)으로 결과 보고."
    )
    log_file = PROJECT_DIR + f"/logs/claude_publish_{blog_id}.log"
    try:
        _fh = open(log_file, "a")
        proc = _sp.Popen(
            [CLAUDE_BIN, "--print", prompt],
            cwd=PROJECT_DIR,
            stdout=_fh,
            stderr=_sp.STDOUT,
        )
        _fh.close()  # 부모 프로세스에서 핸들 닫기 (자식은 독립적으로 유지)
        log(f"[publish] Claude Code 검수 시작 — {blog_id} (키워드: {keyword}, pid={proc.pid})")
    except Exception as e:
        log(f"[publish] Claude Code 실행 실패: {e}")


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
                 "케이블카", "한옥", "올레길", "둘레길", "차박", "글램핑", "리조트",
                 "벚꽃", "단풍", "매화", "유채꽃", "군항제", "꽃놀이", "나들이", "피크닉",
                 "주차", "입장료", "운영시간", "명소", "포토스팟", "뷰", "야경", "산책",
                 "경주", "하동", "광양", "진해", "여의도", "안양", "왕십리"],
    "salim1su": ["살림", "절약", "가스", "전기", "요금", "주방", "청소", "정리", "수납",
                 "가계", "생활비", "난방", "냉방", "가전", "요리", "레시피", "기름때",
                 "세탁", "빨래", "냉장고", "에어컨", "보일러", "다이소",
                 "화장실", "욕실", "물때", "곰팡이", "집안", "먼지", "바닥", "베란다",
                 "주부", "신혼", "인테리어", "수납", "정돈", "소독", "탈취", "제거",
                 "관리비", "수도", "가습기", "건조기", "식기", "행주", "찌든"],
    "goodisak": ["아이폰", "갤럭시", "스마트폰", "노트북", "태블릿", "AI", "앱", "앱스토어",
                 "카드", "적금", "예금", "투자", "주식", "펀드", "청약",
                 "페이", "포인트", "캐시백", "환전", "핀테크", "은행", "증권",
                 "IT", "기술", "소프트웨어", "하드웨어", "가전", "전자"],
    "baremi542": ["지원금", "보조금", "지원사업", "복지", "수당", "혜택", "신청", "환급",
                  "정부", "공공", "청년", "취업", "바우처", "감면", "지원"],
    "triplog": ["호텔", "항공", "맛집", "국내여행", "해외여행", "여행", "숙소", "리조트",
                "투어", "관광", "비행기", "티켓", "패키지", "배낭여행", "자유여행",
                "가볼만한", "여행지", "추천", "코스", "일정", "경비", "항공권", "렌터카", "렌트카",
                "당일치기", "트레킹", "등산", "바다", "계곡", "축제", "글램핑", "캠핑", "펜션"],
    "woll100": ["공항", "공항버스", "리무진버스", "시외버스", "교통", "시간표", "요금", "소요시간",
                "예매", "정류장", "인천공항", "김포공항", "김해공항", "제주공항", "대구공항",
                "청주공항", "무안공항", "KTX", "공항철도", "버스", "노선", "출발", "도착"],
    "phn0502": ["영화", "넷플릭스", "왓챠", "웨이브", "티빙", "OTT", "결말", "줄거리", "해석",
                "쿠키영상", "등장인물", "배우", "출연작", "근황", "추천", "신작", "장르",
                "액션", "로맨스", "스릴러", "공포", "애니", "드라마", "시리즈"],
    "me1091":  ["리뷰", "후기", "추천", "사용기", "써봤어요", "솔직", "장단점", "비교",
                "구매", "쿠팡", "다이소", "생활용품", "주방용품", "청소용품", "뷰티",
                "화장품", "스킨케어", "헤어", "건강", "건강식품", "영양제", "다이어트",
                "가전", "소형가전", "주방가전", "가성비", "핫딜", "신상", "베스트"],
}


def is_keyword_suitable(blog_id: str, keyword: str) -> bool:
    """키워드가 블로그 테마에 적합한지 확인"""
    # goodisak(Tistory): 대출 관련 키워드 차단
    if blog_id == "goodisak":
        _LOAN_BLOCK = ["대출", "금리", "대출비교", "신용대출", "주택담보대출", "카드론", "대출이자", "대출금리", "핀다",
                       "보험", "보험료", "보험사", "실비보험", "자동차보험", "생명보험", "종신보험", "의료보험"]
        if any(w in keyword for w in _LOAN_BLOCK):
            return False

    # baremi542: 법률/법령 관련 키워드 차단 (정부지원/복지만 허용)
    if blog_id == "baremi542":
        _LAW_BLOCK = ["법", "법률", "법령", "법조문", "조항", "형법", "민법", "상법",
                      "고용보험법", "산재법", "근로기준법", "소득세법", "부가세법",
                      "법안", "법원", "소송", "판결", "재판", "변호사", "법적"]
        if any(w in keyword for w in _LAW_BLOCK):
            return False

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
        # 여행/블로그 자주 쓰는 수식어
        '코스', '여행', '일정', '동선', '정복', '완주', '완전', '정보',
        '소개', '총정리', '핵심', '필수', '최신', '2026', '2025',
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
    """블로그 타입에 맞게 중복 글 여부를 확인한다.

    1단계: SQLite DB에서 이미 발행/임시저장된 유사 키워드 확인 (모든 블로그 공통)
    2단계: 블로그별 실제 발행 글 검색 (Naver/WP/Tistory 각각 다른 방법)

    Returns: (is_duplicate: bool, matched_title: str or None)
    """
    def _log(msg):
        if on_log:
            on_log(msg)

    core_words = _extract_core_words(keyword)
    _log(f"[유사문서] 핵심 단어: {core_words}")

    # ── 1단계: SQLite DB 중복 체크 (모든 블로그 공통) ─────────────────
    # 메인키워드 = 핵심어 중 첫 번째 (가장 주제-특정적 단어)
    main_kw = core_words[0] if core_words else keyword.split()[0]
    try:
        from keyword_engine.db_handler import _conn
        with _conn() as db:
            rows = db.execute(
                """SELECT keyword FROM keyword_blog_status
                   WHERE blog_id = ? AND status IN ('published', 'draft_saved', 'in_progress')
                   AND keyword != ?""",
                (blog_id, keyword),
            ).fetchall()
        existing_keywords = [r[0] for r in rows]
        for ek in existing_keywords:
            ek_core = _extract_core_words(ek)
            ek_main = ek_core[0] if ek_core else ek.split()[0]
            # ① 메인키워드 일치 → 즉시 중복 (예: "가스레인지 청소" vs "가스레인지 청소 방법")
            if main_kw == ek_main:
                _log(f"[유사문서] ⚠ DB 메인키워드 중복: '{ek}' (메인: '{main_kw}')")
                return True, ek
            # ② 핵심 단어 절반 이상 겹치면 중복
            ek_core_set = set(ek_core)
            kw_core = set(core_words)
            overlap = ek_core_set & kw_core
            if len(overlap) >= max(2, len(kw_core) * 0.5):
                _log(f"[유사문서] ⚠ DB 중복 키워드: '{ek}' (겹침: {overlap})")
                return True, ek
    except Exception as e:
        _log(f"[유사문서] DB 체크 실패: {e}")

    # ── 2단계: 블로그별 실제 발행 글 확인 ───────────────────────────
    WP_BLOGS = {
        "baremi542": ("TRIPLOG_WP_URL", "TRIPLOG_WP_USER", "TRIPLOG_WP_APP_PASSWORD"),  # 오타 방어
        "triplog":   ("TRIPLOG_WP_URL", "TRIPLOG_WP_USER", "TRIPLOG_WP_APP_PASSWORD"),
    }
    # remote_secrets.json에서 실제 키 확인
    try:
        _sec = json.loads(Path(__file__).parent.joinpath("remote_secrets.json").read_text())
    except Exception:
        _sec = {}

    if blog_id == "baremi542":
        _wp_url = _sec.get("WP_URL", "")
        _wp_user = _sec.get("WP_USER", "")
        _wp_pass = _sec.get("WP_APP_PASSWORD", "")
    elif blog_id == "triplog":
        _wp_url = _sec.get("TRIPLOG_WP_URL", "")
        _wp_user = _sec.get("TRIPLOG_WP_USER", "")
        _wp_pass = _sec.get("TRIPLOG_WP_APP_PASSWORD", "")
    else:
        _wp_url = _wp_user = _wp_pass = ""

    if _wp_url and _wp_user:
        # WordPress REST API로 유사 제목 검색
        try:
            import base64 as _b64, ssl as _ssl
            _auth = _b64.b64encode(f"{_wp_user}:{_wp_pass}".encode()).decode()
            _ctx = _ssl.create_default_context(); _ctx.check_hostname = False; _ctx.verify_mode = 0
            _search_q = urllib.parse.urlencode({"search": " ".join(core_words[:3]), "per_page": 20, "status": "publish"})
            _req = urllib.request.Request(
                f"{_wp_url}/wp-json/wp/v2/posts?{_search_q}",
                headers={"Authorization": f"Basic {_auth}"},
            )
            _posts = json.loads(urllib.request.urlopen(_req, timeout=10, context=_ctx).read())
            for p in _posts:
                title = re.sub(r'<[^>]+>', '', p.get("title", {}).get("rendered", ""))
                match_count = sum(1 for w in core_words if w in title)
                if match_count >= max(2, len(core_words) * 0.5):
                    _log(f"[유사문서] ⚠ WP 중복 발견: \"{title}\" (id={p['id']})")
                    return True, title
            _log(f"[유사문서] WP 검색 완료 — {len(_posts)}개 중 중복 없음")
        except Exception as e:
            _log(f"[유사문서] WP 검색 실패: {e}")

    elif blog_id in ("nolja100", "goodisak", "woll100", "phn0502"):
        # Tistory RSS로 최근 글 확인
        TISTORY_RSS = {
            "nolja100": "https://issue.baremi542.com/rss",
            "goodisak": "https://welfare.baremi542.com/rss",
            "woll100":  "https://info.baremi542.com/rss",
            "phn0502":  "https://film.baremi542.com/rss",
        }
        rss_url = TISTORY_RSS.get(blog_id, "")
        if rss_url:
            try:
                _ctx2 = __import__("ssl").create_default_context(); _ctx2.check_hostname = False; _ctx2.verify_mode = 0
                _rreq = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
                _rss = urllib.request.urlopen(_rreq, timeout=10, context=_ctx2).read().decode("utf-8", errors="ignore")
                _rtitles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', _rss)
                if not _rtitles:
                    _rtitles = re.findall(r'<title>(.*?)</title>', _rss)
                for t in _rtitles[1:21]:  # 첫 번째는 블로그 제목
                    t_clean = re.sub(r'<[^>]+>', '', t).strip()
                    match_count = sum(1 for w in core_words if w in t_clean)
                    if match_count >= max(2, len(core_words) * 0.5):
                        _log(f"[유사문서] ⚠ Tistory RSS 중복: \"{t_clean}\"")
                        return True, t_clean
                _log(f"[유사문서] Tistory RSS 확인 완료 — 중복 없음")
            except Exception as e:
                _log(f"[유사문서] Tistory RSS 실패: {e}")

    elif blog_id == "salim1su":
        # 기존 Naver 블로그 검색
        search_query = "+".join(core_words)
        search_url = (
            f"https://blog.naver.com/PostSearchList.naver?"
            f"blogId={blog_id}&searchText={urllib.parse.quote(search_query)}"
            f"&orderType=sim&directAccess=false"
        )
        try:
            req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
            titles = re.findall(r'<span class="ell">(.*?)</span>', html)
            if not titles:
                titles = re.findall(r'class="pcol2"[^>]*>(.*?)</a>', html)
            clean_titles = [re.sub(r'<[^>]+>', '', t).strip() for t in titles if len(t) > 5]
            for t in clean_titles[:10]:
                match_count = sum(1 for w in core_words if w in t)
                if match_count >= 2 or (len(core_words) == 1 and match_count >= 1):
                    _log(f"[유사문서] ⚠ Naver 중복: \"{t}\"")
                    return True, t
        except Exception as e:
            _log(f"[유사문서] Naver 검색 실패: {e}")

    _log(f"[유사문서] 중복 없음 — 진행 가능")
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


# ─── 내부링크 삽입 ───
_BLOG_RSS = {
    "nolja100": ("https://issue.baremi542.com/rss", "https://issue.baremi542.com"),
    "goodisak": ("https://welfare.baremi542.com/rss", "https://welfare.baremi542.com"),
    "woll100":  ("https://info.baremi542.com/rss", "https://info.baremi542.com"),
    "phn0502":  ("https://film.baremi542.com/rss", "https://film.baremi542.com"),
    "triplog":  ("https://app.baremi542.com/feed", "https://app.baremi542.com"),
    "baremi542": ("https://baremi542.com/feed", "https://baremi542.com"),
}


_TISTORY_BLOGS = {"goodisak", "nolja100", "woll100", "phn0502"}  # HTML이 에디터에서 이스케이프되므로 제외

def _inject_internal_links(body: str, blog_id: str, on_log=None) -> str:
    """본문 하단에 같은 블로그 최근 글 3개 내부링크 섹션 추가"""
    if blog_id not in _BLOG_RSS:
        return body
    # Tistory 블로그는 에디터에서 HTML div가 이스케이프되어 raw text로 노출됨 — 주입 생략
    if blog_id in _TISTORY_BLOGS:
        return body
    rss_url, base_url = _BLOG_RSS[blog_id]
    try:
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = 0
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        rss = urllib.request.urlopen(req, timeout=8, context=ctx).read().decode("utf-8", errors="ignore")
        # 제목 + 링크 파싱
        items = re.findall(r'<item>.*?<title><!\[CDATA\[(.*?)\]\]></title>.*?<link>(.*?)</link>.*?</item>', rss, re.DOTALL)
        if not items:
            items_t = re.findall(r'<title>(.*?)</title>', rss)[1:4]
            items_l = re.findall(r'<link>(.*?)</link>', rss)[1:4]
            items = list(zip(items_t, items_l))
        items = [(t.strip(), l.strip()) for t, l in items[:3] if t.strip() and l.strip()]
        if not items:
            return body
        links_html = '\n'.join(
            f'<li><a href="{url}" target="_blank">{title}</a></li>'
            for title, url in items
        )
        section = (
            f'\n\n<div style="margin-top:30px;padding:16px;background:#f8f9fa;border-left:4px solid #4285f4;border-radius:4px">'
            f'<strong>📌 함께 읽으면 좋은 글</strong>'
            f'<ul style="margin:8px 0 0 0;padding-left:20px">{links_html}</ul>'
            f'</div>'
        )
        if on_log:
            on_log(f"[내부링크] {blog_id}: {len(items)}개 삽입")
        return body + section
    except Exception as e:
        if on_log:
            on_log(f"[내부링크] {blog_id} 실패 (무시): {e}")
        return body


# ─── 전체 포스팅 파이프라인 ───
def run_posting_pipeline(blog_id, keyword, page_id=None):
    """유사문서 체크 → 글 생성 → 이미지 → 포스팅 전체 파이프라인

    page_id가 주어지면 유사문서 발견 시 Notion 상태를 '실패'로 변경.
    """
    from claude_playwright import generate_text
    from image_router import generate_images_for_blog
    from poster import post_single

    # 0-2. 유사문서 체크 (블로그 내 기존 글)
    log(f"[파이프라인] {blog_id} / '{keyword}' — 유사문서 체크")
    is_dup, matched = check_duplicate_post(blog_id, keyword, on_log=log)
    if is_dup:
        log(f"[파이프라인] ⚠ 유사문서 발견 — 키워드 '{keyword}' 건너뜀")
        if page_id:
            update_keyword_status(page_id, "실패", memo=f"유사문서: {matched[:30]}")
        return False

    # 1. triplog: MRT 제휴 링크 조회 후 프롬프트에 포함
    keyword_with_mrt = keyword
    if blog_id == "triplog":
        try:
            from mrt_affiliate import get_affiliate_links
            log(f"[파이프라인] triplog — MRT 제휴 링크 조회 중: '{keyword}'")
            mrt_links = get_affiliate_links(keyword, top_n=5, on_log=log)

            # 관련성 필터: 키워드의 핵심 지역/도시가 상품 제목에 포함되어야 함
            if mrt_links:
                dest_words = _extract_core_words(keyword)  # 핵심 단어 추출
                # 국내 여행 지역 키워드 (1글자 이상)
                dest_keywords = [w for w in dest_words if len(w) >= 2 and w not in {
                    '여행', '코스', '여행코스', '당일치기', '뚜벅이', '드라이브',
                    '맛집', '숙소', '카페', '일정', '추천', '2박3일', '1박2일',
                }]
                relevant_links = []
                for link in mrt_links:
                    title = link.get("title", "")
                    # 지역 키워드가 상품 제목에 하나라도 있어야 관련 있음
                    if any(dw in title for dw in dest_keywords):
                        relevant_links.append(link)
                if len(relevant_links) < len(mrt_links):
                    log(f"[파이프라인] MRT 관련성 필터: {len(mrt_links)}개 → {len(relevant_links)}개 (지역: {dest_keywords})")
                mrt_links = relevant_links[:3]

            if mrt_links:
                mrt_ctx = (
                    "\n\n[마이리얼트립 제휴 상품 — 글 하단 '추천 투어' 섹션에 필수 포함]\n"
                    "글 최상단(첫 문단 전)에 반드시 이 한 줄을 삽입해:\n"
                    "「이 글에는 마이리얼트립 파트너스 프로그램을 통해 소정의 수수료를 받을 수 있는 제휴 링크가 포함되어 있습니다.」\n\n"
                    "글 맨 하단에 '## 추천 투어' 섹션을 만들고, 아래 상품을 반드시 HTML <a href> 링크로 삽입해.\n"
                    "형식: <a href=\"{URL}\" target=\"_blank\">{상품명}</a> — {가격/설명}\n\n"
                )
                for i, p in enumerate(mrt_links, 1):
                    name = p["title"][:60]
                    aff_url = p.get('affiliate_url', '')
                    mrt_ctx += f"{i}. 상품명: {name}\n   URL: {aff_url}\n"
                keyword_with_mrt = keyword + mrt_ctx
                log(f"[파이프라인] MRT {len(mrt_links)}개 관련 제휴 링크 주입 완료")
            else:
                log(f"[파이프라인] MRT 관련 상품 없음 — 제휴 섹션 생략")
        except Exception as e:
            log(f"[파이프라인] MRT 조회 실패 (무시): {e}")

    # 1. Claude.ai 글 생성
    log(f"[파이프라인] {blog_id} / '{keyword}' — Claude.ai 글 생성 시작")
    raw = generate_text("", blog_id=blog_id, keyword=keyword_with_mrt, on_log=log)

    if not raw or "추출 실패" in raw:
        log(f"[파이프라인] 글 생성 실패")
        return False

    # 2. 전처리 — MRT 메타 헤더 및 백틱 마커 정규화
    # 마이리얼트립 메타 정보 블록 제거 (═══...【메타 정보】...회차/앵글/문체 등)
    raw = re.sub(r'(?s)[`"]*\s*[═=─]{5,}.*?마이리얼트립 여행후기 생성 결과.*?[═=─]{5,}\s*\n'
                 r'【메타 정보】.*?(?=📌|===제목|`===제목)', '', raw).strip()
    # 백틱으로 감싸진 마커 정규화: `===제목===` → ===제목===
    raw = re.sub(r'`\s*(===(?:제목|본문|태그|이미지)(?:끝)?===)\s*`', r'\1', raw)
    # 📌 제목 / 📝 본문 헤더 줄 제거
    raw = re.sub(r'📌\s*\*?\*?제목\*?\*?\s*\n', '', raw)
    raw = re.sub(r'📝\s*\*?\*?본문\*?\*?\s*\n', '', raw)
    # ===본문=== 마커 없을 때 대비: 내용이 ===제목끝=== 뒤에 오면 ===본문===...===본문끝=== 추가
    if '===제목끝===' in raw and '===본문===' not in raw:
        raw = re.sub(r'(===제목끝===\s*\n)', r'\1===본문===\n', raw)
        raw = raw.rstrip() + '\n===본문끝==='

    # 3. 파싱 — 각 섹션 정확히 분리
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
    # JSON-LD 스키마 / <script> 태그 전체 제거 (SEO 스키마가 본문에 섞이는 경우)
    body = re.sub(r'<script\b[^>]*>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE).strip()
    # 노출된 HTML 블록 태그 제거 (<div>, <section>, <article> 등 — 인라인 태그는 유지)
    body = re.sub(r'</?(?:div|section|article|aside|header|footer|nav|main|figure|figcaption)(\s[^>]*)?>',
                  '', body, flags=re.IGNORECASE).strip()
    # <br> 태그를 줄바꿈으로 변환 (핵심요약 박스 등 HTML 잔재 처리)
    body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)

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
    if len(title) == 0 or title.strip() == keyword.strip():
        log(f"[파싱] ❌ 제목 생성 실패 (title='{title}') — 발행 중단")
        return False
    if char_count < 100:
        log(f"[파싱] ⚠ 본문이 너무 짧음 ({char_count}자)")
    log(f"[파싱] 본문 미리보기: {body[:80]}...")

    MIN_IMAGES = 3

    # 3. 글 품질 검수 (이미지 생성 전에 먼저 — Gemini 쿼터 낭비 방지)
    MIN_BODY_CHARS_HARD = 1700  # 절대 최소 (이 미만이면 발행 중단)
    MIN_BODY_CHARS_SOFT = 2000  # 권고 최소 (이 미만이면 재생성 1회 시도)

    # 2000자 미만이면 재생성 1회 시도
    if char_count < MIN_BODY_CHARS_SOFT:
        log(f"[검수] ⚠ 본문 짧음 ({char_count}자 < {MIN_BODY_CHARS_SOFT}자) — 재생성 1회 시도")
        raw2 = generate_text("", blog_id=blog_id, keyword=keyword_with_mrt, on_log=log)
        if raw2 and "추출 실패" not in raw2:
            body_m2 = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw2, re.DOTALL)
            if body_m2:
                body2 = body_m2.group(1).strip()
                plain2 = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body2)
                char_count2 = len(re.sub(r"\s+", "", plain2))
                if char_count2 > char_count:
                    log(f"[검수] 재생성 결과 더 길어짐: {char_count}자 → {char_count2}자 — 교체")
                    raw = raw2
                    # 파싱 다시
                    title_m = re.search(r"===제목===\s*\n(.*?)\n*===제목끝===", raw, re.DOTALL)
                    body_m = re.search(r"===본문===\s*\n(.*?)\n*===본문끝===", raw, re.DOTALL)
                    tag_m = re.search(r"===태그===\s*\n(.*?)\n*===태그끝===", raw, re.DOTALL)
                    img_m = re.search(r"===이미지===\s*\n(.*?)\n*===이미지끝===", raw, re.DOTALL)
                    if title_m:
                        title = _truncate_title(title_m.group(1).strip().split('\n')[0].strip(), max_len=40)
                    body = body_m.group(1).strip() if body_m else body2
                    if tag_m:
                        tag_line = tag_m.group(1).strip().split('\n')[0].strip()
                        tags = [t.strip() for t in tag_line.split(",") if t.strip()]
                    body = re.sub(r'\n*항목기준충족.*$', '', body, flags=re.DOTALL).strip()
                    body = re.sub(r'\n*===검수===.*?(?:===검수끝===|$)', '', body, flags=re.DOTALL).strip()
                    body = re.sub(r'\n[✅❌☑️].{0,60}(?:\n[✅❌☑️].{0,60}){2,}', '', body).strip()
                    body = re.sub(r'\[검증\s*필요\]|\[출처\s*필요\]|\[사실\s*확인\]|\[확인\s*필요\]', '', body).strip()
                    body = re.sub(r'</?(?:div|section|article|aside|header|footer|nav|main|figure|figcaption)(\s[^>]*)?>',
                                  '', body, flags=re.IGNORECASE).strip()
                    body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)
                    plain = re.sub(r"##.*|{{.*?}}|\[애드센스\]|\|.*", "", body)
                    char_count = len(re.sub(r"\s+", "", plain))
                else:
                    log(f"[검수] 재생성 결과 더 짧음 — 원본 유지")

    if char_count < MIN_BODY_CHARS_HARD:
        log(f"[검수] ⚠ 본문 짧음 ({char_count}자 < {MIN_BODY_CHARS_HARD}자) — 임시저장 후 클로드코드 보완 예정")
    elif char_count < MIN_BODY_CHARS_SOFT:
        log(f"[검수] ⚠ 본문 권고치 미달 ({char_count}자 < {MIN_BODY_CHARS_SOFT}자) — 임시저장 진행")
    if not tags:
        log(f"[검수] ⚠ 태그 없음 — 기본 태그로 대체")
        tags = [keyword]  # 최소 키워드라도 태그로 사용
    log(f"[검수] 글 품질 기록 — 본문 {char_count}자, 태그 {len(tags)}개 → 임시저장 진행")

    # 4. 이미지 생성 (블로그별 라우팅: salim1su=Gemini→Bing→Pollinations, 그 외=Bing→Pollinations)
    image_paths = {}
    if images:
        is_naver = blog_id in ("salim1su", "me1091")
        log(f"[파이프라인] 이미지 생성 시작 (blog={blog_id}, skip_webp={is_naver})")
        image_paths = generate_images_for_blog(
            blog_id=blog_id,
            image_infos=images,
            skip_webp=is_naver,
            on_log=log,
        )
        log(f"[파이프라인] 이미지 {len(image_paths)}개 생성 완료")

    # 4-1. 이미지 최소 3장 보장 — 부족하면 Pollinations 폴백 보충
    if len(image_paths) < MIN_IMAGES:
        log(f"[파이프라인] ⚠ 이미지 {len(image_paths)}개 < 최소 {MIN_IMAGES}개 — Pollinations 폴백 보충")
        from image_router import _pollinations_image, _enhance_prompt, IMAGES_DIR as _IMG_DIR
        extra_prompts = [keyword, f"{keyword} 관련 정보", f"{keyword} 생활 팁"]
        for i in range(len(image_paths), MIN_IMAGES):
            kw_fb = extra_prompts[i % len(extra_prompts)]
            fname = f"fallback_{blog_id}_{i+1}.jpg"
            enh = _enhance_prompt(blog_id, kw_fb)
            fp = str(_IMG_DIR / fname)
            ok = _pollinations_image(enh, fp, on_log=log)
            if ok:
                images.append({"index": len(images)+1, "prompt": kw_fb, "filename": fname, "alt": kw_fb})
                image_paths[fname] = fp
        log(f"[파이프라인] 이미지 보충 후 총 {len(image_paths)}개")

    if len(image_paths) < MIN_IMAGES:
        log(f"[검수] ⚠ 이미지 부족 ({len(image_paths)}개 < {MIN_IMAGES}개) — 임시저장 후 클로드코드 보완 예정")
    else:
        log(f"[검수] ✅ 이미지 {len(image_paths)}개 확인")

    # 3-5. 내부링크 삽입 (같은 블로그 최근 글 3개)
    body = _inject_internal_links(body, blog_id, log)

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
        _notify_draft_saved(blog_id, keyword)
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
    # me1091: Notion 상품 기반 Coupang 리뷰 파이프라인 (키워드 DB 사용 안 함)
    if blog_id == "me1091":
        try:
            from me1091_bot import run_one_product
            return run_one_product(on_log=log)
        except Exception as e:
            log(f"[me1091] 오류: {e}")
            return False

    from keyword_engine.db_handler import fetch_next_pending, set_keyword_status as _db_set

    # 최소 포스팅 간격 체크 (같은 블로그 3시간 이상 텀)
    # nolja100/triplog는 여행 블로그 그룹 — 하나가 발행되면 둘 다 대기
    TRAVEL_GROUP = {"nolja100", "triplog"}
    if blog_id in TRAVEL_GROUP:
        elapsed = min(_hours_since_last_post(b) for b in TRAVEL_GROUP)
    else:
        elapsed = _hours_since_last_post(blog_id)
    if elapsed < MIN_POST_GAP_HOURS:
        log(f"[{blog_id}] 마지막 포스팅 {elapsed:.1f}시간 전 — 최소 {MIN_POST_GAP_HOURS}시간 필요, 스킵")
        return False

    # 테마 부적합 키워드는 스킵하고 다음 키워드 재시도 (최대 5회)
    kw = None
    for _ in range(5):
        candidate = fetch_next_pending(blog_id)
        if not candidate:
            break
        if is_keyword_suitable(blog_id, candidate):
            kw = candidate
            break
        log(f"[{blog_id}] ⚠ 테마 부적합 '{candidate}' → 스킵")
        _db_set(candidate, "failed", blog_id=blog_id)
    if not kw:
        log(f"[{blog_id}] 대기 키워드 없음 — 스킵")
        return False
    log(f"[{blog_id}] 키워드: {kw}")
    _db_set(kw, "in_progress", blog_id=blog_id)
    try:
        ok = run_posting_pipeline(blog_id, kw, page_id=None)
        if ok:
            # 모든 블로그 임시저장 → draft_saved (Claude Code가 검수 후 발행)
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
    # triplog는 nolja100보다 항상 먼저 — 같은 여행 카테고리에서 triplog 우선 배정
    # me1091은 별도 독립 봇(me1091_bot.py)으로 분리 — overnight 루프에서 제외
    _non_travel = ["salim1su", "baremi542", "goodisak", "woll100", "phn0502"]
    _rand.shuffle(_non_travel)
    BLOGS = ["triplog", "nolja100"] + _non_travel
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

    # ── 재실행 상태 관리 ──
    _STATE_FILE = LOG_DIR / "overnight_state.json"
    _today_str = datetime.now().strftime("%Y-%m-%d")

    def _load_state():
        try:
            if _STATE_FILE.exists():
                s = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                if s.get("run_date") == _today_str:
                    return s
        except Exception:
            pass
        return None

    def _save_state(s):
        try:
            _STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    _state = _load_state()
    if _state:
        log(f"[재실행] 오늘({_today_str}) 상태 복원 — 완료 라운드: {_state.get('completed_rounds', [])}")
    else:
        _state = {
            "run_date": _today_str,
            "crawling_done": False,
            "decision_done": False,
            "extra_rounds": 0,
            "completed_rounds": [],
            "next_times": {},
        }
        _save_state(_state)

    # ── 화면 잠금/슬립 방지 (macOS caffeinate) ──
    import subprocess as _sub
    try:
        _caffeinate = _sub.Popen(["caffeinate", "-d", "-i", "-s"],
                                 stdout=_sub.DEVNULL, stderr=_sub.DEVNULL)
        log("[시스템] caffeinate 시작 (화면 잠금/슬립 방지)")
    except Exception as _e:
        _caffeinate = None
        log(f"[시스템] caffeinate 실패: {_e}")

    # ── 키워드 크롤링 (1회, 오늘 이미 했으면 스킵) ──
    _crawled_keywords = {}
    if not _state.get("crawling_done"):
        log("[크롤링] salim1su, baremi542 키워드 수집")
        from keyword_crawler import crawl_keywords
        for bid in ["salim1su", "baremi542"]:
            try:
                result = crawl_keywords(blog_id=bid, on_log=log)
                cnt = result.get(bid, 0)
                log(f"[크롤링] {bid}: {cnt}개 저장")
                if cnt > 0:
                    _crawled_keywords[bid] = result.get("keywords", [])
            except Exception as e:
                log(f"[크롤링] {bid} 오류: {e}")
        _state["crawling_done"] = True
        _save_state(_state)
        save_log()
    else:
        log("[크롤링] 오늘 이미 완료 — 스킵")

    # ── 롱테일 키워드 확장 (크롤링 직후, 오늘 이미 했으면 스킵) ──
    # 크롤링한 경쟁사 seed → 네이버 자동완성/연관검색어 → 롱테일(4단어↑)만 저장
    if _state.get("crawling_done") and not _crawled_keywords:
        log("[롱테일] 크롤링 이미 완료(재실행) — 새 seed 없음, 스킵")
    _BLOG_LONGTAIL = {
        "nolja100":  "여행",
        "triplog":   "여행",
        "salim1su":  "살림",
        "goodisak":  "IT",
        "baremi542": "정부지원금",
        "woll100":   "교통",
        "phn0502":   "영화",
        "me1091":    "리뷰",
    }
    log("[롱테일] 키워드 확장 시작")
    try:
        from keyword_engine.longtail_expander import expand_longtail
        from keyword_engine.db_handler import get_top_keywords

        # 각 블로그 카테고리별로 seed 구성: 크롤링 신규 키워드 우선, 없으면 DB 기존 키워드
        _CAT_BLOG = {"여행": ["nolja100", "triplog"], "살림": ["salim1su"],
                     "IT": ["goodisak"], "정부지원금": ["baremi542"],
                     "교통": ["woll100"], "영화": ["phn0502"]}
        for bid, cat in _BLOG_LONGTAIL.items():
            # 이미 다른 blog_id가 같은 카테고리를 처리했으면 스킵 (중복 확장 방지)
            if cat in ("여행",) and bid == "triplog":
                continue  # nolja100에서 이미 처리
            # 1순위: 오늘 크롤링한 키워드
            crawled_seeds = []
            for _bid in _CAT_BLOG.get(cat, []):
                crawled_seeds.extend(_crawled_keywords.get(_bid, []))
            # 2순위: DB 기존 키워드 (단어 수 적은 것 — seed 역할)
            db_seeds = [r["keyword"] for r in get_top_keywords(n=20, min_score=0)
                        if r.get("category", "") == cat and len(r["keyword"].split()) <= 4]
            # seed 합치기 (크롤링 우선, 중복 제거)
            seen_seeds = set()
            seeds = []
            for kw in crawled_seeds + db_seeds:
                if kw not in seen_seeds:
                    seen_seeds.add(kw)
                    seeds.append(kw)
            if not seeds:
                continue
            added = expand_longtail(
                base_keywords=seeds,
                category=cat,
                blog_id=bid,
                top_n=8,   # seed 최대 8개 확장 (신규 seed 많으면 더 많이)
                on_log=log,
            )
            log(f"[롱테일] {bid}({cat}): +{added}개 롱테일 추가")
    except Exception as e:
        log(f"[롱테일] 오류: {e}")
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

    # ── 판단 엔진 (라운드 시작 전 1회, 오늘 이미 했으면 스킵) ──
    _extra_rounds = _state.get("extra_rounds", 0)
    if not _state.get("decision_done"):
        try:
            from decision_engine import run_daily_analysis, get_publish_count_recommendation
            run_daily_analysis(on_log=log)
            _rec = get_publish_count_recommendation(on_log=log)
            _rec_count = max(_rec.values()) if _rec else 1
            _extra_rounds = max(0, _rec_count - 3)  # 기본 3라운드 초과분
            if _extra_rounds:
                log(f"[판단엔진] 수익 pace 저조 → 추가 라운드 {_extra_rounds}개 실행 예정")
        except Exception as _de:
            log(f"[판단엔진] 생략: {_de}")
        _state["decision_done"] = True
        _state["extra_rounds"] = _extra_rounds

        # ── 라운드 예약 시간 사전 계산 (첫 실행 시만) ──
        _now_ts = _time.time()
        _d1 = _random.uniform(0, 30 * 60)
        _d2 = _random.uniform(3 * 3600, 6 * 3600)
        _d3 = _random.uniform(3 * 3600, 6 * 3600)
        _state["next_times"] = {
            "1": _now_ts + _d1,
            "2": _now_ts + _d1 + _d2,
            "3": _now_ts + _d1 + _d2 + _d3,
        }
        _prev_ts = _state["next_times"]["3"]
        for _er in range(_extra_rounds):
            _de = _random.uniform(3 * 3600, 5 * 3600)
            _state["next_times"][str(4 + _er)] = _prev_ts + _de
            _prev_ts += _de
        log(f"[스케줄] 라운드 1: {int(_d1/60)}분 후 / 라운드 2: {int((_d1+_d2)/3600)}시간 후 / 라운드 3: {int((_d1+_d2+_d3)/3600)}시간 후")
        _save_state(_state)
    else:
        log(f"[판단엔진] 오늘 이미 완료 — 스킵 (extra_rounds={_extra_rounds})")
    save_log()

    # ── 라운드 실행 (재실행 시 완료 라운드 스킵, 예약 시간 복원) ──
    def _run_round_with_resume(round_num):
        completed = _state.get("completed_rounds", [])
        if round_num in completed:
            log(f"[라운드 {round_num}] 이미 완료 — 스킵")
            return
        target_ts = _state.get("next_times", {}).get(str(round_num))
        if target_ts:
            wait = target_ts - _time.time()
            if wait > 60:
                log(f"[라운드 {round_num}] {int(wait/3600)}시간 {int((wait%3600)/60)}분 후 시작 예정")
                _time.sleep(wait)
            elif wait > 0:
                _time.sleep(wait)
            else:
                log(f"[라운드 {round_num}] 예약 시간 경과({abs(int(wait/60))}분 전) — 즉시 시작")
        run_one_round(round_num)
        _state["completed_rounds"].append(round_num)
        _save_state(_state)

    _total_rounds = 3 + _extra_rounds
    for _rn in range(1, _total_rounds + 1):
        _run_round_with_resume(_rn)

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
