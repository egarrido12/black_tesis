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


def _read_file_data(cache_file: Path) -> dict[str, FileData]:
    """Load the file data stored in `cache_file`.

    Return an empty mapping if the contents are malformed, so that the next call
    to `Cache.write` replaces the broken file.
    """
    with cache_file.open("rb") as fobj:
        try:
            data: dict[str, tuple[float, int, str]] = pickle.load(fobj)
            return {path: FileData(*values) for path, values in data.items()}
        except (
            pickle.UnpicklingError,
            EOFError,
            ValueError,
            IndexError,
            PermissionError,
        ):
            return {}


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

        return cls(mode, cache_file, _read_file_data(cache_file))

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
        resolved = source.resolve()
        cached = self.file_data.get(str(resolved))
        if cached is None:
            return True

        stat = resolved.stat()
        if stat.st_size != cached.st_size:
            return True
        if stat.st_mtime == cached.st_mtime:
            return False
        return Cache.hash_digest(resolved) != cached.hash

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
            data: dict[str, tuple[float, int, str]] = {
                path: tuple(file_data) for path, file_data in self.file_data.items()
            }
            pickle.dump(data, f, protocol=4)
        os.replace(f.name, self.cache_file)
```

## Refactorizaciones aplicadas

- **Extract Method** (`Cache.read` → `_read_file_data`, función privada a nivel de módulo)
  - Se extrajo la apertura del fichero y el `pickle.load`, junto con la conversión a `FileData` y el manejo de los errores de corrupción.
  - Motivo: `read` mezclaba comprobar si el fichero existe con deserializar y tolerar datos corruptos. Ahora `read` solo decide qué caché devolver.
  - El `open` sigue fuera del `try`, así que un `PermissionError` al abrir se propaga como antes.

- **Consolidate Duplicate Conditional Fragments / Replace Magic Return** (`Cache.read`)
  - Los tres `return cls(mode, cache_file)` del camino de datos corruptos se reducen a un único punto de retorno.
  - `_read_file_data` devuelve `{}` en caso de fallo, que equivale al `default_factory=dict`.

- **Extract Method** (`Cache.write` → `Cache._dump_file_data`, método privado)
  - Se aisló la escritura atómica (crear directorio, fichero temporal, `pickle.dump`, `os.replace`). `write` queda como actualizar los datos y capturar `OSError`.
  - La actualización de `file_data` sigue fuera del `try`, igual que antes.

- **Replace Loop/Expression Simplification** (`Cache.write`)
  - `update(**{...})` pasa a `update({...})`: se quita el desempaquetado innecesario de kwargs, con el mismo resultado.
  - `(*v,)` pasa a `tuple(file_data)`, que produce la misma tupla plana.

- **Rename Variable**
  - En `get_file_data`, `hash` pasa a `digest`, porque ocultaba el builtin `hash`.
  - En `is_changed`, `old`, `st` y `res_src` pasan a `cached`, `stat` y `resolved`.
  - En `write`, `k`, `v` pasan a `path`, `file_data`.
  - Los parámetros públicos (`source`, `sources`, `mode`, `cache_dir`) no cambian.

- **Replace Nested Conditional with Guard Clauses** (`Cache.is_changed`)
  - Se invirtió la comparación de `st_mtime` para devolver `False` pronto y terminar con `return Cache.hash_digest(resolved) != cached.hash`. Así se elimina el `if` anidado y la variable temporal `new_hash`.
  - Esto es equivalente: solo se calcula el hash si el mtime difiere.

- **Inline Variable** (`get_cache_dir`)
  - Se eliminó la reasignación seguida de `return` (`cache_dir = cache_dir / __version__; return cache_dir`) y ahora se devuelve la expresión directamente.
  - `user_cache_dir("black")` se sigue evaluando siempre, para mantener el comportamiento observable, por ejemplo con mocks en los tests.

- **Remove Dead Code / Tidy** (`hash_digest`, `get_file_data`)
  - Se quitaron las líneas en blanco entre el docstring y el cuerpo.