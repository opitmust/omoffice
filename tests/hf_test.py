"""Sayfaya özel üst/alt bilgi testi: python tests/hf_test.py [çıktı_klasörü]

6 sayfalık belge: 6. sayfadan üst/alt bilgi kaldırılır, 3. sayfaya özel üst bilgi konur,
5. sayfanın alt bilgisi fareyle ✕ düğmesinden silinir, sondaki boş sayfa silinir.
.docx'e kaydedilir, (varsa) Microsoft Word'ün PDF çıktısında sayfa sayfa doğrulanır,
geri açılınca ayarların korunduğu kontrol edilir.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OMOFFICE_TEST_DATA"] = tempfile.mkdtemp(prefix="omoffice_data_")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QTextCursor, QTextBlockFormat, QTextCharFormat
from PySide6.QtWidgets import QApplication

OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="omoffice_hf_")
os.makedirs(OUT, exist_ok=True)
failures = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def expected(st, total):
    return [(st.hf_for("header", n)[0], st.hf_for("footer", n)[0]) for n in range(1, total + 1)]


def word_pdf_pages(docx_path, pdf_path):
    """Word ile PDF'e çevirip her sayfanın metnini döndürür (Word yoksa None)."""
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        pass
    import subprocess  # nosec B404 - yalnızca test: Word'ü PowerShell COM ile çağırmak için
    ps = (f"$w=New-Object -ComObject Word.Application; $w.Visible=$false; "
          f"$d=$w.Documents.Open('{docx_path}', $false, $true); $d.ExportAsFixedFormat('{pdf_path}', 17); "
          f"$d.Close($false); $w.Quit()")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,  # nosec
                       timeout=180)
    if r.returncode != 0 or not os.path.exists(pdf_path):
        return None
    from PySide6.QtPdf import QPdfDocument
    pd = QPdfDocument()
    pd.load(pdf_path)
    pages = [pd.getAllText(i).text() for i in range(pd.pageCount())]
    for i in range(pd.pageCount()):
        pd.render(i, pd.pagePointSize(i).toSize()).save(os.path.join(OUT, f"word_sayfa{i + 1}.png"))
    return pages


