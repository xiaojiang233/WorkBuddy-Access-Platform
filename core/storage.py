"""Credential and state persistence for the WorkBuddy AstrBot plugin.

Credentials and state are stored as JSON and written atomically (same-directory
temp file plus ``os.replace``).  File permissions are restricted to the owner,
but credentials are intentionally not encrypted.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

_ERR_PARSE = "stored credentials could not be parsed"
_ERR_STATE = "state file could not be parsed"

_CREDENTIAL_FILENAME = "credentials.json"
_STATE_FILENAME = "state.json"


def _atomic_write(directory: Path, target: Path, blob: bytes, prefix: str) -> None:
    """Write ``blob`` to ``target`` via a temp file + ``os.replace``.

    The temp file lives in the same directory (same filesystem) so the replace
    is atomic.  On any failure the temp file is removed and the original target
    is left untouched.
    """
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=str(directory))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(tmp_name, 0o600)
        except OSError:
            pass
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


class CredentialStore:
    """Atomically written, unencrypted credential store."""

    def __init__(
        self,
        data_dir: str | os.PathLike[str],
        master_key: str | None = None,
    ) -> None:
        self._dir = Path(data_dir)
        self._path = self._dir / _CREDENTIAL_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def save(self, credentials: dict) -> None:
        """Atomically persist ``credentials`` as JSON."""
        blob = json.dumps(
            credentials, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        _atomic_write(self._dir, self._path, blob, ".wb-cred-")

    def load(self) -> dict | None:
        """Return the stored credentials, or ``None`` if none are stored."""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            obj = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError(_ERR_PARSE) from None
        if not isinstance(obj, dict):
            raise ValueError(_ERR_PARSE)
        return obj

    def delete(self) -> None:
        """Remove stored credentials; a later ``load`` returns ``None``."""
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass


class StateStore:
    """Small JSON document updated one section at a time, atomically."""

    def __init__(self, data_dir: str | os.PathLike[str]) -> None:
        self._dir = Path(data_dir)
        self._path = self._dir / _STATE_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> dict:
        """Return the state dict; an empty dict if nothing is stored yet."""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        try:
            obj = json.loads(raw)
        except ValueError:
            raise ValueError(_ERR_STATE) from None
        if not isinstance(obj, dict):
            raise ValueError(_ERR_STATE)
        return obj

    def update(self, section: str, value: Any) -> None:
        """Set ``state[section] = value`` and persist atomically."""
        state = self.load()
        state[section] = value
        blob = json.dumps(
            state, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        _atomic_write(self._dir, self._path, blob, ".wb-state-")
