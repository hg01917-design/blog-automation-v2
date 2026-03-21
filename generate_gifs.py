"""에이전트 캐릭터 GIF 생성기 — Stardew Valley 스타일 픽셀 아트"""
from PIL import Image, ImageDraw
from pathlib import Path
import math

ASSETS = Path(__file__).parent / "assets"
ASSETS.mkdir(exist_ok=True)

SIZE = 120  # GIF 크기
FRAMES = 8
DELAY = 200  # ms per frame

# 에이전트별 색상
AGENTS = {
    "keyword": {"shirt": (59, 130, 246), "shirt2": (37, 99, 235), "pants": (30, 64, 175),
                "hair": (74, 55, 40), "hair2": (58, 39, 24), "style": "short"},
    "writer": {"shirt": (34, 197, 94), "shirt2": (22, 163, 74), "pants": (21, 128, 61),
               "hair": (212, 165, 116), "hair2": (196, 148, 100), "style": "long"},
    "review": {"shirt": (234, 179, 8), "shirt2": (202, 138, 4), "pants": (161, 98, 7),
               "hair": (26, 26, 26), "hair2": (10, 10, 10), "style": "spiky"},
    "final_review": {"shirt": (168, 85, 247), "shirt2": (147, 51, 234), "pants": (126, 34, 206),
                     "hair": (220, 38, 38), "hair2": (185, 28, 28), "style": "ponytail"},
    "poster": {"shirt": (239, 68, 68), "shirt2": (220, 38, 38), "pants": (185, 28, 28),
               "hair": (245, 245, 245), "hair2": (212, 212, 212), "style": "buzz"},
}

SKIN = (245, 198, 160)
SKIN_S = (212, 165, 116)
EYE = (45, 27, 14)
MOUTH = (196, 122, 90)
WHITE = (255, 255, 255)
BG = (30, 30, 42)
FLOOR = (58, 48, 32)
DESK = (160, 132, 92)
DESK_S = (122, 100, 64)
MONITOR = (42, 42, 42)
SCREEN = (10, 22, 40)
CHAIR = (74, 74, 90)
CHAIR2 = (58, 58, 74)
SHOE = (42, 32, 32)
WALL2 = (35, 35, 51)


def draw_bg(d, frame):
    """배경: 벽 + 바닥 + 창문 + 화분"""
    # 벽
    d.rectangle([0, 0, 119, 64], fill=BG)
    for x in range(0, 120, 18):
        d.line([(x, 0), (x, 64)], fill=WALL2)
    # 바닥
    d.rectangle([0, 65, 119, 119], fill=FLOOR)
    for x in range(0, 120, 15):
        d.line([(x, 65), (x, 119)], fill=(74, 64, 48))

    # 창문
    d.rectangle([5, 6, 30, 32], fill=(90, 90, 106))
    d.rectangle([7, 8, 28, 30], fill=(26, 42, 74))
    d.rectangle([7, 8, 16, 30], fill=(42, 58, 90))
    d.line([(17, 8), (17, 30)], fill=(90, 90, 106), width=2)
    d.line([(7, 19), (28, 19)], fill=(90, 90, 106), width=2)

    # 화분
    d.rectangle([96, 42, 116, 45], fill=DESK)
    d.rectangle([100, 34, 112, 42], fill=(139, 94, 60))
    sway = 1 if frame % 4 < 2 else -1
    d.rectangle([102 + sway, 24, 110 + sway, 34], fill=(45, 138, 78))
    d.rectangle([98, 28, 106, 34], fill=(29, 122, 62))
    d.rectangle([106 - sway, 26, 114 - sway, 33], fill=(45, 138, 78))


