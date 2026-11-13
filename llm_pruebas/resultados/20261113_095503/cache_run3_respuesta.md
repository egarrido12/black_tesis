```python
"""Caching of formatted files with feature-based invalidation."""

import hashlib
import os
import pickle
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from platformdirs import user_cache_dir

from _black_version import version as __version__
from black.mode import Mode
from black.output import err

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


class FileData(NamedTuple):
    st_mtime: float
    st_size: int
    hash: str


# The cache is pickled as plain tuples because that is faster than NamedTuples.
_RawFileData = dict[str, tuple[float, int, str]]

# Errors that mean "the cache file is unusable"; the next write will replace it.
_CACHE_READ_ERRORS = (
    pickle.UnpicklingError,
    EOFError,
    ValueError,
    IndexError,
    PermissionError,
)


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

        return cls(mode, cache_file, cls._load_file_data(cache_file))

    @staticmethod
    def _load_file_data(cache_file: Path) -> dict[str, FileData]:
        """Load the file data stored in `cache_file`.

        Return an empty mapping if the contents are malformed.
        """
        with cache_file.open("rb") as fobj:
            try:
                data: _RawFileData = pickle.load(fobj)
                return {k: FileData(*v) for k, v in data.items()}
            except _CACHE_READ_ERRORS:
                return {}

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
        res_src = source.resolve()
        old = self.file_data.get(str(res_src))
        if old is None:
            return True

        st = res_src.stat()
        if st.st_size != old.st_size:
            return True
        if st.st_mtime != old.st_mtime:
            return Cache.hash_digest(res_src) != old.hash
        return False

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
            self._dump_file_data()
        except OSError:
            pass

    def _dump_file_data(self) -> None:
        """Atomically replace the cache file with the current `file_data`."""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=str(self.cache_file.parent), delete=False
        ) as f:
            # We store raw tuples in the cache because it's faster.
            data: _RawFileData = {k: (*v,) for k, v in self.file_data.items()}
            pickle.dump(data, f, protocol=4)
        os.replace(f.name, self.cache_file)
```

## Refactorizaciones aplicadas

- **Extract Method** – `Cache.read` → nuevo `Cache._load_file_data(cache_file)`. Motivo: separa el cómo se deserializa el archivo (abrir, `pickle.load`, construir `FileData`) del flujo de decisión de `read` (¿existe?, ¿error de OS?). `read` queda como una secuencia corta de guardas. Si el contenido está mal formado, el helper devuelve `{}` y `read` crea un `Cache` con `file_data` vacío, igual que antes. La llamada a `open()` sigue fuera del `try`, así que un fallo al abrir se propaga como antes.

- **Extract Method** – `Cache.write` → nuevo `Cache._dump_file_data()`. Motivo: aísla la escritura atómica (directorio, archivo temporal, `pickle.dump`, `os.replace`) de la actualización del estado en memoria. El `try/except OSError` queda en `write`, que sigue ocultando los errores de E/S.

- **Replace Magic Literal / Introduce Constant** – la tupla de excepciones de `read` pasa a `_CACHE_READ_ERRORS`. Motivo: nombra su significado («el archivo de caché es inutilizable») y saca ruido del cuerpo del método.

- **Introduce Type Alias** – `dict[str, tuple[float, int, str]]` (repetido en `read` y `write`) pasa a `_RawFileData`. Motivo: evita duplicar el tipo y documenta que es el formato de serialización en disco.

- **Inline Temp / Remove Assignment** – `get_cache_dir`: se elimina la asignación `cache_dir = cache_dir / __version__` seguida de `return cache_dir`, y se devuelve la expresión directamente. Se mantiene la evaluación de `default_cache_dir` como antes, para no cambiar el momento en que se llama a `user_cache_dir`.

- **Simplify Conditional / Consolidate Conditional** – `Cache.is_changed`: el `if` anidado sobre el hash (`if new_hash != old.hash: return True` y luego `return False`) pasa a `return Cache.hash_digest(res_src) != old.hash`. Se elimina la variable `new_hash` y el comportamiento es el mismo.

- **Rename Variable** – `Cache.get_file_data`: la variable local `hash`, que ocultaba el built-in, pasa a `digest`. El campo `FileData.hash` es público y no se toca.

- **Replace Argument Construction** – `Cache.write`: `update(**{...})` pasa a `update({...})`. Motivo: es más directo y no depende de que las claves sean identificadores válidos como `kwargs`. El resultado es idéntico.

Los nombres y firmas públicos (`FileData`, `get_cache_dir`, `CACHE_DIR`, `get_cache_file`, `Cache.read`, `hash_digest`, `get_file_data`, `is_changed`, `filtered_cached`, `write`) no cambian. Los helpers nuevos son privados (prefijo `_`). Se mantienen los nombres de módulo que otros módulos y tests pueden parchear (`CACHE_DIR`, `user_cache_dir`, `Cache.hash_digest`), y el código sigue siendo compatible con Python 3.10+.