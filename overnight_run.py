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


def _ssl_ctx():
    """SSL 인증서 검증 비활성화 컨텍스트 (자체 서명 인증서 대응용)"""
    import ssl as _ssl
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    return ctx


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
                 "IT", "기술", "소프트웨어", "하드웨어", "가전", "전자",
                 # 추가: 실제 IT 키워드 패턴
                 "구글", "카카오", "네이버", "유튜브", "인스타", "틱톡", "챗", "GPT",
                 "드라이브", "클라우드", "와이파이", "블루투스", "USB", "충전",
                 "이어폰", "헤드폰", "스피커", "마우스", "키보드", "모니터", "웹캠",
                 "요금제", "통신", "SKT", "KT", "LG유플", "알뜰폰",
                 "삼성", "LG", "애플", "소니", "다이슨",
                 "스마트워치", "워치", "패드", "이커머스", "쇼핑", "배달",
                 "연금", "세금", "절세", "환급", "공제", "신용점수"],
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



def _naver_competition_check(keyword: str, on_log=None) -> bool:
    """Naver 검색결과 수 확인. 경쟁 너무 심하면 False 반환."""
    # 검색결과 수는 직접 크롤링 어려우므로 키워드 길이+단어수로 경쟁도 근사 추정
    # 롱테일 기준: 단어 2개 미만이면 경쟁 높음으로 간주
    words = keyword.strip().split()
    if len(words) < 2:
        if on_log: on_log(f"[경쟁도] '{keyword}' 단어 1개 — 경쟁 높음 스킵")
        return False
    if len(keyword) < 6:
        if on_log: on_log(f"[경쟁도] '{keyword}' 너무 짧음 — 경쟁 높음 스킵")
        return False
    return True


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
        # 교통/공항 관련 일반 수식어 (이것만으로 중복 판정 금지)
        '시간표', '요금', '노선', '운행', '탑승', '예약',
    }
    words = keyword.split()
    core = [w for w in words if len(w) >= 2 and w not in STOP_WORDS]
    return core if core else words[:2]



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
                   WHERE blog_id = ? AND status IN ('published', 'draft_saved', 'in_progress', 'failed')
                   AND keyword != ?""",
                (blog_id, keyword),
            ).fetchall()
        existing_keywords = [r[0] for r in rows]
        for ek in existing_keywords:
            ek_core = _extract_core_words(ek)
            ek_main = ek_core[0] if ek_core else ek.split()[0]
            # ① 메인키워드 일치 → 중복 판단 (단, 3글자 이하 장소명이 첫 단어인 경우 추가 단어도 겹쳐야 함)
            # 예: "가스레인지 청소" vs "가스레인지 청소 방법" → 중복 O
            # 반례: "서울 김포공항 시간표" vs "서울 인천공항 시간표" → 첫 단어만 같고 내용은 달라서 중복 X
            if main_kw == ek_main:
                if len(core_words) >= 3 or len(main_kw) <= 2:
                    # 짧은 장소명(서울, 인천, 부산 등) 또는 키워드가 길면
                    # 2번째 핵심어도 일치해야 중복으로 판정
                    # 예: "서울 김포공항" vs "서울 인천공항" → 2번째가 다르면 중복 X
                    if len(ek_core) >= 2 and len(core_words) >= 2 and core_words[1] != ek_core[1]:
                        continue  # 2번째 핵심어 다름 → 중복 아님
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
        # WordPress REST API로 유사 제목 검색 (최대 2회 재시도)
        import base64 as _b64
        _auth = _b64.b64encode(f"{_wp_user}:{_wp_pass}".encode()).decode()
        _search_q = urllib.parse.urlencode({"search": " ".join(core_words[:3]), "per_page": 20, "status": "publish"})
        _req = urllib.request.Request(
            f"{_wp_url}/wp-json/wp/v2/posts?{_search_q}",
            headers={"Authorization": f"Basic {_auth}"},
        )
        _posts = None
        for _attempt in range(2):
            try:
                with urllib.request.urlopen(_req, timeout=15, context=_ssl_ctx()) as _r:
                    _posts = json.loads(_r.read())
                break
            except Exception as e:
                _log(f"[유사문서] WP 검색 실패 (시도 {_attempt+1}/2): {e}")
        if _posts is not None:
            for p in _posts:
                title = re.sub(r'<[^>]+>', '', p.get("title", {}).get("rendered", ""))
                match_count = sum(1 for w in core_words if w in title)
                if match_count >= max(2, len(core_words) * 0.5):
                    _log(f"[유사문서] ⚠ WP 중복 발견: \"{title}\" (id={p['id']})")
                    return True, title
            _log(f"[유사문서] WP 검색 완료 — {len(_posts)}개 중 중복 없음")

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
                _ctx2 = _ssl_ctx()
                _rreq = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(_rreq, timeout=10, context=_ctx2) as _r:
                    _rss = _r.read().decode("utf-8", errors="ignore")
                _rtitles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', _rss)
                if not _rtitles:
                    _rtitles = re.findall(r'<title>(.*?)</title>', _rss)
                _log(f"[유사문서] Tistory RSS {len(_rtitles)-1}개 제목 수집")
                for t in _rtitles[1:21]:  # 첫 번째는 블로그 제목
                    t_clean = re.sub(r'<[^>]+>', '', t).strip()
                    match_count = sum(1 for w in core_words if w in t_clean)
                    if match_count >= max(2, len(core_words) * 0.5):
                        _log(f"[유사문서] ⚠ Tistory RSS 중복: \"{t_clean}\"")
                        return True, t_clean
                _log(f"[유사문서] Tistory RSS 확인 완료 — 중복 없음 (최근 20개)")
                # RSS는 최근 글만 포함 → Tistory 검색 API로 전체 글 추가 확인
                TISTORY_DOMAINS = {
                    "nolja100": "issue.baremi542.com",
                    "goodisak": "welfare.baremi542.com",
                    "woll100":  "info.baremi542.com",
                    "phn0502":  "film.baremi542.com",
                }
                _domain = TISTORY_DOMAINS.get(blog_id, "")
                if _domain and core_words:
                    try:
                        _search_q = urllib.parse.quote(" ".join(core_words[:2]))
                        _search_url = f"https://{_domain}/search/{_search_q}"
                        _sreq = urllib.request.Request(_search_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(_sreq, timeout=10, context=_ctx2) as _r:
                            _shtml = _r.read().decode("utf-8", errors="ignore")
                        _stitles = re.findall(r'<h3[^>]*class="[^"]*tit[^"]*"[^>]*>(.*?)</h3>', _shtml, re.S)
                        if not _stitles:
                            _stitles = re.findall(r'<a[^>]+class="[^"]*link[^"]*"[^>]*>(.*?)</a>', _shtml, re.S)
                        for _st in _stitles[:20]:
                            _st_clean = re.sub(r'<[^>]+>', '', _st).strip()
                            if not _st_clean:
                                continue
                            _mc = sum(1 for w in core_words if w in _st_clean)
                            if _mc >= max(2, len(core_words) * 0.5):
                                _log(f"[유사문서] ⚠ Tistory 검색 중복: \"{_st_clean}\"")
                                return True, _st_clean
                        _log(f"[유사문서] Tistory 검색 확인 완료 — 중복 없음")
                    except Exception as _se:
                        _log(f"[유사문서] Tistory 검색 실패: {_se}")
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
            with urllib.request.urlopen(req, timeout=10) as _r:
                html = _r.read().decode("utf-8", errors="ignore")
            titles = re.findall(r'<span class="ell">(.*?)</span>', html)
            if not titles:
                titles = re.findall(r'class="pcol2"[^>]*>(.*?)</a>', html)
            clean_titles = [re.sub(r'<[^>]+>', '', t).strip() for t in titles if len(t) > 5]
            _log(f"[유사문서] Naver 검색 결과 {len(clean_titles)}개")
            for t in clean_titles[:10]:
                match_count = sum(1 for w in core_words if w in t)
                if match_count >= 2 or (len(core_words) == 1 and match_count >= 1):
                    _log(f"[유사문서] ⚠ Naver 중복: \"{t}\"")
                    return True, t
            _log(f"[유사문서] Naver 검색 완료 — 중복 없음")
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
        req = urllib.request.Request(rss_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx()) as _r:
            rss = _r.read().decode("utf-8", errors="ignore")
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


# ─── 텍스트 버퍼 (이미지/포스팅 실패 시 텍스트 재사용) ───
_TEXT_BUFFER_DIR = LOG_DIR / "text_buffers"

def _save_text_buffer(blog_id: str, keyword: str, title: str, body: str, tags: list, images: list):
    """텍스트 생성 완료 후 버퍼 저장 — 이미지/Playwright 실패해도 텍스트 보존"""
    import fcntl
    _TEXT_BUFFER_DIR.mkdir(parents=True, exist_ok=True)
    buf = {"keyword": keyword, "title": title, "body": body, "tags": tags, "images": images,
           "saved_at": datetime.now().isoformat()}
    p = _TEXT_BUFFER_DIR / f"{blog_id}.json"
    with open(p, "w", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.write(json.dumps(buf, ensure_ascii=False, indent=2))
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    log(f"[버퍼] {blog_id} 텍스트 저장 완료 ('{title}')")

def _load_text_buffer(blog_id: str):
    """저장된 텍스트 버퍼 로드. 없거나 파손 시 None 반환."""
    import fcntl
    p = _TEXT_BUFFER_DIR / f"{blog_id}.json"
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.loads(f.read())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return data
    except Exception:
        p.unlink(missing_ok=True)
        return None

def _clear_text_buffer(blog_id: str):
    """텍스트 버퍼 삭제 (포스팅 성공 후 정리)"""
    p = _TEXT_BUFFER_DIR / f"{blog_id}.json"
    if p.exists():
        p.unlink()


# ─── 전체 포스팅 파이프라인 ───
def run_posting_pipeline(blog_id, keyword, _resume=None):
    """유사문서 체크 → 글 생성 → 이미지 → 포스팅 전체 파이프라인

    Returns: (ok: bool, title: str)
    """
    from claude_playwright import generate_text
    from image_router import generate_images_for_blog
    from poster import post_single
    from public_api import fetch_context_for_blog

    # 버퍼 복원 경로: 텍스트는 이미 있고 이미지/포스팅만 재시도
    if _resume:
        title  = _resume["title"]
        body   = _resume["body"]
        tags   = _resume["tags"]
        images = _resume["images"]
        log(f"[파이프라인] 텍스트 버퍼 복원: '{title}' ({len(body)}자) — 이미지/포스팅만 실행")
        ok = _run_image_and_post(blog_id, keyword, title, body, tags, images)
        return (ok, title)

    # 0-2. 유사문서 체크 (블로그 내 기존 글)
    log(f"[파이프라인] {blog_id} / '{keyword}' — 유사문서 체크")
    is_dup, matched = check_duplicate_post(blog_id, keyword, on_log=log)
    if is_dup:
        log(f"[파이프라인] ⚠ 유사문서 발견 — 키워드 '{keyword}' 건너뜀")
        return False, ""

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

            # affiliate_url이 None/빈 것 제거 (원본 URL 폴백 없음 — 제휴링크만 허용)
            valid_links = [p for p in mrt_links if p.get("affiliate_url")]
            if not valid_links and mrt_links:
                log(f"[파이프라인] ⚠️ MRT 제휴 링크 생성 실패 — triplog 발행 스킵")

            if valid_links:
                mrt_ctx = (
                    "\n\n[마이리얼트립 제휴 상품 — 링크 2회 필수 삽입]\n"
                    "글 최상단(첫 문단 전)에 반드시 이 한 줄을 삽입해:\n"
                    "「이 글에는 마이리얼트립 파트너스 프로그램을 통해 소정의 수수료를 받을 수 있는 제휴 링크가 포함되어 있습니다.」\n\n"
                    "아래 제휴 상품 링크를 본문에 2회 삽입해 (CTR 최적화):\n"
                    "  1회차: 첫 번째 소제목(##) 바로 아래 — 후킹 문구 1줄 + 링크\n"
                    "         후킹 예시: '이 투어는 성수기에 금방 마감돼요 — 날짜 먼저 잡아두세요'\n"
                    "  2회차: 맺음말 직전 — '지금 예약 확인해보세요' CTA + 링크\n"
                    "링크 형식: <a href=\"URL\" target=\"_blank\" style=\"color:#1a73e8;font-weight:bold;\">상품명 예약하기</a>\n\n"
                    "아래 상품 중 글 내용과 가장 관련된 것 1~2개 선택해서 삽입:\n"
                )
                for i, p in enumerate(valid_links, 1):
                    name = p["title"][:60]
                    aff_url = p.get('affiliate_url', '')
                    mrt_ctx += f"{i}. 상품명: {name}\n   URL: {aff_url}\n"
                keyword_with_mrt = keyword + mrt_ctx
                log(f"[파이프라인] MRT {len(valid_links)}개 관련 제휴 링크 주입 완료")
            else:
                log(f"[파이프라인] MRT 관련 상품 없음 — 제휴 섹션 생략")
        except Exception as e:
            log(f"[파이프라인] MRT 조회 실패 (무시): {e}")

    # 1. Claude.ai 글 생성
    # 시즌 키워드 감지: 현재 월과 다른 월 키워드면 미리 준비 관점 컨텍스트 추가
    _cur_month = datetime.now().month
    _SEASON_HINTS = {
        1: "1월", 2: "2월", 3: "3월", 4: "4월", 5: "5월", 6: "6월",
        7: "7월", 8: "8월", 9: "9월", 10: "10월", 11: "11월", 12: "12월",
    }
    _season_ctx = ""
    for _sm, _sh in _SEASON_HINTS.items():
        if _sh in keyword_with_mrt and _sm != _cur_month:
            _diff = min(abs(_sm - _cur_month), 12 - abs(_sm - _cur_month))
            if _diff >= 2:
                _season_ctx = (
                    f"\n\n[작성 지침] 현재 {_cur_month}월 기준으로 작성. "
                    f"'{_sh}' 시즌 키워드이므로 '미리 알아두면 좋은', '지금부터 준비하면' 등 "
                    f"현재 시점에서 자연스럽게 연결되도록 작성할 것."
                )
                log(f"[파이프라인] 시즌 키워드 감지 ({_sh}) → 현재 시점 연결 컨텍스트 추가")
            break
    keyword_final = keyword_with_mrt + _season_ctx

    # 공공API 데이터 주입 (축제·공공서비스 실제 데이터 → 할루시네이션 방지)
    _api_ctx = fetch_context_for_blog(blog_id, keyword, on_log=log)

    log(f"[파이프라인] {blog_id} / '{keyword}' — Claude.ai 글 생성 시작")
    raw = generate_text("", blog_id=blog_id, keyword=keyword_final, on_log=log,
                        extra_context=_api_ctx if _api_ctx else None)

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
            r"\[이미지\s*(\d+)\][^\n]*\n.*?(?:Gemini\s*)?프롬프트:\s*(.+?)\n.*?파일명:\s*(.+?)\n.*?alt:\s*(.+?)(?=\[이미지|\Z)",
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
    MIN_BODY_CHARS_HARD = 2000  # 절대 최소 (이 미만이면 발행 중단)
    MIN_BODY_CHARS_SOFT = 3000  # 권고 최소 (이 미만이면 재생성 1회 시도)

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
                    if not img_m:
                        img_m = re.search(r"===이미지===\s*(.*?)\s*===이미지끝===", raw, re.DOTALL)
                    if title_m:
                        title = _truncate_title(title_m.group(1).strip().split('\n')[0].strip(), max_len=40)
                    body = body_m.group(1).strip() if body_m else body  # body2 미정의 방지
                    if tag_m:
                        tag_line = tag_m.group(1).strip().split('\n')[0].strip()
                        tags = [t.strip() for t in tag_line.split(",") if t.strip()]
                    # 이미지 목록도 재생성 결과에서 업데이트 (핵심 버그 수정: 텍스트와 이미지 불일치 방지)
                    if img_m:
                        new_images = []
                        img_text2 = img_m.group(1)
                        for m2 in re.finditer(
                            r"\[이미지\s*(\d+)\][^\n]*\n.*?(?:Gemini\s*)?프롬프트:\s*(.+?)\n.*?파일명:\s*(.+?)\n.*?alt:\s*(.+?)(?=\[이미지|\Z)",
                            img_text2, re.DOTALL,
                        ):
                            new_images.append({
                                "index": int(m2.group(1)),
                                "prompt": m2.group(2).strip(),
                                "filename": m2.group(3).strip(),
                                "alt": m2.group(4).strip(),
                            })
                        if not new_images:
                            for block in re.findall(r"\[이미지\s*\d+\][^\[]+", img_text2, re.DOTALL):
                                n_m2 = re.search(r"\[이미지\s*(\d+)\]", block)
                                p_m2 = re.search(r"프롬프트:\s*(.+)", block)
                                f_m2 = re.search(r"파일명:\s*(.+)", block)
                                a_m2 = re.search(r"alt:\s*(.+)", block)
                                if n_m2 and p_m2:
                                    new_images.append({
                                        "index": int(n_m2.group(1)),
                                        "prompt": p_m2.group(1).strip(),
                                        "filename": f_m2.group(1).strip() if f_m2 else f"image-{n_m2.group(1)}.jpg",
                                        "alt": a_m2.group(1).strip() if a_m2 else "",
                                    })
                        if new_images:
                            log(f"[검수] 재생성 이미지 목록 업데이트: {len(images)}개 → {len(new_images)}개")
                            images = new_images
                        else:
                            log(f"[검수] ⚠ 재생성 이미지 파싱 실패 — 원본 이미지 목록 유지 (불일치 위험)")
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
        log(f"[검수] ⚠ 본문 권고치 미달 ({char_count}자 < {MIN_BODY_CHARS_SOFT}자) — 임시저장 진행 (목표: 3000자)")
    if not tags:
        log(f"[검수] ⚠ 태그 없음 — 기본 태그로 대체")
        tags = [keyword]  # 최소 키워드라도 태그로 사용
    log(f"[검수] 글 품질 기록 — 본문 {char_count}자, 태그 {len(tags)}개 → 임시저장 진행")

    # 텍스트 체크포인트 저장 — 이미지/Playwright 실패 시 다음 라운드에서 재사용
    _save_text_buffer(blog_id, keyword, title, body, tags, images)

    ok = _run_image_and_post(blog_id, keyword, title, body, tags, images)
    return (ok, title) if ok else (False, title)


def _run_image_and_post(blog_id, keyword, title, body, tags, images):
    """이미지 생성 → 내부링크 → 임시저장 (텍스트 생성 이후 단계만)"""
    from image_router import generate_images_for_blog, generate_thumbnail
    from poster import post_single

    # H2 소제목 개수 = 본문 이미지 수 (최소 1)
    h2_count = len(re.findall(r'^##\s+', body, re.MULTILINE))
    MIN_IMAGES = max(h2_count, 1)
    log(f"[파이프라인] H2 소제목 {h2_count}개 → 본문 이미지 {MIN_IMAGES}개 목표")

    # 본문 이미지 생성 (오버레이 없음)
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
        log(f"[파이프라인] 본문 이미지 {len(image_paths)}개 생성 완료")

    # 본문 이미지 부족 시 Pollinations 폴백 (영문 프롬프트 사용)
    if len(image_paths) < MIN_IMAGES:
        log(f"[파이프라인] ⚠ 이미지 {len(image_paths)}개 < 최소 {MIN_IMAGES}개 — Pollinations 폴백 보충")
        from image_router import _pollinations_image, _enhance_prompt, _get_prompt_style, IMAGES_DIR as _IMG_DIR
        _blog_img_dir = _IMG_DIR / blog_id
        _blog_img_dir.mkdir(parents=True, exist_ok=True)
        style = _get_prompt_style(blog_id, keyword)
        fallback_base = [
            f"high quality photo related to {keyword}",
            f"detailed scene about {keyword}, informative",
            f"representative image for {keyword} topic",
        ]
        for i in range(len(image_paths), MIN_IMAGES):
            new_idx = i + 1
            fb_prompt = _enhance_prompt(blog_id, fallback_base[i % len(fallback_base)], index=new_idx)
            fname = f"fallback_{blog_id}_{new_idx}.jpg"
            fp = str(_blog_img_dir / fname)
            ok = _pollinations_image(fb_prompt, fp, on_log=log)
            if ok:
                images.append({"index": new_idx, "prompt": fb_prompt, "filename": fname, "alt": keyword})
                image_paths[new_idx] = fp
        log(f"[파이프라인] 이미지 보충 후 총 {len(image_paths)}개")

    if len(image_paths) < MIN_IMAGES:
        log(f"[검수] ⚠ 이미지 부족 ({len(image_paths)}개 < {MIN_IMAGES}개) — 임시저장 후 클로드코드 보완 예정")
    else:
        log(f"[검수] ✅ 본문 이미지 {len(image_paths)}개 확인")

    # 썸네일 별도 생성 (오버레이 적용)
    log(f"[파이프라인] 썸네일 생성 중...")
    thumb_path = generate_thumbnail(blog_id, keyword, title, on_log=log)
    if thumb_path:
        image_paths[0] = thumb_path
        log(f"[파이프라인] 썸네일 준비 완료: {thumb_path}")

    # 네이버 블로그 첫 문단 키워드 보장 (검색 결과 CTR 개선)
    if blog_id in ("salim1su", "me1091"):
        first_para = body.split("\n\n")[0] if "\n\n" in body else body.split("\n")[0]
        if keyword and keyword not in first_para:
            body = f"{keyword}에 대해 정리했습니다.\n\n" + body
            log(f"[SEO] 네이버 첫 문단에 키워드 '{keyword}' 삽입 완료")
        else:
            log(f"[SEO] 네이버 첫 문단에 키워드 '{keyword}' 이미 포함됨 (패스)")

    # 내부링크 삽입
    body = _inject_internal_links(body, blog_id, log)

    # 임시저장 (Playwright) — 실패 시 최대 2회 재시도
    log(f"[파이프라인] 포스팅 시작: {blog_id}")
    ok = False
    for _attempt in range(3):
        ok = post_single(
            blog_id=blog_id,
            title=title,
            content=body,
            tags=tags,
            image_paths=image_paths,
            image_infos=images,
            thumbnail_path=thumb_path,
            on_log=log,
        )
        if ok:
            break
        if _attempt < 2:
            log(f"[파이프라인] 포스팅 실패 (시도 {_attempt+1}/3) — 30초 후 재시도")
            time.sleep(30)

    if ok:
        log(f"[파이프라인] {blog_id} / '{keyword}' 임시저장완료 ✅")
        _clear_text_buffer(blog_id)  # 성공 시 버퍼 정리
    else:
        log(f"[파이프라인] {blog_id} / '{keyword}' 포스팅 실패 ⚠ (텍스트 버퍼 보존 — 다음 라운드 재시도)")
    return ok


# ─── 블로그 1편 포스팅 ───
MIN_POST_GAP_HOURS = 3  # 같은 블로그 포스팅 최소 간격


def _hours_since_last_post(blog_id: str) -> float:
    """마지막 발행 이후 경과 시간(시간). 발행 이력 없으면 999 반환.

    publish_drafts.py가 logs/blog_publish_times.json에 기록한 실제 발행 시각을
    우선 참조하고, 없으면 SQLite draft_saved 시각으로 fallback.
    """
    import json as _j
    from datetime import datetime as _dt

    # 1순위: publish_drafts.py가 기록한 실제 발행 시각 (Unix timestamp)
    _times_file = LOG_DIR / "blog_publish_times.json"
    if _times_file.exists():
        try:
            times = _j.loads(_times_file.read_text())
            ts = times.get(blog_id)
            if ts:
                return (_dt.now().timestamp() - float(ts)) / 3600
        except Exception:
            pass

    # 2순위: me1091은 별도 SQLite 테이블 (me1091_published) 사용
    if blog_id == "me1091":
        import sqlite3 as _sq
        _db_path = Path(__file__).parent / "keyword_engine" / "engine.db"
        try:
            with _sq.connect(_db_path) as db:
                row = db.execute(
                    "SELECT published_at FROM me1091_published ORDER BY published_at DESC LIMIT 1"
                ).fetchone()
            if row:
                last_time = _dt.fromisoformat(row[0])
                return (_dt.now() - last_time).total_seconds() / 3600
        except Exception:
            pass
        return 999.0

    # 3순위: SQLite draft_saved 시각
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
    try:
        last_time = _dt.fromisoformat(row[0])
        return (_dt.now() - last_time).total_seconds() / 3600
    except Exception:
        return 999.0


def post_one_blog(blog_id):
    """한 블로그에 키워드 1개 선택 → 포스팅 (SQLite 키워드 엔진만 사용)"""
    import fcntl as _fcntl

    # 블로그별 락 파일 — 동일 블로그에 동시 2개 프로세스 방지 (이미지/텍스트 버퍼 충돌 방지)
    _lock_path = LOG_DIR / f"{blog_id}.lock"
    try:
        _lock_fh = open(_lock_path, "w")
        _fcntl.flock(_lock_fh, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
    except OSError:
        log(f"[{blog_id}] ⚠ 다른 프로세스가 이미 실행 중 (락 파일 있음) — 스킵")
        return False

    try:
        return _post_one_blog_inner(blog_id)
    finally:
        _fcntl.flock(_lock_fh, _fcntl.LOCK_UN)
        _lock_fh.close()
        try:
            _lock_path.unlink(missing_ok=True)
        except Exception:
            pass


def _post_one_blog_inner(blog_id):
    """post_one_blog 실제 로직 (락 획득 후 호출)"""
    # me1091: Notion 상품 기반 Coupang 리뷰 파이프라인 (키워드 DB 사용 안 함)
    if blog_id == "me1091":
        elapsed = _hours_since_last_post("me1091")
        if elapsed < MIN_POST_GAP_HOURS:
            log(f"[me1091] 마지막 포스팅 {elapsed:.1f}시간 전 — 최소 {MIN_POST_GAP_HOURS}시간 필요, 스킵")
            return False
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

    # 이전 텍스트 버퍼 확인 — 이미지/Playwright만 실패했다면 텍스트 재생성 없이 재시도
    buf = _load_text_buffer(blog_id)
    if buf:
        log(f"[{blog_id}] 텍스트 버퍼 발견 ('{buf['keyword']}') — 이미지/포스팅만 재시도")
        try:
            ok, saved_title = run_posting_pipeline(blog_id, buf["keyword"], _resume=buf)
            if ok:
                _db_set(buf["keyword"], "draft_saved", blog_id=blog_id, title=saved_title)
                return True
        except Exception as e:
            log(f"[{blog_id}] 버퍼 재시도 실패: {e}")
        log(f"[{blog_id}] 버퍼 재시도도 실패 — 버퍼 제거 후 새로 생성")
        _clear_text_buffer(blog_id)

    # 테마 부적합 키워드는 스킵하고 다음 키워드 재시도 (최대 5회)
    kw = None
    for _ in range(5):
        candidate = fetch_next_pending(blog_id)
        if not candidate:
            break
        if is_keyword_suitable(blog_id, candidate) and _naver_competition_check(candidate, on_log=log):
            kw = candidate
            break
        log(f"[{blog_id}] ⚠ 테마 부적합 또는 경쟁 높음 '{candidate}' → 스킵")
        _db_set(candidate, "failed", blog_id=blog_id)
    if not kw:
        log(f"[{blog_id}] 대기 키워드 없음 — 스킵")
        return False
    log(f"[{blog_id}] 키워드: {kw}")
    _db_set(kw, "in_progress", blog_id=blog_id)
    try:
        ok, saved_title = run_posting_pipeline(blog_id, kw)
        if ok:
            # 모든 블로그 임시저장 → draft_saved (Claude Code가 검수 후 발행)
            _db_set(kw, "draft_saved", blog_id=blog_id, title=saved_title)
        else:
            _db_set(kw, "failed", blog_id=blog_id)
        return ok
    except Exception as e:
        import traceback as _tb
        tb_str = _tb.format_exc()
        log(f"[{blog_id}] 오류: {e}")
        _db_set(kw, "failed", blog_id=blog_id)
        return False


def run_one_round(round_num):
    """모든 블로그에 1편씩 포스팅 (1라운드) — 순서 랜덤. 실패 블로그는 1회 재시도."""
    import time as _time
    import random as _rand
    # triplog는 nolja100보다 항상 먼저 — 같은 여행 카테고리에서 triplog 우선 배정
    _non_travel = ["salim1su", "baremi542", "goodisak", "woll100", "phn0502", "me1091"]
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

    # 리프레시 대상 확인 (30~60일 된 글)
    try:
        from refresh_posts import run_refresh
        run_refresh()
    except Exception as e:
        log(f"[리프레시] 스킵: {e}")

    # MRT 파트너 블로그 딜 모니터링 (triplog용 프로모션 글 자동 생성)
    try:
        from mrt_deals import run_deal_check
        run_deal_check()
    except Exception as e:
        log(f"[딜모니터] 스킵: {e}")


# ─── 메인 실행 ───
# 사용법: python3 overnight_run.py [blog_id]
#   blog_id 지정 시: 해당 블로그 1편만 생성+임시저장
#   blog_id 없을 시: 전체 블로그 1라운드 실행
if __name__ == "__main__":
    import sys as _sys

    log("=" * 60)
    log(f"자동 실행 시작 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    log("=" * 60)

    # ── 일 1회 작업: 키워드 크롤링 + 롱테일 확장 + 경쟁모니터 (상태파일로 중복 방지) ──
    _STATE_FILE = LOG_DIR / "overnight_state.json"
    _today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        _state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        if _state.get("run_date") != _today_str:
            _state = None
    except Exception:
        _state = None
    if not _state:
        _state = {"run_date": _today_str, "crawling_done": False}
        try:
            _STATE_FILE.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

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
        try:
            _STATE_FILE.write_text(json.dumps(_state, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        save_log()

        log("[롱테일] 키워드 확장 시작")
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
        try:
            from keyword_engine.longtail_expander import expand_longtail
            from keyword_engine.db_handler import get_top_keywords
            _CAT_BLOG = {"여행": ["nolja100", "triplog"], "살림": ["salim1su"],
                         "IT": ["goodisak"], "정부지원금": ["baremi542"],
                         "교통": ["woll100"], "영화": ["phn0502"]}
            for bid, cat in _BLOG_LONGTAIL.items():
                if cat == "여행" and bid == "triplog":
                    continue
                crawled_seeds = []
                for _bid in _CAT_BLOG.get(cat, []):
                    crawled_seeds.extend(_crawled_keywords.get(_bid, []))
                db_seeds = [r["keyword"] for r in get_top_keywords(n=20, min_score=0)
                            if r.get("category", "") == cat and len(r["keyword"].split()) <= 4]
                seen_seeds = set()
                seeds = []
                for kw in crawled_seeds + db_seeds:
                    if kw not in seen_seeds:
                        seen_seeds.add(kw)
                        seeds.append(kw)
                if not seeds:
                    continue
                added = expand_longtail(base_keywords=seeds, category=cat, blog_id=bid,
                                        top_n=8, on_log=log)
                log(f"[롱테일] {bid}({cat}): +{added}개 롱테일 추가")
        except Exception as e:
            log(f"[롱테일] 오류: {e}")

        _today_wd = datetime.now().weekday()
        if _today_wd in (0, 2, 4):
            log("[경쟁모니터] 경쟁 사이트 신규 포스트 감지 시작")
            try:
                from keyword_engine.competitor_monitor import monitor_competitors
                _added = monitor_competitors(on_log=log)
                log(f"[경쟁모니터] 신규 키워드 {_added}개 추가 완료")
            except Exception as _e:
                log(f"[경쟁모니터] 오류: {_e}")
        save_log()
    else:
        log("[크롤링] 오늘 이미 완료 — 스킵")

    # ── 포스팅 실행 ──
    _target_blog = _sys.argv[1] if len(_sys.argv) > 1 else None
    if _target_blog:
        log(f"[실행] 블로그 지정: {_target_blog}")
        ok = post_one_blog(_target_blog)
        log(f"[완료] {_target_blog}: {'✅' if ok else '⚠'}")
    else:
        log("[실행] 전체 블로그 1라운드")
        run_one_round(1)

    log("\n" + "=" * 60)
    log("완료")
    log("=" * 60)
    save_log()