def draw_desk(d):
    """책상"""
    d.rectangle([28, 58, 86, 62], fill=DESK)
    d.rectangle([26, 58, 28, 62], fill=DESK_S)
    d.rectangle([86, 58, 88, 62], fill=DESK_S)
    d.rectangle([30, 63, 34, 80], fill=DESK_S)
    d.rectangle([82, 63, 86, 80], fill=DESK_S)
    # 서랍
    d.rectangle([74, 63, 86, 76], fill=DESK_S)
    d.rectangle([76, 65, 84, 69], fill=DESK)
    d.rectangle([76, 71, 84, 75], fill=DESK)


def draw_monitor(d, state, frame):
    """모니터"""
    mx, my = 40, 30
    d.rectangle([mx, my, mx + 34, my + 24], fill=MONITOR)
    d.rectangle([mx + 3, my + 3, mx + 31, my + 19], fill=SCREEN)
    d.rectangle([mx + 13, my + 24, mx + 21, my + 28], fill=MONITOR)
    d.rectangle([mx + 9, my + 28, mx + 25, my + 30], fill=MONITOR)

    sx, sy = mx + 5, my + 5
    if state == "working":
        colors = [(74, 222, 128), (96, 165, 250), (251, 191, 36)]
        for row in range(3):
            c = colors[(row + frame) % 3]
            w = 6 + ((frame + row * 3) % 8)
            if w > 22:
                w = 22
            if not (frame % 3 == 0 and row == 2):
                d.rectangle([sx, sy + row * 4, sx + w, sy + row * 4 + 2], fill=c)
        if frame % 2 == 0:
            d.rectangle([sx + 18, sy + (frame % 3) * 4, sx + 20, sy + (frame % 3) * 4 + 3], fill=WHITE)
    elif state == "done":
        g = (74, 222, 128)
        # 체크마크
        pts = [(sx + 4, sy + 8), (sx + 8, sy + 12), (sx + 18, sy + 2)]
        for i in range(len(pts) - 1):
            d.line([pts[i], pts[i + 1]], fill=g, width=2)
        if frame % 4 < 2:
            d.rectangle([sx + 1, sy + 1, sx + 3, sy + 3], fill=(253, 224, 71))
            d.rectangle([sx + 19, sy + 2, sx + 21, sy + 4], fill=(253, 224, 71))
    elif state == "failed":
        r = (239, 68, 68)
        d.line([(sx + 4, sy + 2), (sx + 18, sy + 12)], fill=r, width=2)
        d.line([(sx + 18, sy + 2), (sx + 4, sy + 12)], fill=r, width=2)
        if frame % 3 != 0:
            d.rectangle([sx + 8, sy, sx + 14, sy + 2], fill=(251, 191, 36))
    else:
        bx = (frame * 3) % 20
        by = (frame * 2) % 12
        d.rectangle([sx + bx, sy + by, sx + bx + 2, sy + by + 2], fill=(51, 65, 85))


def draw_keyboard(d):
    d.rectangle([38, 56, 62, 58], fill=(58, 58, 58))
    d.rectangle([39, 56, 61, 57], fill=(74, 74, 74))


