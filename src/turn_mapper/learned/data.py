"""Mask datasets for training: ``<dir>/images/<id>.png`` (any image) + ``<dir>/masks/<id>.png`` (uint8 class
ids from ``classes.CLASSES``, 255 = ignore) + optional ``<dir>/{train,val,test}.txt`` id lists.

CubiCasa5K is converted into this format by ``cubicasa.prepare``; our own annotated plans (any venue)
use the same format, so pre-training and fine-tuning share one loader.

Images are converted to grey: colour conventions differ between plan sources and carry little information
for walls/doors, and many institutional plans are effectively grey.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .classes import BG, DOOR, ESCALATOR, IGNORE, LIFT, OTHER, ROOM, STAIRS, WALKABLE, WALL

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


def to_input(gray: np.ndarray) -> np.ndarray:
    """HxW uint8 grey -> 3xHxW float32, ImageNet-normalised (encoders are ImageNet pre-trained)."""
    x = np.repeat((gray.astype(np.float32) / 255.0)[..., None], 3, axis=2)
    return ((x - MEAN) / STD).transpose(2, 0, 1).copy()


def list_ids(d: Path, split: str | None) -> list[str]:
    f = d / f"{split}.txt" if split else None
    if f and f.exists():
        return [ln.strip() for ln in f.read_text().splitlines() if ln.strip()]
    return sorted(p.stem for p in (d / "masks").glob("*.png"))


def restyle(mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Draw a plan image from a mask in a random flat style (grey fill, black walls, ...).

    Bridges the domain gap between CubiCasa's drawing style and other plan sources: the network sees the
    same geometry in many conventions and learns shape, not one dataset's colours."""
    paper = int(rng.integers(235, 256))
    floor = int(rng.integers(200, paper + 1)) if rng.random() < 0.6 else paper
    wall = int(rng.integers(0, max(floor - 40, 1)))
    img = np.full(mask.shape, paper, np.uint8)
    inside = np.isin(mask, (ROOM, WALKABLE, DOOR, STAIRS, LIFT, ESCALATOR, OTHER))
    img[inside] = floor
    if rng.random() < 0.5:  # rooms in different shades
        n, lab = cv2.connectedComponents((mask == ROOM).astype(np.uint8))
        shades = rng.integers(max(floor - 25, 0), min(floor + 10, 255) + 1, n)
        img[mask == ROOM] = shades[lab[mask == ROOM]]
    st = np.isin(mask, (STAIRS, ESCALATOR))
    if st.any():  # treads
        period = int(rng.integers(4, 10))
        yy, xx = np.indices(mask.shape)
        lines = ((xx if rng.random() < 0.5 else yy) % period) == 0
        img[st & lines] = wall
    img[mask == WALL] = wall
    if rng.random() < 0.3:  # outline-only walls (double-line drawing)
        w = (mask == WALL).astype(np.uint8)
        inner = cv2.erode(w, np.ones((3, 3), np.uint8))
        img[(w > 0) & (inner > 0)] = floor
    return img


def augment(img: np.ndarray, mask: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    k = int(rng.integers(4))
    img, mask = np.rot90(img, k), np.rot90(mask, k)
    if rng.random() < 0.5:
        img, mask = img[:, ::-1], mask[:, ::-1]
    img, mask = np.ascontiguousarray(img), np.ascontiguousarray(mask)
    if rng.random() < 0.8:  # contrast / brightness
        a, b = rng.uniform(0.7, 1.3), rng.uniform(-30, 30)
        img = np.clip(img.astype(np.float32) * a + b, 0, 255).astype(np.uint8)
    if rng.random() < 0.3:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.5, 1.5))
    if rng.random() < 0.3:
        img = np.clip(img + rng.normal(0, rng.uniform(2, 10), img.shape), 0, 255).astype(np.uint8)
    if rng.random() < 0.3:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(40, 90))])
        img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return img, mask


class MaskDataset:
    """Random crops (training) or whole images (evaluation) from one or more mask dataset folders."""

    def __init__(
        self,
        dirs: list[str | Path],
        split: str | None = "train",
        crop: int = 512,
        train: bool = True,
        restyle_p: float = 0.3,
        scale_range: tuple[float, float] = (0.6, 1.4),
        repeat: int = 1,
        seed: int = 0,
    ):
        self.items = [(Path(d), i) for d in dirs for i in list_ids(Path(d), split)] * repeat
        if not self.items:
            raise ValueError(f"no samples in {dirs} (split={split})")
        self.crop, self.train, self.restyle_p, self.scale_range = crop, train, restyle_p, scale_range
        self.seed = seed
        self._epoch = 0

    def __len__(self) -> int:
        return len(self.items)

    def load(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        d, sid = self.items[i]
        img = cv2.imread(str(next((d / "images").glob(f"{sid}.*"))), cv2.IMREAD_GRAYSCALE)
        mask = cv2.imread(str(d / "masks" / f"{sid}.png"), cv2.IMREAD_UNCHANGED)
        if img.shape != mask.shape:
            raise ValueError(f"{d}/{sid}: image {img.shape} != mask {mask.shape}")
        return img, mask

    def __getitem__(self, i: int):
        img, mask = self.load(i)
        if not self.train:
            return to_input(img), mask.astype(np.int64)
        rng = np.random.default_rng((self.seed, i, self._epoch, np.random.randint(1 << 30)))
        s = rng.uniform(*self.scale_range)
        if abs(s - 1) > 0.02:
            img = cv2.resize(
                img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
            )
            mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
        if rng.random() < self.restyle_p:
            img = restyle(
                np.where(mask == IGNORE, WALKABLE, mask).astype(np.uint8), rng
            )  # ignored = inside, unknown use
        c = self.crop
        ph, pw = max(0, c - img.shape[0]), max(0, c - img.shape[1])
        if ph or pw:
            img = cv2.copyMakeBorder(img, 0, ph, 0, pw, cv2.BORDER_CONSTANT, value=int(np.median(img[:3])))
            mask = cv2.copyMakeBorder(mask, 0, ph, 0, pw, cv2.BORDER_CONSTANT, value=BG)
        for _ in range(5):  # prefer crops that contain a building
            y = int(rng.integers(0, img.shape[0] - c + 1))
            x = int(rng.integers(0, img.shape[1] - c + 1))
            m = mask[y : y + c, x : x + c]
            if (m != BG).mean() > 0.2:
                break
        img, m = augment(img[y : y + c, x : x + c], m, rng)
        return to_input(img), m.astype(np.int64)
