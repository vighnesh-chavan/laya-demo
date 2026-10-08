# How the Doom & Shooting Range Demos Work

Both demos follow the exact same pattern: **the game does all the real spatial math itself
(coordinates, distances, geometry), turns the result into a short English sentence, and only
that sentence goes to Laya.** Laya never sees pixels, coordinates, or angles — it just picks
whichever pre-written action description shares the most words with that sentence. The
[HOW_THE_HEURISTIC_WORKS.md](HOW_THE_HEURISTIC_WORKS.md) doc covers the word-matching mechanism
in detail; this doc is about how each game feeds Laya and uses its answer.

---

## 1. `play_doom.py` — real Doom, Laya both aims and moves

### The loop (once per game tick)

```
 1. Ask VizDoom for the current game state
                     │
                     ▼
 2. Find the nearest non-player object in the "labels" buffer
    (VizDoom tags every visible object on screen with its
    name + pixel bounding box: x, width, etc.)
                     │
                     ▼
 3. Compute that object's horizontal offset from screen center,
    normalized to [-1, 1]:
       offset = (label_center_x - screen_center_x) / screen_center_x
    (negative = left of center, positive = right, 0 = dead center)
                     │
                     ▼
 4. Also read two game variables directly: HEALTH and AMMO2
                     │
                     ▼
 5. Turn all of that into ONE English sentence, e.g.:
    "enemy monster spotted left side off center, health low (health=45, ammo=12)"
                     │
                     ▼
 6. Send that sentence to Laya's /decide as an ENUM question,
    with 3 fixed options: turn_left, turn_right, shoot
                     │
                     ▼
 7. Laya returns whichever option's description shares the most
    words with the sentence
                     │
                     ▼
 8. Map the answer to a real VizDoom action (a 3-element button
    array) and send it to the game: game.make_action([...])
                     │
                     ▼
 9. Repeat, ~20 times per second
```

### Where exactly does the offset number come from? (step 2-3)

VizDoom's "labels buffer" is a built-in feature that tags every visible sprite on screen with
its object name and a pixel bounding box (`lbl.x`, `lbl.width`, ...). The code
(`_nearest_enemy_offset` in [play_doom.py](play_doom.py):49) loops over every visible label,
skips the player's own label, and finds whichever one is closest to the horizontal center of
the screen. That's real, hard geometry computed by Python/VizDoom — Laya has no part in this.

### The 3 options Laya is choosing between

```python
OPTIONS = [
    {"label": "turn_left",  "description": "enemy monster spotted left side off center, aim not lined up, must rotate left"},
    {"label": "turn_right", "description": "enemy monster spotted right side off center, aim not lined up, must rotate right"},
    {"label": "shoot",      "description": "enemy monster centered lined up directly ahead in crosshair, fire weapon now"},
]
```

Notice each option's description was written to closely mirror the exact wording the sentence
generator (`describe_state`) produces. That's deliberate — Laya's word-overlap scoring only
works well if the vocabulary lines up between the "question" and the "options". If `describe_state`
said "opponent to the left" instead of "enemy monster spotted left side off center", the overlap
with `turn_left`'s description would drop and Laya could pick the wrong thing more often.

### Example run

Question sent to Laya:
```
"enemy monster spotted left side off center, health low (health=45, ammo=12)"
```
Laya compares this against all 3 option descriptions, counts matching words for each, and
returns whichever scores highest — here `turn_left` wins because of the shared words
`enemy`, `monster`, `spotted`, `left`, `side`, `off`, `center`. The game then does
`game.make_action(ACTIONS["turn_left"])`, i.e. `[1, 0, 0]`, which is VizDoom's button-press
array for "turn left".

### What Laya does NOT know

- It never sees the screen, a WAD file, or any Doom-specific concept.
- It doesn't know the enemy's actual pixel position or distance — only whichever short phrase
  `describe_state` decided to write based on that position.
- If two very differently-positioned enemies produced the same generated sentence, Laya would
  make the same decision both times — it has no memory of past frames either.

---

## 2. `shooting_range.py` — you move the monster, Laya only aims + shoots

This is the same pattern as Doom, but with the monster's movement (game-side player skill)
separated from the turret's decision-making (Laya's job) — you can watch Laya's targeting
logic work in isolation.

