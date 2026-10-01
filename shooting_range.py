"""Laya shooting range: you move the monster, Laya aims and shoots it.

A simple pygame game. You control the monster's position with the arrow
keys (all 4 directions). Every tick, Laya's /decide endpoint is asked
whether the turret should turn_left, turn_right, turn_up, turn_down, or
shoot, based on the monster's position relative to the turret's aim point.
When the aim lines up on both axes and Laya says "shoot", the monster is
destroyed and respawns.

Sprites are hand-drawn with pygame's vector primitives (no external image
files) -- this avoids any asset licensing/attribution concerns while still
looking better than plain circles.

Usage:
    uv run python shooting_range.py
Make sure the Laya API is running first:
    uv run uvicorn app.main:app --reload
"""
import math
import os
import random
import sys

import pygame
import requests

LAYA_URL = "http://127.0.0.1:8000/decide"
DEBUG = os.environ.get("LAYA_DEBUG") == "1"

WIDTH, HEIGHT = 800, 500
TURRET_BASE_Y = HEIGHT - 50
MONSTER_SIZE = 46
MONSTER_SPEED = 6
MONSTER_X_RANGE = (40, WIDTH - 40)
MONSTER_Y_RANGE = (40, HEIGHT - 160)  # keep monster above the turret area
CENTER_TOLERANCE = 16  # pixels; how close counts as "aimed" on an axis
DECIDE_EVERY_N_FRAMES = 2  # how often Laya re-decides (lower = snappier aiming)
BULLET_SPEED = 63  # pixels per frame -- fast homing travel from turret to target

DIFFICULTY_AIM_SPEEDS = {
    "easy": 5,
    "medium": 8,
    "high": 11,
    "xhigh": 15,
}

OPTIONS = [
    {
        "label": "turn_left",
        "description": "monster spotted to the left off center horizontally, aim not lined up, must rotate left",
    },
    {
        "label": "turn_right",
        "description": "monster spotted to the right off center horizontally, aim not lined up, must rotate right",
    },
    {
        "label": "turn_up",
        "description": "monster spotted above off center vertically, aim not lined up, must raise aim up",
    },
    {
        "label": "turn_down",
        "description": "monster spotted below off center vertically, aim not lined up, must lower aim down",
    },
    {
        "label": "shoot",
        "description": "monster centered lined up directly ahead in crosshair on both axes, fire weapon now",
    },
]


def ask_laya(question: str) -> str:
    try:
        response = requests.post(
            LAYA_URL,
            json={"question": question, "type": "enum", "options": OPTIONS},
            timeout=2,
        )
        response.raise_for_status()
        return response.json()["answer"]
    except requests.RequestException as exc:
        print(f"[laya unreachable, holding position] {exc}")
        return "turn_left"


def describe_offset(offset_x: float, offset_y: float) -> str:
    x_aligned = abs(offset_x) <= CENTER_TOLERANCE
    y_aligned = abs(offset_y) <= CENTER_TOLERANCE
    if x_aligned and y_aligned:
        return "monster centered lined up directly ahead in crosshair on both axes"

    # Describe whichever axis is furthest off, so the turret corrects the
    # bigger error first.
    if abs(offset_x) >= abs(offset_y):
        return (
            "monster spotted to the left off center horizontally"
            if offset_x < 0
            else "monster spotted to the right off center horizontally"
        )
    return (
        "monster spotted above off center vertically"
        if offset_y < 0
        else "monster spotted below off center vertically"
    )


