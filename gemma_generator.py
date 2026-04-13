"""Gemma 4 (Google AI Studio) 글 생성 — claude_playwright.generate_text() 대체

사용 전 .env에 GEMINI_API_KEY 설정 필요:
  https://aistudio.google.com/app/apikey 에서 무료 발급

의존성:
  pip3 install google-genai
"""
import os
import re
import time
from pathlib import Path

# .env 로드 (독립 실행 시)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# 모델 설정 — Gemma 3 27B (무료 15 RPM)
# Google AI Studio에서 지원하는 Gemma 최신 버전으로 자동 선택
_PREFERRED_MODELS = [
    "gemma-3-27b-it",   # Gemma 3 27B (안정)
    "gemma-3n-e4b-it",  # Gemma 3n (경량, 폴백)
]
_FALLBACK_MODEL = "gemini-2.0-flash"  # Gemma 실패 시 Gemini 플래시로 폴백

MAX_RETRIES = 2
MIN_CHARS = 1000  # 이 글자수 미만이면 재시도


# ─── 프롬프트 공통 규칙 ───

_BOLD_RULE = (
    "\n\n[볼드 처리 규칙]\n"
    "중요한 내용은 반드시 **볼드** 처리해줘.\n"
    "볼드 처리 대상: 핵심 키워드, 중요 수치/금액, 신청 기간 및 마감일, 자격 조건, 주의사항\n"
    "볼드 남용 금지: 한 문단에 1~2개 이내\n"
    "제목(H2/H3)은 볼드 처리 불필요\n"
    "\n[제목 규칙]\n"
    "===제목=== 안의 제목은 반드시 명사형/명사구로 작성해.\n"
    "문장형 어미(~습니다/~해요/~입니다/~세요/~합니다/~있어요) 절대 금지.\n"
    "제목에 '완벽가이드', '완벽정리', '완벽정복', '완벽 가이드', '완벽 정리', '완벽 정복', '총정리', '꿀팁', '마이리얼트립', '한눈에 보기', '한눈에 정리', '알아보기', '쉽게 알아보는', '대해서 알아보자' 등 마케팅/요약 문구 절대 금지.\n"
    "제목이 '정리'로 끝나는 것도 금지 (예: '~항목 정리', '~내용 정리'). 단 '정리수납' 같은 합성어는 허용.\n"
    "제목은 구체적인 롱테일 검색어처럼 — 조건/날짜/지역/방법 등 세부 정보 포함.\n"
    "예) X: '다자녀 혜택 지원금 총정리'\n"
    "예) O: '다자녀 혜택 2026 신청 조건 자격 지원금 종류'\n"
    "키워드에 아래 패턴이 포함되면 해당 질문형/공감형 제목으로 변환:\n"
    "  ~안될때 → '~가 안 될 때 이렇게 해결했어요'\n"
    "  ~오류   → '~오류 떴을 때 원인과 해결법'\n"
    "  ~이유   → '왜 ~이 되는 걸까요'\n"
    "  ~후기   → '직접 써본 ~ 후기'\n"
    "  ~비교   → '~, 뭐가 더 나을까요'\n"
    "예) X: '제주도 3박4일 완벽 가이드'\n"
    "예) O: '제주도 3박4일 뚜벅이 여행 코스 숙소 경비'\n"
    "\n[이미지 규칙]\n"
    "반드시 ===이미지=== 섹션에 이미지 2개를 포함해줘.\n"
    "형식:\n"
    "===이미지===\n"
    "[이미지1]\n"
    "- Gemini프롬프트: (Gemini 이미지 생성용 영어 또는 한국어 프롬프트)\n"
    "- 파일명: (영문-소문자-하이픈.webp)\n"
    "- alt: (키워드 포함 한국어 alt 텍스트)\n"
    "[이미지2]\n"
    "- Gemini프롬프트: ...\n"
    "- 파일명: ...\n"
    "- alt: ...\n"
    "===이미지끝==="
)

