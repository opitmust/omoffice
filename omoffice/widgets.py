"""Mini araç çubuğu, komut paleti, açıklamalar bölmesi, başlangıç ekranı."""
import datetime
import os

from PySide6.QtCore import Qt, QSize, QPoint, Signal, QTimer
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QToolButton, QDialog, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QWidget, QScrollArea, QPushButton, QPlainTextEdit, QGridLayout,
    QSizePolicy, QApplication,
)

from .common import turkish_lower
from .theme import CURRENT


def _muted():
    return CURRENT["theme"]["muted"]


class MiniBar(QFrame):
    """Metin seçilince imlecin üstünde beliren küçük biçim çubuğu."""

    def __init__(self, actions, extra_widgets=(), parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.NoDropShadowWindowHint)
        self.setObjectName("miniBar")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(1)
        for w in extra_widgets:
            lay.addWidget(w)
        for a in actions:
            if a is None:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet("color: rgba(128,128,128,0.35);")
                lay.addWidget(sep)
                continue
            b = QToolButton()
            b.setDefaultAction(a)
            b.setIconSize(QSize(18, 18))
            b.setAutoRaise(True)
            lay.addWidget(b)
        self.hide_timer = QTimer(self, singleShot=True, interval=7000, timeout=self.hide)

    def show_at(self, global_pt):
        self.adjustSize()
        x = global_pt.x() - self.width() // 3
        y = global_pt.y() - self.height() - 10
        screen = QApplication.screenAt(global_pt)
        if screen is not None:
            g = screen.availableGeometry()
            x = max(g.left() + 4, min(x, g.right() - self.width() - 4))
            if y < g.top():
                y = global_pt.y() + 28
        self.move(x, y)
        self.show()
        self.raise_()
        self.hide_timer.start()


def _fuzzy(query, text):
    q = turkish_lower(query).split()
    t = turkish_lower(text)
    return all(w in t for w in q)


