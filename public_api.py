"""공공데이터포털 + TMDB API 연동 모듈

블로그 글 생성 전 실제 데이터를 extra_context로 주입해 할루시네이션 방지.

지원 API:
- 한국관광공사 축제/행사정보  → nolja100, triplog
- 정부24 공공서비스 정보      → baremi542, goodisak, salim1su
- TMDB 영화/드라마 정보       → phn0502 (OTT 시청 가능 플랫폼 포함)
"""
import json
import os
import urllib.parse
import urllib.request
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

# 한국관광공사 API
_FESTIVAL_URL = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
# 정부24 공공서비스 API
_GOV_SERVICE_URL = "https://api.odcloud.kr/api/gov24/v3/serviceList"


def _get(url: str, params: dict) -> dict:
    params["serviceKey"] = SERVICE_KEY
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

    # 키워드에서 검색어 추출 (앞 2단어)
    words = keyword.replace(",", " ").split()
    search_kw = " ".join(words[:2]) if words else keyword[:10]

    params = {
        "page": "1",
        "perPage": "5",
        "cond[서비스명::LIKE]": search_kw,
    }
    log(f"[PublicAPI] 공공서비스 검색: '{search_kw}'")

    data = _get(_GOV_SERVICE_URL, params)

    if "error" in data:
        log(f"[PublicAPI] 공공서비스 API 오류: {data['error']}")
        return ""

    try:
        items = data.get("data", [])
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


def fetch_context_for_blog(blog_id: str, keyword: str, on_log=None) -> str:
    """blog_id에 따라 적합한 공공API 데이터를 가져와 extra_context로 반환.

    overnight_run.py → generate_text(..., extra_context=...) 에 주입용.
    """
    if blog_id in {"nolja100", "triplog"}:
        # 여행 블로그: 관광지 + 숙박 + 음식점 + 축제 통합 정보
        return fetch_travel_context(keyword, on_log=on_log)
    elif blog_id in {"baremi542", "goodisak", "salim1su"}:
        # 정보성 블로그: 정부24 공공서비스
        welfare_hints = ["지원", "혜택", "신청", "급여", "보조", "복지", "정책", "수당", "바우처"]
        if any(h in keyword for h in welfare_hints):
            return fetch_gov_service_context(keyword, on_log=on_log)
    elif blog_id == "phn0502":
        # 영화/드라마 블로그: TMDB 실제 정보 + OTT 시청 가능 플랫폼
        return fetch_tmdb_context(keyword, on_log=on_log)
    return ""
