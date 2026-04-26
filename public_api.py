"""공공데이터포털 + TMDB API 연동 모듈

블로그 글 생성 전 실제 데이터를 extra_context로 주입해 할루시네이션 방지.

지원 API:
- 한국관광공사 축제/행사정보  → nolja100, triplog
- 정부24 공공서비스 정보      → baremi542, goodisak, salim1su
- 복지로 복지서비스 정보       → baremi542 (지역 복지 포함)
- TMDB 영화/드라마 정보       → phn0502 (OTT 시청 가능 플랫폼 포함)
- 네이버 쇼핑 검색 API        → goodisak (IT 제품 정보)
"""
import html as html_mod
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# .env 로드
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_RAW_KEY = os.environ.get("PUBLIC_DATA_API_KEY", "")
# URL 인코딩된 키를 디코딩
SERVICE_KEY = urllib.parse.unquote(_RAW_KEY)

# 네이버 쇼핑 검색 API
NAVER_SEARCH_CLIENT_ID = os.environ.get("NAVER_SEARCH_CLIENT_ID", "")
NAVER_SEARCH_CLIENT_SECRET = os.environ.get("NAVER_SEARCH_CLIENT_SECRET", "")
_NAVER_SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"

# 복지로 복지서비스 API (data.go.kr 별도 신청)
_BOKJIRO_KEY_RAW = os.environ.get("BOKJIRO_API_KEY", "")
BOKJIRO_KEY = urllib.parse.unquote(_BOKJIRO_KEY_RAW) if _BOKJIRO_KEY_RAW else ""
_BOKJIRO_LIST_URL = "http://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfarelistV001"
_BOKJIRO_DETAIL_URL = "http://apis.data.go.kr/B554287/NationalWelfareInformationsV001/NationalWelfaredetailedV001"

# 교통 전용 API 키 (data.go.kr 별도 신청)
EXPRESS_BUS_KEY = os.environ.get("EXPRESS_BUS_API_KEY", SERVICE_KEY)
BUS_STOP_KEY = os.environ.get("BUS_STOP_API_KEY", SERVICE_KEY)
SEOUL_BUS_KEY = os.environ.get("SEOUL_BUS_API_KEY", SERVICE_KEY)
BUSAN_BUS_KEY = os.environ.get("BUSAN_BUS_API_KEY", SERVICE_KEY)

# 한국관광공사 API
_FESTIVAL_URL = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
# 정부24 공공서비스 API
_GOV_SERVICE_URL = "https://api.odcloud.kr/api/gov24/v3/serviceList"
# 버스정류소 API (TAGO) — 서울은 자체 TOPIS 사용이라 제외
_BUS_STOP_URL = "http://apis.data.go.kr/1613000/BusSttnInfoInqireService/getSttnNoList"
# 도시코드 (TAGO 버스정류소) — 서울(11) 제외
_BUS_CITY_CODES = {
    "부산": "21", "대구": "22", "인천": "23", "광주": "24",
    "대전": "25", "울산": "26", "세종": "29",
    "수원": "31060", "춘천": "32010", "강릉": "32030", "속초": "32050",
    "청주": "33010", "천안": "34020", "전주": "35010", "여수": "36040",
    "순천": "36050", "목포": "36060", "포항": "37030", "경주": "37040",
    "안동": "37010", "창원": "38010", "진주": "38030", "통영": "38050",
}