_FORMAT_RULE = (
    "\n\n[제목 규칙 — 필수]\n"
    "===제목=== 안의 제목에 '완벽가이드', '완벽정리', '완벽정복', '완벽 가이드', '완벽 정리', '완벽 정복', '총정리', '꿀팁', '마이리얼트립', '한눈에 보기', '한눈에 정리', '알아보기', '쉽게 알아보는', '대해서 알아보자' 절대 금지.\n"
    "제목이 '정리'로 끝나는 것도 금지 (예: '~항목 정리', '~내용 정리'). 단 '정리수납' 같은 합성어는 허용.\n"
    "제목은 아래 두 가지 스타일 중 키워드에 더 어울리는 것으로 작성해:\n"
    "  [스타일A — 키워드 나열형] 검색어를 쭉 나열 (네이버 스마트블록 최적화)\n"
    "    예) '속초 영금정 가볼만한곳 주차 입장료 버스 노선'\n"
    "    예) '청년 주거급여 신청방법 2026 소득기준 신청서류'\n"
    "  [스타일B — 롱테일 명사구형] 구체적 조건/지역/방법 포함 명사구\n"
    "    예) '제주도 3박4일 뚜벅이 여행 코스 숙소 경비'\n"
    "    예) '2026 청년도약계좌 신청 조건 금리 가입방법'\n"
    "키워드에 아래 패턴이 포함되면 해당 질문형/공감형 제목으로 변환:\n"
    "  ~안될때 → '~가 안 될 때 이렇게 해결했어요'\n"
    "  ~오류   → '~오류 떴을 때 원인과 해결법'\n"
    "  ~이유   → '왜 ~이 되는 걸까요'\n"
    "  ~후기   → '직접 써본 ~ 후기'\n"
    "  ~비교   → '~, 뭐가 더 나을까요'\n"
    "\n[말투 규칙 — 필수]\n"
    "본문 전체를 반드시 존댓말(해요체/합니다체)로 작성해. 예) '~해요', '~입니다', '~됩니다', '~있어요'.\n"
    "독자에게 반말(~야, ~해, ~봐, ~지) 절대 금지. 친한 독자에게 정보를 안내하는 따뜻한 해요체.\n"
    "문장이 마침표('.')로 끝날 경우 반드시 빈 줄(엔터 두 번)로 단락을 구분해. 모바일 가독성 최우선.\n"
    "\n[AI 글쓰기 금지 패턴 — 필수]\n"
    "아래는 AI 특유의 어색한 표현 — 절대 사용 금지:\n"
    "금지 단어: '정말', '압도적으로', '환상적이다', '환상적인', '마치', '놀라운', '실로', '탁월한', '눈에 띄게', '뛰어나다', '한마디로', '경이로운'\n"
    "금지 패턴: '~살펴보겠습니다', '~알아보겠습니다', '~라고 할 수 있습니다', '~라고 볼 수 있습니다', '다양한 ~', '여러 가지 ~', '~해 보겠습니다'\n"
    "금지 문장: '100% 확신합니다', '무조건 추천드려요', '완벽한 선택입니다'\n"
    "대체 표현: '꽤', '꽤나', '진짜', '괜찮던데요', '마음에 들더라고요', '~더라고요', '~하던데요', '~더라고요'\n"
    "\n[본문 형식 규칙 — 필수]\n"
    "글은 반드시 도입부 텍스트 2~3문단으로 시작해. 핵심요약이나 소제목으로 바로 시작하면 안 돼.\n"
    "도입부 → 핵심요약 박스 → 소제목 순서로 작성해.\n"
    "핵심요약 박스는 도입부 다음, 첫 번째 소제목 바로 위에 삽입 (HTML div 사용):\n"
    "<div style=\"background:#f8f9fa;border-left:4px solid #4A90D9;padding:12px 16px;margin:16px 0;border-radius:4px\">\n"
    "💡 핵심요약<br>• (핵심 정보 1줄)<br>• (핵심 정보 2줄)<br>• (핵심 정보 3줄)\n"
    "</div>\n"
    "본문 소제목은 반드시 ## (H2) 또는 ### (H3) 마크다운 헤딩 형식으로 작성해.\n"
    "중요 키워드·수치·조건은 **볼드** 처리해. (한 문단 1~2개 이내)\n"
    "구체적 수치·날짜·금액 반드시 포함. 모호한 '알려져 있습니다' '~로 보입니다' 금지.\n"
    "본문 마지막 단락에 면책 문구 한 줄 추가: '※ 이 글은 2026년 기준으로 작성되었으며, 정책·요금은 변동될 수 있습니다.'\n"
    "본문 길이: 공백 제외 순수 텍스트 **반드시 2000자 이상** 작성 (소제목 3개 이상, 각 소제목 아래 3~5문단).\n"
    "\n[글쓰기 방식 — 필수]\n"
    "'TOP 3', '5가지 방법', 'N개의 팁' 식의 나열형 구성 절대 금지.\n"
    "하나의 주제를 깊이 있게 파고드는 글 구성.\n"
    "제목에 숫자+나열 패턴 금지: 'TOP N', 'N가지', 'N개의' 로 시작하는 제목 금지.\n"
    "\n[이미지 규칙 — 필수]\n"
    "본문 내 H2 소제목(##) 바로 아래에 {{이미지N}} 마커를 반드시 삽입해 (N은 1부터 순서대로).\n"
    "H2 소제목 개수만큼 이미지 마커를 삽입할 것 — H2가 3개면 {{이미지1}}, {{이미지2}}, {{이미지3}}.\n"
    "그리고 본문 끝에 ===이미지=== 섹션으로 각 이미지의 Gemini 생성 프롬프트를 작성해.\n"
    "===이미지===\n"
    "[이미지1]\n"
    "- Gemini프롬프트: (해당 H2 내용을 구체적으로 묘사하는 영어 프롬프트)\n"
    "- 파일명: (영문-소문자-하이픈.jpg)\n"
    "- alt: (키워드 포함 한국어 alt 텍스트)\n"
    "[이미지2]\n"
    "- Gemini프롬프트: ...\n"
    "- 파일명: ...\n"
    "- alt: ...\n"
    "(H2 개수만큼 반복)\n"
    "===이미지끝===\n"
)

