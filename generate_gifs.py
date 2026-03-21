"""에이전트 캐릭터 GIF 생성기 — Stardew Valley 스타일 픽셀 아트 (개선판)"""
from PIL import Image, ImageDraw
from pathlib import Path
import math

ASSETS = Path(__file__).parent / "assets"
ASSETS.mkdir(exist_ok=True)

SIZE = 192  # 출력 GIF 크기 (픽셀 아트 NEAREST 스케일업) — 기존 160 → 192
DRAW_SIZE = 120  # 내부 드로잉 크기

# 상태별 프레임/딜레이 설정
STATE_FRAMES = {
    "idle": 12,    # idle은 12프레임으로 부드럽게 (기존 8)
    "working": 10, # working은 10프레임으로 역동적
    "done": 12,    # done도 12프레임
    "failed": 8,
}
STATE_DELAY = {
    "idle": 140,    # 부드러운 bob 효과를 위해 빠르게 (기존 200)
    "working": 100, # 타이핑 더 빠르게 (기존 200)
    "done": 120,    # 점프 애니메이션 빠르게 (기존 200)
    "failed": 200,
}

# 에이전트별 색상 — 채도 높임
AGENTS = {
    "keyword": {
        "shirt": (41, 121, 255),   # 더 선명한 파란색 (기존 59,130,246)
        "shirt2": (20, 80, 220),
        "pants": (10, 40, 180),
        "hair": (90, 60, 30),
        "hair2": (65, 40, 15),
        "style": "short",
    },
    "writer": {
        "shirt": (20, 220, 80),    # 더 선명한 초록 (기존 34,197,94)
        "shirt2": (10, 170, 55),
        "pants": (5, 120, 40),
        "hair": (230, 175, 90),
        "hair2": (205, 155, 70),
        "style": "long",
    },
    "review": {
        "shirt": (255, 200, 0),    # 더 선명한 노란색 (기존 234,179,8)
        "shirt2": (220, 160, 0),
        "pants": (180, 110, 0),
        "hair": (20, 20, 20),
        "hair2": (5, 5, 5),
        "style": "spiky",
    },
    "final_review": {
        "shirt": (180, 60, 255),   # 더 선명한 보라 (기존 168,85,247)
        "shirt2": (155, 30, 240),
        "pants": (120, 10, 215),
        "hair": (255, 20, 20),
        "hair2": (200, 10, 10),
        "style": "ponytail",
    },
    "poster": {
        "shirt": (255, 50, 50),    # 더 선명한 빨강 (기존 239,68,68)
        "shirt2": (230, 20, 20),
        "pants": (190, 5, 5),
        "hair": (250, 250, 250),
        "hair2": (210, 210, 210),
        "style": "buzz",
    },
}

# 공통 색상 — 더 선명하게
SKIN = (255, 210, 168)     # 밝고 따뜻하게 (기존 245,198,160)
SKIN_S = (225, 175, 120)
EYE = (35, 18, 8)
MOUTH = (210, 110, 80)
WHITE = (255, 255, 255)
BG = (22, 22, 40)           # 배경 더 어둡게 (대비 높이기)
FLOOR = (70, 56, 35)
DESK = (180, 148, 100)      # 책상 더 밝게
DESK_S = (138, 112, 72)
MONITOR = (38, 38, 52)
SCREEN = (8, 20, 45)
CHAIR = (80, 80, 100)
CHAIR2 = (62, 62, 82)
SHOE = (38, 28, 28)
WALL2 = (32, 32, 55)


