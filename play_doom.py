"""Laya plays Doom.

Runs a visible VizDoom window (defend_the_center scenario: enemies close in
from all sides, you can only turn and shoot). Every tick, the raw game state
is turned into a plain-English description, sent to Laya's /decide endpoint
as an enum question, and the chosen action is applied to the game.

Laya has no vision and no spatial reasoning -- it is just word-overlap
scoring -- so this is a demo of the *pattern* (symbolic state -> typed
decision -> game action), not a competent Doom bot.

Usage:
    uv run python play_doom.py
Make sure the Laya API is running first:
    uv run uvicorn app.main:app --reload
"""
import os
import time

import numpy as np
import pygame
import requests
import vizdoom as vzd

LAYA_URL = "http://127.0.0.1:8000/decide"

TARGET_FPS = 30
FRAME_DURATION = 1 / TARGET_FPS
EPISODE_TIMEOUT_SECONDS = 5 * 60
DOOM_SKILL = 1  # difficulty, 1 (easiest) - 5 (hardest); scenario default is 3
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
DEATH_PAUSE_SECONDS = 1.5

ACTIONS = {
    "turn_left": [1, 0, 0],
    "turn_right": [0, 1, 0],
    "shoot": [0, 0, 1],
}

OPTIONS = [
    {
        "label": "turn_left",
        "description": "enemy monster spotted left side off center, aim not lined up, must rotate left; also scan left when no target was last seen on the left",
    },
    {
        "label": "turn_right",
        "description": "enemy monster spotted right side off center, aim not lined up, must rotate right; also scan right when no target was last seen on the right",
    },
    {
        "label": "shoot",
        "description": "enemy monster centered lined up directly ahead in crosshair, fire weapon now",
    },
]

CENTER_TOLERANCE_FRACTION = 0.12  # how close to dead-center counts as "aimed"


def _nearest_enemy_offset(game: vzd.DoomGame) -> float | None:
    """Return the enemy's horizontal offset from screen center, normalized to
    [-1, 1] (negative = left of center, positive = right). None if no enemy
    is visible in the labels buffer."""
    state = game.get_state()
    if state is None or not state.labels:
        return None

    screen_width = game.get_screen_width()
    center_x = screen_width / 2

    best_offset = None
    best_distance = float("inf")
    for lbl in state.labels:
        # Only living monsters are valid targets -- VizDoom keeps labeling
        # a killed monster's corpse/blood splatter (category "Gibs") and
        # bullet impacts (category "Explosive") at the same spot, which
        # were wrongly being read as "enemy still centered, keep shooting".
        if lbl.object_category != "Monster":
            continue
        label_center = lbl.x + lbl.width / 2
        distance = abs(label_center - center_x)
        if distance < best_distance:
            best_distance = distance
            best_offset = (label_center - center_x) / center_x
    return best_offset


def describe_state(game: vzd.DoomGame, last_seen_side: str | None) -> tuple[str, str | None]:
    """Build the state description, and track which side an enemy was last
    seen on so that scanning (when no target is visible) turns toward where
    one is likely to reappear instead of always defaulting the same way."""
    health = game.get_game_variable(vzd.GameVariable.HEALTH)
    ammo = game.get_game_variable(vzd.GameVariable.AMMO2)
    offset = _nearest_enemy_offset(game)

    parts = []
    if offset is None:
        if last_seen_side == "left":
            parts.append("no target in sight, area looks clear, last seen on the left, scan left")
        elif last_seen_side == "right":
            parts.append("no target in sight, area looks clear, last seen on the right, scan right")
        else:
            parts.append("no target in sight, area looks clear")
    elif abs(offset) <= CENTER_TOLERANCE_FRACTION:
        parts.append("enemy monster centered lined up directly ahead in crosshair")
    elif offset < 0:
        parts.append("enemy monster spotted left side off center")
        last_seen_side = "left"
    else:
        parts.append("enemy monster spotted right side off center")
        last_seen_side = "right"

    if health < 30:
        parts.append("health critical")
    elif health < 60:
        parts.append("health low")
    if ammo < 5:
        parts.append("ammo low")
    return f"{', '.join(parts)} (health={int(health)}, ammo={int(ammo)})", last_seen_side


def render_frame(screen: pygame.Surface, game: vzd.DoomGame, font: pygame.font.Font) -> None:
    """Draw the current VizDoom frame buffer into our own pygame window
    (instead of relying on VizDoom's native window), so we can overlay a
    DEAD banner on top when the player dies."""
    state = game.get_state()
    if state is not None:
        # VizDoom buffer is (channels, height, width) in RGB order; pygame
        # surfaces want (width, height, channels).
        frame = np.transpose(state.screen_buffer, (2, 1, 0))
        surface = pygame.surfarray.make_surface(frame)
        screen.blit(pygame.transform.scale(surface, (SCREEN_WIDTH, SCREEN_HEIGHT)), (0, 0))

    if game.is_player_dead():
        text = font.render("DEAD", True, (255, 40, 40))
        shadow = font.render("DEAD", True, (0, 0, 0))
        rect = text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
        screen.blit(shadow, rect.move(3, 3))
        screen.blit(text, rect)

    pygame.display.flip()
    pygame.event.pump()


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
        print(f"[laya unreachable, defaulting to turn_right] {exc}")
        return "turn_right"


def main() -> None:
    scenarios_dir = os.path.join(os.path.dirname(vzd.__file__), "scenarios")

    game = vzd.DoomGame()
    game.load_config(os.path.join(scenarios_dir, "defend_the_center.cfg"))
    game.set_doom_scenario_path(os.path.join(scenarios_dir, "defend_the_center.wad"))
    # Rendered ourselves via pygame (see render_frame) so we can draw a DEAD
    # banner on top; VizDoom's own window is turned off.
    game.set_window_visible(False)
    game.set_labels_buffer_enabled(True)
    game.set_screen_resolution(vzd.ScreenResolution.RES_640X480)
    game.set_episode_timeout(EPISODE_TIMEOUT_SECONDS * vzd.DEFAULT_TICRATE)
    game.set_doom_skill(DOOM_SKILL)
    game.init()

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Laya plays Doom")
    font = pygame.font.SysFont(None, 96, bold=True)

    episodes = 10
    for episode in range(1, episodes + 1):
        print(f"\n=== Episode {episode} ===")
        game.new_episode()
        tick = 0
        last_seen_side: str | None = None
        while not game.is_episode_finished():
            frame_start = time.perf_counter()

            question, last_seen_side = describe_state(game, last_seen_side)
            action = ask_laya(question)
            print(f"tick={tick:03d} | state: {question} | laya says: {action}")

            game.make_action(ACTIONS[action])
            tick += 1
            render_frame(screen, game, font)

            elapsed = time.perf_counter() - frame_start
            remaining = FRAME_DURATION - elapsed
            if remaining > 0:
                time.sleep(remaining)

        print(f"Episode {episode} finished. Total reward: {game.get_total_reward()}")
        if game.is_player_dead():
            render_frame(screen, game, font)
            time.sleep(DEATH_PAUSE_SECONDS)
        else:
            time.sleep(1)

    game.close()
    pygame.quit()


if __name__ == "__main__":
    main()
