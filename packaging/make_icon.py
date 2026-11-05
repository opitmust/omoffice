"""Program simgesini üretir: python packaging/make_icon.py  ->  omoffice/omoffice.ico"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = (16, 24, 32, 48, 64, 128, 256)


def frame(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    r = size * 0.2
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2F5DA8"))
    p.drawRoundedRect(QRectF(0, 0, size, size), r, r)
    font = QFont("Segoe UI", weight=QFont.Weight.Bold)
    font.setPixelSize(round(size * 0.74))
    p.setFont(font)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "O")
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 - yazı tipleri için gerekli
    frames = [(s, frame(s)) for s in SIZES]
    offset = 6 + 16 * len(frames)
    out = struct.pack("<HHH", 0, 1, len(frames))
    for s, data in frames:
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out += b"".join(d for _, d in frames)
    with open(os.path.join(ROOT, "omoffice", "omoffice.ico"), "wb") as f:
        f.write(out)


if __name__ == "__main__":
    main()