def draw_bg(d, frame):
    """배경: 벽 + 바닥 + 창문 + 화분"""
    # 벽
    d.rectangle([0, 0, 119, 64], fill=BG)
    for x in range(0, 120, 18):
        d.line([(x, 0), (x, 64)], fill=WALL2)
    # 바닥
    d.rectangle([0, 65, 119, 119], fill=FLOOR)
    for x in range(0, 120, 15):
        d.line([(x, 65), (x, 119)], fill=(85, 72, 52))

    # 창문 — 더 선명한 색
    d.rectangle([5, 6, 30, 32], fill=(100, 100, 120))
    d.rectangle([7, 8, 28, 30], fill=(20, 45, 90))
    d.rectangle([7, 8, 16, 30], fill=(35, 65, 110))
    d.line([(17, 8), (17, 30)], fill=(100, 100, 120), width=2)
    d.line([(7, 19), (28, 19)], fill=(100, 100, 120), width=2)
    # 창문 빛 반사
    if frame % 6 < 3:
        d.rectangle([8, 9, 10, 18], fill=(70, 110, 160))

    # 화분
    d.rectangle([96, 42, 116, 45], fill=DESK)
    d.rectangle([100, 34, 112, 42], fill=(160, 100, 55))
    sway = 1 if frame % 4 < 2 else -1
    d.rectangle([102 + sway, 22, 110 + sway, 34], fill=(40, 165, 80))   # 더 선명한 초록
    d.rectangle([98, 26, 106, 34], fill=(20, 140, 55))
    d.rectangle([106 - sway, 24, 114 - sway, 33], fill=(40, 165, 80))
    # 화분 하이라이트
    d.rectangle([101, 35, 103, 41], fill=(185, 125, 75))


def draw_desk(d):
    """책상"""
    d.rectangle([28, 58, 86, 62], fill=DESK)
    d.rectangle([26, 58, 28, 62], fill=DESK_S)
    d.rectangle([86, 58, 88, 62], fill=DESK_S)
    d.rectangle([30, 63, 34, 80], fill=DESK_S)
    d.rectangle([82, 63, 86, 80], fill=DESK_S)
    # 책상 상단 하이라이트
    d.rectangle([29, 58, 85, 59], fill=(200, 168, 118))
    # 서랍
    d.rectangle([74, 63, 86, 76], fill=DESK_S)
    d.rectangle([76, 65, 84, 69], fill=DESK)
    d.rectangle([76, 71, 84, 75], fill=DESK)
    # 서랍 손잡이
    d.rectangle([79, 67, 81, 68], fill=(210, 180, 100))
    d.rectangle([79, 72, 81, 73], fill=(210, 180, 100))


def draw_monitor(d, state, frame):
    """모니터"""
    mx, my = 40, 30
    d.rectangle([mx, my, mx + 34, my + 24], fill=MONITOR)
    d.rectangle([mx + 3, my + 3, mx + 31, my + 19], fill=SCREEN)
    # 모니터 베젤 하이라이트
    d.rectangle([mx + 1, my + 1, mx + 33, my + 2], fill=(55, 55, 72))
    d.rectangle([mx + 13, my + 24, mx + 21, my + 28], fill=MONITOR)
    d.rectangle([mx + 9, my + 28, mx + 25, my + 30], fill=MONITOR)

    sx, sy = mx + 5, my + 5
    if state == "working":
        # 더 선명한 텍스트 색상
        colors = [(80, 240, 140), (100, 185, 255), (255, 210, 40)]
        for row in range(3):
            c = colors[(row + frame) % 3]
            w = 6 + ((frame + row * 3) % 9)
            if w > 22:
                w = 22
            if not (frame % 3 == 0 and row == 2):
                d.rectangle([sx, sy + row * 4, sx + w, sy + row * 4 + 2], fill=c)
        # 커서 깜빡임
        if frame % 2 == 0:
            d.rectangle([sx + 18, sy + (frame % 3) * 4, sx + 20, sy + (frame % 3) * 4 + 3], fill=WHITE)
        # 코드 줄 완성 이펙트
        if frame % 5 == 0:
            d.rectangle([sx, sy + 8, sx + 22, sy + 9], fill=(80, 240, 140))
    elif state == "done":
        g = (80, 240, 100)
        # 체크마크 — 더 두껍게
        pts = [(sx + 3, sy + 8), (sx + 8, sy + 13), (sx + 19, sy + 2)]
        for i in range(len(pts) - 1):
            d.line([pts[i], pts[i + 1]], fill=g, width=3)
        # 반짝임 이펙트
        sparkle_pos = [(sx + 1, sy + 1), (sx + 19, sy + 2), (sx + 10, sy + 14)]
        sp = sparkle_pos[frame % 3]
        if frame % 4 < 2:
            d.rectangle([sp[0], sp[1], sp[0] + 2, sp[1] + 2], fill=(255, 240, 50))
    elif state == "failed":
        r = (255, 60, 60)
        d.line([(sx + 3, sy + 2), (sx + 19, sy + 13)], fill=r, width=3)
        d.line([(sx + 19, sy + 2), (sx + 3, sy + 13)], fill=r, width=3)
        if frame % 3 != 0:
            d.rectangle([sx + 8, sy, sx + 14, sy + 2], fill=(255, 210, 40))
    else:
        # idle — 스크린세이버 느낌
        bx = (frame * 2) % 18
        by = (frame * 3) % 10
        d.rectangle([sx + bx, sy + by, sx + bx + 3, sy + by + 2], fill=(45, 70, 100))
        d.rectangle([sx + bx + 5, sy + by + 4, sx + bx + 8, sy + by + 5], fill=(35, 55, 85))


