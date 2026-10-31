from __future__ import annotations

import math
import pickle
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from tg_msg_checker.analyzers.coordinates import CoordinateAnalyzer
from tg_msg_checker.analyzers.lexical import LexicalAnalyzer
from tg_msg_checker.config import Settings
from tg_msg_checker.dictionaries import DictionaryNotFound, DictionaryStore, validate_dictionary
from tg_msg_checker.lemmatize import build_form_index
from tg_msg_checker.models import Dictionary, Finding, Message

_SMALL_COUNT = 4
_SMALL_BYTES = 32 * 1024
_worker_cache: dict[str, object] = {"path": None, "key": None, "cascade": None}


class Cascade:
    def __init__(self, analyzers: list):
        self.analyzers = analyzers

    @classmethod
    def from_forms(cls, forms: dict, coord_crs: str) -> Cascade:
        return cls(
            [
                LexicalAnalyzer(forms),
                CoordinateAnalyzer(coord_crs),
            ]
        )

    def analyze_many(self, messages: list[Message]) -> list[dict]:
        results: list[dict] = []
        for message in messages:
            item = self.analyze_one(message)
            if item is not None:
                results.append(item)
        return results

    def analyze_one(self, message: Message) -> dict | None:
        findings: list[Finding] = []
        for analyzer in self.analyzers:
            findings.extend(analyzer.analyze(message.text))
        return group_findings(message.id, findings)