def draw_monster(screen, x, y, size, wobble):
    color_body = (210, 50, 50)
    color_dark = (140, 20, 20)
    r = size // 2
    bob = math.sin(wobble) * 3

    # body
    pygame.draw.circle(screen, color_body, (int(x), int(y + bob)), r)
    # horns
    pygame.draw.polygon(
        screen,
        color_dark,
        [(x - r * 0.6, y - r * 0.6 + bob), (x - r * 0.9, y - r * 1.4 + bob), (x - r * 0.2, y - r * 0.8 + bob)],
    )
    pygame.draw.polygon(
        screen,
        color_dark,
        [(x + r * 0.6, y - r * 0.6 + bob), (x + r * 0.9, y - r * 1.4 + bob), (x + r * 0.2, y - r * 0.8 + bob)],
    )
    # eyes
    eye_dx = r * 0.35
    for sign in (-1, 1):
        pygame.draw.circle(screen, (255, 255, 255), (int(x + sign * eye_dx), int(y - r * 0.1 + bob)), int(r * 0.22))
        pygame.draw.circle(screen, (20, 20, 20), (int(x + sign * eye_dx), int(y - r * 0.1 + bob)), int(r * 0.1))
    # mouth
    pygame.draw.arc(
        screen,
        color_dark,
        pygame.Rect(int(x - r * 0.5), int(y + r * 0.05 + bob), int(r), int(r * 0.6)),
        math.pi * 0.1,
        math.pi * 0.9,
        3,
    )


def draw_turret(screen, base_x, aim_x, aim_y, muzzle_flash):
    base_color = (90, 100, 110)
    barrel_color = (60, 200, 255)

    # base platform
    pygame.draw.polygon(
        screen,
        base_color,
        [
            (base_x - 34, TURRET_BASE_Y + 30),
            (base_x + 34, TURRET_BASE_Y + 30),
            (base_x + 22, TURRET_BASE_Y),
            (base_x - 22, TURRET_BASE_Y),
        ],
    )
    pygame.draw.circle(screen, base_color, (base_x, TURRET_BASE_Y), 20)

    # barrel points from the turret base toward the aim point
    dx, dy = aim_x - base_x, aim_y - TURRET_BASE_Y
    length = math.hypot(dx, dy) or 1
    dx, dy = dx / length, dy / length
    barrel_len = 42
    end_x, end_y = base_x + dx * barrel_len, TURRET_BASE_Y + dy * barrel_len
    pygame.draw.line(screen, barrel_color, (base_x, TURRET_BASE_Y), (end_x, end_y), 8)
    pygame.draw.circle(screen, barrel_color, (base_x, TURRET_BASE_Y), 12)

    if muzzle_flash > 0:
        pygame.draw.circle(screen, (255, 210, 60), (int(end_x), int(end_y)), 14, 3)

    return end_x, end_y


def spawn_bullet(start_x, start_y):
    return {"x": start_x, "y": start_y, "vx": 0.0, "vy": 0.0}


def update_and_draw_bullets(screen, bullets, monster_x, monster_y):
    """Homing bullets: every frame, re-aim at the monster's CURRENT position
    (not where it was when fired), so they visibly chase a moving target."""
    alive = []
    for b in bullets:
        dx, dy = monster_x - b["x"], monster_y - b["y"]
        distance = math.hypot(dx, dy) or 1
        b["vx"], b["vy"] = dx / distance * BULLET_SPEED, dy / distance * BULLET_SPEED
        b["x"] += b["vx"]
        b["y"] += b["vy"]

        reached = distance <= BULLET_SPEED
        pygame.draw.line(
            screen,
            (255, 235, 120),
            (b["x"] - b["vx"] * 0.6, b["y"] - b["vy"] * 0.6),
            (b["x"], b["y"]),
            4,
        )
        pygame.draw.circle(screen, (255, 255, 200), (int(b["x"]), int(b["y"])), 4)
        if not reached:
            alive.append(b)
    return alive


