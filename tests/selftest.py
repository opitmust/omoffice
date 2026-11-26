"""OmOffice kendi kendini sınama: python tests/selftest.py [çıktı_klasörü]

Belge oluşturur, .docx'e yazar, geri okur, karşılaştırır; PDF üretir ve
arayüzün ekran görüntülerini alır. Sonunda SELFTEST PASS / FAIL yazar.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OMOFFICE_TEST_DATA"] = tempfile.mkdtemp(prefix="omoffice_data_")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QTextCharFormat, QTextCursor, QTextListFormat
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from omoffice.common import TC_TYPE, STYLE_PROP
from omoffice.docx_io import export_docx, import_docx
from omoffice.mainwindow import MainWindow
from omoffice.editor import new_document
from omoffice.common import PageSetup

OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="omoffice_")
os.makedirs(OUT, exist_ok=True)
failures = []


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def enter(e):
    QTest.keyClick(e, Qt.Key.Key_Return)


def type_keys(w, text):
    # QTest.keyClicks ASCII dışı karakterlerde (ü, ş…) çöküyor; olayı doğrudan gönder
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    for ch in text:
        key = Qt.Key.Key_Space if ch == " " else Qt.Key.Key_unknown
        QApplication.sendEvent(w, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, ch))


def build(win):
    e = win.editor
    c = e.textCursor()
    e.insertPlainText("OmOffice Deneme Belgesi")
    e.apply_style("Konu Başlığı")
    enter(e)
    e.apply_style("Başlık 1")
    e.insertPlainText("Giriş")
    enter(e)
    e.apply_style("Normal")
    e.insertPlainText("Bu paragrafta ")
    f = QTextCharFormat()
    f.setFontWeight(QFont.Weight.Bold)
    e.textCursor().insertText("kalın", f)
    f = QTextCharFormat()
    f.setFontItalic(True)
    f.setForeground(QColor("#C00000"))
    e.textCursor().insertText(" kırmızı italik", f)
    f = QTextCharFormat()
    f.setBackground(QColor("#FFFF00"))
    e.textCursor().insertText(" vurgulu", f)
    e.textCursor().insertText(" ve normal metin var. Yazım hatsı burada.", QTextCharFormat())
    e.insert_link("bağlantı", "https://example.com")
    e.insert_footnote("Bu bir dipnot metnidir.")
    c = e.textCursor()
    blk = c.block()
    i = blk.text().find("kırmızı italik")
    c.setPosition(blk.position() + i)
    c.setPosition(blk.position() + i + len("kırmızı italik"), QTextCursor.MoveMode.KeepAnchor)
    e.setTextCursor(c)
    e.add_comment("Bu renk uygun mu?")
    c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    e.setTextCursor(c)
    enter(e)
    e.insertPlainText("Birinci madde")
    e.toggle_list(QTextListFormat.Style.ListDisc)
    enter(e)
    e.insertPlainText("İç içe madde")
    e.change_list_level(1)
    enter(e)
    e.change_list_level(-1)
    e.insertPlainText("İkinci madde")
    enter(e)
    e.change_list_level(-1)
    e.toggle_list(QTextListFormat.Style.ListDecimal)
    e.insertPlainText("Numaralı bir")
    enter(e)
    e.insertPlainText("Numaralı iki")
    enter(e)
    e.change_list_level(-1)
    e.insert_table(3, 3)
    c = e.textCursor()
    t = c.currentTable()
    for r in range(3):
        for col in range(3):
            t.cellAt(r, col).firstCursorPosition().insertText(f"H{r}{col}")
    t.mergeCells(2, 0, 1, 2)
    e.setTextCursor(t.cellAt(0, 0).firstCursorPosition())
    e.set_cell_background("#DDEBF7")
    c = e.textCursor()
    c.setPosition(t.lastPosition() + 1)
    e.setTextCursor(c)
    img = QImage(160, 90, QImage.Format.Format_RGB32)
    img.fill(QColor("#4A90D9"))
    p = QPainter(img)
    p.fillRect(20, 20, 60, 50, QColor("#F5A623"))
    p.end()
    e.insert_image(img)
    e.insert_page_break()
    e.apply_style("Başlık 2")
    e.insertPlainText("İkinci Sayfa")
    enter(e)
    e.apply_style("Normal")
    e.insertPlainText("Değişiklik izleme: ")
    e.track_changes = True
    e.type_text("eklenen metin")
    e.track_changes = False
    e.insertPlainText(" ve ")
    c = e.textCursor()
    start = c.position()
    e.insertPlainText("silinen metin")
    e.track_changes = True
    c = e.textCursor()
    c.setPosition(start)
    c.setPosition(start + len("silinen metin"), QTextCursor.MoveMode.KeepAnchor)
    e.setTextCursor(c)
    e._tc_delete(True, False)
    e.track_changes = False
    s = e.setup.copy()
    s.header_text = "OmOffice — deneme"
    s.footer_text = "Sayfa {SAYFA} / {TOPLAM}"
    s.watermark = "TASLAK"
    s.page_border = True
    win._apply_setup(s)


def summary(e):
    doc = e.document()
    text = doc.toPlainText()
    kinds = [k for _, _, k, _ in e.tc_segments() if k]
    lists = set()
    block = doc.begin()
    styles = []
    while block.isValid():
        if block.textList() is not None:
            lists.add((block.textList().format().style(), block.textList().format().indent(), block.text()))
        st = block.blockFormat().property(STYLE_PROP)
        if st and st != "Normal":
            styles.append(st)
        block = block.next()
    return text, kinds, lists, styles


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.start_screen = False
    win.apply_theme("Açık", "Lacivert")
    win.resize(1400, 950)
    win.show()
    app.processEvents()
    build(win)
    e = win.editor
    app.processEvents()
    t1, k1, l1, s1 = summary(e)
    check(e.page_count() == 2, f"sayfa sayısı 2 (={e.page_count()})")
    check("ins" in k1 and "del" in k1, "değişiklik izleme işaretleri oluştu")

    path = os.path.join(OUT, "deneme.docx")
    export_docx(e, path)
    check(os.path.getsize(path) > 3000, f"docx yazıldı: {path}")
    doc, setup, meta = import_docx(path)
    win._set_doc(doc, setup, path, meta)
    app.processEvents()
    t2, k2, l2, s2 = summary(e)
    check(t1.replace("￼", "") == t2.replace("￼", ""), "metin gidiş-dönüşte aynı")
    check(k1 == k2, f"izlenen değişiklikler korundu {k2}")
    check(l1 == l2, f"listeler korundu ({len(l2)} öğe)")
    check(s1 == s2, f"stiller korundu {s2}")
    check(setup.footer_text == "Sayfa {SAYFA} / {TOPLAM}", f"alt bilgi: {setup.footer_text!r}")
    check(setup.header_text == "OmOffice — deneme", f"üst bilgi: {setup.header_text!r}")
    check(setup.watermark == "TASLAK" and setup.page_border, f"filigran/kenarlık: {setup.watermark!r} {setup.page_border}")
    cm = list(e.comments.values())
    check(len(cm) == 1 and cm[0]["text"] == "Bu renk uygun mu?" and len(e.comment_ranges()) == 1,
          f"açıklama geri okundu {cm}")
    fn = [(e.footnotes.get(f), t) for _, _, f in e.footnote_refs() for t in [0]]
    check(len(fn) == 1 and fn[0][0] == "Bu bir dipnot metnidir.", f"dipnot geri okundu {e.footnotes}")
    check(len(e.image_names()) == 1, "resim geri okundu")
    tables = 0
    it = doc.rootFrame().begin()
    while not it.atEnd():
        if it.currentFrame() is not None:
            tables += 1
        it += 1
    check(tables == 1, "tablo geri okundu")
    check(e.page_count() == 2, f"içe aktarımdan sonra sayfa sayısı 2 (={e.page_count()})")

    # İkinci tur: yeniden yaz/oku, docx kararlı mı
    path2 = os.path.join(OUT, "deneme2.docx")
    export_docx(e, path2)
    doc3, _, _ = import_docx(path2)
    check(doc3.toPlainText() == doc.toPlainText(), "ikinci gidiş-dönüş kararlı")

    # Kabul / ret
    n = e.tc_resolve(True)
    check(n == 2 and "silinen metin" not in e.document().toPlainText() and "eklenen metin" in
          e.document().toPlainText(), "tümünü kabul et")

    pdf = os.path.join(OUT, "deneme.pdf")
    from PySide6.QtGui import QPdfWriter, QPageLayout, QPageSize
    from PySide6.QtCore import QSizeF, QMarginsF
    w = QPdfWriter(pdf)
    w.setResolution(150)
    w.setPageLayout(win._page_layout())
    pages = e.render_pages(w)
    del w
    check(os.path.getsize(pdf) > 2000 and pages == 2, f"PDF yazıldı ({pages} sayfa)")
    try:
        from PySide6.QtPdf import QPdfDocument
        pd = QPdfDocument()
        pd.load(pdf)
        check(pd.pageCount() == 2, f"PDF sayfa sayısı {pd.pageCount()}")
        for i in range(pd.pageCount()):
            im = pd.render(i, pd.pagePointSize(i).toSize() * 1.5)
            im.save(os.path.join(OUT, f"pdf_sayfa{i + 1}.png"))
    except ImportError:
        print("  (QtPdf yok, PDF görüntüsü atlandı)")

    # Ekran görüntüleri
    e.undo()  # kabul etmeyi geri al, işaretler görünsün
    win.comments_dock.show()
    for i in range(win.ribbon.count()):
        win.ribbon.setCurrentIndex(i)
        app.processEvents()
        win.grab().save(os.path.join(OUT, f"ekran_{i}_{win.ribbon.tabText(i)}.png"))
    win.ribbon.setCurrentIndex(0)
    win.view.set_zoom(0.6)
    app.processEvents()
    check(abs(win.view.zoom - 0.6) < 1e-6 and win.zoom_label.text() == "%60", "yakınlaştırma %60")
    win.grab().save(os.path.join(OUT, "ekran_zoom60.png"))
    win.view.set_zoom(1.0)
    win.view.verticalScrollBar().setValue(win.view.verticalScrollBar().maximum())
    app.processEvents()
    win.grab().save(os.path.join(OUT, "ekran_sayfa2.png"))
    win.apply_theme("Koyu", "Mor")
    win.view.verticalScrollBar().setValue(0)
    c = e.textCursor()
    c.movePosition(QTextCursor.MoveOperation.Start)
    c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    e.setTextCursor(c)
    win._show_minibar()
    app.processEvents()
    win.grab().save(os.path.join(OUT, "ekran_koyu.png"))
    win.minibar.grab().save(os.path.join(OUT, "minibar.png"))
    win.show_palette()
    win._palette.edit.setText("filigran")
    app.processEvents()
    check(win._palette.list.count() >= 1, f"komut paletinde 'filigran' bulundu ({win._palette.list.count()})")
    win._palette.grab().save(os.path.join(OUT, "palet.png"))
    win._palette.close()
    win.apply_theme("Açık", "Lacivert")
    # Şablonlar
    from omoffice.templates import build as build_template
    from omoffice.editor import new_document
    from omoffice.common import PageSetup
    for name in ("Mektup", "Özgeçmiş", "Rapor", "Toplantı notları"):
        win._set_doc(new_document(), PageSetup(), None)
        build_template(e, name)
        app.processEvents()
        check(len(e.document().toPlainText()) > 50, f"şablon: {name} ({e.page_count()} sayfa)")
        win.grab().save(os.path.join(OUT, f"sablon_{name}.png"))
    # Otomatik düzeltme
    win._set_doc(new_document(), PageSetup(), None)
    e.autocorrect = True
    type_keys(e, "merhaba dünya. herşey yolunda (c) ")
    check(e.document().toPlainText() == "Merhaba dünya. Her şey yolunda © ",
          f"otomatik düzeltme: {e.document().toPlainText()!r}")
    type_keys(e, "bu bir TEst. cAPS lock. ")
    check(e.document().toPlainText().endswith("© bu bir Test. Caps lock. "),
          f"İKi BAşharf / cAPS LOCK düzeltmesi: {e.document().toPlainText()!r}")

    # Seçilen yazı tipi Enter'dan sonra da sürer (otomatik düzeltme ve boş satır onu düşürmemeli)
    def font_after(steps):
        win._set_doc(new_document(), PageSetup(), None)
        for s in steps:
            if s == "pick":
                win.font_box.textActivated.emit("Georgia")
            elif s == "enter":
                enter(e)
            else:
                type_keys(e, s)
        type_keys(e, "yeni")
        c = QTextCursor(e.document().lastBlock())
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        return (c.charFormat().fontFamilies() or ["?"])[0]
    for name, steps in (("tek sözcük düzeltilince", ["merhaba", "pick", "enter"]),
                        ("boş sayfada", ["pick", "enter"]),
                        ("iki kez Enter", ["abc def", "pick", "enter", "enter"]),
                        ("boşluktan sonra", ["ali", "pick", " ", "enter"])):
        fam = font_after(steps)
        check(fam == "Georgia", f"yazı tipi Enter'dan sonra korunur ({name}): {fam}")

    # Başka programdan yapıştırma biçimi korur (Word <style> kuralları, web px boyutları, başlıklar)
    from PySide6.QtCore import QMimeData

    def paste_html(html):
        win._set_doc(new_document(), PageSetup(), None)
        md = QMimeData()
        md.setHtml(html)
        e.insertFromMimeData(md)
        app.processEvents()

    def fmt_of(word):
        i = e.document().toPlainText().find(word)
        c = QTextCursor(e.document())
        c.setPosition(i + 1)
        f = c.charFormat()
        return (f.fontFamilies() or ["?"])[0], f.fontPointSize()
    paste_html("""<html><head><style><!--
