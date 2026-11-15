from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class VideoInfo:
    id: str
    title: str
    channel: str = ""
    url: str = ""
    duration: float = 0.0  # secondes
    views: int = 0
    license: str = ""  # "creativeCommon" | "youtube" | ""
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Moment:
    start: float
    end: float
    title: str
    hook: str
    reason: str
    score: int  # 1-10
    hashtags: list[str] = field(default_factory=list)
    face_x: float | None = None  # position horizontale du sujet (0-1) pour le recadrage
    visual_note: str = ""  # avis de Claude après avoir regardé les images

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = round(self.duration, 2)
        return d