def choose_difficulty(screen, clock, font, title_font) -> tuple[str, int]:
    """Blocking pre-game screen: press 1-4 to pick a difficulty, which sets
    how fast the aim reticle moves per decision. Returns the chosen
    AIM_SPEED value."""
    options = list(DIFFICULTY_AIM_SPEEDS.items())
    key_to_index = {
        pygame.K_1: 0,
        pygame.K_2: 1,
        pygame.K_3: 2,
        pygame.K_4: 3,
    }

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key in key_to_index:
                return options[key_to_index[event.key]]

        screen.fill((18, 18, 30))
        title = title_font.render("Laya Shooting Range", True, (255, 255, 255))
        screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 60))

        subtitle = font.render("Choose a difficulty (sets aim speed):", True, (200, 200, 210))
        screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, 130))

        for i, (name, speed) in enumerate(options):
            line = f"{i + 1}. {name.upper()}  (aim speed {speed})"
            surface = font.render(line, True, (230, 230, 90))
            screen.blit(surface, (WIDTH // 2 - surface.get_width() // 2, 190 + i * 40))

        pygame.display.flip()
        clock.tick(30)


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Laya Shooting Range")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(None, 28)
    title_font = pygame.font.SysFont(None, 44)

    difficulty_name, aim_speed = choose_difficulty(screen, clock, font, title_font)

    monster_x, monster_y = WIDTH // 2, MONSTER_Y_RANGE[0]
    aim_x, aim_y = WIDTH // 2, MONSTER_Y_RANGE[0]
    turret_base_x = WIDTH // 2
    score = 0
    last_decision = "..."
    frame = 0
    muzzle_flash_timer = 0
    wobble = 0.0
    bullets = []

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            monster_x -= MONSTER_SPEED
        if keys[pygame.K_RIGHT]:
            monster_x += MONSTER_SPEED
        if keys[pygame.K_UP]:
            monster_y -= MONSTER_SPEED
        if keys[pygame.K_DOWN]:
            monster_y += MONSTER_SPEED
        monster_x = max(MONSTER_X_RANGE[0], min(MONSTER_X_RANGE[1], monster_x))
        monster_y = max(MONSTER_Y_RANGE[0], min(MONSTER_Y_RANGE[1], monster_y))

        if frame % DECIDE_EVERY_N_FRAMES == 0:
            offset_x = monster_x - aim_x
            offset_y = monster_y - aim_y
            question = describe_offset(offset_x, offset_y)
            last_decision = ask_laya(question)

            if last_decision == "turn_left":
                aim_x -= aim_speed
            elif last_decision == "turn_right":
                aim_x += aim_speed
            elif last_decision == "turn_up":
                aim_y -= aim_speed
            elif last_decision == "turn_down":
                aim_y += aim_speed
            elif last_decision == "shoot":
                muzzle_flash_timer = 6
                bullets.append(spawn_bullet(turret_base_x, TURRET_BASE_Y))
                if abs(monster_x - aim_x) <= CENTER_TOLERANCE and abs(monster_y - aim_y) <= CENTER_TOLERANCE:
                    score += 1
                    monster_x = random.randint(*MONSTER_X_RANGE)
                    monster_y = random.randint(*MONSTER_Y_RANGE)

            if DEBUG:
                print(
                    f"frame={frame:04d} monster=({monster_x},{monster_y}) aim=({aim_x},{aim_y}) "
                    f"offset=({offset_x:+.0f},{offset_y:+.0f}) decision={last_decision} score={score}"
                )

            aim_x = max(0, min(WIDTH, aim_x))
            aim_y = max(0, min(HEIGHT, aim_y))

        frame += 1
        wobble += 0.1

        screen.fill((18, 18, 30))

        # subtle floor line for depth
        pygame.draw.line(screen, (40, 40, 55), (0, TURRET_BASE_Y + 30), (WIDTH, TURRET_BASE_Y + 30), 2)

        draw_monster(screen, monster_x, monster_y, MONSTER_SIZE, wobble)
        draw_turret(screen, turret_base_x, aim_x, aim_y, muzzle_flash_timer)
        bullets = update_and_draw_bullets(screen, bullets, monster_x, monster_y)
        if muzzle_flash_timer > 0:
            muzzle_flash_timer -= 1

        pygame.draw.circle(screen, (255, 255, 0), (int(aim_x), int(aim_y)), 6, 2)

        hud_lines = [
            f"Score: {score}",
            f"Difficulty: {difficulty_name.upper()} (aim speed {aim_speed})",
            f"Laya's last decision: {last_decision}",
            "Move monster: arrow keys (up/down/left/right)",
        ]
        for i, line in enumerate(hud_lines):
            surface = font.render(line, True, (230, 230, 230))
            screen.blit(surface, (10, 10 + i * 26))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