def _get(url: str, params: dict, service_key: str = None) -> dict:
    params["serviceKey"] = service_key or SERVICE_KEY
    params["_type"] = "json"
    full_url = url + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(full_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def _extract_region(keyword: str) -> str:
    """키워드에서 지역명 추출 (단순 포함 검색)."""
    regions = [
        "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
        "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
        "수원", "고양", "용인", "성남", "부천", "안산", "화성", "남양주",
        "전주", "청주", "천안", "안양", "창원", "포항", "김해", "진주",
        "속초", "강릉", "춘천", "양양", "평창", "여수", "순천", "목포",
        "경주", "안동", "통영", "거제", "남해",
    ]
    for r in regions:
        if r in keyword:
            return r
    return ""


def fetch_festival_context(keyword: str, on_log=None) -> str:
    """키워드 지역의 현재~3개월 내 축제 정보를 문자열로 반환.

    Returns: extra_context 문자열 (없으면 빈 문자열)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not SERVICE_KEY:
        log("[PublicAPI] API 키 없음 — 축제 데이터 스킵")
        return ""

    region = _extract_region(keyword)
    today = datetime.now()
    start_date = today.strftime("%Y%m%d")
    # 3개월 후
    end_month = today.month + 3
    end_year = today.year + (end_month - 1) // 12
    end_month = ((end_month - 1) % 12) + 1
    end_date = f"{end_year}{end_month:02d}28"

    params = {
        "numOfRows": "10",
        "pageNo": "1",
        "MobileOS": "ETC",
        "MobileApp": "blog-auto",
        "eventStartDate": start_date,
        "eventEndDate": end_date,
        "arrange": "A",  # 제목순
    }
    if region:
        # areaCode 매핑 (한국관광공사 지역코드)
        area_map = {
            "서울": "1", "인천": "2", "대전": "3", "대구": "4", "광주": "5",
            "부산": "6", "울산": "7", "세종": "8", "경기": "31", "강원": "32",
            "충북": "33", "충남": "34", "경북": "35", "경남": "36", "전북": "37",
            "전남": "38", "제주": "39",
        }
        area_code = area_map.get(region, "")
        if area_code:
            params["areaCode"] = area_code
            log(f"[PublicAPI] 축제 검색: {region} (areaCode={area_code}), {start_date}~{end_date}")
        else:
            log(f"[PublicAPI] 축제 검색: 전국, {start_date}~{end_date}")
    else:
        log(f"[PublicAPI] 축제 검색: 전국 (지역 미추출), {start_date}~{end_date}")

    data = _get(_FESTIVAL_URL, params)

    if "error" in data:
        log(f"[PublicAPI] 축제 API 오류: {data['error']}")
        return ""

    try:
        items = data["response"]["body"]["items"]
        if not items:
            log("[PublicAPI] 축제 검색 결과 없음")
            return ""
        item_list = items.get("item", [])
        if isinstance(item_list, dict):
            item_list = [item_list]
        if not item_list:
            log("[PublicAPI] 축제 항목 없음")
            return ""

        lines = [f"[현재 {region or '전국'} 축제/행사 정보 (공공데이터포털)]"]
        for item in item_list[:5]:
            name = item.get("title", "")
            addr = item.get("addr1", "") + item.get("addr2", "")
            start = item.get("eventstartdate", "")
            end = item.get("eventenddate", "")
            tel = item.get("tel", "")
            if name:
                lines.append(f"- 행사명: {name}")
                if addr:
                    lines.append(f"  주소: {addr}")
                if start:
                    lines.append(f"  기간: {start} ~ {end}")
                if tel:
                    lines.append(f"  전화: {tel}")
        ctx = "\n".join(lines)
        log(f"[PublicAPI] 축제 데이터 {len(item_list)}건 수집 완료")
        return ctx
    except Exception as e:
        log(f"[PublicAPI] 축제 데이터 파싱 실패: {e}")
        return ""


_TOUR_SPOT_URL = "https://apis.data.go.kr/B551011/KorService2/searchKeyword2"
_TOUR_DETAIL_URL = "https://apis.data.go.kr/B551011/KorService2/detailCommon2"

# 한국관광공사 contentTypeId
_CONTENT_TYPE = {
    "관광지": "12",
    "숙박": "32",
    "음식점": "39",
    "행사": "15",
}

_AREA_MAP = {
    "서울": "1", "인천": "2", "대전": "3", "대구": "4", "광주": "5",
    "부산": "6", "울산": "7", "세종": "8", "경기": "31", "강원": "32",
    "충북": "33", "충남": "34", "경북": "35", "경남": "36", "전북": "37",
    "전남": "38", "제주": "39",
}


def fetch_travel_context(keyword: str, on_log=None) -> str:
    """키워드 지역의 관광지 + 숙박 + 음식점 + 축제 정보를 반환.

    Returns: extra_context 문자열 (없으면 빈 문자열)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not SERVICE_KEY:
        log("[PublicAPI] API 키 없음 — 여행 데이터 스킵")
        return ""

    region = _extract_region(keyword)

    # 키워드에서 구체적인 장소명 추출 (지역명 제거 후 나머지)
    spot_query = keyword
    for r in list(_AREA_MAP.keys()) + ["국내", "해외", "추천", "여행", "코스"]:
        spot_query = spot_query.replace(r, "").strip()
    spot_query = spot_query.strip() or region or keyword

    area_code = _AREA_MAP.get(region, "")
    base_params = {
        "numOfRows": "5",
        "pageNo": "1",
        "MobileOS": "ETC",
        "MobileApp": "blog-auto",
        "arrange": "Q",  # 평점순
        "keyword": spot_query,
    }
    if area_code:
        base_params["areaCode"] = area_code

    all_lines = []

    # 1. 관광지
    p = {**base_params, "contentTypeId": _CONTENT_TYPE["관광지"]}
    data = _get(_TOUR_SPOT_URL, p)
    try:
        items = data["response"]["body"]["items"]
        item_list = items.get("item", []) if items else []
        if isinstance(item_list, dict):
            item_list = [item_list]
        if item_list:
            all_lines.append(f"[관광지 정보 ({region or spot_query})]")
            for it in item_list[:3]:
                name = it.get("title", "")
                addr = (it.get("addr1", "") + " " + it.get("addr2", "")).strip()
                tel = it.get("tel", "")
                if name:
                    line = f"- {name}"
                    if addr:
                        line += f" / {addr}"
                    if tel:
                        line += f" / {tel}"
                    all_lines.append(line)
            log(f"[PublicAPI] 관광지 {len(item_list)}건 수집")
    except Exception:
        pass

    # 2. 숙박
    p2 = {**base_params, "contentTypeId": _CONTENT_TYPE["숙박"], "keyword": region or spot_query}
    data2 = _get(_TOUR_SPOT_URL, p2)
    try:
        items2 = data2["response"]["body"]["items"]
        item_list2 = items2.get("item", []) if items2 else []
        if isinstance(item_list2, dict):
            item_list2 = [item_list2]
        if item_list2:
            all_lines.append(f"[숙박 정보 ({region or spot_query})]")
            for it in item_list2[:3]:
                name = it.get("title", "")
                addr = (it.get("addr1", "") + " " + it.get("addr2", "")).strip()
                tel = it.get("tel", "")
                if name:
                    line = f"- {name}"
                    if addr:
                        line += f" / {addr}"
                    if tel:
                        line += f" / {tel}"
                    all_lines.append(line)
            log(f"[PublicAPI] 숙박 {len(item_list2)}건 수집")
    except Exception:
        pass

    # 3. 음식점
    p3 = {**base_params, "contentTypeId": _CONTENT_TYPE["음식점"], "keyword": region or spot_query}
    data3 = _get(_TOUR_SPOT_URL, p3)
    try:
        items3 = data3["response"]["body"]["items"]
        item_list3 = items3.get("item", []) if items3 else []
        if isinstance(item_list3, dict):
            item_list3 = [item_list3]
        if item_list3:
            all_lines.append(f"[맛집/음식점 정보 ({region or spot_query})]")
            for it in item_list3[:3]:
                name = it.get("title", "")
                addr = (it.get("addr1", "") + " " + it.get("addr2", "")).strip()
                tel = it.get("tel", "")
                if name:
                    line = f"- {name}"
                    if addr:
                        line += f" / {addr}"
                    if tel:
                        line += f" / {tel}"
                    all_lines.append(line)
            log(f"[PublicAPI] 음식점 {len(item_list3)}건 수집")
    except Exception:
        pass

    # 4. 축제 (기존 함수 결과 병합)
    festival_ctx = fetch_festival_context(keyword, on_log=on_log)
    if festival_ctx:
        all_lines.append(festival_ctx)

    if not all_lines:
        log(f"[PublicAPI] 여행 데이터 없음 ({keyword})")
        return ""

    return "\n".join(all_lines)


def fetch_bokjiro_context(keyword: str, on_log=None) -> str:
    """복지로 API로 복지서비스 목록 조회 후 context 반환.

    data.go.kr B554287/NationalWelfareInformationsV001 서비스 사용.
    BOKJIRO_API_KEY 환경변수 필요.

    Returns: extra_context 문자열 (없으면 빈 문자열)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    key = BOKJIRO_KEY or SERVICE_KEY
    if not key:
        log("[복지로API] API 키 없음 — 스킵")
        return ""

    # SEO 부사구 제거 후 핵심 검색어 추출
    _strip = re.compile(
        r"(서류\s*준비\s*없이|빠르게|쉽게|간단하게|신청하는\s*법|"
        r"신청\s*방법|조건\s*금액|신청\s*자격|총정리|완벽정리|한눈에|"
        r"\d{4}년?\s*최신|2026\s*년?\s*기준|최신\s*정보|"
        r"얼마\s*받나|얼마나|받나|지급액과|대상자별|혜택금액|"
        r"지원금액|지급방법|지급일|지급기준|얼마씩|월\s*얼마|어떻게|어디서)",
        re.IGNORECASE,
    )
    _stop = {"월", "일", "년", "원", "명", "개", "건", "회", "번", "차",
             "및", "또", "등", "의", "을", "를", "이", "가", "은", "는",
             "얼마", "몇", "어떤", "누구", "언제", "어디", "왜", "어떻게",
             "받을", "받나", "있나", "있어", "있는", "수", "되나", "되는",
             "하는", "하나", "인지", "인가", "할까", "해야", "인데", "이고"}
    # 복지 용어 단축 정규화 (API 제목 검색 호환)
    _welfare_norm = {
        "차상위계층": "차상위", "기초생활수급자": "기초수급", "기초수급자": "기초수급",
        "의료급여수급자": "의료급여", "장애인복지": "장애인", "노인복지": "노인",
        "한부모가족": "한부모", "다문화가족": "다문화", "청소년복지": "청소년",
    }

    cleaned = _strip.sub("", keyword).strip()
    words = [w for w in cleaned.split() if len(w) >= 2 and w not in _stop]
    # 정규화 적용
    words = [_welfare_norm.get(w, w) for w in words]

    # 2단어 → 1단어 → 4자 초과 시 앞 3자 로 폴백
    candidates = []
    if len(words) >= 2:
        candidates.append(" ".join(words[:2]))
    if words:
        candidates.append(words[0])
    # 첫 단어가 5자 이상이면 앞 3자도 후보
    if words and len(words[0]) >= 5:
        candidates.append(words[0][:3])

    def _call(search_kw: str, srch_code: str = "001") -> list:
        """복지로 API 호출 → servList 목록 반환 (없으면 [])"""
        params = {
            "serviceKey": key,
            "callTp": "L",
            "pageNo": "1",
            "numOfRows": "5",
            "srchKeyCode": srch_code,  # 001=제목, 002=내용, 003=제목+내용
            "searchWrd": search_kw,
        }
        url = _BOKJIRO_LIST_URL + "?" + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
        except Exception as e:
            log(f"[복지로API] 호출 실패: {e}")
            return []
        try:
            root = ET.fromstring(raw)
            code = root.findtext(".//resultCode") or ""
            # 0 = 성공, 40 = NO DATA FOUND (정상 케이스)
            if code not in ("0", "00", "40", ""):
                log(f"[복지로API] API 오류 코드 {code}: {root.findtext('.//resultMessage') or ''}")
                return []
            return root.findall(".//servList")
        except ET.ParseError:
            return []

    items = []
    search_kw = ""
    # 1차: 제목 검색(001) → 2차: 제목+내용 검색(003)
    for srch_code in ("001", "003"):
        for cand in candidates:
            log(f"[복지로API] 검색어: '{cand}' srch={srch_code} (원본: '{keyword}')")
            items = _call(cand, srch_code)
            if items:
                search_kw = cand
                break
            log(f"[복지로API] '{cand}' 결과 없음 (srch={srch_code})")
        if items:
            break

    if not items:
        log(f"[복지로API] 검색 결과 없음 — 폴백")
        return ""

    lines = [f"[복지로 복지서비스 정보 ('{search_kw}' 검색 결과)]"]
    for item in items[:3]:
        def t(tag): return (item.findtext(tag) or "").strip()

        name = t("servNm")
        dept = t("jurMnofNm")
        target = t("trgterIndvdlArray")
        summary = t("servDgst")
        cycle = t("sprtCycNm")
        give_type = t("srvPvsnNm")
        detail_link = t("servDtlLink")
        theme = t("intrsThemaArray")

        if not name:
            continue
        lines.append(f"\n[서비스] {name}")
        if dept:
            lines.append(f"  소관기관: {dept}")
        if target:
            lines.append(f"  지원대상: {target[:100]}")
        if give_type:
            lines.append(f"  급여유형: {give_type}")
        if cycle:
            lines.append(f"  지급주기: {cycle}")
        if theme:
            lines.append(f"  관심주제: {theme[:80]}")
        if summary:
            lines.append(f"  요약: {summary[:200]}")
        if detail_link:
            lines.append(f"  상세: {detail_link}")

    if len(lines) <= 1:
        log(f"[복지로API] 파싱 결과 없음")
        return ""

    ctx = "\n".join(lines)
    log(f"[복지로API] {len(items)}건 수집 완료 ({len(ctx)}자)")
    return ctx


def fetch_gov_service_context(keyword: str, on_log=None) -> str:
    """키워드 관련 정부24 공공서비스 정보를 문자열로 반환.

    Returns: extra_context 문자열 (없으면 빈 문자열)
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not SERVICE_KEY:
        log("[PublicAPI] API 키 없음 — 공공서비스 데이터 스킵")
        return ""

    # 키워드에서 검색어 추출 — SEO 부사구·의문어 제거 후 핵심 2단어
    _strip = re.compile(
        r"(서류\s*준비\s*없이|빠르게|쉽게|간단하게|신청하는\s*법|"
        r"신청\s*방법|조건\s*금액|신청\s*자격|총정리|완벽정리|한눈에|"
        r"\d{4}년?\s*최신|2026\s*년?\s*기준|최신\s*정보|"
        r"얼마\s*받나|얼마나|받나|지급액과|대상자별|혜택금액|"
        r"지원금액|지급방법|지급일|지급기준|얼마씩|월\s*얼마|어떻게|어디서)",
        re.IGNORECASE,
    )
    _stop = {"월", "일", "년", "원", "명", "개", "건", "회", "번", "차",
             "및", "또", "등", "의", "을", "를", "이", "가", "은", "는",
             "얼마", "몇", "어떤", "누구", "언제", "어디", "왜", "어떻게",
             "받을", "받나", "있나", "있어", "있는", "수", "되나", "되는",
             "하는", "하나", "인지", "인가", "할까", "해야", "인데", "이고"}
    cleaned = _strip.sub("", keyword).strip()
    words = [w for w in cleaned.replace(",", " ").split() if len(w) >= 2 and w not in _stop]
    search_kw = " ".join(words[:2]) if words else keyword[:10]

    def _search(q: str) -> list:
        params = {"page": "1", "perPage": "5", "cond[서비스명::LIKE]": q}
        log(f"[PublicAPI] 공공서비스 검색: '{q}'")
        d = _get(_GOV_SERVICE_URL, params)
        if "error" in d:
            log(f"[PublicAPI] 공공서비스 API 오류: {d['error']}")
            return []
        return d.get("data", [])

    items = _search(search_kw)

    # 1차 검색 실패 시 — API에 없는 지역/특수 프로그램일 가능성 높음
    # fallback 데이터는 주입하지 않음 (엉뚱한 프로그램 혼입 방지)
    if not items:
        log(f"[PublicAPI] '{search_kw}' 검색 결과 없음 — 관련 없는 데이터 주입 방지로 스킵")
        if items:
            search_kw = fallback_kw

    try:
        if not items:
            log("[PublicAPI] 공공서비스 검색 결과 없음")
            return ""

        lines = [f"[정부24 공공서비스 정보 ('{search_kw}' 검색 결과)]"]
        for item in items[:3]:
            name = item.get("서비스명", "")
            summary = item.get("서비스목적요약", "") or item.get("서비스목적", "")
            dept = item.get("소관기관명", "")
            target = item.get("지원대상", "")
            amount = item.get("지원내용", "")
            url = item.get("상세조회URL", "")
            if name:
                lines.append(f"\n[서비스] {name}")
                if dept:
                    lines.append(f"  소관기관: {dept}")
                if target:
                    lines.append(f"  지원대상: {target[:100]}")
                if amount:
                    lines.append(f"  지원내용: {amount[:150]}")
                if summary:
                    lines.append(f"  요약: {summary[:100]}")
                if url:
                    lines.append(f"  상세: {url}")
        ctx = "\n".join(lines)
        log(f"[PublicAPI] 공공서비스 데이터 {len(items)}건 수집 완료")
        return ctx
    except Exception as e:
        log(f"[PublicAPI] 공공서비스 데이터 파싱 실패: {e}")
        return ""


_TMDB_KEY = os.environ.get("TMDB_API_KEY", "")
_TMDB_BASE = "https://api.themoviedb.org/3"

# 한국 OTT 제공업체 ID 매핑
_KR_PROVIDER_NAMES = {
    8: "넷플릭스",
    356: "웨이브",
    97: "왓챠",
    96: "티빙",
    337: "디즈니+",
    582: "쿠팡플레이",
    119: "아마존 프라임",
    350: "애플TV+",
}


def _tmdb_get(path: str, params: dict = None) -> dict:
    params = params or {}
    params["api_key"] = _TMDB_KEY
    params["language"] = "ko-KR"
    url = _TMDB_BASE + path + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def fetch_tmdb_context(keyword: str, on_log=None) -> str:
    """키워드로 TMDB 영화/드라마 검색 후 OTT 시청 정보 포함한 context 반환."""
    def log(msg):
        if on_log:
            on_log(msg)

    if not _TMDB_KEY:
        return ""

    # 영화/드라마 구분 힌트
    is_tv = any(w in keyword for w in ["드라마", "시즌", "시리즈", "OTT", "오리지널"])

    # 제목 추출 (OTT명, "추천", "분석" 등 제거)
    remove_words = ["넷플릭스", "웨이브", "왓챠", "티빙", "디즈니+", "쿠팡플레이",
                    "추천", "분석", "리뷰", "결말", "해석", "줄거리", "드라마", "영화",
                    "시즌", "오리지널", "시리즈"]
    search_q = keyword
    for w in remove_words:
        search_q = search_q.replace(w, "").strip()
    search_q = search_q.strip()
    if not search_q:
        search_q = keyword

    # 검색
    media_type = "tv" if is_tv else "movie"
    data = _tmdb_get(f"/search/{media_type}", {"query": search_q})
    results = data.get("results", [])

    # movie 실패시 tv도 시도
    if not results and media_type == "movie":
        data2 = _tmdb_get("/search/tv", {"query": search_q})
        results2 = data2.get("results", [])
        if results2:
            results = results2
            media_type = "tv"

    if not results:
        log(f"[TMDB] '{search_q}' 검색 결과 없음")
        return ""

    item = results[0]
    tmdb_id = item.get("id")
    title = item.get("title") or item.get("name", "")
    overview = item.get("overview", "")
    vote = item.get("vote_average", 0)
    release = item.get("release_date") or item.get("first_air_date", "")
    log(f"[TMDB] 검색 결과: {title} ({release[:4] if release else '?'}) — {vote}/10")

    # 상세 정보
    detail = _tmdb_get(f"/{media_type}/{tmdb_id}", {"append_to_response": "credits"})
    genres = [g["name"] for g in detail.get("genres", [])]
    runtime = detail.get("runtime") or detail.get("episode_run_time", [None])[0] if detail.get("episode_run_time") else None
    cast = [c["name"] for c in detail.get("credits", {}).get("cast", [])[:5]]
    crew = detail.get("credits", {}).get("crew", [])
    director = next((c["name"] for c in crew if c.get("job") == "Director"), "")

    # 한국 OTT 시청 가능 플랫폼
    watch_data = _tmdb_get(f"/{media_type}/{tmdb_id}/watch/providers")
    kr_providers = watch_data.get("results", {}).get("KR", {})
    flatrate = kr_providers.get("flatrate", [])  # 월정액 포함
    rent = kr_providers.get("rent", [])          # 개별 구매/렌탈
    ott_list = []
    seen = set()
    for p in flatrate + rent:
        pid = p.get("provider_id")
        name = _KR_PROVIDER_NAMES.get(pid, p.get("provider_name", ""))
        if name and name not in seen:
            ott_list.append(name + ("(월정액)" if p in flatrate else "(개별구매)"))
            seen.add(name)

    # context 조립
    lines = [
        f"[TMDB 실제 데이터]",
        f"제목: {title}",
        f"장르: {', '.join(genres)}",
        f"평점: {vote}/10 (TMDB 기준)",
    ]
    if release:
        lines.append(f"개봉/공개: {release[:7]}")
    if runtime:
        lines.append(f"러닝타임: {runtime}분")
    if director:
        lines.append(f"감독: {director}")
    if cast:
        lines.append(f"주요 출연: {', '.join(cast)}")
    if overview:
        lines.append(f"줄거리(참고용): {overview[:200]}")
    if ott_list:
        lines.append(f"한국 OTT 시청 가능: {', '.join(ott_list)}")
    else:
        lines.append("한국 OTT 시청 가능: 정보 없음 (직접 각 플랫폼에서 확인)")

    context = "\n".join(lines)
    log(f"[TMDB] context 생성 완료 ({len(context)}자)")
    return context


# 교통 API 엔드포인트 (http 필수 — https 사용 시 500 오류)
_EXPRESS_BUS_URL = "http://apis.data.go.kr/1613000/ExpBusInfo/GetStrtpntAlocFndExpbusInfo"
_EXPRESS_BUS_TERMINAL_URL = "http://apis.data.go.kr/1613000/ExpBusInfo/GetExpBusTrminlList"

# 주요 터미널 코드 (고속버스) — GetExpBusTrminlList API 기준
_TERMINAL_CODES = {
    "서울": "NAEK010", "강남": "NAEK020", "센트럴": "NAEK020", "동서울": "NAEK030",
    "수원": "NAEK110", "인천": "NAEK100", "부산": "NAEK700",
    "대구": "NAEK800", "광주": "NAEK500", "대전": "NAEK300",
    "울산": "NAEK750", "전주": "NAEK600", "청주": "NAEK400",
    "춘천": "NAEK250", "강릉": "NAEK200", "속초": "NAEK230",
    "여수": "NAEK550", "순천": "NAEK530", "목포": "NAEK560",
    "포항": "NAEK850", "경주": "NAEK830", "안동": "NAEK820",
    "진주": "NAEK780", "통영": "NAEK770", "제주": "NAEK900",
}


def _extract_transport_locations(keyword: str):
    """키워드에서 출발지/도착지 추출."""
    # "A에서 B" / "A-B" / "A B" 패턴
    import re
    m = re.search(r'([가-힣]+)\s*(?:에서|→|->|-)\s*([가-힣]+)', keyword)
    if m:
        return m.group(1), m.group(2)
    # 지역명 2개 연속
    regions = list(_TERMINAL_CODES.keys())
    found = [r for r in regions if r in keyword]
    if len(found) >= 2:
        return found[0], found[1]
    if len(found) == 1:
        return found[0], ""
    return "", ""


def fetch_transport_context(keyword: str, on_log=None) -> str:
    """교통 키워드에서 실제 노선/요금/시간표 정보를 반환.

    고속버스, 시외버스, KTX, 공항버스를 자동 감지.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    if not SERVICE_KEY:
        log("[교통API] 공공데이터 API 키 없음 — 스킵")
        return ""

    dep, arr = _extract_transport_locations(keyword)
    is_express = any(w in keyword for w in ["고속버스", "고속", "강남버스", "동서울버스"])
    is_ktx = any(w in keyword for w in ["KTX", "ktx", "기차", "무궁화", "새마을", "ITX"])
    is_airport = any(w in keyword for w in ["공항버스", "공항리무진", "리무진", "인천공항", "김포공항", "김해공항"])
    is_intercity = any(w in keyword for w in ["시외버스", "시외"])

    lines = []
    log(f"[교통API] 키워드 분석: dep={dep}, arr={arr}, 유형={'공항' if is_airport else 'KTX' if is_ktx else '고속' if is_express else '시외' if is_intercity else '교통'}")

    # 고속버스 노선 조회
    if is_express or (dep and arr and not is_ktx and not is_airport):
        dep_code = _TERMINAL_CODES.get(dep, "")
        arr_code = _TERMINAL_CODES.get(arr, "")
        if dep_code and arr_code:
            today = datetime.now().strftime("%Y%m%d")
            params = {
                "numOfRows": "10", "pageNo": "1",
                "depTerminalId": dep_code, "arrTerminalId": arr_code,
                "depPlandTime": today,
            }
            data = _get(_EXPRESS_BUS_URL, params, service_key=EXPRESS_BUS_KEY)
            try:
                items = data["response"]["body"]["items"]
                item_list = items.get("item", []) if items else []
                if isinstance(item_list, dict):
                    item_list = [item_list]
                if item_list:
                    lines.append(f"[고속버스 운행정보: {dep} → {arr}]")
                    for it in item_list[:5]:
                        dep_raw = str(it.get("depPlandTime", ""))
                        arr_raw = str(it.get("arrPlandTime", ""))
                        # 형식: YYYYMMDDHHMM (12자리) or YYYYMMDD (8자리)
                        dep_time = f"{dep_raw[8:10]}:{dep_raw[10:12]}" if len(dep_raw) >= 12 else dep_raw[8:]
                        arr_time = f"{arr_raw[8:10]}:{arr_raw[10:12]}" if len(arr_raw) >= 12 else arr_raw[8:]
                        charge = it.get("charge", "")
                        grade = it.get("gradeNm", "")
                        if dep_time.strip(":"):
                            line = f"- {dep_time} 출발 → {arr_time} 도착"
                            if grade:
                                line += f" ({grade})"
                            if charge:
                                line += f" / {int(charge):,}원"
                            lines.append(line)
                    log(f"[교통API] 고속버스 {len(item_list)}건 수집")
            except Exception as e:
                log(f"[교통API] 고속버스 파싱 오류: {e}")
        else:
            log(f"[교통API] 터미널 코드 없음: dep={dep}({dep_code}), arr={arr}({arr_code})")

    # KTX/기차
    if is_ktx:
        lines.append(f"[KTX/열차 정보: {dep or '출발지'} → {arr or '도착지'}]")
        lines.append("- 코레일 예약: www.letskorail.com / 1544-7788")
        lines.append(f"- KTX 서울-부산 약 2시간 30분, 59,800원~")
        lines.append(f"- KTX 서울-광주송정 약 1시간 40분, 46,800원~")
        lines.append(f"- KTX 서울-대전 약 50분, 23,700원~")
        lines.append(f"- KTX 서울-강릉 약 1시간 50분, 27,600원~")
        lines.append("※ 실제 요금/시간은 코레일 사이트에서 확인 (할인 운임 별도)")
        log("[교통API] KTX 기본 정보 삽입")

    # 공항버스/리무진
    if is_airport:
        airport = "인천공항" if "인천" in keyword else "김포공항" if "김포" in keyword else "김해공항" if "김해" in keyword else "공항"
        lines.append(f"[{airport} 버스/리무진 정보]")
        if "인천" in keyword:
            lines.append("- 인천공항 제1터미널·제2터미널 운행")
            lines.append("- 공항버스 예약: www.airportbus.or.kr / 1644-2700")
            lines.append("- 서울 주요 지역까지 6,000~18,000원 / 60~90분 소요")
            lines.append("- 김포공항 ↔ 인천공항 리무진: 약 7,000원 / 40~60분")
        elif "김포" in keyword:
            lines.append("- 김포공항 버스 예약: 1644-2700")
            lines.append("- 서울 시내까지 3,000~6,000원 / 30~60분 소요")
        lines.append("※ 시간대별 배차·요금은 공항버스 공식 사이트에서 확인")
        log("[교통API] 공항버스 기본 정보 삽입")

    # 시외버스
    if is_intercity:
        lines.append(f"[시외버스 정보: {dep or '출발지'} → {arr or '도착지'}]")
        lines.append("- 시외버스 예약: www.bustago.or.kr / 1588-6900")
        lines.append("- 전국 주요 노선 시간표·요금 조회 가능")
        log("[교통API] 시외버스 기본 정보 삽입")

    # 버스정류소 위치 조회 (도착지 기준)
    stop_city = arr or dep
    city_code = _BUS_CITY_CODES.get(stop_city, "")
    if city_code and stop_city:
        params_stop = {"cityCode": city_code, "nodeName": stop_city, "numOfRows": "5", "pageNo": "1"}
        try:
            data_stop = _get(_BUS_STOP_URL, params_stop, service_key=BUS_STOP_KEY)
            stop_items = (data_stop.get("response", {}).get("body", {}).get("items") or {})
            stop_list = stop_items.get("item", []) if isinstance(stop_items, dict) else []
            if isinstance(stop_list, dict):
                stop_list = [stop_list]
            if stop_list:
                lines.append(f"[{stop_city} 주요 버스정류소]")
                for s in stop_list[:5]:
                    nm = s.get("nodenm", "")
                    lat = s.get("gpslati", "")
                    lng = s.get("gpslong", "")
                    if nm:
                        loc = f" (위도 {lat:.4f}, 경도 {lng:.4f})" if lat and lng else ""
                        lines.append(f"- {nm}{loc}")
                log(f"[교통API] {stop_city} 버스정류소 {len(stop_list)}개 수집")
        except Exception as e:
            log(f"[교통API] 버스정류소 조회 오류: {e}")

    if not lines:
        log(f"[교통API] 매칭 유형 없음 — 기본 교통 안내만 제공")
        lines.append(f"[교통 정보: {keyword}]")
        lines.append("- 고속버스: www.kobus.co.kr / 1588-6900")
        lines.append("- 시외버스: www.bustago.or.kr")
        lines.append("- KTX·열차: www.letskorail.com / 1544-7788")
        lines.append("- 공항버스: www.airportbus.or.kr / 1644-2700")

    return "\n".join(lines)


def _simplify_product_query(keyword: str) -> str:
    """IT 제품 키워드에서 핵심 제품명만 추출.

    예: "엘지 그램 노트북 발열이랑 스펙" → "LG 그램 노트북"
        "갤럭시 s25 울트라 카메라 성능" → "갤럭시 s25 울트라"
    """
    # 제거할 노이즈 패턴 (동사/형용사/조사 등)
    noise = [
        r"이랑\s*\w+", r"하는\s*법", r"설정\s*방법", r"사용\s*법", r"구매\s*가이드",
        r"차이점?", r"비교", r"추천", r"후기", r"리뷰", r"가성비", r"발열", r"배터리",
        r"성능", r"스펙", r"가격", r"할인", r"최저가", r"고르는\s*법", r"선택\s*기준",
        r"입문자?", r"직장인", r"학생", r"디자이너", r"영상\s*편집",
    ]
    q = keyword
    for pat in noise:
        q = re.sub(pat, "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s+", " ", q).strip()
    # 너무 짧아지면 원본 앞 3단어 사용
    words = q.split()
    if len(q) < 4 and keyword:
        words = keyword.split()[:3]
    return " ".join(words[:4])  # 최대 4단어


def fetch_naver_shopping_context(keyword: str, on_log=None) -> str:
    """네이버 쇼핑 검색 API로 IT 제품 정보를 가져와 extra_context로 반환."""
    def log(msg):
        if on_log:
            on_log(msg)

    if not NAVER_SEARCH_CLIENT_ID or not NAVER_SEARCH_CLIENT_SECRET:
        log("[네이버쇼핑] API 키 없음 — 건너뜀")
        return ""

    query = _simplify_product_query(keyword)
    log(f"[네이버쇼핑] 검색어: '{query}' (원본: '{keyword}')")

    params = urllib.parse.urlencode({
        "query": query,
        "display": 5,
        "sort": "sim",
    })
    url = f"{_NAVER_SHOP_URL}?{params}"
    try:
        req = urllib.request.Request(url, headers={
            "X-Naver-Client-Id": NAVER_SEARCH_CLIENT_ID,
            "X-Naver-Client-Secret": NAVER_SEARCH_CLIENT_SECRET,
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"[네이버쇼핑] API 호출 오류: {e}")
        return ""

    items = data.get("items", [])
    if not items:
        log(f"[네이버쇼핑] 결과 없음: {query}")
        return ""

    lines = [f"[네이버 쇼핑 검색 결과 — {query}]"]
    seen_titles = set()
    for item in items[:5]:
        title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        title = html_mod.unescape(title).strip()
        if title in seen_titles:
            continue
        seen_titles.add(title)
        brand = item.get("brand", "").strip()
        maker = item.get("maker", "").strip()
        low = item.get("lprice", "")
        high = item.get("hprice", "")
        category = item.get("category1", "")
        price_str = f"{int(low):,}원" if low else "가격 미정"
        if high and high != low:
            price_str += f" ~ {int(high):,}원"
        parts = [f"- 상품명: {title}"]
        if brand:
            parts.append(f"  브랜드: {brand}")
        if maker and maker != brand:
            parts.append(f"  제조사: {maker}")
        parts.append(f"  최저가: {price_str}")
        if category:
            parts.append(f"  카테고리: {category}")
        lines.append("\n".join(parts))

    log(f"[네이버쇼핑] {len(seen_titles)}개 제품 정보 수집")
    return "\n\n".join(lines)


def fetch_context_for_blog(blog_id: str, keyword: str, on_log=None) -> str:
    """blog_id에 따라 적합한 공공API 데이터를 가져와 extra_context로 반환.

    overnight_run.py → generate_text(..., extra_context=...) 에 주입용.
    """
    if blog_id in {"nolja100", "triplog"}:
        # 여행 블로그: 관광지 + 숙박 + 음식점 + 축제 통합 정보
        return fetch_travel_context(keyword, on_log=on_log)
    elif blog_id in {"baremi542", "salim1su"}:
        welfare_hints = ["지원", "혜택", "신청", "급여", "보조", "복지", "정책", "수당", "바우처"]
        if any(h in keyword for h in welfare_hints):
            if blog_id == "baremi542" and BOKJIRO_KEY:
                # baremi542: 복지로 API 우선 (지역 복지 포함), 실패 시 정부24 폴백
                ctx = fetch_bokjiro_context(keyword, on_log=on_log)
                return ctx if ctx else fetch_gov_service_context(keyword, on_log=on_log)
            return fetch_gov_service_context(keyword, on_log=on_log)
    elif blog_id == "phn0502":
        # 영화/드라마 블로그: TMDB 실제 정보 + OTT 시청 가능 플랫폼
        return fetch_tmdb_context(keyword, on_log=on_log)
    elif blog_id == "woll100":
        # 교통 블로그: 고속버스·시외버스·KTX·공항버스 노선/요금/시간표
        return fetch_transport_context(keyword, on_log=on_log)
    return ""
