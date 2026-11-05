"""Şablon belgelerde tablo silme: python tests/table_edit_test.py  ->  TABLO PASS/FAIL

Tüm tabloyu seçip Backspace/Delete, tablonun altında iki kez Backspace, tam satır/sütun silme,
silinen tablonun yerine normal boyutta yazı, geri al ve her şablonda bütün tabloların silinebilmesi."""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OMOFFICE_TEST_DATA"] = tempfile.mkdtemp()
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent, QTextCursor, QTextTable
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from omoffice.mainwindow import MainWindow
from omoffice.templates import build_kind
from omoffice.editor import new_document
from omoffice.common import PageSetup

w = MainWindow(); w.start_screen = False; w.resize(1200, 800); w.show(); app.processEvents()
e = w.editor
ok_all = True


def check(cond, msg):
    global ok_all
    ok_all &= bool(cond)
    print(("  ok  " if cond else "  HATA ") + msg)


def fresh(kind="ara_rapor"):
    w._set_doc(new_document(), PageSetup(), None); app.processEvents()
    build_kind(e, kind, {"title": "Deneme", "author": "Ayşe"}, {"cover": True, "toc": True, "placeholders": True})
    app.processEvents()


def tables():
    out, it = [], e.document().rootFrame().begin()
    while not it.atEnd():
        if isinstance(it.currentFrame(), QTextTable):
            out.append(it.currentFrame())
        it += 1
    return out


def find(prefix):
    for t in tables():
        c = t.cellAt(0, 0).firstCursorPosition()
        c.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        if c.selectedText().startswith(prefix):
            return t


def key(k, text=""):
    for t in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(e, QKeyEvent(t, k, Qt.KeyboardModifier.NoModifier, text))
    app.processEvents()


def typed_size():
    """İmleçte 'X' yazıp boyutunu ölçer, sonra geri alır."""
    key(Qt.Key.Key_X, "X")
    c = e.textCursor()
    c.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
    size = c.charFormat().fontPointSize()
    h = e.document().documentLayout().blockBoundingRect(c.block()).height()
    return size, h


for label, k in (("Backspace", Qt.Key.Key_Backspace), ("Delete", Qt.Key.Key_Delete)):
    fresh(); n = len(tables()); t = find("Sorun")
    e._select_table(t); key(k)
    check(len(tables()) == n - 1 and find("Sorun") is None, f"tüm tabloyu seçip {label} tabloyu siler")
    size, h = typed_size()
    check(size >= 8 and h >= 10, f"  silinen tablonun yerine yazı normal boyutta ({size:.1f} pt, satır {h:.0f} px)")

fresh(); n = len(tables()); t = find("Sorun")
c = QTextCursor(e.document()); c.setPosition(t.lastPosition() + 1); e.setTextCursor(c)
key(Qt.Key.Key_Backspace)
check(e.textCursor().hasComplexSelection() and len(tables()) == n, "tablonun altında 1. Backspace tabloyu seçer")
key(Qt.Key.Key_Backspace)
check(len(tables()) == n - 1, "2. Backspace tabloyu siler")

fresh(); t = find("Bütçe"); rows = t.rows()
c = QTextCursor(e.document()); c.setPosition(t.cellAt(1, 0).firstPosition())
c.setPosition(t.cellAt(2, t.columns() - 1).lastPosition(), QTextCursor.MoveMode.KeepAnchor); e.setTextCursor(c)
key(Qt.Key.Key_Backspace)
check(find("Bütçe") is not None and find("Bütçe").rows() == rows - 2, "iki tam satırı seçip silmek satırları siler")

fresh(); t = find("Bütçe"); cols = t.columns()
c = QTextCursor(e.document()); c.setPosition(t.cellAt(0, 3).firstPosition())
c.setPosition(t.cellAt(t.rows() - 1, 3).lastPosition(), QTextCursor.MoveMode.KeepAnchor); e.setTextCursor(c)
key(Qt.Key.Key_Delete)
check(find("Bütçe").columns() == cols - 1, "tam sütunu seçip silmek sütunu siler")

fresh(); t = find("Bütçe")
c = QTextCursor(e.document()); c.setPosition(t.cellAt(1, 1).firstPosition())
c.setPosition(t.cellAt(2, 2).lastPosition(), QTextCursor.MoveMode.KeepAnchor); e.setTextCursor(c)
key(Qt.Key.Key_Delete)
t = find("Bütçe")
check(t is not None and t.rows() == 6 and t.columns() == 4, "birkaç hücre seçip Delete yalnızca içeriği temizler")

fresh(); n = len(tables()); t = find("1. ARA")
e.setTextCursor(t.cellAt(0, 0).firstCursorPosition()); w.actions["del_table"].trigger(); app.processEvents()
check(len(tables()) == n - 1, "kapak bandı 'Tabloyu Sil' ile silinir")
e.undo(); app.processEvents()
check(len(tables()) == n, "geri al tabloyu geri getirir")

fresh(); n = len(tables()); t = find("Sorun")
c = QTextCursor(e.document()); c.setPosition(t.firstPosition() - 2)
c.setPosition(t.lastPosition() + 2, QTextCursor.MoveMode.KeepAnchor); e.setTextCursor(c)
key(Qt.Key.Key_Delete)
check(len(tables()) == n - 1, "tabloyu çevresiyle seçip Delete siler")

# izleme açıkken eski davranış bozulmasın
fresh(); e.track_changes = True; t = find("Sorun"); n = len(tables())
e._select_table(t); key(Qt.Key.Key_Backspace)
check(len(tables()) == n, "değişiklik izleme açıkken tablo sessizce silinmez")
e.track_changes = False

# her şablonda: tüm tabloları tek tek silmek çökme yapmasın
from omoffice.guide import KINDS
for kind in KINDS:
    fresh(kind)
    for _ in range(40):
        ts = tables()
        if not ts:
            break
        e._select_table(ts[0]); key(Qt.Key.Key_Backspace)
    check(not tables(), f"{kind}: bütün tablolar silinebildi")

e.document().setModified(False); w.close()
print("TABLO", "PASS" if ok_all else "FAIL")