def main():
    app = QApplication(sys.argv)
    from omoffice.mainwindow import MainWindow
    from omoffice.docx_io import export_docx, import_docx
    win = MainWindow()
    win.start_screen = False
    win.resize(1400, 950)
    win.show()
    app.processEvents()
    e = win.editor
    c = e.textCursor()
    para = ("Bu paragraf sayfaları doldurmak için yazılmış örnek bir metindir; üst ve alt bilginin "
            "sayfa sayfa yönetimini sınamak amacıyla tekrar edilmektedir. ")
    for i in range(1, 6):
        c.insertText(f"BÖLÜM {i}")
        c.insertBlock(QTextBlockFormat(), QTextCharFormat())
        for _ in range(9 if i < 6 else 2):
            c.insertText(para * 2)
            c.insertBlock(QTextBlockFormat(), QTextCharFormat())
        if i < 5:
            e.setTextCursor(c)
            e.insert_page_break()
            c = e.textCursor()
    c.insertText("SON SAYFA: kısa metin")
    e.setTextCursor(c)
    e.insert_page_break()
    c = e.textCursor()
    c.insertText("ALTINCI SAYFA")
    st = e.setup.copy()
    st.header_text, st.footer_text = "OmOffice Raporu", "Sayfa {SAYFA}"
    win._apply_setup(st)
    app.processEvents()
    total = e.page_count()
    check(total == 6, f"belge 6 sayfa ({total})")

    # 6. sayfadan kaldır, 3. sayfaya özel üst bilgi
    e.hf_set(6, "header", "", scope="page")
    e.hf_set(6, "footer", "", scope="page")
    e.hf_set(3, "header", "Ek-A: Yöntem", "right", scope="page")
    exp = expected(e.setup, total)
    check(exp[5] == ("", ""), f"6. sayfada üst/alt bilgi yok {exp[5]}")
    check(exp[2][0] == "Ek-A: Yöntem" and exp[0][0] == "OmOffice Raporu", "3. sayfaya özel üst bilgi, diğerleri aynı")

    # 5. sayfanın alt bilgisini fareyle ✕ düğmesinden sil
    from PySide6.QtCore import QRectF
    pw, ph = e.page_px()
    zone = e.hf_zone("footer", QRectF(0, 4 * ph, pw, ph))
    _, del_r = e.hf_buttons(zone)
    pos = del_r.center()
    move = QMouseEvent(QEvent.Type.MouseMove, pos, pos, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                       Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(e.viewport(), move)
    check(e._hf_hover == (4, "footer"), f"fare 5. sayfanın alt bilgisinde: vurgulandı {e._hf_hover}")
    win.view.ensureVisible(win.view.proxy.mapRectToScene(zone), 0, 200)
    app.processEvents()
    win.grab().save(os.path.join(OUT, "hover_alt_bilgi.png"))
    press = QMouseEvent(QEvent.Type.MouseButtonPress, pos, pos, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(e.viewport(), press)
    check(e.setup.hf_for("footer", 5)[0] == "", "✕ ile 5. sayfanın alt bilgisi silindi")
    check(e.setup.hf_for("footer", 4)[0] == "Sayfa {SAYFA}", "4. sayfanın alt bilgisi yerinde")

    # 'Bu sayfadan itibaren' ve varsayılana döndürme
    e.hf_set(2, "header", "Yeni başlık", scope="from")
    exp2 = expected(e.setup, total)
    check(exp2[0][0] == "OmOffice Raporu" and exp2[1][0] == "Yeni başlık" and exp2[3][0] == "Yeni başlık"
          and exp2[5][0] == "", f"'bu sayfadan itibaren' doğru: {[x[0] for x in exp2]}")
    e.hf_set(2, "header", "OmOffice Raporu", scope="from")
    e.hf_set(3, "header", "Ek-A: Yöntem", "right", scope="page")
    e.hf_set(6, "header", "", scope="page")

    # Sondaki boş sayfa: oluştur ve sil
    c = e.textCursor()
    c.movePosition(QTextCursor.MoveOperation.End)
    e.setTextCursor(c)
    e.insert_page_break()
    app.processEvents()
    check(e.page_count() == 7 and e.page_is_empty(7), f"7. boş sayfa oluştu ({e.page_count()})")
    check(e.delete_empty_page(7) and e.page_count() == 6, f"boş sayfa silindi ({e.page_count()})")
    exp = expected(e.setup, 6)
    app.processEvents()
    win.view.verticalScrollBar().setValue(int(4.5 * ph))
    app.processEvents()
    win.grab().save(os.path.join(OUT, "sayfa5_6.png"))

    # .docx gidiş-dönüş
    path = os.path.join(OUT, "sayfaya_ozel.docx")
    export_docx(e, path)
    doc, setup, meta = import_docx(path)
    win._set_doc(doc, setup, path, meta)
    app.processEvents()
    back = expected(e.setup, e.page_count())
    check(back == exp, f"geri açılınca sayfa sayfa aynı:\n      beklenen {exp}\n      okunan   {back}")

    # Microsoft Word ile doğrulama
    pages = word_pdf_pages(path, os.path.join(OUT, "word.pdf"))
    if pages is None:
        print("  (Word bulunamadı; Word doğrulaması atlandı)")
    else:
        check(len(pages) == 6, f"Word'de 6 sayfa ({len(pages)})")
        for n, (txt, (h, f)) in enumerate(zip(pages, exp), 1):
            has_h = "OmOffice Raporu" in txt or "Ek-A" in txt
            has_f = f"Sayfa {n}" in txt
            ok = (("Ek-A" in txt) == (h == "Ek-A: Yöntem")) and (has_h == bool(h)) and (has_f == bool(f))
            check(ok, f"Word sayfa {n}: üst bilgi={'var' if has_h else 'yok'}, alt bilgi={'var' if has_f else 'yok'}"
                      f" (beklenen: {h or '-'} / {f or '-'})")
    e.document().setModified(False)
    win.close()
    print("\nHF TEST", "PASS" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
