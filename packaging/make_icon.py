"""Program simgesini ve logoyu üretir: python packaging/make_icon.py

Çıktılar:
  omoffice/omoffice.ico   (16–256 px, program ve kurulum simgesi)
  omoffice/omoffice.png   (256 px, uygulama içi logo)
  docs/logo.png           (512 px, README)

Amblem: şeffaf zeminde indigo bir daire, ortasında çerçevesiz beyaz belge; hafif cam efekti
(üstte yumuşak ışık, altta mavi yansıma, ince ışıklı kenar).
"""
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

DISC_TOP, DISC_BOTTOM = QColor("#5468E6"), QColor("#3F2FC4")   # daire: maviden indigoya
GLOW = (140, 200, 255)                                          # alttaki yansıma
LINE = QColor("#4A3FD6")                                        # sayfadaki satırlar
FOLD = QColor(200, 206, 250, 230)                               # sayfanın kıvrık köşesi


def _page_path(x0, y0, w, h, fold):
    p = QPainterPath()
    p.moveTo(x0, y0)
    p.lineTo(x0 + w - fold, y0)
    p.lineTo(x0 + w, y0 + fold)
    p.lineTo(x0 + w, y0 + h)
    p.lineTo(x0, y0 + h)
    p.closeSubpath()
    return p


def _fold_path(x0, y0, w, fold):
    p = QPainterPath()
    p.moveTo(x0 + w - fold, y0)
    p.lineTo(x0 + w - fold, y0 + fold)
    p.lineTo(x0 + w, y0 + fold)
    p.closeSubpath()
    return p


def draw(s):
    """s × s piksellik amblem (küçük boyutlar için icon_image kullanın)."""
    img = QImage(s, s, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QPointF(s * 0.5, s * 0.5)
    R = s * 0.44
    disc = QPainterPath()
    disc.addEllipse(c, R, R)

    # daire
    g = QLinearGradient(c.x() - R, c.y() - R, c.x() + R * 0.6, c.y() + R)
    g.setColorAt(0, DISC_TOP)
    g.setColorAt(1, DISC_BOTTOM)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(disc)
    glow = QRadialGradient(QPointF(c.x(), c.y() + R * 0.9), R * 1.1)
    glow.setColorAt(0, QColor(*GLOW, 70))
    glow.setColorAt(1, QColor(*GLOW, 0))
    p.setBrush(glow)
    p.drawPath(disc)

    # buzlu beyaz sayfa
    w, h = s * 0.34, s * 0.44
    x0, y0 = c.x() - w / 2, c.y() - h / 2
    fold = w * 0.3
    pg = QLinearGradient(x0, y0, x0 + w, y0 + h)
    pg.setColorAt(0, QColor(255, 255, 255, 250))
    pg.setColorAt(1, QColor(236, 240, 255, 240))
    p.setBrush(pg)
    p.drawPath(_page_path(x0, y0, w, h, fold))
    p.setBrush(FOLD)
    p.drawPath(_fold_path(x0, y0, w, fold))
    pen = QPen(LINE, h * 0.055)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(pen)
    for i, f in enumerate((0.7, 0.7, 0.7, 0.45)):
        y = y0 + h * (0.32 + i * 0.15)
        p.drawLine(QPointF(x0 + w * 0.16, y), QPointF(x0 + w * (0.16 + f * 0.72), y))

    # üstte yumuşak cam ışığı
    hl = QPainterPath()
    hl.addEllipse(QRectF(c.x() - R * 0.86, c.y() - R * 0.97, R * 1.72, R * 1.05))
    hl = hl.intersected(disc)
    lg = QLinearGradient(0, c.y() - R, 0, c.y() + R * 0.05)
    lg.setColorAt(0, QColor(255, 255, 255, 65))
    lg.setColorAt(0.55, QColor(255, 255, 255, 12))
    lg.setColorAt(1, QColor(255, 255, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(lg)
    p.drawPath(hl)

    # ince ışıklı kenar
    rim = QLinearGradient(c.x(), c.y() - R, c.x(), c.y() + R)
    rim.setColorAt(0, QColor(255, 255, 255, 120))
    rim.setColorAt(0.5, QColor(255, 255, 255, 20))
    rim.setColorAt(1, QColor(255, 255, 255, 50))
    p.setPen(QPen(rim, max(1.0, s * 0.012)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, R - s * 0.006, R - s * 0.006)
    p.end()
    return img


def icon_image(size):
    """Küçük boyutlar dört kat büyük çizilip yumuşakça küçültülür (ince ayrıntılar bulanık leke olmasın)."""
    if size >= 128:
        return draw(size)
    big = draw(size * 4)
    return big.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)


def _png(img):
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def main():
    app = QGuiApplication(sys.argv)  # noqa: F841 - QImage/QPainter için gerekli
    frames = [(s, _png(icon_image(s))) for s in SIZES]
    offset = 6 + 16 * len(frames)
    out = struct.pack("<HHH", 0, 1, len(frames))
    for s, data in frames:
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out += b"".join(d for _, d in frames)
    with open(os.path.join(ROOT, "omoffice", "omoffice.ico"), "wb") as f:
        f.write(out)
    icon_image(256).save(os.path.join(ROOT, "omoffice", "omoffice.png"))
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    draw(512).save(os.path.join(ROOT, "docs", "logo.png"))
    print("omoffice.ico, omoffice.png, docs/logo.png yazıldı")


if __name__ == "__main__":
    main()
