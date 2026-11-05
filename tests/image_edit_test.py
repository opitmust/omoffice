"""Resim alanları ve boyutlandırma: python tests/image_edit_test.py <klasör>  ->  LOGO PASS/FAIL

"Logo ekle" alanına tek tıkla resim yerleştirme (alana sığdırma, oran), tutamaçla boyutlandırma,
geri al, Delete ile silme ve .docx gidiş-dönüşte alanın korunması."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OMOFFICE_TEST_DATA"] = tempfile.mkdtemp()
OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
from PySide6.QtCore import Qt, QPointF, QPoint
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog
app = QApplication(sys.argv)
from omoffice.mainwindow import MainWindow
from omoffice.templates import build_kind
from omoffice.editor import new_document
from omoffice.common import PageSetup, image_slot
from omoffice.docx_io import export_docx, import_docx
from omoffice.guide import KINDS

ok_all = True
def check(c, m):
    global ok_all
    ok_all &= bool(c)
    print(("  ok  " if c else "  HATA ") + m)

# test resimleri: geniş ve uzun logo
def make(w, h, col, path):
    im = QImage(w, h, QImage.Format.Format_RGB32); im.fill(QColor(col))
    p = QPainter(im); p.fillRect(w // 4, h // 4, w // 2, h // 2, QColor("#FFFFFF")); p.end(); im.save(path)
WIDE, TALL = os.path.join(OUT, "genis.png"), os.path.join(OUT, "uzun.png")
make(900, 300, "#C62828", WIDE); make(200, 800, "#2E7D32", TALL)
pick = {"path": WIDE}
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (pick["path"], ""))

w = MainWindow(); w.start_screen = False; w.resize(1300, 900); w.show(); app.processEvents()
e = w.editor

def fresh(kind):
    w._set_doc(new_document(), PageSetup(), None); app.processEvents()
    build_kind(e, kind, {"title": "Deneme", "author": "Ayşe"}, {"cover": True, "toc": False, "placeholders": True})
    app.processEvents()

def images():
    out = []; b = e.document().begin()
    while b.isValid():
        it = b.begin()
        while not it.atEnd():
            f = it.fragment()
            if f.charFormat().isImageFormat():
                fm = f.charFormat().toImageFormat()
                out.append((f.position(), fm.name(), fm.width(), fm.height()))
            it += 1
        b = b.next()
    return out

def show(pos):
    """Resmin görünür olmasını sağla (görünüm kaydırması) ve editördeki noktasını ver."""
    c = e.textCursor(); c.setPosition(pos); e.setTextCursor(c); app.processEvents()
    w.view.ensure_cursor() if hasattr(w.view, "ensure_cursor") else None
    app.processEvents()
    return e.image_rect(pos)

def click(pt):
    QTest.mouseClick(e.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt.toPoint())
    app.processEvents()

def drag(a, b):
    vp = e.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, a.toPoint())
    for i in range(1, 6):
        p = a + (b - a) * (i / 5)
        QTest.mouseMove(vp, p.toPoint())
        app.processEvents()
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, b.toPoint())
    app.processEvents()

print("Şablonlardaki alanlar:")
with_slot = []
for kind in KINDS:
    fresh(kind)
    slots = [i for i in images() if image_slot(i[1])]
    if slots:
        with_slot.append(kind)
    print(f"   {kind:10s} {[image_slot(i[1]) for i in slots]}")
check(len(with_slot) >= 8, f"{len(with_slot)} şablonda logo/fotoğraf alanı var")

for kind in with_slot:
    for path, label in ((WIDE, "geniş"), (TALL, "uzun")):
        fresh(kind)
        pos, name, bw, bh = [i for i in images() if image_slot(i[1])][0]
        r = show(pos)
        pick["path"] = path
        click(r.center())
        im = [i for i in images() if i[0] == pos][0]
        fits = im[2] <= bw + 0.5 and im[3] <= bh + 0.5 and (abs(im[2] - bw) < 0.5 or abs(im[3] - bh) < 0.5)
        ratio_ok = abs(im[2] / im[3] - (900 / 300 if path == WIDE else 200 / 800)) < 0.02
        check(not image_slot(im[1]) and fits and ratio_ok,
              f"{kind}: {label} resim tek tıkla alana sığdı ({bw:.0f}×{bh:.0f} kutuya {im[2]:.0f}×{im[3]:.0f})")

# boyutlandırma: ara rapor logosu
fresh("ara_rapor")
pos = [i for i in images() if image_slot(i[1])][0][0]
r = show(pos); pick["path"] = WIDE; click(r.center())
r = e.image_rect(pos); w0, h0 = r.width(), r.height()
check(e.selected_image() == pos, "yerleştirilen resim seçili geliyor (tutamaçlar görünür)")
grab = w.view.grab() if hasattr(w, "view") else e.grab()
grab.save(os.path.join(OUT, "tutamaclar.png"))
drag(r.bottomRight(), r.bottomRight() + QPointF(120, 0))
fm = [i for i in images() if i[0] == pos][0]
check(fm[2] > w0 + 60 and abs(fm[2] / fm[3] - w0 / h0) < 0.02,
      f"köşeden sürükleme büyütür, oran korunur ({w0:.0f}×{h0:.0f} → {fm[2]:.0f}×{fm[3]:.0f})")
r = e.image_rect(pos)
drag(QPointF(r.right(), r.center().y()), QPointF(r.right() - 80, r.center().y()))
fm2 = [i for i in images() if i[0] == pos][0]
check(fm2[2] < fm[2] - 40 and abs(fm2[3] - fm[3]) < 0.5, f"kenardan sürükleme yalnızca genişliği değiştirir ({fm2[2]:.0f}×{fm2[3]:.0f})")
e.undo(); app.processEvents()
fm3 = [i for i in images() if i[0] == pos][0]
check(abs(fm3[2] - fm[2]) < 0.5, "geri al boyutu geri getirir")
e._select_image(pos); app.processEvents()   # geri almadan sonra resmi yeniden seç
r = e.image_rect(pos)
drag(r.bottomRight(), r.bottomRight() + QPointF(900, 300))
fm4 = [i for i in images() if i[0] == pos][0]
check(fm[2] + 100 < fm4[2] <= e.text_width() + 0.5,
      f"çok büyütülen resim sayfa genişliğinde durur ({fm4[2]:.0f} ≤ {e.text_width():.0f})")

# sıradan resme tıklayınca seçilir; Delete siler
fresh("makale")
c = e.textCursor(); c.movePosition(c.MoveOperation.End); e.setTextCursor(c)
pick["path"] = TALL; w.insert_image(); app.processEvents()
ip = e.selected_image()
check(ip is not None, "Ekle › Resim: eklenen resim seçili geliyor")
n = len(images())
from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeyEvent
for t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
    QApplication.sendEvent(e, QKeyEvent(t, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier, ""))
app.processEvents()
check(len(images()) == n - 1, "seçili resim Delete ile silinir")

# docx gidiş-dönüş: boş alan yine "Logo ekle" alanı olarak açılır
fresh("tez")
path = os.path.join(OUT, "alan.docx"); export_docx(e, path)
doc, setup, meta = import_docx(path); w._set_doc(doc, setup, path, meta); app.processEvents()
check(any(image_slot(i[1]) == "logo" for i in images()), "docx'e kaydedip açınca logo alanı korunur")

e.document().setModified(False); w.close()
print("LOGO", "PASS" if ok_all else "FAIL")
