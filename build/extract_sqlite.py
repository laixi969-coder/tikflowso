"""Extract only the pinned runtime library from the verified conda-forge artifact."""
import ctypes
import io
from pathlib import Path
import tarfile
import zipfile

with zipfile.ZipFile("/tmp/sqlite.conda") as package:
    member, = (entry for entry in package.namelist() if entry.startswith("pkg-") and entry.endswith(".tar.zst"))
    frame = package.read(member)
zstd = ctypes.CDLL("libzstd.so.1")
zstd.ZSTD_decompress.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t)
zstd.ZSTD_decompress.restype = ctypes.c_size_t
buffer = ctypes.create_string_buffer(32 * 1024 * 1024)
size = zstd.ZSTD_decompress(buffer, len(buffer), frame, len(frame))
if size > len(buffer):
    raise ValueError("SQLite package did not decompress within its expected size")
with tarfile.open(fileobj=io.BytesIO(buffer.raw[:size])) as archive:
    library, = (entry for entry in archive if entry.isfile() and entry.name.startswith("lib/libsqlite3.so."))
    Path("/tmp/libsqlite3.so.0").write_bytes(archive.extractfile(library).read())

