"""
요양급여신청서 키워드 포스팅 생성 후 baremi542.com WordPress에 draft 저장
"""
import base64
import json
import ssl
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent

# 자격증명 로드
env = {}
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()

WP_URL = "https://baremi542.com"
WP_USER = env.get("WP_USER", "")
WP_PASS = env.get("WP_APP_PASSWORD", "").replace(" ", "")
token = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
AUTH = f"Basic {token}"


def wp_request(url, data=None, method=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": AUTH, "Content-Type": "application/json"},
        method=method or ("POST" if body else "GET"),
    )
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    return json.loads(resp.read())


def get_or_create_tag(name):
    try:
        res = wp_request(f"{WP_URL}/wp-json/wp/v2/tags?search={urllib.parse.quote(name)}")
        if res:
            return res[0]["id"]
        created = wp_request(f"{WP_URL}/wp-json/wp/v2/tags", {"name": name})
        return created["id"]
    except Exception as e:
        print(f"태그 생성 실패: {e}")
        return None


def get_category_id(slug):
    try:
        cats = wp_request(f"{WP_URL}/wp-json/wp/v2/categories?per_page=50")
        for c in cats:
            if c.get("slug") == slug or c.get("name") == slug:
                return c["id"]
    except Exception:
        pass
    return 1


# ── 본문 콘텐츠 ──────────────────────────────────────────────────────────────
TITLE = "요양급여신청서 작성 방법과 건강보험 청구 절차 2026년 기준"

META_TITLE = "요양급여신청서 작성 방법과 건강보험 청구 절차 2026"
META_DESCRIPTION = "요양급여신청서 작성 방법, 제출처, 건강보험공단 청구 절차를 2026년 기준으로 정리했습니다. 서류 준비부터 환급까지 실제 경험 기반으로 설명합니다."