def draw_chair(d):
    cx = 36
    d.rectangle([cx - 2, 64, cx + 2, 80], fill=CHAIR)
    d.rectangle([cx - 1, 64, cx + 1, 80], fill=CHAIR2)
    d.rectangle([cx - 2, 80, cx + 22, 84], fill=CHAIR)
    d.rectangle([cx, 80, cx + 20, 82], fill=CHAIR2)
    d.rectangle([cx, 85, cx + 3, 96], fill=CHAIR)
    d.rectangle([cx + 17, 85, cx + 20, 96], fill=CHAIR)
    d.rectangle([cx - 2, 96, cx + 5, 98], fill=(42, 42, 42))
    d.rectangle([cx + 15, 96, cx + 22, 98], fill=(42, 42, 42))


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
        d.rectangle([hx + 1, hy - 6, hx + 4, hy - 2], fill=h)
        d.rectangle([hx + 5, hy - 7, hx + 8, hy - 2], fill=h2)
        d.rectangle([hx + 9, hy - 5, hx + 12, hy - 2], fill=h)
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

    # 눈
    if state == "idle" and frame % 8 in (6, 7):
        d.line([(hx + 2, hy + 6), (hx + 4, hy + 6)], fill=EYE)
        d.line([(hx + 7, hy + 6), (hx + 9, hy + 6)], fill=EYE)
    elif state == "failed":
        # X 눈
        d.line([(hx + 2, hy + 5), (hx + 4, hy + 7)], fill=EYE)
        d.line([(hx + 4, hy + 5), (hx + 2, hy + 7)], fill=EYE)
        d.line([(hx + 7, hy + 5), (hx + 9, hy + 7)], fill=EYE)
        d.line([(hx + 9, hy + 5), (hx + 7, hy + 7)], fill=EYE)
    else:
        d.rectangle([hx + 2, hy + 5, hx + 4, hy + 7], fill=WHITE)
        d.rectangle([hx + 7, hy + 5, hx + 9, hy + 7], fill=WHITE)
        dx = 1 if state == "working" else 0
        d.rectangle([hx + 3 + dx, hy + 6, hx + 4 + dx, hy + 7], fill=EYE)
        d.rectangle([hx + 8 + dx, hy + 6, hx + 9 + dx, hy + 7], fill=EYE)

    # 입
    if state == "done":
        d.rectangle([hx + 3, hy + 10, hx + 8, hy + 10], fill=MOUTH)
        d.rectangle([hx + 4, hy + 11, hx + 7, hy + 11], fill=MOUTH)
        # 볼 홍조
        d.rectangle([hx, hy + 8, hx + 2, hy + 10], fill=(255, 153, 153))
        d.rectangle([hx + 9, hy + 8, hx + 11, hy + 10], fill=(255, 153, 153))
    elif state == "failed":
        d.rectangle([hx + 4, hy + 11, hx + 7, hy + 11], fill=MOUTH)
        d.rectangle([hx + 3, hy + 10, hx + 3, hy + 10], fill=MOUTH)
        d.rectangle([hx + 8, hy + 10, hx + 8, hy + 10], fill=MOUTH)
    else:
        d.rectangle([hx + 4, hy + 10, hx + 7, hy + 10], fill=MOUTH)