def draw_keyboard(d):
    d.rectangle([38, 56, 62, 58], fill=(55, 55, 55))
    d.rectangle([39, 56, 61, 57], fill=(78, 78, 78))
    # 키보드 키 디테일
    for kx in range(40, 61, 4):
        d.rectangle([kx, 56, kx + 2, 57], fill=(65, 65, 65))


def draw_chair(d):
    cx = 36
    d.rectangle([cx - 2, 64, cx + 2, 80], fill=CHAIR)
    d.rectangle([cx - 1, 64, cx + 1, 80], fill=CHAIR2)
    d.rectangle([cx - 2, 80, cx + 22, 84], fill=CHAIR)
    d.rectangle([cx, 80, cx + 20, 82], fill=CHAIR2)
    d.rectangle([cx, 85, cx + 3, 96], fill=CHAIR)
    d.rectangle([cx + 17, 85, cx + 20, 96], fill=CHAIR)
    d.rectangle([cx - 2, 96, cx + 5, 98], fill=(38, 38, 38))
    d.rectangle([cx + 15, 96, cx + 22, 98], fill=(38, 38, 38))
    # 의자 등받이 하이라이트
    d.rectangle([cx - 1, 81, cx + 1, 83], fill=CHAIR2)


def draw_hair(d, info, hx, hy):
    """헤어스타일"""
    h, h2, style = info["hair"], info["hair2"], info["style"]
    if style == "short":
        d.rectangle([hx - 1, hy - 2, hx + 12, hy + 1], fill=h)
        d.rectangle([hx - 2, hy + 1, hx + 1, hy + 6], fill=h)
        d.rectangle([hx + 10, hy + 1, hx + 13, hy + 4], fill=h)
        d.rectangle([hx, hy - 3, hx + 11, hy - 1], fill=h2)
    elif style == "long":
        d.rectangle([hx - 2, hy - 3, hx + 13, hy + 1], fill=h)
        d.rectangle([hx - 3, hy + 1, hx + 1, hy + 14], fill=h)
        d.rectangle([hx + 10, hy + 1, hx + 14, hy + 14], fill=h)
        d.rectangle([hx - 1, hy - 4, hx + 12, hy - 2], fill=h2)
        d.rectangle([hx, hy, hx + 4, hy + 3], fill=h2)
    elif style == "spiky":
        d.rectangle([hx - 1, hy - 2, hx + 12, hy + 1], fill=h)
        d.rectangle([hx + 1, hy - 7, hx + 4, hy - 2], fill=h)    # 더 뾰족하게
        d.rectangle([hx + 5, hy - 9, hx + 8, hy - 2], fill=h2)   # 중앙 뾰족
        d.rectangle([hx + 9, hy - 6, hx + 12, hy - 2], fill=h)
        d.rectangle([hx - 2, hy, hx + 1, hy + 5], fill=h)
        d.rectangle([hx + 10, hy, hx + 13, hy + 4], fill=h)
    elif style == "ponytail":
        d.rectangle([hx - 1, hy - 3, hx + 12, hy + 1], fill=h)
        d.rectangle([hx - 2, hy + 1, hx + 1, hy + 5], fill=h)
        d.rectangle([hx + 11, hy - 1, hx + 15, hy + 2], fill=h)
        d.rectangle([hx + 13, hy + 2, hx + 16, hy + 10], fill=h)
        d.rectangle([hx + 14, hy + 10, hx + 17, hy + 14], fill=h2)
        d.rectangle([hx, hy - 4, hx + 11, hy - 2], fill=h2)
    elif style == "buzz":
        d.rectangle([hx, hy - 1, hx + 11, hy + 2], fill=h)
        d.rectangle([hx - 1, hy + 1, hx + 1, hy + 4], fill=h)
        d.rectangle([hx + 10, hy + 1, hx + 12, hy + 4], fill=h)


