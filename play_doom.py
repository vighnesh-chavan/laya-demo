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

import requests
import vizdoom as vzd

LAYA_URL = "http://127.0.0.1:8000/decide"

ACTIONS = {
    "turn_left": [1, 0, 0],
    "turn_right": [0, 1, 0],
    "shoot": [0, 0, 1],
}

OPTIONS = [
    {
        "label": "turn_left",
        "description": "enemy monster spotted left side off center, aim not lined up, must rotate left",
    },
    {
        "label": "turn_right",
        "description": "enemy monster spotted right side off center, aim not lined up, must rotate right",
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
        if lbl.object_name == "DoomPlayer":
            continue
        label_center = lbl.x + lbl.width / 2
        distance = abs(label_center - center_x)
        if distance < best_distance:
            best_distance = distance
            best_offset = (label_center - center_x) / center_x
    return best_offset


def describe_state(game: vzd.DoomGame) -> str:
    health = game.get_game_variable(vzd.GameVariable.HEALTH)
    ammo = game.get_game_variable(vzd.GameVariable.AMMO2)
    offset = _nearest_enemy_offset(game)

    parts = []
    if offset is None:
        parts.append("no target in sight, area looks clear")
    elif abs(offset) <= CENTER_TOLERANCE_FRACTION:
        parts.append("enemy monster centered lined up directly ahead in crosshair")
    elif offset < 0:
        parts.append("enemy monster spotted left side off center")
    else:
        parts.append("enemy monster spotted right side off center")

    if health < 30:
        parts.append("health critical")
    elif health < 60:
        parts.append("health low")
    if ammo < 5:
        parts.append("ammo low")
    return f"{', '.join(parts)} (health={int(health)}, ammo={int(ammo)})"


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
    game.set_window_visible(True)
    game.set_labels_buffer_enabled(True)
    game.set_screen_resolution(vzd.ScreenResolution.RES_640X480)
    game.init()

    episodes = 3
    for episode in range(1, episodes + 1):
        print(f"\n=== Episode {episode} ===")
        game.new_episode()
        tick = 0
        while not game.is_episode_finished():
            question = describe_state(game)
            action = ask_laya(question)
            print(f"tick={tick:03d} | state: {question} | laya says: {action}")

            game.make_action(ACTIONS[action])
            tick += 1
            time.sleep(0.05)

        print(f"Episode {episode} finished. Total reward: {game.get_total_reward()}")
        time.sleep(1)

    game.close()


if __name__ == "__main__":
    main()
