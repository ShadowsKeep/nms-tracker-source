"""
Read-only No Man's Sky save reader.

Safety rules this module follows:
  * It never opens a save for writing. The file is read into memory in one call
    (shared read, so it works while the game is running) and then closed.
  * It never touches the running game.

Format (PC, since 2019): the file is a sequence of chunks
    magic 0xFEEDA1E5 | compressed size u32 | uncompressed size u32 | 4 bytes padding | LZ4 block
whose concatenated output is one JSON document with obfuscated 3-character keys.
Older saves are plain JSON. Keys are translated with the community mapping file
(MBINCompiler's mapping.json), bundled as app/data/save_mapping.json.
"""
import json
import os
import struct
import sys
from pathlib import Path

MAGIC = 0xFEEDA1E5


class SaveError(Exception):
    pass


# ── LZ4 block decompression (pure Python, no dependency) ────────────────────
def lz4_block_decompress(src: bytes, expected: int) -> bytes:
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break  # last sequence has literals only
        offset = src[i] | (src[i + 1] << 8); i += 2
        if offset == 0 or offset > len(out):
            raise SaveError('corrupt LZ4 data (bad offset)')
        mlen = token & 15
        if mlen == 15:
            while True:
                b = src[i]; i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(out) - offset
        if offset >= mlen:
            out += out[start:start + mlen]
        else:  # overlapping copy repeats the pattern
            for k in range(mlen):
                out.append(out[start + k])
    if expected and len(out) != expected:
        raise SaveError(f'LZ4 size mismatch ({len(out)} != {expected})')
    return bytes(out)


def decode_bytes(raw: bytes) -> str:
    """Save file bytes -> JSON text."""
    if raw[:1] == b'{':
        return raw.decode('utf-8', errors='replace').rstrip('\x00')
    chunks, pos = [], 0
    while pos + 16 <= len(raw):
        magic, csize, usize, _pad = struct.unpack_from('<IIII', raw, pos)
        if magic != MAGIC:
            raise SaveError('not a No Man\'s Sky save (bad chunk header)')
        pos += 16
        chunks.append(lz4_block_decompress(raw[pos:pos + csize], usize))
        pos += csize
    if not chunks:
        raise SaveError('empty save file')
    return b''.join(chunks).decode('utf-8', errors='replace').rstrip('\x00')


# ── key de-obfuscation ──────────────────────────────────────────────────────
def _mapping_file() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'app' / 'data' / 'save_mapping.json'  # type: ignore[attr-defined]
    return Path(__file__).parent / 'data' / 'save_mapping.json'


_MAPPING = None


def key_mapping() -> dict:
    global _MAPPING
    if _MAPPING is None:
        data = json.loads(_mapping_file().read_text(encoding='utf-8'))
        _MAPPING = {m['Key']: m['Value'] for m in data.get('Mapping', data if isinstance(data, list) else [])}
    return _MAPPING


def translate(node, mapping):
    if isinstance(node, dict):
        return {mapping.get(k, k): translate(v, mapping) for k, v in node.items()}
    if isinstance(node, list):
        return [translate(v, mapping) for v in node]
    return node


def load(path) -> dict:
    """Read and fully decode a save. Opens the file read-only."""
    path = Path(path)
    with open(path, 'rb') as f:      # read-only, never 'wb' / 'r+b'
        raw = f.read()
    doc = json.loads(decode_bytes(raw))
    if 'PlayerStateData' not in doc and 'Version' not in doc:
        doc = translate(doc, key_mapping())
    return doc


# ── locating saves ──────────────────────────────────────────────────────────
def save_root() -> Path:
    return Path(os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))) / 'HelloGames' / 'NMS'


def find_saves():
    """All save files on this PC, newest first. Slot N uses save(2N-1).hg (auto) and save(2N).hg (manual)."""
    out = []
    root = save_root()
    if not root.exists():
        return out
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        for f in folder.glob('save*.hg'):
            digits = ''.join(ch for ch in f.stem if ch.isdigit())
            index = int(digits) if digits else 1
            out.append({
                'path': str(f),
                'account': folder.name,
                'slot': (index + 1) // 2,
                'kind': 'Manual' if index % 2 == 0 else 'Auto',
                'modified': f.stat().st_mtime,
                'size': f.stat().st_size,
            })
    out.sort(key=lambda s: -s['modified'])
    return out