def draw_face(d, hx, hy, state, frame):
    """얼굴"""
    d.rectangle([hx, hy + 2, hx + 11, hy + 13], fill=SKIN)
    d.rectangle([hx + 9, hy + 4, hx + 11, hy + 11], fill=SKIN_S)
    # 코 하이라이트
    d.rectangle([hx + 5, hy + 8, hx + 6, hy + 9], fill=SKIN_S)

    # 눈 깜빡임 (idle: 12프레임에서 frame 10,11에 눈 감음)
    if state == "idle" and frame % 12 in (10, 11):
        d.line([(hx + 2, hy + 6), (hx + 4, hy + 6)], fill=EYE)
        d.line([(hx + 7, hy + 6), (hx + 9, hy + 6)], fill=EYE)
    elif state == "failed":
        # X 눈
        d.line([(hx + 2, hy + 5), (hx + 4, hy + 7)], fill=EYE)
        d.line([(hx + 4, hy + 5), (hx + 2, hy + 7)], fill=EYE)
        d.line([(hx + 7, hy + 5), (hx + 9, hy + 7)], fill=EYE)
        d.line([(hx + 9, hy + 5), (hx + 7, hy + 7)], fill=EYE)
    elif state == "done" and frame % 12 in (4, 5, 10, 11):
        # 완료: 행복한 눈 (반달)
        d.line([(hx + 2, hy + 6), (hx + 4, hy + 6)], fill=EYE)
        d.line([(hx + 7, hy + 6), (hx + 9, hy + 6)], fill=EYE)
        d.line([(hx + 2, hy + 7), (hx + 4, hy + 7)], fill=EYE)
        d.line([(hx + 7, hy + 7), (hx + 9, hy + 7)], fill=EYE)
    else:
        d.rectangle([hx + 2, hy + 5, hx + 4, hy + 7], fill=WHITE)
        d.rectangle([hx + 7, hy + 5, hx + 9, hy + 7], fill=WHITE)
        dx = 1 if state == "working" else 0
        d.rectangle([hx + 3 + dx, hy + 6, hx + 4 + dx, hy + 7], fill=EYE)
        d.rectangle([hx + 8 + dx, hy + 6, hx + 9 + dx, hy + 7], fill=EYE)

    # 입
    if state == "done":
        # 크게 웃는 입
        d.rectangle([hx + 2, hy + 10, hx + 9, hy + 10], fill=MOUTH)
        d.rectangle([hx + 3, hy + 11, hx + 8, hy + 12], fill=MOUTH)
        d.rectangle([hx + 4, hy + 12, hx + 7, hy + 13], fill=(180, 80, 80))
        # 볼 홍조 — 더 선명하게
        d.rectangle([hx - 1, hy + 8, hx + 2, hy + 11], fill=(255, 130, 130))
        d.rectangle([hx + 9, hy + 8, hx + 12, hy + 11], fill=(255, 130, 130))
    elif state == "failed":
        d.rectangle([hx + 4, hy + 11, hx + 7, hy + 11], fill=MOUTH)
        d.rectangle([hx + 3, hy + 10, hx + 3, hy + 10], fill=MOUTH)
        d.rectangle([hx + 8, hy + 10, hx + 8, hy + 10], fill=MOUTH)
    elif state == "working":
        # 집중한 표정 — 입 꾹
        if frame % 10 < 5:
            d.rectangle([hx + 4, hy + 10, hx + 7, hy + 10], fill=MOUTH)
        else:
            d.rectangle([hx + 3, hy + 10, hx + 8, hy + 10], fill=MOUTH)
    else:
        d.rectangle([hx + 4, hy + 10, hx + 7, hy + 10], fill=MOUTH)