def generate_character(agent_id, state):
    """한 에이전트의 한 상태에 대한 GIF 프레임들을 생성"""
    info = AGENTS[agent_id]
    frames = []

    for frame in range(FRAMES):
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
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
            body_dy = 1 if frame % 6 < 3 else 0
            head_dy = body_dy
        elif state == "working":
            head_dy = 0
        elif state == "done":
            stand_up = True
            head_dy = -8 - (2 if frame % 4 < 2 else 0)
            body_dy = -6
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
            d.rectangle([hx + 13, hy + 3 + sd, hx + 14, hy + 5 + sd], fill=(96, 165, 250))

        # 몸통
        bx, by = cx - 2, cy + body_dy
        shirt, shirt2 = info["shirt"], info["shirt2"]
        if not stand_up:
            d.rectangle([bx, by, bx + 15, by + 12], fill=shirt)
            d.rectangle([bx + 11, by + 2, bx + 14, by + 10], fill=shirt2)
            d.rectangle([bx + 4, by, bx + 11, by + 1], fill=WHITE)
        else:
            d.rectangle([bx, by - 2, bx + 15, by + 14], fill=shirt)
            d.rectangle([bx + 11, by, bx + 14, by + 12], fill=shirt2)
            d.rectangle([bx + 4, by - 2, bx + 11, by - 1], fill=WHITE)

        # 팔
        if state == "working":
            af = frame % 4
            lax = 40 + (af % 2) * 3
            d.rectangle([bx - 4, by + 4, bx, by + 7], fill=shirt)
            d.rectangle([bx - 5, by + 6, bx - 2, by + 9], fill=SKIN)
            d.rectangle([lax, 54, lax + 3, 56], fill=SKIN)
            rax = 52 - (af % 2) * 3
            d.rectangle([bx + 15, by + 4, bx + 19, by + 7], fill=shirt)
            d.rectangle([bx + 17, by + 6, bx + 20, by + 9], fill=SKIN)
            d.rectangle([rax, 54, rax + 3, 56], fill=SKIN)
        elif state == "done":
            au = 3 if frame % 4 < 2 else 0
            d.rectangle([bx - 4, by - 2, bx, by + 2], fill=shirt)
            d.rectangle([bx - 6, by - 8 - au, bx - 2, by - 2], fill=shirt)
            d.rectangle([bx - 7, by - 11 - au, bx - 3, by - 8 - au], fill=SKIN)
            d.rectangle([bx + 15, by - 2, bx + 19, by + 2], fill=shirt)
            d.rectangle([bx + 17, by - 8 - au, bx + 21, by - 2], fill=shirt)
            d.rectangle([bx + 18, by - 11 - au, bx + 22, by - 8 - au], fill=SKIN)
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
        else:
            d.rectangle([bx - 4, by + 4, bx, by + 7], fill=shirt)
            d.rectangle([bx - 4, by + 6, bx, by + 9], fill=SKIN)
            d.rectangle([bx + 15, by + 4, bx + 19, by + 7], fill=shirt)
            d.rectangle([bx + 17, by + 6, bx + 20, by + 9], fill=SKIN)

        # 바지 + 신발
        pants = info["pants"]
        if not stand_up:
            d.rectangle([bx + 1, by + 12, bx + 6, by + 17], fill=pants)
            d.rectangle([bx + 8, by + 12, bx + 13, by + 17], fill=pants)
            d.rectangle([bx + 1, by + 17, bx + 5, by + 19], fill=SHOE)
            d.rectangle([bx + 9, by + 17, bx + 13, by + 19], fill=SHOE)
        else:
            d.rectangle([bx + 2, by + 14, bx + 6, by + 22], fill=pants)
            d.rectangle([bx + 8, by + 14, bx + 12, by + 22], fill=pants)
            d.rectangle([bx + 1, by + 22, bx + 7, by + 24], fill=SHOE)
            d.rectangle([bx + 7, by + 22, bx + 13, by + 24], fill=SHOE)

        # 완료 이펙트 (별)
        if state == "done":
            star = (253, 224, 71)
            pts_list = [
                [(hx - 8, hy - 6), (hx + 18, hy - 10)],
                [(hx - 12, hy - 2), (hx + 22, hy - 4)],
                [(hx - 6, hy - 12), (hx + 16, hy - 8)],
                [(hx - 10, hy - 8), (hx + 20, hy - 6)],
            ]
            pts = pts_list[frame % 4]
            for sx, sy in pts:
                d.rectangle([sx, sy, sx + 2, sy], fill=star)
                d.rectangle([sx + 1, sy - 1, sx + 1, sy + 1], fill=star)

        # 실패 이펙트 (소용돌이)
        if state == "failed" and head_dy > 4:
            swirl = (156, 163, 175)
            r = frame % 4
            offsets = [(0, 0), (3, -2), (5, 1), (2, 3)]
            ox, oy = offsets[r]
            d.rectangle([hx + 2 + ox, hy - 5 + oy, hx + 3 + ox, hy - 4 + oy], fill=swirl)
            d.rectangle([hx + 5 + ox, hy - 6 + oy, hx + 6 + ox, hy - 5 + oy], fill=swirl)

        frames.append(img)

    return frames


def save_gif(frames, path):
    """프레임 리스트를 GIF로 저장"""
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=DELAY,
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
            save_gif(frames, path)
            print(f"  {path.name}")

    print(f"완료! {len(AGENTS) * len(states)}개 GIF 생성됨")


if __name__ == "__main__":
    main()
