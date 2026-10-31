from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    workers: int
    coord_crs: str

    @classmethod
    def from_env(cls) -> Settings:
        cpu = os.cpu_count() or 1
        raw_workers = os.environ.get("WORKERS")
        if raw_workers is None or raw_workers.strip() == "":
            workers = min(4, cpu)
        else:
            workers = int(raw_workers)
        crs = os.environ.get("COORD_CRS", "sk42").strip().lower()
        if crs not in {"sk42", "usk2000"}:
            raise ValueError("COORD_CRS має бути sk42 або usk2000")
        return cls(workers=max(0, workers), coord_crs=crs)
