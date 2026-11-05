"""Program simgesini ve logoyu üretir: python packaging/make_icon.py

Çıktılar:
  omoffice/omoffice.ico   (16–256 px, program ve kurulum simgesi)
  omoffice/omoffice.png   (256 px, uygulama içi logo)
  docs/logo.png           (512 px, README)

Amblem: mavi-indigo zeminde açık bir "O" halkası, içinde belge, halkanın açıklığında sarı yazı imleci.
"""
import math
import os
import struct
import sys

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                           QRadialGradient)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

TOP, BOTTOM = QColor("#3E9BFF"), QColor("#5236D6")      # zemin degradesi (mavi → indigo)
CURSOR_A, CURSOR_B = QColor("#FFE27A"), QColor("#FFB800")
LINE = QColor("#4A55E6")                                 # sayfadaki satırlar
FOLD = QColor("#D6DAFF")                                 # sayfanın kıvrık köşesi
RING_END = QColor("#E3E6FF")
PAGE_END = QColor("#F1F3FF")
SHADOW = (20, 16, 90)


def _img(s):
    img = QImage(s, s, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    return img


def _painter(img):
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    return p


def _shadow(p, s, path, dx, dy, blur, alpha, pen=None):
    """Yolun yumuşak gölgesi (küçültüp büyüterek bulanıklaştırılır)."""
    if s < 40:
        return
    img = _img(s)
    q = _painter(img)
    q.translate(dx, dy)
    col = QColor(*SHADOW, alpha)
    if pen is not None:
        pp = QPen(pen)
        pp.setColor(col)
        q.setPen(pp)
        q.setBrush(Qt.BrushStyle.NoBrush)
    else:
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(col)
    q.drawPath(path)
    q.end()
    k = max(2, int(blur))
    smooth = Qt.TransformationMode.SmoothTransformation
    ign = Qt.AspectRatioMode.IgnoreAspectRatio
    img = img.scaled(max(1, s // k), max(1, s // k), ign, smooth)
    img = img.scaled(max(1, s // max(1, k // 2)), max(1, s // max(1, k // 2)), ign, smooth)
    p.drawImage(0, 0, img.scaled(s, s, ign, smooth))


def _background(p, s):
    rect = QRectF(0, 0, s, s)
    rad = s * 0.225
    g = QLinearGradient(0, 0, s * 0.6, s)
    g.setColorAt(0, TOP)
    g.setColorAt(1, BOTTOM)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(rect, rad, rad)
    if s >= 32:
        light = QRadialGradient(QPointF(s * 0.25, s * 0.15), s * 0.75)
        light.setColorAt(0, QColor(255, 255, 255, 60))
        light.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(light)
        p.drawRoundedRect(rect, rad, rad)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 45), max(1.0, s * 0.006)))
        d = s * 0.004
        p.drawRoundedRect(rect.adjusted(d, d, -d, -d), rad, rad)


def _ring(p, s, c, r, width, start, span):
    path = QPainterPath()
    rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    path.arcMoveTo(rect, start)
    path.arcTo(rect, start, span)
    pen = QPen(QColor("#FFFFFF"), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    _shadow(p, s, path, s * 0.012, s * 0.022, s * 0.06, 85, pen)
    g = QLinearGradient(c.x() - r, c.y() - r, c.x() + r, c.y() + r)
    g.setColorAt(0, QColor("#FFFFFF"))
    g.setColorAt(1, RING_END)
    pen.setBrush(QBrush(g))
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def _page(p, s, c, w, h):
    x0, y0 = c.x() - w / 2, c.y() - h / 2
    fold, r = w * 0.3, w * 0.08
    path = QPainterPath()
    path.moveTo(x0 + r, y0)
    path.lineTo(x0 + w - fold, y0)
    path.lineTo(x0 + w, y0 + fold)
    path.lineTo(x0 + w, y0 + h - r)
    path.quadTo(x0 + w, y0 + h, x0 + w - r, y0 + h)
    path.lineTo(x0 + r, y0 + h)
    path.quadTo(x0, y0 + h, x0, y0 + h - r)
    path.lineTo(x0, y0 + r)
    path.quadTo(x0, y0, x0 + r, y0)
    _shadow(p, s, path, s * 0.012, s * 0.022, s * 0.06, 90)
    g = QLinearGradient(x0, y0, x0, y0 + h)
    g.setColorAt(0, QColor("#FFFFFF"))
    g.setColorAt(1, PAGE_END)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)
    corner = QPainterPath()
    corner.moveTo(x0 + w - fold, y0)
    corner.lineTo(x0 + w - fold, y0 + fold - r * 0.6)
    corner.quadTo(x0 + w - fold, y0 + fold, x0 + w - fold + r * 0.6, y0 + fold)
    corner.lineTo(x0 + w, y0 + fold)
    corner.closeSubpath()
    p.setBrush(FOLD)
    p.drawPath(corner)
    if s < 96:
        return  # küçük boyutlarda satırlar bulanık bir lekeye dönüşür
    pen = QPen(LINE, h * 0.065)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for i, f in enumerate((0.42, 0.72, 0.72, 0.5)):
        y = y0 + h * 0.27 + i * h * 0.16
        p.drawLine(QPointF(x0 + w * 0.18, y), QPointF(x0 + w * (0.18 + f * 0.66), y))


def _cursor(p, s, x, y1, y2, width):
    pen = QPen(CURSOR_B, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    path = QPainterPath()
    path.moveTo(x, y1)
    path.lineTo(x, y2)
    _shadow(p, s, path, s * 0.01, s * 0.018, s * 0.05, 80, pen)
    g = QLinearGradient(x, y1, x, y2)
    g.setColorAt(0, CURSOR_A)
    g.setColorAt(1, CURSOR_B)
    pen.setBrush(QBrush(g))
    p.setPen(pen)
    p.drawPath(path)


def draw(s):
    """s × s piksellik amblem."""
    img = _img(s)
    p = _painter(img)
    _background(p, s)
    c = QPointF(s * 0.48, s * 0.52)
    r = s * 0.285
    _ring(p, s, c, r, s * 0.095, 88, 300)          # açıklık 28°–88° (sağ üst)
    _page(p, s, c, s * 0.235, s * 0.3)
    a = math.radians(58)
    x, yc = c.x() + r * math.cos(a), c.y() - r * math.sin(a)
    _cursor(p, s, x, yc - s * 0.1, yc + s * 0.1, s * 0.072)
    p.end()
    return img


def icon_image(size):
    """Küçük boyutlar dört kat büyük çizilip yumuşakça küçültülür."""
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
