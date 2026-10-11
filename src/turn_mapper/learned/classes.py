"""TURN segmentation classes and the mapping from CubiCasa5K labels.

The learned segmenter predicts one class per pixel. Classes are chosen for navigation, not for
architecture: what matters is where you can walk (room / walkable), what blocks you (wall), where you
pass between spaces (door) and where you change floors (stairs / lift / escalator).
"""

from __future__ import annotations

CLASSES = ("background", "wall", "room", "walkable", "door", "stairs", "lift", "escalator", "other")
BG, WALL, ROOM, WALKABLE, DOOR, STAIRS, LIFT, ESCALATOR, OTHER = range(len(CLASSES))
IGNORE = 255  # mask value excluded from the loss (unlabelled pixels in partial annotations)

# colours for previews (RGB)
PALETTE = (
    (255, 255, 255),
    (40, 40, 40),
    (120, 170, 230),
    (250, 200, 110),
    (60, 180, 75),
    (230, 120, 200),
    (200, 60, 60),
    (150, 90, 200),
    (190, 190, 190),
)

# CubiCasa5K "Space <Type>" names -> TURN class. Anything not listed is an ordinary room.
_WALKABLE = {
    "hall",
    "hallway",
    "corridor",
    "entry",
    "draughtlobby",
    "lobby",
    "reception",
    "vestibule",
    "foyer",
    "passage",
}
_STAIRS = {"stairwell", "stairs", "staircase", "stair"}
_LIFT = {"elevator", "lift"}
_OTHER = {"outdoor", "opentobelow", "skylights", "balcony", "terrace", "patio", "below150cm"}


def cubicasa_space_class(space_type: str) -> int:
    t = space_type.strip().lower().replace(" ", "").replace("_", "")
    if t in _WALKABLE:
        return WALKABLE
    if t in _STAIRS:
        return STAIRS
    if t in _LIFT:
        return LIFT
    if t in _OTHER:
        return OTHER
    return ROOM