@font-face {font-family:"Cambria Math"; panose-1:2 4 5 3 5 4 6 3 2 4;}
p.MsoNormal, li.MsoNormal, div.MsoNormal {margin-bottom:8.0pt; font-size:12.0pt; font-family:"Times New Roman",serif;}
@page WordSection1 {size:595.3pt 841.9pt; margin:70.85pt;}
div.WordSection1 {page:WordSection1;}
--></style></head><body lang=TR><div class=WordSection1><!--StartFragment-->
<p class=MsoNormal>Wordmetni burada</p><!--EndFragment--></div></body></html>""")
    check(fmt_of("Wordmetni") == ("Times New Roman", 12.0), f"Word'den yapıştırma biçimi korur: {fmt_of('Wordmetni')}")
    paste_html('<h2 style="font-family: Roboto, Arial; font-size: 24px">Webbaslik</h2>'
               '<p style="font-family: Verdana; font-size: 16px">Webmetin</p><h1>Duzbaslik</h1>')
    check(fmt_of("Webbaslik") == ("Roboto", 18.0) and fmt_of("Webmetin") == ("Verdana", 12.0),
          f"web sayfasından yapıştırma px→punto: {fmt_of('Webbaslik')} {fmt_of('Webmetin')}")
    check(fmt_of("Duzbaslik")[1] == 22.0, f"yapıştırılan başlık boyutu puntoya çevrilir: {fmt_of('Duzbaslik')}")

    # Fare tekerleği sayfanın üstündeyken de kaydırır
    win._set_doc(new_document(), PageSetup(), None)
    e.textCursor().insertText("satır\n" * 300)
    app.processEvents()
    from PySide6.QtCore import QPoint as _QP, QPointF as _QPF
    from PySide6.QtGui import QWheelEvent
    sb = win.view.verticalScrollBar()
    sb.setValue(sb.maximum() // 2)
    before = sb.value()
    vp = win.view.viewport()
    mid = _QP(vp.width() // 2, vp.height() // 2)
    QApplication.sendEvent(vp, QWheelEvent(_QPF(mid), _QPF(vp.mapToGlobal(mid)), _QP(0, 0), _QP(0, -120),
                                           Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                           Qt.ScrollPhase.NoScrollPhase, False))
    app.processEvents()
    check(sb.value() > before, f"tekerlek sayfanın üstünde kaydırır: {before} → {sb.value()}")

    # Tüm belgede büyük harf düzeltmesi
    win._set_doc(new_document(), PageSetup(), None)
    e.autocorrect = False
    e.textCursor().insertText("ankara güzel. bugün hava güzel! yarın da İSTanbul.")
    e.autocorrect = True
    import time as _t
    t0 = _t.time()
    while not e.spell.ready and _t.time() - t0 < 30:
        app.processEvents()
    fixes = e.fix_capitalization(apply=True)
    check(e.document().toPlainText() == "Ankara güzel. Bugün hava güzel! Yarın da İstanbul.",
          f"belge büyük harf düzeltmesi ({len(fixes)}): {e.document().toPlainText()!r}")

    # Sihirbazdaki tüm belge türleri
    from omoffice.guide import KINDS, format_reference, in_text
    from omoffice.templates import build_kind
    from omoffice.guidepanel import add_reference, sections
    for key, info in KINDS.items():
        win._set_doc(new_document(), PageSetup(), None)
        answers = {"title": "Yapay Zekâ ve Eğitim", "author": "Ayşe Yılmaz", "institution": "Örnek Üniversitesi",
                   "department": "Eğitim Bilimleri", "course": "Araştırma Yöntemleri", "keywords": "yapay zekâ, eğitim, öğrenme"}
        opts = {"cover": True, "toc": True, "placeholders": True, "examples": True, "citation": "APA 7"}
        build_kind(e, key, answers, opts)
        app.processEvents()
        import re as _re
        norm = lambda s_: _re.sub(r"^[\d.\s]+", "", s_).strip()  # noqa: E731  ("1.  Giriş" → "Giriş")
        heads = [norm(t) for t, *_ in sections(e)]
        want = [norm(t) for t, _, _ in info["sections"]]
        missing = [w for w in want if w not in heads]
        ok = not missing and (key == "bos" or len(e.document().toPlainText()) > 30)
        if missing:
            print("      eksik başlıklar:", missing)
        check(ok, f"tür şablonu: {info['name']} ({e.page_count()} sayfa, {e.placeholder_count()} yer tutucu)")
        if key in ("makale", "tez", "odev", "dilekce"):
            win.grab().save(os.path.join(OUT, f"tur_{key}.png"))
            export_docx(e, os.path.join(OUT, f"tur_{key}.docx"))
    # Kaynak ekleme (APA sıralı + IEEE numaralı)
    win._set_doc(new_document(), PageSetup(), None)
    build_kind(e, "makale", {"title": "Deneme"}, {"placeholders": True, "citation": "APA 7"})
    r1 = {"type": "Dergi makalesi", "authors": "Yılmaz, Ayşe; Demir, Can", "year": "2023",
          "title": "Öğrenme analitiği", "source": "Eğitim Dergisi", "volume": "12", "issue": "3", "pages": "45-60",
          "doi": "10.1234/ed.2023"}
    r2 = {"type": "Kitap", "authors": "Arslan, Mehmet", "year": "2020", "title": "Araştırma yöntemleri",
          "publisher": "Örnek Yayınevi"}
    c1 = add_reference(e, "APA 7", r1)
    c2 = add_reference(e, "APA 7", r2)
    refs = [b for t, _, _, body in sections(e) if t == "Kaynakça" for b in body if b.text().strip()]
    check(c1 == "(Yılmaz & Demir, 2023)" and c2 == "(Arslan, 2020)" and len(refs) == 2
          and refs[0].text().startswith("Arslan"), f"APA kaynakça: {c1} {c2} {[b.text()[:30] for b in refs]}")
    check(format_reference("IEEE", r1).startswith("A. Yılmaz and C. Demir") and in_text("IEEE", r1, 3) == "[3]",
          f"IEEE biçimi: {format_reference('IEEE', r1)[:60]}")
    # Rehber kontrol listesi
    win.guide_page.show()
    win.guide_panel.refresh()
    app.processEvents()
    checks = win.guide_panel.checks(KINDS["makale"], "makale")
    check(any("yer tutucu" in t for _, t in checks), f"rehber kontrol listesi: {[t for _, t in checks][:4]}")
    win.grab().save(os.path.join(OUT, "rehber.png"))

    # ODT gidiş-dönüş (Qt ile yazılıp OmOffice ile okunur)
    from PySide6.QtGui import QTextDocumentWriter
    from omoffice.odt_io import import_odt
    win._set_doc(new_document(), PageSetup(), None)
    build_kind(e, "odev", {"title": "ODT Deneme"}, {"placeholders": False})
    odt = os.path.join(OUT, "deneme.odt")
    QTextDocumentWriter(odt, b"odf").write(e.document())
    d4, s4, m4 = import_odt(odt)
    check("Giriş" in d4.toPlainText() and "Sonuç" in d4.toPlainText(), "ODT içe aktarma")
    check(win.open_path(odt), "ODT dosyası arayüzden açıldı")

    # .dotx (Word şablonu) açma
    import zipfile
    dotx = os.path.join(OUT, "sablon.dotx")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(dotx, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            data = zin.read(it.filename)
            if it.filename == "[Content_Types].xml":
                data = data.replace(b"wordprocessingml.document.main+xml", b"wordprocessingml.template.main+xml")
            zout.writestr(it, data)
    check(win.open_path(dotx) and win.path is None and "OmOffice Deneme Belgesi" in e.document().toPlainText(),
          ".dotx şablon olarak açıldı (yeni belge, adsız)")

    # Yeni açılan boş belge "değişti" sayılmamalı (kapatırken boşuna kaydet sorusu çıkmasın)
    fresh = MainWindow()
    fresh.show()
    QTest.qWait(800)
    check(not fresh.editor.document().isModified() and not fresh.windowTitle().startswith("●"),
          f"yeni boş belge değişmemiş sayılıyor: {fresh.windowTitle()!r}")
    fresh.close()
    QApplication.processEvents()

    # Eski adla (Kalem) kaydedilmiş belgelerin tür bilgisi okunmaya devam etmeli
    from docx import Document
    old_name = os.path.join(OUT, "eski_ad.docx")
    d_old = Document(path)
    d_old.core_properties.category = "Kalem:makale|APA"
    d_old.save(old_name)
    info = import_docx(old_name)[2]["info"]
    check(info.get("kind") == "makale" and info.get("citation") == "APA", f"eski adla kaydedilmiş belge: {info}")

    # Güvenli kayıt: hata olursa mevcut dosya bozulmamalı, geçici dosya kalmamalı
    from unittest import mock
    from PySide6.QtWidgets import QMessageBox
    safe = os.path.join(OUT, "guvenli_kayit.docx")
    check(win.save_to(safe), "güvenli kayıt: ilk kayıt")
    with open(safe, "rb") as f:
        before = f.read()

    def half_write(_editor, target):
        with open(target, "wb") as f:
            f.write(b"PK yarim kalan kayit")
        raise OSError("disk dolu")

    with mock.patch("omoffice.mainwindow.export_docx", half_write), mock.patch.object(QMessageBox, "critical") as box:
        check(not win.save_to(safe) and box.called, "güvenli kayıt: hata kullanıcıya bildirildi")
    with open(safe, "rb") as f:
        check(f.read() == before, "güvenli kayıt: hata sonrası eski dosya bozulmadı")
    with mock.patch("omoffice.mainwindow.export_docx", lambda _e, t: open(t, "wb").close()), \
            mock.patch.object(QMessageBox, "critical"):
        check(not win.save_to(safe), "güvenli kayıt: geçersiz çıktı reddedildi")
    with open(safe, "rb") as f:
        check(f.read() == before, "güvenli kayıt: geçersiz çıktı eski dosyanın üzerine yazılmadı")
    check(not [n for n in os.listdir(OUT) if n.startswith(".~")], "güvenli kayıt: geçici dosya kalmadı")

    # Kurtarma: çökmüş bir oturumu taklit et
    import json
    win._autosave(force=True)
    base = win._rec_base()
    check(os.path.exists(base + ".docx"), "kurtarma kopyası yazıldı")
    fake = os.path.join(win._rec_dir(), "testcrash000")
    import shutil
    shutil.copy(base + ".docx", fake + ".docx")
    with open(fake + ".json", "w", encoding="utf-8") as f:
        json.dump({"path": None, "title": "Çöken belge", "time": 0, "pid": 999999}, f)
    ent = [x for x in win.recovery_entries() if x[1] == fake + ".docx"]
    check(len(ent) == 1 and "beklenmedik" in ent[0][0], "çöken oturum kurtarma listesinde")
    for ext in (".docx", ".json"):
        os.remove(fake + ext)
    win._clear_recovery()
    check(not os.path.exists(base + ".docx"), "düzgün kapanışta kurtarma dosyası silindi")
    win.editor.document().setModified(False)
    print("\nÇıktılar:", OUT)
    print("SELFTEST", "PASS" if not failures else f"FAIL ({len(failures)})")
    win.close()
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