class CommandPalette(QDialog):
    """Her komutu adıyla arayıp çalıştırmak için (Ctrl+Shift+P / Alt+Q)."""

    def __init__(self, entries, parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.entries = entries   # [(ad, kategori, QAction)]
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("palette")
        outer.addWidget(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Ne yapmak istiyorsunuz?  (ör. tablo, filigran, pdf, koyu tema)")
        f = self.edit.font()
        f.setPointSize(12)
        self.edit.setFont(f)
        self.edit.setMinimumHeight(34)
        lay.addWidget(self.edit)
        self.list = QListWidget()
        self.list.setMinimumHeight(340)
        lay.addWidget(self.list)
        hint = QLabel("↑↓ seç · Enter çalıştır · Esc kapat")
        hint.setProperty("hint", True)
        hint.setStyleSheet("font-size: 8pt;")
        lay.addWidget(hint)
        self.edit.textChanged.connect(self.refresh)
        self.edit.returnPressed.connect(self.run_current)
        self.list.itemActivated.connect(lambda _: self.run_current())
        self.edit.installEventFilter(self)
        self.resize(560, 440)
        self.refresh()

    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() == e.Type.KeyPress and e.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            row = self.list.currentRow() + (1 if e.key() == Qt.Key.Key_Down else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
            return True
        return super().eventFilter(obj, e)

    def refresh(self):
        q = self.edit.text().strip()
        self.list.clear()
        for name, cat, act in self.entries:
            hay = f"{name} {cat} {act.toolTip()} {act.property('keywords') or ''}"
            if q and not _fuzzy(q, hay):
                continue
            sc = act.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            item = QListWidgetItem(f"{name}" + (f"      {sc}" if sc else ""))
            item.setToolTip(cat)
            item.setData(Qt.ItemDataRole.UserRole, act)
            if not act.isEnabled():
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            if not act.icon().isNull():
                item.setIcon(act.icon())
            self.list.addItem(item)
        for i in range(self.list.count()):
            if self.list.item(i).flags() & Qt.ItemFlag.ItemIsEnabled:
                self.list.setCurrentRow(i)
                break

    def run_current(self):
        item = self.list.currentItem()
        if item is None:
            return
        act = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if act.isCheckable():
            act.toggle()
        else:
            QTimer.singleShot(0, act.trigger)

    def open_centered(self, parent):
        g = parent.geometry()
        self.move(g.x() + (g.width() - self.width()) // 2, g.y() + 90)
        self.edit.clear()
        self.refresh()
        self.show()
        self.edit.setFocus()


class CommentsPanel(QWidget):
    """Açıklamaları kart olarak gösteren yan bölme."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 2)
        self.count = QLabel()
        top.addWidget(self.count)
        top.addStretch(1)
        self.show_resolved = QToolButton()
        self.show_resolved.setText("Çözülenler")
        self.show_resolved.setCheckable(True)
        self.show_resolved.toggled.connect(self.refresh)
        top.addWidget(self.show_resolved)
        lay.addLayout(top)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        lay.addWidget(self.area)
        self.host = QWidget()
        self.host.setObjectName("cardHost")
        self.cards = QVBoxLayout(self.host)
        self.cards.setContentsMargins(8, 4, 8, 8)
        self.cards.setSpacing(8)
        self.area.setWidget(self.host)
        editor.commentsChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        while self.cards.count():
            it = self.cards.takeAt(0)
            w = it.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        e = self.editor
        ranges = e.comment_ranges()
        doc = e.document()
        shown = 0
        open_count = 0
        for cid, (a, b) in ranges.items():
            info = e.comments.get(cid)
            if info is None:
                continue
            if not info.get("resolved"):
                open_count += 1
            elif not self.show_resolved.isChecked():
                continue
            shown += 1
            self.cards.addWidget(self._card(cid, info, doc, a, b))
        if not shown:
            empty = QLabel("Henüz açıklama yok.\n\nMetin seçip Gözden Geçir › Yeni Açıklama\n"
                           "(Ctrl+Alt+M) ile ekleyin.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setProperty("hint", True)
            empty.setStyleSheet("padding: 30px 8px;")
            empty.setWordWrap(True)
            self.cards.addWidget(empty)
        self.cards.addStretch(1)
        self.count.setText(f"<b>{open_count}</b> açık açıklama")

    def _card(self, cid, info, doc, a, b):
        e = self.editor
        card = QFrame()
        card.setObjectName("card")
        card.setProperty("active", "true" if cid == e.active_comment else "false")
        v = QVBoxLayout(card)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)
        head = QHBoxLayout()
        initials = "".join(w[:1] for w in (info.get("author") or "?").split()[:2]).upper()
        av = QLabel(initials or "?")
        av.setFixedSize(26, 26)
        av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        from .spell import author_color
        av.setStyleSheet(f"background: {author_color(info.get('author')).name()}; color: white; "
                         f"border-radius: 13px; font-weight: 600;")
        head.addWidget(av)
        date = info.get("date") or ""
        try:
            date = datetime.datetime.fromisoformat(date.rstrip("Z")).strftime("%d.%m.%Y %H:%M")
        except ValueError:
            pass
        who = QLabel(f"<b>{info.get('author') or 'Bilinmeyen'}</b><br><span style='color:{_muted()};font-size:8pt'>{date}</span>")
        head.addWidget(who, 1)
        v.addLayout(head)
        from PySide6.QtGui import QTextCursor
        c = QTextCursor(doc)
        c.setPosition(a)
        c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        quote = c.selectedText().replace(" ", " ")
        if len(quote) > 80:
            quote = quote[:77] + "…"
        q = QLabel(f"“{quote}”")
        q.setWordWrap(True)
        q.setProperty("hint", True)
        q.setStyleSheet("font-style: italic; border-left: 3px solid rgba(128,128,128,0.5); padding-left: 6px;")
        v.addWidget(q)
        body = QLabel(info.get("text") or "")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if info.get("resolved"):
            body.setProperty("hint", True)
        v.addWidget(body)
        row = QHBoxLayout()
        for label, fn in (("Git", lambda: e.select_comment(cid)),
                          ("Düzenle", lambda: self._edit(cid)),
                          ("Yeniden aç" if info.get("resolved") else "Çözüldü",
                           lambda: e.resolve_comment(cid, not info.get("resolved"))),
                          ("Sil", lambda: e.delete_comment(cid))):
            btn = QToolButton()
            btn.setText(label)
            btn.clicked.connect(fn)
            row.addWidget(btn)
        row.addStretch(1)
        v.addLayout(row)
        card.mousePressEvent = lambda _ev: e.select_comment(cid)
        return card

    def _edit(self, cid):
        text = ask_text(self, "Açıklamayı Düzenle", self.editor.comments[cid]["text"])
        if text is not None:
            self.editor.edit_comment(cid, text)


def ask_text(parent, title, text="", label=""):
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    v = QVBoxLayout(dlg)
    if label:
        v.addWidget(QLabel(label))
    ed = QPlainTextEdit(text)
    ed.setMinimumSize(380, 120)
    v.addWidget(ed)
    row = QHBoxLayout()
    row.addStretch(1)
    ok = QPushButton("Tamam")
    ok.setObjectName("primary")
    cancel = QPushButton("İptal")
    ok.clicked.connect(dlg.accept)
    cancel.clicked.connect(dlg.reject)
    row.addWidget(cancel)
    row.addWidget(ok)
    v.addLayout(row)
    ed.setFocus()
    if dlg.exec() and ed.toPlainText().strip():
        return ed.toPlainText().strip()
    return None


TEMPLATES = [
    ("Boş belge", "Temiz bir sayfa", ""),
    ("Mektup", "Resmî yazı / dilekçe düzeni", ""),
    ("Özgeçmiş", "Bölümlü, maddeli CV", ""),
    ("Rapor", "İçindekiler, başlıklar, tablo", ""),
    ("Toplantı notları", "Gündem ve kararlar", ""),
]


class StartDialog(QDialog):
    """Açılış ekranı: şablonlar ve son belgeler."""

    def __init__(self, recent, icon_fn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OmOffice — Başlangıç")
        self.choice = None
        self.resize(900, 560)
        h = QHBoxLayout(self)
        h.setContentsMargins(28, 24, 28, 24)
        h.setSpacing(28)
        left = QVBoxLayout()
        hour = datetime.datetime.now().hour
        greet = "Günaydın" if 5 <= hour < 12 else "İyi günler" if hour < 18 else "İyi akşamlar"
        t = QLabel(f"<span style='font-size:22pt;font-weight:600'>{greet}</span><br>"
                   "<span>Yeni bir belge başlatın ya da kaldığınız yerden devam edin.</span>")
        left.addWidget(t)
        left.addSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (name, desc, ch) in enumerate(TEMPLATES):
            b = QToolButton()
            b.setText(f"{name}\n{desc}")
            b.setIcon(icon_fn(ch))
            b.setIconSize(QSize(40, 40))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFixedSize(168, 132)
            b.setStyleSheet("QToolButton { border: 1px solid rgba(128,128,128,0.35); border-radius: 10px; "
                            "padding: 10px; } QToolButton:hover { border: 2px solid palette(highlight); }")
            b.clicked.connect(lambda _=False, n=name: self._pick(("template", n)))
            grid.addWidget(b, i // 3, i % 3)
        left.addLayout(grid)
        left.addStretch(1)
        h.addLayout(left, 3)
        right = QVBoxLayout()
        right.addWidget(QLabel("<b>Son belgeler</b>"))
        self.recent = QListWidget()
        for f in recent:
            it = QListWidgetItem(f"{os.path.basename(f)}\n{os.path.dirname(f)}")
            it.setData(Qt.ItemDataRole.UserRole, f)
            self.recent.addItem(it)
        if not recent:
            it = QListWidgetItem("(henüz yok)")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent.addItem(it)
        self.recent.setSpacing(3)
        self.recent.itemActivated.connect(lambda it: self._pick(("open", it.data(Qt.ItemDataRole.UserRole))))
        self.recent.itemClicked.connect(lambda it: self._pick(("open", it.data(Qt.ItemDataRole.UserRole)))
                                        if it.data(Qt.ItemDataRole.UserRole) else None)
        right.addWidget(self.recent, 1)
        browse = QPushButton("Bilgisayardan aç…")
        browse.clicked.connect(lambda: self._pick(("browse", None)))
        right.addWidget(browse)
        h.addLayout(right, 2)

    def _pick(self, choice):
        self.choice = choice
        self.accept()