### The loop (once every `DECIDE_EVERY_N_FRAMES` frames)

```
 1. Read arrow-key input, move the monster's (x, y) in pygame
    (this part has NOTHING to do with Laya)
                     │
                     ▼
 2. Compute how far the aim point currently is from the monster,
    on BOTH axes:
       offset_x = monster_x - aim_x
       offset_y = monster_y - aim_y
                     │
                     ▼
 3. Turn that into ONE English sentence describing whichever
    axis is furthest off (describe_offset()):
    e.g. "monster spotted to the left off center horizontally"
    or,  if both axes are within CENTER_TOLERANCE pixels:
         "monster centered lined up directly ahead in crosshair on both axes"
                     │
                     ▼
 4. Send that sentence to Laya's /decide as an ENUM question,
    with 5 fixed options: turn_left, turn_right, turn_up,
    turn_down, shoot
                     │
                     ▼
 5. Laya returns whichever option's description shares the
    most words with the sentence
                     │
                     ▼
 6. Apply the decision to the AIM POINT (not the monster!):
      turn_left/right -> nudge aim_x by aim_speed
      turn_up/down    -> nudge aim_y by aim_speed
      shoot           -> fire a bullet toward the monster's
                          CURRENT position; if aim_x/aim_y are
                          both within CENTER_TOLERANCE of the
                          monster, score += 1 and respawn it
                     │
                     ▼
 7. Repeat every couple of frames, all while you keep moving
    the monster freely with the arrow keys
```

### Why only ONE axis is described per question (step 3)

`describe_offset()` ([shooting_range.py](shooting_range.py):85) deliberately picks whichever
axis (horizontal or vertical) has the bigger error and only mentions that one in the sentence.
This keeps the vocabulary unambiguous — if the sentence tried to describe both axes at once
("left and above"), the word overlap against 4 different turn options would get muddier and
Laya would pick worse. By always describing the single biggest error, the turret corrects the
worst-aimed axis first, then the next, converging on the target over a few decisions — visible
in-game as the yellow aim reticle "walking" toward the monster in a slight zig-zag.

### The 5 options Laya is choosing between

```python
OPTIONS = [
    {"label": "turn_left",  "description": "monster spotted to the left off center horizontally, ..."},
    {"label": "turn_right", "description": "monster spotted to the right off center horizontally, ..."},
    {"label": "turn_up",    "description": "monster spotted above off center vertically, ..."},
    {"label": "turn_down",  "description": "monster spotted below off center vertically, ..."},
    {"label": "shoot",      "description": "monster centered lined up directly ahead in crosshair on both axes, fire weapon now"},
]
```
Same trick as Doom: each description's wording is written to closely match whatever
`describe_offset()` would generate for that situation, so the word-overlap scoring reliably
picks the right one.

### What "difficulty" actually changes

The difficulty menu (`choose_difficulty()`) only changes `aim_speed` — how many pixels the aim
point moves per decision (easy=5 ... xhigh=15). It does **not** change how Laya decides, or
how often it decides (`DECIDE_EVERY_N_FRAMES` is fixed). A higher aim speed just means each
correct decision closes the gap faster, so the turret "feels" more responsive — but Laya's
underlying word-matching logic is identical at every difficulty.

### What happens after "shoot"

Firing is a two-part effect:
1. **Immediately**: if the aim point is already within `CENTER_TOLERANCE` of the monster on
   both axes, the hit is scored right away and the monster teleports to a new random spot.
   This check is instant game logic — not something Laya computed.
2. **Visually**: a bullet is spawned and animated flying from the turret toward the monster's
   *live* position every subsequent frame (`update_and_draw_bullets`), so it looks like it's
   chasing the target — but the actual hit/miss result was already decided in step 1, before
   the bullet sprite even started moving.

---

## The one-sentence summary of both

**Laya is handed a single short English sentence every tick, generated by ordinary Python
math (offsets, thresholds, game variables) — and it responds by picking whichever of a small,
fixed set of pre-written options shares the most words with that sentence.** All the "seeing"
and "aiming logic" is really just: game state → templated sentence → word-overlap lookup →
action label → game input. Nothing in between involves real perception, memory, or reasoning.
