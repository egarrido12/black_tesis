"""Caching of formatted files with feature-based invalidation."""

import hashlib
import os
import pickle
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NamedTuple

from platformdirs import user_cache_dir

from _black_version import version as __version__
from black.mode import Mode
from black.output import err

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


# Cache entries are stored on disk as raw tuples because it's faster than
# pickling `FileData` instances.
_RawFileData = tuple[float, int, str]

_PICKLE_PROTOCOL: Final = 4

# Errors that mean the cache file is unusable and should be treated as empty.
_UNREADABLE_CACHE_ERRORS: Final = (
    pickle.UnpicklingError,
    EOFError,
    ValueError,
    IndexError,
    PermissionError,
)


class FileData(NamedTuple):
    st_mtime: float
    st_size: int
    hash: str


def get_cache_dir(cache_dir: Path | None = None) -> Path:
    """Get the cache directory used by black.

    Users can customize this directory directly or, on all systems, using the
    `BLACK_CACHE_DIR` environment variable. By default, the cache directory is the
    user cache directory under the black application.

    This result is immediately set to a constant `black.cache.CACHE_DIR` as to avoid
    repeated calls.
    """
    # NOTE: Function mostly exists as a clean way to test getting the cache directory.
    default_cache_dir = user_cache_dir("black")
    if cache_dir is None:
        cache_dir = Path(os.environ.get("BLACK_CACHE_DIR", default_cache_dir))
    return cache_dir / __version__


CACHE_DIR = get_cache_dir()


def get_cache_file(mode: Mode, cache_dir: Path) -> Path:
    return cache_dir / f"cache.{mode.get_cache_key()}.pickle"


def _load_file_data(cache_file: Path) -> dict[str, FileData] | None:
    """Load the entries stored in `cache_file`.

    Return None if the file is not well-formed.
    """
    with cache_file.open("rb") as fobj:
        try:
            raw_data: dict[str, _RawFileData] = pickle.load(fobj)
            return {path: FileData(*values) for path, values in raw_data.items()}
        except _UNREADABLE_CACHE_ERRORS:
            return None


@dataclass
class Cache:
    mode: Mode
    cache_file: Path
    file_data: dict[str, FileData] = field(default_factory=dict)

    @classmethod
    def read(cls, mode: Mode, cache_dir: Path = CACHE_DIR) -> Self:
        """Read the cache if it exists and is well-formed.

        If it is not well-formed, the call to write later should
        resolve the issue.
        """
        cache_file = get_cache_file(mode, cache_dir)
        try:
            exists = cache_file.exists()
        except OSError as e:
            # Likely file too long; see #4172 and #4174
            err(f"Unable to read cache file {cache_file} due to {e}")
            return cls(mode, cache_file)
        if not exists:
            return cls(mode, cache_file)

        file_data = _load_file_data(cache_file)
        if file_data is None:
            return cls(mode, cache_file)
        return cls(mode, cache_file, file_data)

    @staticmethod
    def hash_digest(path: Path) -> str:
        """Return hash digest for path."""
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def get_file_data(path: Path) -> FileData:
        """Return file data for path."""
        stat = path.stat()
        digest = Cache.hash_digest(path)
        return FileData(stat.st_mtime, stat.st_size, digest)

    def is_changed(self, source: Path) -> bool:
        """Check if source has changed compared to cached version."""
        resolved_source = source.resolve()
        cached = self.file_data.get(str(resolved_source))
        if cached is None:
            return True

        current = resolved_source.stat()
        if current.st_size != cached.st_size:
            return True
        if current.st_mtime == cached.st_mtime:
            return False
        # The mtime differs, so only the content can tell whether it really changed.
        return Cache.hash_digest(resolved_source) != cached.hash

    def filtered_cached(self, sources: Iterable[Path]) -> tuple[set[Path], set[Path]]:
        """Split an iterable of paths in `sources` into two sets.

        The first contains paths of files that modified on disk or are not in the
        cache. The other contains paths to non-modified files.
        """
        changed: set[Path] = set()
        done: set[Path] = set()
        for src in sources:
            if self.is_changed(src):
                changed.add(src)
            else:
                done.add(src)
        return changed, done

    def write(self, sources: Iterable[Path]) -> None:
        """Update the cache file data and write a new cache file."""
        self.file_data.update({
            str(src.resolve()): Cache.get_file_data(src) for src in sources
        })
        try:
            self._dump_to_disk()
        except OSError:
            pass

    def _dump_to_disk(self) -> None:
        """Atomically replace the cache file with the current `file_data`."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=str(self.cache_file.parent), delete=False
        ) as f:
            raw_data: dict[str, _RawFileData] = {
                path: tuple(data) for path, data in self.file_data.items()
            }
            pickle.dump(raw_data, f, protocol=_PICKLE_PROTOCOL)
        os.replace(f.name, self.cache_file)
