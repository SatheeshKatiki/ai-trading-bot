"""Append-only research store: RAW / NORMALIZED / DERIVED / EVENTS.

RESEARCH INFRASTRUCTURE. Never imported by production code.

Design (Phase 12 sec14, sec32)
------------------------------
* **Append-only.** Writers open in ``"a"`` mode and never seek. There is no
  update or delete path in this module, by construction rather than by
  convention.
* **RAW is immutable.** The broker payload is written verbatim, once, with a
  content hash. Nothing in this package rewrites it. :func:`verify_partition`
  re-checks those hashes so tampering is detectable.
* **Partitioned by layer / instrument / session date.** A day's collection is
  one file per layer, so a frozen dataset is a directory copy and a resumed
  run appends without touching what is already there.
* **JSONL, not a database.** A research dataset that must survive months and
  be auditable by hand is better as newline-delimited JSON with a manifest
  than as a binary store needing this exact code to read.

Layout::

    research_data/
      raw/<instrument>/<session_date>/chain.jsonl        broker payloads, verbatim
      normalized/<instrument>/<session_date>/quotes.jsonl  OptionQuote records
      derived/<instrument>/<session_date>/underlying.jsonl UnderlyingSnapshot
      events/<instrument>/<session_date>/signals.jsonl     SignalEvent
      manifest/<instrument>/<session_date>.json            checksums + counts
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .schema import (RECORDER_VERSION, SCHEMA_VERSION, observation_key,
                     record_checksum)

LAYERS = ("raw", "normalized", "derived", "events")

#: Default root, alongside the other research artefacts and gitignored.
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "research_data"

_WRITE_LOCK = threading.Lock()


def _as_dict(obj: Any) -> Dict[str, Any]:
    if is_dataclass(obj):
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return asdict(obj)
    if isinstance(obj, dict):
        return obj
    raise TypeError(f"cannot serialise {type(obj).__name__}")


class ResearchStore:
    """Append-only store. One instance per collector process."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or DEFAULT_ROOT)

    # -- paths ---------------------------------------------------------
    def partition(self, layer: str, instrument: str, session_date: str) -> Path:
        if layer not in LAYERS:
            raise ValueError(f"unknown layer {layer!r}; expected one of {LAYERS}")
        return self.root / layer / instrument / session_date

    def _file(self, layer: str, instrument: str, session_date: str,
              name: str) -> Path:
        d = self.partition(layer, instrument, session_date)
        d.mkdir(parents=True, exist_ok=True)
        return d / name

    def manifest_path(self, instrument: str, session_date: str) -> Path:
        d = self.root / "manifest" / instrument
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{session_date}.json"

    # -- writing -------------------------------------------------------
    def append(self, layer: str, instrument: str, session_date: str,
               name: str, records: Iterable[Any]) -> int:
        """Append records durably. Returns how many were written.

        Thread-safe and crash-tolerant. Two properties matter (Phase 13 sec18):

        * **Whole lines.** Each record is serialised completely before it is
          written, so a reader never sees half a JSON object except as a
          truncated final line, which :meth:`read` skips.
        * **Durable.** The handle is flushed and ``fsync``-ed before it
          closes. Without that, a power loss can lose minutes of quotes that
          the process already reported as written -- the recorder would claim
          coverage it does not have, which is worse than a visible gap.
        """
        path = self._file(layer, instrument, session_date, name)
        written = 0
        with _WRITE_LOCK:
            with path.open("a", encoding="utf-8") as fh:
                for rec in records:
                    payload = _as_dict(rec)
                    payload.setdefault("schema_version", SCHEMA_VERSION)
                    payload["_checksum"] = record_checksum(payload)
                    fh.write(json.dumps(payload, default=str,
                                        separators=(",", ":")) + "\n")
                    written += 1
                if written:
                    fh.flush()
                    os.fsync(fh.fileno())
        return written

    # -- deduplication (sec6) ------------------------------------------
    def _key_index_path(self, instrument: str, session_date: str) -> Path:
        d = self.root / "index" / instrument
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{session_date}.keys"

    def load_keys(self, instrument: str, session_date: str) -> set:
        """Every observation key already stored for this session.

        Read from the sidecar index when present, and otherwise rebuilt from
        the normalized layer itself. The rebuild is what makes a restart safe
        without trusting the index file: the data is the source of truth.
        """
        path = self._key_index_path(instrument, session_date)
        keys = set()
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                keys = {ln.strip() for ln in fh if ln.strip()}
        for rec in self.read("normalized", instrument, session_date,
                             "quotes.jsonl"):
            try:
                keys.add(observation_key(
                    rec.get("underlying"), rec.get("event_time"),
                    rec.get("option_symbol"), rec.get("expiry"),
                    rec.get("strike") or 0.0, rec.get("option_type")))
            except (TypeError, ValueError):
                continue
        return keys

    def append_deduped(self, layer: str, instrument: str, session_date: str,
                       name: str, records: Iterable[Any],
                       seen: Optional[set] = None):
        """Append only records whose observation key is new.

        Returns ``(written, skipped, seen)``. ``seen`` is carried by the
        caller across the session so the common path costs no disk reads.
        Re-running a snapshot for an instant already recorded is therefore a
        no-op rather than a second vote for that instant.
        """
        if seen is None:
            seen = self.load_keys(instrument, session_date)
        fresh, skipped = [], 0
        new_keys = []
        for rec in records:
            key = (rec.observation_key() if hasattr(rec, "observation_key")
                   else None)
            if key is None:
                fresh.append(rec)
                continue
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            new_keys.append(key)
            fresh.append(rec)
        written = self.append(layer, instrument, session_date, name, fresh) if fresh else 0
        if new_keys:
            kp = self._key_index_path(instrument, session_date)
            with _WRITE_LOCK:
                with kp.open("a", encoding="utf-8") as fh:
                    fh.write("\n".join(new_keys) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
        return written, skipped, seen

    # -- checkpoints (sec21) -------------------------------------------
    def checkpoint_path(self, instrument: str, session_date: str) -> Path:
        d = self.root / "checkpoint" / instrument
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{session_date}.json"

    def write_checkpoint(self, instrument: str, session_date: str,
                         state: Dict[str, Any]) -> Path:
        """Record progress so a restart resumes instead of starting over.

        Written atomically via a temp file and ``os.replace``: a checkpoint
        half-written by a crash would be worse than none, because the reader
        cannot tell it is truncated.
        """
        path = self.checkpoint_path(instrument, session_date)
        body = dict(state)
        body.update({"instrument": instrument, "session_date": session_date,
                     "recorder_version": RECORDER_VERSION,
                     "updated_at": datetime.now().isoformat(timespec="seconds")})
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(body, fh, indent=2, default=str)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        return path

    def read_checkpoint(self, instrument: str,
                        session_date: str) -> Optional[Dict[str, Any]]:
        path = self.checkpoint_path(instrument, session_date)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None


    def append_raw(self, instrument: str, session_date: str,
                   payload: Dict[str, Any], *, endpoint: str,
                   retrieved_at: str) -> int:
        """Write a broker payload verbatim. RAW is never re-derived."""
        envelope = {
            "retrieved_at": retrieved_at,
            "endpoint": endpoint,
            "instrument": instrument,
            "session_date": session_date,
            "schema_version": SCHEMA_VERSION,
            "payload": payload,
        }
        return self.append("raw", instrument, session_date, "chain.jsonl",
                           [envelope])

    # -- reading -------------------------------------------------------
    def read(self, layer: str, instrument: str, session_date: str,
             name: str) -> Iterator[Dict[str, Any]]:
        path = self.partition(layer, instrument, session_date) / name
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # A truncated final line from a killed process. Skipping
                    # is correct: the record was never completely observed.
                    continue

    def sessions(self, layer: str, instrument: str) -> List[str]:
        base = self.root / layer / instrument
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    def instruments(self, layer: str = "normalized") -> List[str]:
        base = self.root / layer
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    # -- integrity (sec32) ---------------------------------------------
    def write_manifest(self, instrument: str, session_date: str) -> Dict[str, Any]:
        """Checksum every partition file and record counts. Written at the end
        of a session; re-runnable."""
        entries = {}
        for layer in LAYERS:
            d = self.partition(layer, instrument, session_date)
            if not d.exists():
                continue
            for f in sorted(d.iterdir()):
                if not f.is_file():
                    continue
                import hashlib
                h = hashlib.sha256()
                lines = 0
                with f.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        h.update(chunk)
                        lines += chunk.count(b"\n")
                entries[f"{layer}/{f.name}"] = {
                    "sha256": h.hexdigest(), "lines": lines,
                    "bytes": f.stat().st_size,
                }
        manifest = {
            "instrument": instrument, "session_date": session_date,
            "schema_version": SCHEMA_VERSION,
            "written_at": datetime.now().isoformat(timespec="seconds"),
            "files": entries,
        }
        self.manifest_path(instrument, session_date).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def verify_partition(self, instrument: str, session_date: str) -> Dict[str, Any]:
        """Re-hash every file and compare against the manifest.

        Returns ``{"ok": bool, "mismatches": [...], "missing": [...]}``. This
        is how a frozen dataset proves it has not been rewritten.
        """
        mp = self.manifest_path(instrument, session_date)
        if not mp.exists():
            return {"ok": False, "error": "no manifest", "mismatches": [], "missing": []}
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        mismatches, missing = [], []
        import hashlib
        for rel, meta in manifest.get("files", {}).items():
            layer, name = rel.split("/", 1)
            f = self.partition(layer, instrument, session_date) / name
            if not f.exists():
                missing.append(rel)
                continue
            h = hashlib.sha256()
            with f.open("rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            if h.hexdigest() != meta["sha256"]:
                mismatches.append(rel)
        return {"ok": not mismatches and not missing,
                "mismatches": mismatches, "missing": missing,
                "files": len(manifest.get("files", {}))}


__all__ = ["ResearchStore", "LAYERS", "DEFAULT_ROOT"]
