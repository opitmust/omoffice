"""Tüm şablonların sayfa önizlemelerini tek görselde toplar: python tests/template_gallery.py <klasör> [palet] [yazıtipi]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    app = QApplication(sys.argv)
    from omoffice.common import PageSetup
    from omoffice.editor import PageEdit, new_document
    from omoffice.guide import KINDS
    from omoffice.templates import build_kind
    answers = {"title": "Yapay Zekâ Destekli Öğrenmenin Akademik Başarıya Etkisi", "author": "Ayşe Yılmaz",
               "institution": "Örnek Üniversitesi", "department": "Eğitim Bilimleri",
               "course": "Araştırma Yöntemleri", "keywords": "yapay zekâ, öğrenme analitiği, başarı",
               "advisor": "Prof. Dr. Mehmet Demir", "degree": "Yüksek Lisans Tezi", "student_no": "20231234",
               "instructor": "Doç. Dr. Selin Kaya", "recipient": "Mühendislik Fakültesi Dekanlığına",
               "subject": "Ders kaydı hakkında"}
    opts = {"cover": True, "toc": True, "placeholders": True, "citation": "APA 7"}
    if len(sys.argv) > 2:
        opts["palette"] = sys.argv[2]
    if len(sys.argv) > 3:
        opts["fontset"] = sys.argv[3]
    e = PageEdit(None)
    W = 360
    shots = []
    for key in KINDS:
        e.set_document(new_document(), PageSetup())
        build_kind(e, key, answers, opts)
        pages = [e.render_page_image(i, W) for i in range(min(3, e.page_count()))]
        shots.append((KINDS[key]["name"], pages, e.page_count()))
        for i, im in enumerate(pages):
            im.save(os.path.join(out, f"{key}_{i + 1}.png"))
    cols = 3
    H = pages[0].height()
    sheet = QImage(cols * (W + 12) + 12, len(shots) * (H + 40) + 12, QImage.Format.Format_RGB32)
    sheet.fill(QColor("#D9DCE1"))
    p = QPainter(sheet)
    f = QFont("Segoe UI", 11)
    f.setBold(True)
    p.setFont(f)
    for r, (name, pages, n) in enumerate(shots):
        y = 12 + r * (H + 40)
        p.drawText(14, y + 18, f"{name}  ({n} sayfa)")
        for c, im in enumerate(pages):
            p.drawImage(12 + c * (W + 12), y + 28, im)
    p.end()
    sheet.save(os.path.join(out, "galeri.png"))
    print("tamam", os.path.join(out, "galeri.png"))


if __name__ == "__main__":
    main()