_MOBILE_PARA_RULE = (
    "\n\n[모바일 가독성 규칙 — 필수]\n"
    "각 문단은 1~2문장으로 짧게 작성해. 문장이 끝나면 반드시 빈 줄(엔터 두 번)로 구분해.\n"
    "긴 문단(3문장 이상 연속) 절대 금지. 모바일에서 스크롤하기 편하게 짧은 덩어리로 나눠줘.\n"
)

_SECTION_FORMAT = (
    "\n\n아래 형식으로만 출력해줘 (다른 형식 절대 금지):\n"
    "===제목===\n"
    "(SEO 최적화된 롱테일 제목 — 구체적 조건/지역/방법 포함 명사구, 25~45자)\n"
    "===제목끝===\n\n"
    "===본문===\n"
    "(블로그 본문 전체)\n"
    "===본문끝===\n\n"
    "===태그===\n"
    "태그1, 태그2, 태그3 (10~20개)\n"
    "===태그끝===\n"
)


def _build_prompt(blog_id: str, keyword: str, extra_context: str = None) -> str:
    """claude_playwright.py의 프롬프트 빌딩 로직과 동일하게 구성."""
    prompt = keyword + _MOBILE_PARA_RULE

    if blog_id == "triplog":
        is_itinerary = any(w in keyword for w in ["2박3일", "1박2일", "3박4일", "당일치기", "일정", "코스"])
        prompt += (
            "\n\n[작성자 설정 — 마이리얼트립 제휴 블로거]\n"
            "이 블로그는 마이리얼트립 파트너 제휴 블로그야. 독자가 투어·액티비티를 예약하도록 유도하는 게 목표야.\n"
            "'~했어요', '~하더라고요', '직접 예약해봤는데' 등 실제 이용자 경험 톤으로 작성해.\n"
            "관광청 홍보글 느낌 금지. 실제로 예약해서 다녀온 사람이 추천해주는 느낌.\n"
            "글은 반드시 도입부 텍스트 2~3문단으로 시작해. 핵심요약이나 소제목으로 바로 시작 금지.\n"
            "여행 블로그이므로 '핵심요약' 박스 사용 금지. 대신 도입부 뒤에 여행 정보 요약이 필요하면 자연스러운 문단으로 작성해.\n"
        )
        if is_itinerary:
            prompt += (
                "\n\n[제휴 마케팅 여행 코스 작성 규칙 — 필수]\n"
                "독자가 '이거 예약하고 싶다'는 생각이 들도록 써야 해.\n"
                "1. 도입부: 이 여행을 고민하는 사람의 구체적인 상황·고민 공감으로 시작\n"
                "2. 날짜별 동선: 구체적 시간·이동 방법·비용 포함\n"
                "3. 예산 총정리: 항공·숙소·투어·식사 각각 실제 예산 명시 (구체적 숫자 필수)\n"
            )
        else:
            prompt += (
                "\n\n[제휴 마케팅 장소 심층 작성 규칙 — 필수]\n"
                "독자가 '이 투어 신청해야겠다'고 느끼도록 써야 해.\n"
                "1. 도입부: 이 장소를 검색하는 사람의 기대·불안 공감으로 시작\n"
                "2. 직접 다녀온 것처럼 구체적 묘사: 분위기, 볼거리, 시간대별 추천\n"
                "3. 실용 정보: 입장료, 운영시간, 가는 법 (구체적 번호·금액)\n"
            )
    elif blog_id == "nolja100":
        is_itinerary = any(w in keyword for w in ["2박3일", "1박2일", "3박4일", "당일치기", "일정", "코스"])
        prompt += (
            "\n\n[작성자 설정 — 여행 블로거 필수]\n"
            "주말 나들이나 여행 코스를 친근하게 소개하는 30대 블로거의 편안한 말투로 작성해.\n"
            "'~했어요', '~하더라고요', '~가볼 만해요', '괜찮더라고요' 등 자연스러운 구어체 사용.\n"
            "뉴스 기사나 백과사전처럼 딱딱하게 쓰는 것 금지. 동네 친구가 여행 후기 얘기해주는 느낌.\n"
            "글은 반드시 도입부 텍스트 2~3문단으로 시작해. 소제목으로 바로 시작 금지.\n"
            "여행 블로그이므로 '핵심요약' 박스 사용 금지. 여행 정보는 본문에 자연스럽게 녹여서 작성해.\n"
        )
        if is_itinerary:
            prompt += (
                "\n\n[여행 코스 작성 규칙 — 필수]\n"
                "이 키워드를 검색하는 사람은 '실제로 어떻게 다닐지' 모르는 상태야.\n"
                "단순 관광지 나열 금지. 아래를 반드시 포함해:\n"
                "1. 날짜별 상세 동선 (몇 시에 어디서 출발 → 어디로 이동)\n"
                "2. 각 장소 실제 입장료·운영시간·주차 정보\n"
                "3. 숙소 추천 지역 + 가격대 (실제 예산)\n"
                "4. 교통 수단별 비용\n"
                "5. 현지인만 아는 꿀팁\n"
            )
        else:
            prompt += (
                "\n\n[장소 심층 작성 규칙 — 필수]\n"
                "키워드에서 가장 적합한 장소 1곳을 직접 선정해서 그 장소만 깊게 작성해.\n"
                "여러 장소를 나열하는 가이드 글 금지. 1곳의 볼거리·먹거리·교통·시간·꿀팁을 구체적으로 작성해.\n"
                "반드시 포함: 실제 입장료, 운영시간, 주차 유무, 가는 법.\n"
            )
    elif blog_id == "goodisak":
        prompt += (
            "\n\n[주제 심층 작성 규칙 — 필수]\n"
            "goodisak 블로그는 IT 기기 리뷰·추천, 금융 정보, 정부지원·복지 혜택을 다루는 블로그야.\n"
            "이 키워드를 검색하는 사람이 진짜 알고 싶어하는 1가지 핵심 정보를 직접 선정해서 깊게 작성해.\n"
            "여러 제품/제도를 단순 나열하는 글 금지. 1가지를 구체적 수치·조건으로 깊게 작성해.\n"
        )
    elif blog_id == "salim1su":
        prompt += (
            "\n\n[주제 심층 작성 규칙 — 필수]\n"
            "이 키워드를 검색하는 사람은 '어떻게 하면 되는지' 구체적인 방법을 모르는 상태야.\n"
            "키워드에서 가장 적합한 살림 방법·절약 팁·생활 정보 1가지를 직접 선정해서 그것만 깊게 작성해.\n"
            "여러 방법을 나열하는 글 금지. 1가지를 단계별로 구체적으로 작성해.\n"
        )
    elif blog_id == "me1091":
        prompt += (
            "\n\n[쿠팡파트너스 리뷰 작성 규칙 — 필수]\n"
            "me1091은 쿠팡 상품 리뷰 블로그야. 반드시 아래 순서로 작성해:\n"
            "1. 인트로(후킹): 이 상품을 고민하는 사람의 상황·고민을 공감으로 시작.\n"
            "2. 가격 앵커링: 쿠팡 현재 가격 + 로켓배송 정보.\n"
            "3. 왜 이걸 골랐나(구매 이유): 구체적으로.\n"
            "4. 실사용 후기(본문): 구체적 사용 경험. 장점 위주, 아쉬운 점 1가지 솔직하게.\n"
            "5. 이런 분께 추천: 구체적인 대상.\n"
            "6. 맺음말 + 구매 유도.\n"
            "제휴 링크가 extra_context로 제공되면 가격 앵커링 섹션 + 맺음말 직전에 반드시 삽입.\n"
            "\n[작성자 설정 — 쿠팡 리뷰어]\n"
            "실제로 구매해서 써본 30대 생활 블로거 톤. 자연스러운 구어체.\n"
        )
    elif blog_id == "baremi542":
        prompt += (
            "\n\n[주제 심층 작성 규칙 — 필수]\n"
            "이 키워드를 검색하는 사람은 '어떤 혜택을 받을 수 있는지' 모르는 상태야.\n"
            "키워드에서 가장 적합한 정부지원·복지·생활정보 1가지를 직접 선정해서 그것만 깊게 작성해.\n"
            "여러 혜택을 나열하는 글 금지. 1가지의 대상·신청절차·금액·유의사항을 구체적으로 작성해.\n"
            "\n[글쓰기 형식 — 필수]\n"
            "반드시 정보성 가이드 형식으로 작성해. 경험담/후기 형식 절대 금지.\n"
            "1인칭 서술('저는', '다녀왔어요', '해봤어요', '찾아봤어요') 절대 금지.\n"
        )
    else:
        # woll100, phn0502 등 기타 블로그
        prompt = keyword + _SECTION_FORMAT + _FORMAT_RULE + _BOLD_RULE

    # 프로젝트 모드 blog_id에는 FORMAT_RULE 추가
    if blog_id in ("nolja100", "salim1su", "goodisak", "baremi542", "triplog", "me1091"):
        # Claude 프로젝트 없이 API 직접 호출이므로 출력 형식도 명시
        prompt += _SECTION_FORMAT + _FORMAT_RULE

    # 팩트 컨텍스트 주입
    if extra_context:
        prompt = f"{prompt}\n\n[참고 자료 — 아래 수치/날짜만 사용, 임의 수치 금지]\n{extra_context}"

    return prompt


