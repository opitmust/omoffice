"""'Sonrakiyle birlikte tut': python tests/keep_next_test.py  ->  KEEP PASS/FAIL

Başlıklar ve tablo başlıkları sayfanın en altında yalnız kalmaz; yazı eklenip silindikçe taşımalar güncellenir,
geri al tutarlı kalır, .docx'e keepNext yazılır."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OMOFFICE_TEST_DATA"] = tempfile.mkdtemp()
from PySide6.QtCore import QEvent, QEventLoop, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from omoffice.common import KEEP_AUTO_PROP, PageSetup
from omoffice.docx_io import export_docx
from omoffice.editor import new_document
from omoffice.mainwindow import MainWindow
from omoffice.templates import build_kind

ok_all = True


def check(c, m):
    global ok_all
    ok_all &= bool(c)
    print(("  ok  " if c else "  HATA ") + m)


w = MainWindow()
w.start_screen = False
w.resize(1200, 800)
w.show()
app.processEvents()
e = w.editor


def wait(ms=500):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def fresh(kind):
    w._set_doc(new_document(), PageSetup(), None)
    app.processEvents()
    build_kind(e, kind, {"title": "Deneme", "author": "Ayşe"}, {"cover": True, "toc": True, "placeholders": True,
                                                              "citation": "APA 7"})
    app.processEvents()


def violations():
    """Hedefiyle aynı sayfada olmayan, sayfanın başında da olmayan birlikte-tutulan bloklar."""
    out, b = [], e.document().begin()
    while b.isValid():
        if e._keeps(b):
            t = e._keep_target(b)
            if t is not None:
                pb, y = e._page_y(b.position())
                if e._page_y(t.position())[0] > pb and y > 20:
                    out.append(b.text()[:30])
        b = b.next()
    return out


def autos():
    n, b = 0, e.document().begin()
    while b.isValid():
        n += b.blockFormat().hasProperty(KEEP_AUTO_PROP)
        b = b.next()
    return n


def key(k, text=""):
    for t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(e, QKeyEvent(t, k, Qt.KeyboardModifier.NoModifier, text))
    app.processEvents()


for kind in ("makale", "ara_rapor", "arastirma", "proje", "tez", "lab"):
    t0 = time.time()
    fresh(kind)
    check(not violations(), f"{kind}: şablonda yalnız kalan başlık yok ({autos()} taşıma, {time.time() - t0:.1f} s)")

# düzenlerken: Bulgular'dan önce satırlar ekle/sil, her adımda kural korunur
fresh("makale")
doc = e.document()
pos = doc.find("Sonuçları yorum").position()
c = QTextCursor(doc)
c.setPosition(pos)
c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
e.setTextCursor(c)
bad = []
for i in range(14):
    key(Qt.Key.Key_Return)
    wait(450)
    v = violations()
    if v:
        bad.append((i, v))
check(not bad, f"satır eklerken başlık/tablo başlığı hiç yalnız kalmadı {bad[:2]}")
pages_full = e.page_count()
for i in range(14):
    key(Qt.Key.Key_Backspace)
    wait(450)
    v = violations()
    if v:
        bad.append((i, v))
check(not bad, "satır silerken de yalnız kalan yok")
fresh("makale")
ref_pages, ref_autos = e.page_count(), autos()
# aynı içerik: eskimiş taşıma kalmamalı (gereksiz boş sayfa olmamalı)
check(ref_autos <= 2, f"eskimiş taşıma birikmiyor ({ref_autos})")

# geri al: metin ve taşıma birlikte geri gelir
fresh("makale")
doc = e.document()
before_autos = autos()
pos = doc.find("Sonuçları yorum").position()
c = QTextCursor(doc)
c.setPosition(pos)
c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
e.setTextCursor(c)
for _ in range(6):
    key(Qt.Key.Key_Return)
wait(500)
mid = autos()
for _ in range(6):
    e.undo()
    app.processEvents()
wait(500)
check(autos() == before_autos and not violations(), f"geri al tutarlı (taşıma {before_autos}→{mid}→{autos()})")

# .docx: başlıklar ve tablo başlıkları keepNext, otomatik taşıma sayfa sonu olarak yazılmaz
fresh("makale")
path = os.path.join(tempfile.mkdtemp(), "keep.docx")
export_docx(e, path)
import zipfile
xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
check(xml.count("<w:keepNext/>") >= 8, f"docx'te keepNext var ({xml.count('<w:keepNext/>')})")
check("Tablo 1." in xml, "tablo başlığı yazıldı")

e.document().setModified(False)
w.close()
print("KEEP", "PASS" if ok_all else "FAIL")