def generate_character(agent_id, state):
    """한 에이전트의 한 상태에 대한 GIF 프레임들을 생성"""
    info = AGENTS[agent_id]
    frames = []
    num_frames = STATE_FRAMES.get(state, 8)

    for frame in range(num_frames):
        img_draw = Image.new("RGBA", (DRAW_SIZE, DRAW_SIZE), (0, 0, 0, 0))
        img = img_draw
        d = ImageDraw.Draw(img)

        draw_bg(d, frame)
        draw_desk(d)
        draw_monitor(d, state, frame)
        draw_keyboard(d)
        draw_chair(d)

        # 캐릭터 기준점
        cx, cy = 42, 48
        head_dy = 0
        body_dy = 0
        stand_up = False

        if state == "idle":
            # 부드러운 sine 기반 bob 효과 (12프레임)
            bob = math.sin(frame / num_frames * 2 * math.pi)
            body_dy = int(round(bob * 1.5))  # ±1~2 픽셀
            head_dy = body_dy
        elif state == "working":
            # 타이핑 시 상체 미세한 앞뒤 흔들림
            lean = frame % 10
            head_dy = 1 if lean < 5 else 0
            body_dy = 0
        elif state == "done":
            stand_up = True
            # 점프: sine 곡선으로 더 높이 (최대 -14)
            jump_t = frame / num_frames
            jump_h = int(math.sin(jump_t * math.pi) * 14)
            head_dy = -jump_h - 8
            body_dy = -jump_h - 6
        elif state == "failed":
            head_dy = 6 + (2 if frame % 4 < 2 else 0)
            body_dy = 2

        # 머리
        hx, hy = cx, cy + head_dy - 14
        draw_hair(d, info, hx, hy)
        draw_face(d, hx, hy, state, frame)

        # 실패 땀방울
        if state == "failed":
            sd = frame % 3
            d.rectangle([hx + 13, hy + 3 + sd, hx + 14, hy + 5 + sd], fill=(100, 180, 255))

        # 몸통
        bx, by = cx - 2, cy + body_dy
        shirt, shirt2 = info["shirt"], info["shirt2"]
        if not stand_up:
            d.rectangle([bx, by, bx + 15, by + 12], fill=shirt)
            d.rectangle([bx + 11, by + 2, bx + 14, by + 10], fill=shirt2)
            d.rectangle([bx + 4, by, bx + 11, by + 1], fill=WHITE)
            # 셔츠 하이라이트
            d.rectangle([bx + 1, by + 1, bx + 3, by + 5], fill=shirt2)
        else:
            d.rectangle([bx, by - 2, bx + 15, by + 14], fill=shirt)
            d.rectangle([bx + 11, by, bx + 14, by + 12], fill=shirt2)
            d.rectangle([bx + 4, by - 2, bx + 11, by - 1], fill=WHITE)
            d.rectangle([bx + 1, by - 1, bx + 3, by + 3], fill=shirt2)

        # 팔 — working 더 역동적, done 만세 강화
        if state == "working":
            af = frame % 10
            # 왼팔: 더 큰 움직임 범위
            lax_offsets = [0, 1, 3, 4, 4, 3, 1, 0, -1, -1]
            lax = 40 + lax_offsets[af]
            lay_offsets = [0, -1, -1, 0, 1, 1, 0, -1, -1, 0]
            lay = 54 + lay_offsets[af]
            d.rectangle([bx - 5, by + 3, bx - 1, by + 7], fill=shirt)
            d.rectangle([bx - 6, by + 6, bx - 2, by + 10], fill=SKIN)
            d.rectangle([lax, lay, lax + 4, lay + 2], fill=SKIN)
            # 오른팔: 반대 방향
            rax_offsets = [4, 3, 1, 0, 0, 1, 3, 4, 4, 3]
            rax = 50 + rax_offsets[af]
            ray_offsets = [1, 1, 0, -1, -1, 0, 1, 1, 0, -1]
            ray = 54 + ray_offsets[af]
            d.rectangle([bx + 15, by + 3, bx + 20, by + 7], fill=shirt)
            d.rectangle([bx + 17, by + 6, bx + 21, by + 10], fill=SKIN)
            d.rectangle([rax, ray, rax + 4, ray + 2], fill=SKIN)
        elif state == "done":
            # 만세: 팔을 더 크게 벌리고 V자 모양
            au = int(math.sin(frame / num_frames * 2 * math.pi) * 4)
            # 왼팔: 위로 벌리기
            d.rectangle([bx - 6, by - 3, bx - 1, by + 1], fill=shirt)
            d.rectangle([bx - 9, by - 10 - au, bx - 3, by - 3], fill=shirt)
            d.rectangle([bx - 11, by - 14 - au, bx - 4, by - 10 - au], fill=SKIN)
            # 왼손 손가락 V
            d.rectangle([bx - 10, by - 17 - au, bx - 8, by - 14 - au], fill=SKIN)
            d.rectangle([bx - 7, by - 17 - au, bx - 5, by - 14 - au], fill=SKIN)
            # 오른팔: 위로 벌리기
            d.rectangle([bx + 15, by - 3, bx + 20, by + 1], fill=shirt)
            d.rectangle([bx + 18, by - 10 - au, bx + 24, by - 3], fill=shirt)
            d.rectangle([bx + 19, by - 14 - au, bx + 26, by - 10 - au], fill=SKIN)
            # 오른손 손가락 V
            d.rectangle([bx + 19, by - 17 - au, bx + 21, by - 14 - au], fill=SKIN)
            d.rectangle([bx + 22, by - 17 - au, bx + 24, by - 14 - au], fill=SKIN)
        elif state == "failed":
            if frame % 4 < 2:
                d.rectangle([bx - 4, by + 2, bx, by + 7], fill=shirt)
                d.rectangle([hx - 3, hy + 4, hx, hy + 7], fill=SKIN)
                d.rectangle([bx + 15, by + 2, bx + 19, by + 7], fill=shirt)
                d.rectangle([hx + 11, hy + 4, hx + 14, hy + 7], fill=SKIN)
            else:
                d.rectangle([bx - 4, by + 4, bx, by + 11], fill=shirt)
                d.rectangle([bx - 5, by + 11, bx - 1, by + 14], fill=SKIN)
                d.rectangle([bx + 15, by + 4, bx + 19, by + 11], fill=shirt)
                d.rectangle([bx + 16, by + 11, bx + 20, by + 14], fill=SKIN)
        else:  # idle
            # 살짝 흔들리는 팔
            a_swing = 1 if frame % 6 < 3 else 0
            d.rectangle([bx - 4, by + 4 - a_swing, bx, by + 7 - a_swing], fill=shirt)
            d.rectangle([bx - 4, by + 6 - a_swing, bx, by + 9 - a_swing], fill=SKIN)
            d.rectangle([bx + 15, by + 4 + a_swing, bx + 19, by + 7 + a_swing], fill=shirt)
            d.rectangle([bx + 17, by + 6 + a_swing, bx + 20, by + 9 + a_swing], fill=SKIN)

        # 바지 + 신발
        pants = info["pants"]
        if not stand_up:
            d.rectangle([bx + 1, by + 12, bx + 6, by + 17], fill=pants)
            d.rectangle([bx + 8, by + 12, bx + 13, by + 17], fill=pants)
            d.rectangle([bx + 1, by + 17, bx + 5, by + 19], fill=SHOE)
            d.rectangle([bx + 9, by + 17, bx + 13, by + 19], fill=SHOE)
            # 신발 하이라이트
            d.rectangle([bx + 2, by + 17, bx + 3, by + 18], fill=(58, 45, 45))
            d.rectangle([bx + 10, by + 17, bx + 11, by + 18], fill=(58, 45, 45))
        else:
            d.rectangle([bx + 2, by + 14, bx + 6, by + 22], fill=pants)
            d.rectangle([bx + 8, by + 14, bx + 12, by + 22], fill=pants)
            d.rectangle([bx + 1, by + 22, bx + 7, by + 24], fill=SHOE)
            d.rectangle([bx + 7, by + 22, bx + 13, by + 24], fill=SHOE)

        # 완료 이펙트 — 더 풍부한 별 이펙트
        if state == "done":
            star = (255, 235, 50)
            star2 = (255, 180, 50)
            # 여러 위치에 별 그리기
            star_positions = [
                (hx - 10, hy - 8),
                (hx + 18, hy - 10),
                (hx - 14, hy - 3),
                (hx + 22, hy - 5),
                (hx + 4, hy - 16),
                (hx - 6, hy - 14),
            ]
            active_count = 2 + (frame % 3)
            for i, (sx, sy) in enumerate(star_positions):
                if i < active_count:
                    sc = star if i % 2 == 0 else star2
                    d.rectangle([sx, sy, sx + 2, sy], fill=sc)
                    d.rectangle([sx + 1, sy - 1, sx + 1, sy + 1], fill=sc)
                    d.rectangle([sx - 1, sy, sx + 3, sy], fill=sc)

        # 실패 이펙트 (소용돌이 — 더 선명하게)
        if state == "failed" and head_dy > 4:
            swirl = (170, 180, 195)
            r = frame % 4
            offsets = [(0, 0), (3, -2), (5, 1), (2, 3)]
            ox, oy = offsets[r]
            d.rectangle([hx + 2 + ox, hy - 5 + oy, hx + 4 + ox, hy - 3 + oy], fill=swirl)
            d.rectangle([hx + 5 + ox, hy - 6 + oy, hx + 7 + ox, hy - 4 + oy], fill=swirl)

        # NEAREST 스케일업으로 픽셀 아트 선명하게 확대
        img_scaled = img.resize((SIZE, SIZE), Image.NEAREST)
        frames.append(img_scaled)

    return frames


def save_gif(frames, path, delay):
    """프레임 리스트를 GIF로 저장"""
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=delay,
        loop=0,
        disposal=2,
    )


def main():
    print("GIF 생성 시작...")
    states = ["idle", "working", "done", "failed"]

    for agent_id in AGENTS:
        for state in states:
            frames = generate_character(agent_id, state)
            path = ASSETS / f"{agent_id}_{state}.gif"
            delay = STATE_DELAY.get(state, 200)
            save_gif(frames, path, delay)
            print(f"  {path.name} ({len(frames)}프레임, {delay}ms/frame)")

    print(f"\n완료! {len(AGENTS) * len(states)}개 GIF 생성됨")
    print(f"출력 크기: {SIZE}x{SIZE}px")


if __name__ == "__main__":
    main()