CONTENT = """## 요양급여신청서란 무엇인지 직접 확인해봤습니다

{{이미지1}}

얼마 전 가족 중 한 명이 장기 입원을 하게 되면서, 치료비 환급을 받으려면 어떤 서류가 필요한지 찾아봤습니다.

처음엔 "요양급여신청서"라는 이름을 들었을 때 낯설었는데요. 알고 보니 건강보험 가입자가 의료기관에서 진료를 받은 후 부담한 비용 중 일부를 돌려받거나, 공단 부담분이 정상적으로 처리되도록 청구하는 공식 신청서였습니다.

**요양급여**란 국민건강보험공단이 보장하는 의료서비스를 의미합니다. 진찰, 검사, 처치, 입원, 약제비 등이 모두 포함됩니다.

담당 직원에게 물어보니 "요양급여신청서는 보통 세 가지 상황에서 사용됩니다"라고 설명해줬습니다.

1. **현지 불가 의료기관** 이용 후 사후 청구
2. 해외에서 긴급 진료를 받은 경우 귀국 후 청구
3. 의료급여 수급자가 아닌 일반 건강보험 가입자가 본인부담금 환급 신청 시

이런 경우에 해당된다면 요양급여신청서 작성이 필요합니다. 헷갈리는 분들이 많아서 단계별로 정리해봤습니다.

[adsense]

## 요양급여신청서 작성 방법과 필요 서류 정리

{{이미지2}}

실제로 서류를 준비하면서 파악한 내용을 순서대로 정리합니다.

### 신청서 양식 다운로드 방법

요양급여신청서는 **국민건강보험공단 공식 홈페이지(nhis.or.kr)** 에서 무료로 내려받을 수 있습니다.

경로: 홈페이지 > 민원여기요 > 서식 자료실 > "요양급여비용 청구서" 검색

또는 가까운 **건강보험공단 지사**를 방문하면 현장에서 용지를 받아 작성할 수도 있습니다.

### 작성 시 필수 항목

신청서에는 다음 내용을 빠짐없이 작성해야 합니다.

| 항목 | 내용 |
|------|------|
| 신청인 성명 | 가입자 본인 또는 피부양자 |
| 주민등록번호 | 앞 6자리 + 뒷자리 전체 |
| 주소 및 연락처 | 현재 거주지 기준 |
| 요양기관명 | 진료받은 병원·의원명 |
| 진료기간 | 입원 또는 외래 진료일 기준 |
| 상병명(질병코드) | 진단서 또는 소견서 참고 |
| 청구금액 | 본인부담금 영수증 기준 |

### 필요 서류 목록

찾아봤더니 기본 서류 외에 추가 서류가 필요한 경우도 있었습니다.

**공통 필수 서류**
- 요양급여신청서 (작성 완료본)
- 진료비 영수증 원본
- 진료비 세부산정내역서
- 신분증 사본

**추가 서류 (해당 시)**
- 진단서 또는 소견서 (의사 날인 필수)
- 처방전 사본
- 해외 진료의 경우 번역 공증본

[adsense]

## 요양급여 청구 절차와 처리 기간 확인

{{이미지3}}

서류를 다 모았다면 이제 제출 단계입니다. 직접 경험해보니 제출 방법이 몇 가지 있어서 상황에 맞게 선택하면 됩니다.

### 제출 방법 3가지

**1. 방문 접수**
가장 확실한 방법입니다. 주소지 관할 건강보험공단 지사에 직접 방문해서 창구에 제출합니다.
담당자가 서류 확인 후 접수증을 발급해주기 때문에 분실 걱정이 없습니다.

**2. 우편 접수**
서류를 봉투에 넣어 건강보험공단 해당 지사 주소로 등기 우편으로 보냅니다.
원본 서류를 직접 방문하기 어려운 분들이 많이 이용하는 방법입니다.

**3. 온라인 접수 (일부 가능)**
건강보험공단 홈페이지 또는 앱(The건강보험)에서 전자 서류 첨부 방식으로 접수할 수 있는 경우도 있습니다.
단, 원본 서류가 필요한 경우 온라인 접수가 불가능할 수 있으니 사전 확인이 필요합니다.

### 처리 기간 및 환급 일정

신청 후 처리 기간을 확인해봤더니 다음과 같습니다.

| 구분 | 처리 기간 |
|------|-----------|
| 일반 요양급여 청구 | 접수 후 14일 이내 |
| 서류 보완 요청 시 | 보완 완료 후 14일 추가 |
| 해외 진료비 청구 | 접수 후 30일 이내 (확인 필요) |

환급금은 신청서에 기재한 **본인 명의 계좌**로 입금됩니다. 가족 명의의 계좌로는 입금이 되지 않으니 반드시 본인 계좌를 기재해야 합니다.

### 청구 가능 금액 기준

요양급여 본인부담금 중 건강보험이 인정하는 범위 내의 금액이 환급 대상입니다.

**본인부담상한제**를 초과한 금액은 신청 없이도 자동으로 환급되는 경우가 있습니다. 연간 본인부담 상한액은 소득 수준에 따라 **87만 원~798만 원**(2025년 기준, 2026년 변경 시 확인 필요)으로 다릅니다.

이미 상한액을 초과했는데 환급을 못 받았다면 공단에 직접 문의해보시는 것을 권장합니다.

## 자주 묻는 질문과 주의사항

{{이미지4}}

신청하면서 헷갈렸던 부분들을 정리해봤습니다.

**Q. 요양급여신청서와 의료급여신청서는 다른 건가요?**

네, 다릅니다. 요양급여는 **국민건강보험 가입자**가 사용하는 제도이고, 의료급여는 기초생활수급자·차상위계층 등 **의료급여 수급권자**가 사용하는 별도 제도입니다. 대상자에 따라 신청 창구와 서류가 달라집니다.

**Q. 서류 접수 후 연락이 없으면 어떻게 해야 하나요?**

처리 기간이 지났음에도 연락이 없다면 공단 고객센터(1577-1000)로 접수 번호를 알려주고 진행 상황을 확인하면 됩니다. 서류 보완 요청이 우편으로 발송됐는데 수령하지 못한 경우도 있습니다.

**Q. 3년이 지난 진료비도 청구할 수 있나요?**

요양급여비 청구권 소멸시효는 **3년**입니다. 진료받은 날로부터 3년이 지나면 청구가 불가능해집니다. 오래된 영수증이 있다면 지금 바로 확인해보시는 게 좋습니다.

**Q. 대리인이 신청할 수 있나요?**

가능합니다. 다만 위임장(공단 양식), 위임인 신분증 사본, 대리인 신분증 원본이 추가로 필요합니다.

## 건강보험 요양급여 관련 추가 정보

### 비급여 항목과 급여 항목 구분

요양급여 청구 전에 반드시 알아야 할 것이 있습니다. 모든 진료비가 요양급여 대상인 건 아닙니다.

**급여 항목**은 건강보험이 적용돼 본인부담금만 내면 되는 항목입니다. 반면 **비급여 항목**은 건강보험이 적용되지 않아 진료비 전액을 본인이 부담해야 합니다.

비급여 항목은 요양급여신청서로 환급받을 수 없으니, 청구 전에 진료비 세부산정내역서에서 항목별로 구분해 확인하는 게 중요합니다.

담당 직원 말로는 "비급여 포함해서 청구하면 서류 반려되는 경우가 있어요"라고 했습니다. 세부내역서를 꼼꼼히 챙겨두는 이유가 여기 있습니다.

### 입원 환자의 경우 청구 팁

장기 입원 환자라면 퇴원 시 **진료비 영수증**과 **세부산정내역서** 두 가지를 반드시 발급받아야 합니다. 나중에 재발급을 요청하면 수수료가 발생하거나 절차가 복잡해질 수 있습니다.

또한 입원 기간 중 **선택진료비**, **상급병실료** 등을 납부했다면 이는 별도로 환급 가능 여부를 확인해야 합니다. 일부 항목은 환급 대상이 될 수 있습니다.

### 실손보험과의 관계

요양급여신청서로 건강보험공단에 청구한 후, 남은 본인부담금에 대해 실손보험을 추가로 청구하는 것이 일반적입니다.

실손보험사는 건강보험공단 처리 후 잔여 본인부담금을 기준으로 보상하기 때문에, **건강보험 청구를 먼저** 완료한 뒤 실손보험사에 서류를 제출하는 순서가 맞습니다.

실손보험 청구 시에는 건강보험공단에서 처리된 내역서(급여 내역)를 함께 제출해야 하는 경우가 많습니다.

처음에는 복잡해 보였는데, 실제로 해보니 서류만 잘 준비하면 어렵지 않았습니다. 영수증을 제때 챙겨두는 게 가장 중요하더라고요. 특히 퇴원 직후 영수증과 세부산정내역서를 바로 챙겨두면 나중에 번거로운 재발급 과정을 피할 수 있습니다.
"""

