"""PDF içe aktarma testi: python tests/pdf_import_test.py <çıktı_klasörü> [pdf ...]

PDF verilmezse OmOffice ile bir belge oluşturup PDF'e aktarır, sonra geri içe aktarır.
Her PDF için: metinde bozuk karakter yok mu, sayfa resimleri (png) ve .docx kopyası yazılır.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OMOFFICE_TEST_DATA", os.path.join(os.path.abspath(sys.argv[1]), "_data"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from omoffice.docx_io import export_docx  # noqa: E402
from omoffice.mainwindow import MainWindow  # noqa: E402

OUT = os.path.abspath(sys.argv[1])
os.makedirs(OUT, exist_ok=True)
FAIL = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def bad_ratio(text):
    t = text.replace("￼", "")
    if not t.strip():
        return 0.0
    bad = len(re.findall(r"\(cid:\d+\)", t)) * 6 + sum(
        1 for c in t if c == "�" or 0xE000 <= ord(c) <= 0xF8FF or (ord(c) < 32 and c not in "\n\t "))
    return bad / len(t)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.information = staticmethod(lambda *a, **k: print("     uyarı:", a[2].replace("\n", " ")))
    QMessageBox.warning = staticmethod(lambda *a, **k: print("     HATA:", a[2].replace("\n", " ")))
    QMessageBox.critical = QMessageBox.warning
    win = MainWindow()
    win.start_screen = False
    win.resize(1300, 900)
    win.show()
    app.processEvents()
    pdfs = sys.argv[2:]
    if not pdfs:
        e = win.editor
        e.setPlainText("")
        from PySide6.QtGui import QTextCursor
        c = QTextCursor(e.document())
        c.insertText("Türkçe karakter denemesi: ğüşıöç ĞÜŞİÖÇ.\n" + "Uzun paragraf metni. " * 60)
        src = os.path.join(OUT, "kaynak.pdf")
        win.export_pdf(src)
        pdfs = [src]
    for i, p in enumerate(pdfs):
        print(f"[{i}] {os.path.basename(p)}")
        win.editor.document().setModified(False)
        ok = win.open_path(p)
        app.processEvents()
        check(ok, "açıldı")
        if not ok:
            continue
        e = win.editor
        text = e.document().toPlainText()
        print("     " + text[:300].replace("\n", " | "))
        check(bad_ratio(text) < 0.02, f"bozuk karakter oranı {bad_ratio(text):.3f}")
        check(len(text.strip()) > 0 or e.image_names(), "içerik var")
        n = e.page_count()
        print(f"     sayfa: {n}, resim: {len(e.image_names())}")
        for k in range(min(n, 2)):
            e.render_page_image(k, 900).save(os.path.join(OUT, f"pdf{i}_s{k + 1}.png"))
        export_docx(e, os.path.join(OUT, f"pdf{i}.docx"))
    print("PDF IMPORT", "FAIL" if FAIL else "PASS")
    win.editor.document().setModified(False)
    win.close()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