def _get_client():
    """google.genai Client 반환. API 키 없으면 예외."""
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY가 비어 있어. .env에 키 설정 필요.\n"
            "무료 발급: https://aistudio.google.com/app/apikey"
        )
    return genai.Client(api_key=api_key)


def _try_generate(client, model: str, prompt: str, on_log=None) -> str:
    """단일 모델로 생성 시도. 실패 시 빈 문자열 반환."""
    def log(msg):
        if on_log:
            on_log(msg)
    try:
        log(f"[Gemma] 모델 {model} 호출 중 ({len(prompt)}자 프롬프트)...")
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )
        text = response.text or ""
        log(f"[Gemma] 응답 수신: {len(text)}자")
        return text
    except Exception as e:
        log(f"[Gemma] {model} 실패: {e}")
        return ""


def generate_text(prompt: str, blog_id: str = None, keyword: str = None,
                  on_log=None, extra_context: str = None) -> str:
    """Gemma 4 (Google AI Studio)로 블로그 글 생성.

    claude_playwright.generate_text()와 동일한 시그니처.
    응답이 MIN_CHARS 미만이면 최대 MAX_RETRIES 재시도.
    Gemma 실패 시 Gemini 2.0 Flash 폴백.
    """
    def log(msg):
        if on_log:
            on_log(msg)

    # API 키 확인
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        log("[Gemma] ⚠ GEMINI_API_KEY 미설정 — Gemma 생성 건너뜀")
        return ""

    # 프롬프트 빌드
    if blog_id and keyword:
        final_prompt = _build_prompt(blog_id, keyword, extra_context)
        log(f"[Gemma] 프롬프트 빌드 완료: {blog_id} / '{keyword}' ({len(final_prompt)}자)")
    else:
        final_prompt = prompt
        if extra_context:
            final_prompt += f"\n\n{extra_context}"

    try:
        client = _get_client()
    except RuntimeError as e:
        log(f"[Gemma] 클라이언트 초기화 실패: {e}")
        return ""

    # 모델 우선순위 시도
    models_to_try = list(_PREFERRED_MODELS) + [_FALLBACK_MODEL]
    result = ""

    for attempt in range(1, MAX_RETRIES + 2):
        if attempt > 1:
            log(f"[Gemma] === 재시도 {attempt - 1}/{MAX_RETRIES} ===")
            time.sleep(3)

        for model in models_to_try:
            text = _try_generate(client, model, final_prompt, on_log)
            if text and len(text) >= MIN_CHARS:
                result = text
                log(f"[Gemma] ✓ 생성 완료 (모델: {model}, {len(text)}자)")
                break
            elif text:
                log(f"[Gemma] ⚠ 응답 너무 짧음 ({len(text)}자 < {MIN_CHARS}자) — 다음 모델 시도")
        else:
            # 모든 모델 실패 또는 짧음 → 재시도
            if attempt <= MAX_RETRIES:
                continue
            # 마지막 시도에서도 실패
            log("[Gemma] ✗ 모든 모델 실패")
            return ""

        if result:
            break

    return result


if __name__ == "__main__":
    # 단독 테스트
    import sys
    blog = sys.argv[1] if len(sys.argv) > 1 else "salim1su"
    kw = sys.argv[2] if len(sys.argv) > 2 else "에어컨 전기세 절약 방법"
    print(f"테스트: blog={blog}, keyword={kw}")
    result = generate_text("", blog_id=blog, keyword=kw, on_log=print)
    print("─" * 40)
    print(result[:500] if result else "(생성 실패)")