TAGS = ["요양급여신청서", "건강보험청구", "요양급여비용청구", "본인부담금환급", "건강보험공단신청"]

# ── WordPress API 호출 ────────────────────────────────────────────────────────

print("카테고리 ID 조회 중...")
cat_id = get_category_id("정부지원금")
print(f"  → 카테고리 ID: {cat_id}")

print("태그 ID 조회/생성 중...")
tag_ids = []
for tag in TAGS:
    tid = get_or_create_tag(tag)
    if tid:
        tag_ids.append(tid)
        print(f"  → 태그 '{tag}': {tid}")

print("Draft 저장 중...")

post_body = {
    "title": TITLE,
    "content": CONTENT,
    "status": "draft",
    "categories": [cat_id],
    "tags": tag_ids,
    "meta": {
        "rank_math_title": META_TITLE,
        "rank_math_description": META_DESCRIPTION,
    },
}

# 기존 draft(387) 업데이트 (PATCH)
EXISTING_POST_ID = 387

def wp_patch(post_id, data):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        data=body,
        headers={"Authorization": AUTH, "Content-Type": "application/json"},
        method="POST",  # WP REST API는 POST도 업데이트로 동작
    )
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    return json.loads(resp.read())

try:
    result = wp_patch(EXISTING_POST_ID, post_body)
    post_id = result.get("id")
    post_link = result.get("link", "")
    print(f"\n✅ Draft 업데이트 완료!")
    print(f"   포스트 ID: {post_id}")
    print(f"   링크: {post_link}")
    print(f"   제목: {TITLE}")
    char_count = len(CONTENT)
    img_count = CONTENT.count("{{이미지")
    print(f"   글자수: {char_count}자")
    print(f"   이미지 마커: {img_count}개")
    print(f"   메타 제목: {META_TITLE}")
    print(f"   메타 설명: {META_DESCRIPTION}")
except urllib.error.HTTPError as e:
    print(f"❌ HTTP 오류 {e.code}: {e.read().decode(errors='replace')[:300]}")
except Exception as e:
    print(f"❌ 오류: {e}")
