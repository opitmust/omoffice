"""Tema ve vurgu rengi denetimi: python tests/theme_audit.py <klasör>

Her tema × vurgu rengi için
  * arayüzdeki renk çiftlerinin WCAG kontrast oranını ölçer (metin 4.5:1, simge/kenar 3:1,
    katman ve seçim farkları için daha düşük ama görünür eşikler),
  * ana pencerenin, yan panel sayfalarının ve başlangıç sihirbazının ekran görüntüsünü alır.
THEME AUDIT PASS/FAIL yazar.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OMOFFICE_TEST_DATA", tempfile.mkdtemp(prefix="omoffice_theme_"))

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(col):
    q = QColor(col)
    return 0.2126 * _lin(q.red()) + 0.7152 * _lin(q.green()) + 0.0722 * _lin(q.blue())


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def pairs(t, a, derived):
    """(ad, ön, arka, eşik) — derived: theme.derived(t, a) sonucu."""
    d = derived
    out = []
    for bg in ("panel", "window", "card", "input", "hover", "checked", "menu"):
        out.append((f"metin / {bg}", t["text"], t[bg], 4.5))
    for bg in ("panel", "window", "card", "menu"):
        out.append((f"soluk metin / {bg}", t["muted"], t[bg], 4.5))
    out += [
        ("beyaz yazı / vurgu (üst çubuk, durum çubuğu)", "#FFFFFF", d["bar"], 4.5),
        ("beyaz yazı / Dosya düğmesi", "#FFFFFF", d["file"], 4.5),
        ("beyaz yazı / birincil düğme", "#FFFFFF", d["primary"], 4.5),
        ("soluk beyaz (dosya yolu) / üst çubuk", d["path_text"], d["bar"], 4.5),
        ("seçili ray yazısı / seçili zemin", d["rail_checked_text"], t["checked"], 4.5),
        ("vurgu kenarı / kart", d["accent_ui"], t["card"], 3.0),
        ("vurgu kenarı / panel", d["accent_ui"], t["panel"], 3.0),
        ("vurgu kenarı / pencere", d["accent_ui"], t["window"], 3.0),
        ("cetvel işareti / cetvel", d["accent_ui"], t["ruler_bg"], 3.0),
        ("simge / panel", t["icon"], t["panel"], 3.0),
        ("simge / kart", t["icon"], t["card"], 3.0),
        ("simge / seçili", t["icon"], t["checked"], 3.0),
        ("pasif simge / kart (görünür ama soluk)", t["icon_disabled"], t["card"], 1.8),
        ("giriş kenarı / giriş zemini", t["input_border"], t["input"], 1.6),
        ("onay kutusu kenarı / kart", t["input_border"], t["card"], 1.6),
        ("seçili zemin / kart (seçim görünür)", t["checked"], t["card"], 1.25),
        ("üzerine gelme / kart", t["hover"], t["card"], 1.08),
        ("kenarlık / kart (katmanlar ayrışır)", t["border"], t["card"], 1.15),
        ("kart / pencere (katmanlar ayrışır)", t["card"], t["window"], 1.06),
        ("Dosya düğmesi / üst çubuk (ayrışır)", d["file"], d["bar"], 1.15),
        ("cetvel sayıları / yazı alanı", t["muted"], t["ruler_text"], 3.0),
        ("cetvel sayıları / kenar boşluğu", t["muted"], t["ruler_margin"], 3.0),
        ("cetvel yazı alanı / kenar boşluğu (ayrışır)", t["ruler_text"], t["ruler_margin"], 1.2),
        ("sayfada seçili siyah yazı / seçim zemini", "#000000", d["page_select"], 7.0),
        ("seçim zemini / sayfa (seçim görünür)", d["page_select"], "#FFFFFF", 1.3),
        ("belge alanı / sayfa (beyaz)", t["view_bg"], "#FFFFFF", 1.15),
        ("beyaz yazı / cam üst çubuk (parlak üst)", "#FFFFFF", d["glass_bar_top"], 4.5),
        ("beyaz yazı / cam üst çubuk", "#FFFFFF", d["glass_bar"], 4.5),
        ("soluk beyaz (dosya yolu) / cam üst çubuk", d["path_text"], d["glass_bar"], 4.5),
        ("ray yazısı / cam ray", d["glass_rail_text"], d["glass_rail"], 4.5),
        ("ray yazısı / cam ray (parlak üst)", d["glass_rail_text"], d["glass_rail_top"], 4.5),
        ("seçili ray yazısı / cam seçili zemin", d["glass_checked_text"], d["glass_checked"], 4.5),
        ("simge / cam ray", t["icon"], d["glass_rail"], 3.0),
        ("metin / cam panel", t["text"], d["glass_panel"], 4.5),
        ("metin / cam panel (parlak üst)", t["text"], d["glass_panel_top"], 4.5),
        ("soluk metin / cam panel", t["muted"], d["glass_panel"], 4.5),
    ]
    return out


def audit(out):
    from omoffice import theme
    rows, bad = [], 0
    for tname, t in theme.THEMES.items():
        for aname, a in theme.ACCENTS.items():
            d = theme.derived(t, a)
            for name, fg, bg, need in pairs(t, a, d):
                r = contrast(fg, bg)
                ok = r >= need
                bad += not ok
                rows.append((tname, aname, name, fg, bg, r, need, ok))
    with open(os.path.join(out, "kontrast.txt"), "w", encoding="utf-8") as f:
        for tname, aname, name, fg, bg, r, need, ok in rows:
            f.write(f"{'OK ' if ok else 'KÖTÜ'} {tname:5s} {aname:9s} {r:5.2f} (≥{need}) {name}  {fg} / {bg}\n")
    for tname, aname, name, fg, bg, r, need, ok in rows:
        if not ok:
            print(f"  KÖTÜ {tname:5s} {aname:9s} {r:5.2f} < {need}  {name}  {fg} / {bg}")
    return bad, len(rows)


def screenshots(out):
    app = QApplication.instance()
    from omoffice import theme
    from omoffice.mainwindow import MainWindow
    from omoffice.templates import build_kind
    from omoffice.wizard import StartWizard
    win = MainWindow()
    win.start_screen = False
    win.resize(1280, 820)
    win.show()
    build_kind(win.editor, "ara_rapor", {"title": "Akıllı Sulama Sistemi", "author": "Ayşe Yılmaz"},
               {"cover": True, "toc": True, "placeholders": True})
    app.processEvents()
    shots = []
    for tname in theme.THEMES:
        for aname in theme.ACCENTS:
            win.apply_theme(tname, aname)
            win.ribbon.setCurrentIndex(0)
            app.processEvents()
            shots.append((f"{tname} · {aname}", win.grab().toImage()))
    sheet(shots, os.path.join(out, "temalar.png"), 3, 560)
    # koyu temada tüm yan panel sayfaları
    for tname in theme.THEMES:
        win.apply_theme(tname, "Lacivert")
        pages = []
        for i in range(win.ribbon.count()):
            win.ribbon.setCurrentIndex(i)
            app.processEvents()
            img = win.grab().toImage()
            pages.append((win.ribbon.tabText(i), img.copy(img.width() - 400, 0, 400, img.height())))
        sheet(pages, os.path.join(out, f"paneller_{tname}.png"), len(pages), 300)
        wz = StartWizard([], lambda ch: theme.glyph(ch, color="accent"), "", win)
        wz.setStyleSheet(theme.style_sheet())
        wz.resize(1100, 720)
        wz.show()
        app.processEvents()
        wz.grab().save(os.path.join(out, f"sihirbaz_{tname}.png"))
        if True:
            try:
                wz._pick("ara_rapor")
                wz._to_form()
                app.processEvents()
                wz.grab().save(os.path.join(out, f"sihirbaz2_{tname}.png"))
            except Exception as ex:  # sihirbaz API'si değişirse denetim yine çalışsın
                print("  (sihirbaz 2. sayfa alınamadı:", ex, ")")
        wz.close()
    win.apply_theme("Açık", "Lacivert")
    win.editor.document().setModified(False)
    win.close()


def sheet(shots, path, cols, w):
    h = int(shots[0][1].height() * w / shots[0][1].width())
    rows = (len(shots) + cols - 1) // cols
    img = QImage(cols * (w + 10) + 10, rows * (h + 34) + 10, QImage.Format.Format_RGB32)
    img.fill(QColor("#888C93"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
    for i, (name, im) in enumerate(shots):
        x, y = 10 + (i % cols) * (w + 10), 10 + (i // cols) * (h + 34)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(x, y, w, 22), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        p.drawImage(QRectF(x, y + 24, w, h), im)
    p.end()
    img.save(path)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    bad, total = audit(out)
    screenshots(out)
    print(f"{total} renk çifti denetlendi, {bad} sorunlu")
    print("THEME AUDIT", "PASS" if not bad else "FAIL")


if __name__ == "__main__":
    main()
