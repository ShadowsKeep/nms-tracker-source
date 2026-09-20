"""
Generate app/static/img/icon.ico (multi-size) with no extra dependencies.

Design: a glowing red diamond (the brand mark) over deep space, drawn as vector
shapes at each size so it stays sharp. ICO files may embed PNGs directly, so the
container is written by hand.

Run:  python tools/make_icon.py
"""
import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                         QPolygonF, QRadialGradient)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'app' / 'static' / 'img' / 'icon.ico'
SIZES = (16, 24, 32, 48, 64, 128, 256)
STARS = [(0.18, 0.22, 1.0), (0.80, 0.16, 0.8), (0.86, 0.70, 1.0), (0.14, 0.78, 0.7),
         (0.62, 0.88, 0.6), (0.34, 0.10, 0.6), (0.92, 0.42, 0.5)]


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    s = float(size)

    # rounded deep-space tile
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(0.5, 0.5, s - 1, s - 1), s * 0.2, s * 0.2)
    bg = QLinearGradient(0, 0, 0, s)
    bg.setColorAt(0, QColor('#16203a'))
    bg.setColorAt(1, QColor('#070a13'))
    p.fillPath(tile, bg)
    p.setClipPath(tile)

    if size >= 32:
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, r in STARS:
            p.setBrush(QColor(232, 238, 249, 190))
            rad = max(0.5, s * 0.012 * r)
            p.drawEllipse(QPointF(x * s, y * s), rad, rad)

    # glow
    glow = QRadialGradient(QPointF(s / 2, s / 2), s * 0.5)
    glow.setColorAt(0, QColor(255, 79, 58, 150))
    glow.setColorAt(1, QColor(255, 79, 58, 0))
    p.setBrush(glow)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(QRectF(0, 0, s, s))

    # diamond
    h = s * 0.33
    c = s / 2
    diamond = QPolygonF([QPointF(c, c - h), QPointF(c + h * 0.78, c), QPointF(c, c + h), QPointF(c - h * 0.78, c)])
    body = QLinearGradient(c - h, c - h, c + h, c + h)
    body.setColorAt(0, QColor('#ff8a66'))
    body.setColorAt(0.5, QColor('#ff4f3a'))
    body.setColorAt(1, QColor('#a81e15'))
    p.setBrush(body)
    p.setPen(QPen(QColor(255, 220, 205, 230), max(1.0, s * 0.02)))
    p.drawPolygon(diamond)
    # facet highlight
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 70))
    p.drawPolygon(QPolygonF([QPointF(c, c - h), QPointF(c + h * 0.78, c), QPointF(c, c)]))

    p.setClipping(False)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(90, 110, 160, 200), max(1.0, s * 0.015)))
    p.drawPath(tile)
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, 'PNG')
    buf.close()
    return bytes(data)


def main() -> int:
    images = [(size, png_bytes(render(size))) for size in SIZES]
    header = struct.pack('<HHH', 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, payload = b'', b''
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack('<BBBBHHII', dim, dim, 0, 0, 1, 32, len(png), offset)
        payload += png
        offset += len(png)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(header + entries + payload)
    render(256).save(str(OUT.with_suffix('.png')), 'PNG')
    print(f'Wrote {OUT} ({OUT.stat().st_size} bytes, sizes {SIZES})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