class AnalysisEngine:
    def __init__(self, data_dir: Path, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = DictionaryStore(self.data_dir / "dictionaries.json")
        self._pool: ProcessPoolExecutor | None = None
        self._version = 0
        self._snapshot_file: Path | None = None
        self._stats: dict[str, dict[str, int]] = {}
        self._cascade = self._install(self.store.entries)

    def start_pool(self) -> None:
        if self.settings.workers <= 0 or self._pool is not None:
            return
        self._pool = ProcessPoolExecutor(max_workers=self.settings.workers)

    def shutdown(self) -> None:
        pool = self._pool
        self._pool = None
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    def list_dictionaries(self) -> list[dict]:
        return [self._public(entry) for entry in self.store.entries]

    def create_dictionary(self, name: str, language: str, tag: str, words: list[str]) -> dict:
        name, language, tag, words = validate_dictionary(name, language, tag, words)
        entry = Dictionary(id=self.store.new_id(), name=name, language=language, tag=tag, words=words)
        self._commit([*self.store.entries, entry])
        return self._public(entry)

    def update_dictionary(self, dictionary_id: str, name: str, language: str, tag: str, words: list[str]) -> dict:
        name, language, tag, words = validate_dictionary(name, language, tag, words)
        if not any(entry.id == dictionary_id for entry in self.store.entries):
            raise DictionaryNotFound("Словник не знайдено")
        updated = Dictionary(id=dictionary_id, name=name, language=language, tag=tag, words=words)
        entries = [updated if entry.id == dictionary_id else entry for entry in self.store.entries]
        self._commit(entries)
        return self._public(updated)

    def delete_dictionary(self, dictionary_id: str) -> None:
        if not any(entry.id == dictionary_id for entry in self.store.entries):
            raise DictionaryNotFound("Словник не знайдено")
        entries = [entry for entry in self.store.entries if entry.id != dictionary_id]
        self._commit(entries)

    def analyze(self, messages: list[Message], *, parallel: bool | None = None) -> list[dict]:
        if not messages:
            return []
        cascade = self._cascade
        pool = self._pool
        snapshot = self._snapshot_file
        use_parallel = self._should_parallel(messages, parallel) and pool is not None and snapshot is not None
        if not use_parallel or pool is None or snapshot is None:
            return cascade.analyze_many(messages)
        pairs = [(message.id, message.text) for message in messages]
        chunks = _chunks(pairs, self.settings.workers)
        futures = [
            pool.submit(
                analyze_chunk,
                str(snapshot),
                chunk,
                self.settings.coord_crs,
            )
            for chunk in chunks
        ]
        results: list[dict] = []
        for future in futures:
            results.extend(future.result())
        return results

    def _should_parallel(self, messages: list[Message], parallel: bool | None) -> bool:
        if parallel is False or self._pool is None or self.settings.workers <= 0:
            return False
        if parallel is True:
            return True
        total = sum(len(message.text) for message in messages)
        return len(messages) > _SMALL_COUNT and total > _SMALL_BYTES

    def _commit(self, entries: list[Dictionary]) -> None:
        forms, stats = build_form_index(entries)
        cascade = Cascade.from_forms(forms, self.settings.coord_crs)
        version = self._version + 1
        snapshot = self.data_dir / f"index-{version}.pkl"
        _write_pickle(snapshot, {"version": version, "forms": forms})
        previous = list(self.store.entries)
        self.store.entries = entries
        try:
            self.store.save()
        except Exception:
            self.store.entries = previous
            snapshot.unlink(missing_ok=True)
            raise
        self._version = version
        self._snapshot_file = snapshot
        self._stats = stats
        self._cascade = cascade
        _cleanup_snapshots(self.data_dir, version)

    def _install(self, entries: list[Dictionary]) -> Cascade:
        forms, stats = build_form_index(entries)
        cascade = Cascade.from_forms(forms, self.settings.coord_crs)
        version = self._version + 1
        snapshot = self.data_dir / f"index-{version}.pkl"
        _write_pickle(snapshot, {"version": version, "forms": forms})
        self._version = version
        self._snapshot_file = snapshot
        self._stats = stats
        _cleanup_snapshots(self.data_dir, version)
        return cascade

    def _public(self, entry: Dictionary) -> dict:
        stats = self._stats.get(entry.id, {"word_count": len(entry.words), "form_count": 0})
        return {
            "id": entry.id,
            "name": entry.name,
            "language": entry.language,
            "tag": entry.tag,
            "words": list(entry.words),
            "word_count": stats["word_count"],
            "form_count": stats["form_count"],
        }


def group_findings(message_id: str, findings: list[Finding]) -> dict | None:
    ordered = sorted(findings, key=lambda item: (item.start, item.end, item.kind, item.name))
    tags: dict[str, list[dict]] = {}
    entities: dict[str, list[dict]] = {}
    seen_tags: set[tuple] = set()
    seen_entities: set[tuple] = set()
    for finding in ordered:
        if finding.kind == "tag":
            key = (finding.name, finding.start, finding.end, finding.payload.get("lemma"))
            if key in seen_tags:
                continue
            seen_tags.add(key)
            tags.setdefault(finding.name, []).append(
                {
                    "text": finding.text,
                    "lemma": finding.payload.get("lemma", ""),
                    "start": finding.start,
                    "end": finding.end,
                }
            )
            continue
        key = (finding.name, finding.start, finding.end, finding.text)
        if key in seen_entities:
            continue
        seen_entities.add(key)
        entities.setdefault(finding.name, []).append(_entity_match(finding))
    if not tags and not entities:
        return None
    result: dict = {"id": message_id}
    if tags:
        result["tags"] = [{"tag": name, "matches": matches} for name, matches in tags.items()]
    if entities:
        result["entities"] = [{"type": name, "matches": matches} for name, matches in entities.items()]
    return result


def _entity_match(finding: Finding) -> dict:
    if finding.name == "coordinates":
        return {
            "text": finding.text,
            "format": finding.payload.get("format", ""),
            "lat": finding.payload.get("lat"),
            "lon": finding.payload.get("lon"),
            "start": finding.start,
            "end": finding.end,
        }
    payload = {"text": finding.text, "start": finding.start, "end": finding.end}
    payload.update(finding.payload)
    return payload


def analyze_chunk(snapshot_path: str, pairs: list[tuple[str, str]], coord_crs: str) -> list[dict]:
    cascade = _load_worker_cascade(snapshot_path, coord_crs)
    messages = [Message(message_id, text) for message_id, text in pairs]
    return cascade.analyze_many(messages)


def _load_worker_cascade(snapshot_path: str, coord_crs: str) -> Cascade:
    if _worker_cache["path"] == snapshot_path and _worker_cache["key"] == coord_crs:
        return _worker_cache["cascade"]  # type: ignore[return-value]
    with open(snapshot_path, "rb") as handle:
        data = pickle.load(handle)
    cascade = Cascade.from_forms(data["forms"], coord_crs)
    _worker_cache["path"] = snapshot_path
    _worker_cache["key"] = coord_crs
    _worker_cache["cascade"] = cascade
    return cascade


def _chunks(pairs: list[tuple[str, str]], workers: int) -> list[list[tuple[str, str]]]:
    count = max(1, min(workers, len(pairs)))
    size = math.ceil(len(pairs) / count)
    return [pairs[index : index + size] for index in range(0, len(pairs), size)]


def _write_pickle(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(path)


def _cleanup_snapshots(data_dir: Path, current: int, keep: int = 20) -> None:
    for path in data_dir.glob("index-*.pkl"):
        suffix = path.stem.removeprefix("index-")
        try:
            version = int(suffix)
        except ValueError:
            continue
        if version < current - keep:
            path.unlink(missing_ok=True)
