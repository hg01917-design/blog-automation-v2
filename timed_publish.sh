#!/bin/bash
# 3.5h 간격 충족 후 순서대로 발행
# 1차: triplog WP draft 2906 (제주벚꽃) + baremi542_parental_leave_app
# 2차 (+3.5h): triplog_tongyeong_2026 + baremi542_income_tax_refund
cd /Users/hana/Downloads/blog-automation-v2

log() { echo "[$(date '+%H:%M:%S')] $1" | tee -a logs/timed_publish.log; }

baremi542_avail=1776130558  # 07:05 + 3.5h
triplog_avail=1776130636    # 07:07 + 3.5h

# === 1차 발행 배치 ===
now=$(python3 -c "import time; print(int(time.time()))")
wait_t=$((triplog_avail - now))
if [ $wait_t -gt 0 ]; then
    log "1차 배치까지 ${wait_t}초 대기..."
    sleep $wait_t
fi

log "=== 1차 발행 배치 시작 ==="

# triplog WP draft 2906 (제주 4월 벚꽃) 발행
log "triplog WP draft 2906 발행..."
python3 - >> logs/timed_publish.log 2>&1 << 'PYEOF'
import publish_pending_drafts as ppd, json, ssl, urllib.request, time

env = ppd._load_secrets()
wp_url = 'https://app.baremi542.com'
auth = ppd._auth_header('triplog', env)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

data = json.dumps({'status': 'publish'}).encode()
req = urllib.request.Request(
    f'{wp_url}/wp-json/wp/v2/posts/2906',
    data=data,
    headers={'Authorization': auth, 'Content-Type': 'application/json'},
    method='POST'
)
try:
    resp = urllib.request.urlopen(req, timeout=30, context=ctx)
    result = json.loads(resp.read())
    print(f'[OK] triplog 2906 발행: {result.get("link","")}')
    times_file = 'logs/blog_publish_times.json'
    times = json.loads(open(times_file).read())
    times['triplog'] = time.time()
    open(times_file, 'w').write(json.dumps(times))
    print('[OK] triplog publish_time 업데이트')
except Exception as e:
    print(f'[FAIL] triplog 2906: {e}')
PYEOF
log "triplog WP draft 2906 처리 완료"

# baremi542 첫번째 (parental_leave_app) 발행
wait_b=$((baremi542_avail - $(python3 -c "import time; print(int(time.time()))")))
if [ $wait_b -gt 0 ]; then
    log "baremi542까지 ${wait_b}초 추가 대기..."
    sleep $wait_b
fi

log "baremi542_parental_leave_app.json 발행..."
python3 - >> logs/timed_publish.log 2>&1 << 'PYEOF'
import publish_pending_drafts as ppd, json, time
from pathlib import Path

env = ppd._load_secrets()
f = Path('drafts/baremi542_parental_leave_app.json')
if f.exists() and json.loads(f.read_text()).get('status') == 'pending_publish':
    r = ppd.publish_draft(f, env)
    print(r)
    times_file = 'logs/blog_publish_times.json'
    times = json.loads(open(times_file).read())
    times['baremi542'] = time.time()
    open(times_file, 'w').write(json.dumps(times))
    print('[OK] baremi542 publish_time 업데이트')
else:
    print('baremi542_parental_leave_app 없거나 이미 발행됨')
PYEOF
log "1차 배치 완료"

# === 2차 발행 배치 (3.5시간 후) ===
log "2차 배치까지 3.5시간(12600초) 대기..."
sleep 12600

log "=== 2차 발행 배치 시작 ==="

# triplog_tongyeong_2026 JSON 발행
log "triplog_tongyeong_2026.json 발행..."
python3 - >> logs/timed_publish.log 2>&1 << 'PYEOF'
import publish_pending_drafts as ppd, json, time
from pathlib import Path

env = ppd._load_secrets()
f = Path('drafts/triplog_tongyeong_2026.json')
if f.exists() and json.loads(f.read_text()).get('status') == 'pending_publish':
    r = ppd.publish_draft(f, env)
    print(r)
    times_file = 'logs/blog_publish_times.json'
    times = json.loads(open(times_file).read())
    times['triplog'] = time.time()
    open(times_file, 'w').write(json.dumps(times))
    print('[OK] triplog publish_time 업데이트')
else:
    print('triplog_tongyeong_2026 없거나 이미 발행됨')
PYEOF
log "triplog_tongyeong 발행 완료"

# baremi542 두번째 (income_tax_refund) 발행
log "baremi542_income_tax_refund.json 발행..."
python3 - >> logs/timed_publish.log 2>&1 << 'PYEOF'
import publish_pending_drafts as ppd, json, time
from pathlib import Path

env = ppd._load_secrets()
f = Path('drafts/baremi542_income_tax_refund.json')
if f.exists() and json.loads(f.read_text()).get('status') == 'pending_publish':
    r = ppd.publish_draft(f, env)
    print(r)
    times_file = 'logs/blog_publish_times.json'
    times = json.loads(open(times_file).read())
    times['baremi542'] = time.time()
    open(times_file, 'w').write(json.dumps(times))
    print('[OK] baremi542 publish_time 업데이트')
else:
    print('baremi542_income_tax_refund 없거나 이미 발행됨')
PYEOF
log "2차 배치 완료! 모든 발행 처리됨."
