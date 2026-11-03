"""Rehber paneli: bölüme göre ipuçları, örnek ifadeler, kontrol listesi, kaynak ekleme."""
import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QTextBlockFormat, QTextCharFormat, QTextCursor, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QToolButton, QFrame,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
)

from .common import PLACEHOLDER_PROP, STYLE_PROP, pt2px, turkish_lower, turkish_sort_key
from .guide import (
    KINDS, GENERAL_TIPS, PHRASE_BANK, CITATION_STYLES, REF_TYPES, match_section, format_reference, in_text,
)
from .spell import WORD_RE

REF_HEADINGS = ("kaynakça", "kaynaklar", "references", "bibliyografya", "works cited")


def _norm(text):
    return turkish_lower(re.sub(r"^[\d.\s]+", "", text or "")).strip()


def sections(editor):
    """Başlıklara göre bölümler: [(başlık, düzey, başlık_bloğu, [gövde blokları])]."""
    out = []
    block = editor.document().begin()
    cur = None
    while block.isValid():
        lvl = block.blockFormat().headingLevel()
        if lvl and block.text().strip():
            cur = (block.text().strip(), lvl, block, [])
            out.append(cur)
        elif cur is not None:
            cur[3].append(block)
        block = block.next()
    return out


def _text_without_placeholders(block):
    parts = []
    it = block.begin()
    while not it.atEnd():
        f = it.fragment()
        if not f.charFormat().hasProperty(PLACEHOLDER_PROP):
            parts.append(f.text())
        it += 1
    return "".join(parts)


def _insert_marked(cursor, text, base):
    """'*italik*' işaretlerini italik biçime çevirerek ekler."""
    for i, part in enumerate(text.split("*")):
        if not part:
            continue
        f = QTextCharFormat(base)
        f.setFontItalic(i % 2 == 1)
        cursor.insertText(part, f)


def add_reference(editor, style, ref):
    """Kaynakça bölümüne kaynağı ekler; metin içi atıf metnini döndürür."""
    doc = editor.document()
    secs = sections(editor)
    target = next((s for s in secs if _norm(s[0]).startswith(REF_HEADINGS)), None)
    c = QTextCursor(doc)
    c.beginEditBlock()
    if target is None:
        c.movePosition(QTextCursor.MoveOperation.End)
        bf = QTextBlockFormat()
        c.insertBlock(bf, QTextCharFormat())
        editor_cursor = editor.textCursor()
        editor.setTextCursor(c)
        editor.apply_style("Başlık 1")
        c = editor.textCursor()
        c.insertText("Kaynakça")
        editor.setTextCursor(editor_cursor)
        secs = sections(editor)
        target = next(s for s in secs if _norm(s[0]).startswith(REF_HEADINGS))
    head_block, body = target[2], list(target[3])
    # yer tutucuları kaldır
    for b in reversed(body):
        if b.text().strip() and not _text_without_placeholders(b).strip():
            bc = QTextCursor(b)
            bc.select(QTextCursor.SelectionType.BlockUnderCursor)
            bc.removeSelectedText()
    secs = sections(editor)
    target = next(s for s in secs if _norm(s[0]).startswith(REF_HEADINGS))
    entries = [b for b in target[3] if b.text().strip()]
    number = len(entries) + 1
    text = format_reference(style, ref)
    if style.startswith("IEEE"):
        text = f"[{number}] {text}"
        after = entries[-1] if entries else target[2]
    else:
        key = turkish_sort_key(text.replace("*", ""))
        after = target[2]
        for b in entries:
            if turkish_sort_key(b.text()) <= key:
                after = b
    ic = QTextCursor(after)
    ic.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    bf = QTextBlockFormat()
    bf.setProperty(STYLE_PROP, "Normal")
    bf.setBottomMargin(pt2px(6))
    if style.startswith("IEEE"):
        bf.setLeftMargin(pt2px(28))
        bf.setTextIndent(-pt2px(28))
    else:
        bf.setLeftMargin(pt2px(36))
        bf.setTextIndent(-pt2px(36))
    base = QTextCharFormat()
    base.setFontPointSize(11)
    base.setFontWeight(QFont.Weight.Normal)
    base.setForeground(QColor("#000000"))
    ic.insertBlock(bf, base)
    _insert_marked(ic, text, base)
    c.endEditBlock()
    return in_text(style, ref, number)


class CitationDialog(QDialog):
    def __init__(self, style, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kaynak Ekle")
        v = QVBoxLayout(self)
        f = QFormLayout()
        self.style = QComboBox()
        self.style.addItems(CITATION_STYLES)
        if style in CITATION_STYLES:
            self.style.setCurrentText(style)
        self.kind = QComboBox()
        self.kind.addItems(REF_TYPES)
        self.fields = {}
        f.addRow("Atıf stili:", self.style)
        f.addRow("Kaynak türü:", self.kind)
        for key, label, ph in (("authors", "Yazar(lar)", "Soyad, A.; Soyad, B. C."),
                               ("year", "Yıl", "2024"), ("title", "Başlık", "Makalenin/kitabın başlığı"),
                               ("source", "Dergi / Site", "Dergi adı ya da web sitesi"),
                               ("volume", "Cilt", ""), ("issue", "Sayı", ""), ("pages", "Sayfalar", "12-34"),
                               ("publisher", "Yayınevi", "Kitaplar için"), ("doi", "DOI", "10.xxxx/xxxxx"),
                               ("url", "Web adresi", "https://…"), ("accessed", "Erişim tarihi", "")):
            e = QLineEdit()
            e.setPlaceholderText(ph)
            e.textChanged.connect(self._preview)
            self.fields[key] = e
            f.addRow(label + ":", e)
        v.addLayout(f)
        self.prev = QLabel()
        self.prev.setWordWrap(True)
        self.prev.setMinimumHeight(60)
        self.prev.setStyleSheet("border: 1px dashed rgba(128,128,128,0.6); padding: 8px; border-radius: 6px;")
        v.addWidget(QLabel("<b>Önizleme</b>"))
        v.addWidget(self.prev)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Ekle")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.style.currentTextChanged.connect(self._preview)
        self.kind.currentTextChanged.connect(self._preview)
        self._preview()

    def ref(self):
        r = {k: e.text().strip() for k, e in self.fields.items()}
        r["type"] = self.kind.currentText()
        return r

    def _preview(self):
        r = self.ref()
        html = format_reference(self.style.currentText(), r)
        html = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", html)
        self.prev.setText(f"{html}<br><br><span style='color:gray'>Metin içi atıf: "
                          f"{in_text(self.style.currentText(), r, 1)}</span>")


class GuidePanel(QWidget):
    citationRequested = Signal()
    fixCapsRequested = Signal()
    tocRequested = Signal()

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel("Belge türü:"))
        self.kind = QComboBox()
        for k, info in KINDS.items():
            self.kind.addItem(info["name"], k)
        self.kind.activated.connect(self._kind_changed)
        row.addWidget(self.kind, 1)
        v.addLayout(row)

        self.section_card = self._card("Bulunduğunuz bölüm")
        v.addWidget(self.section_card)
        self.check_card = self._card("Kontrol listesi")
        v.addWidget(self.check_card)
        tools = self._card("Araçlar")
        for label, sig in (("Kaynak ekle (APA / IEEE / MLA)…", self.citationRequested),
                           ("Büyük harf hatalarını düzelt", self.fixCapsRequested),
                           ("İçindekileri oluştur / güncelle", self.tocRequested)):
            b = QPushButton(label)
            b.clicked.connect(sig.emit)
            tools.body.addWidget(b)
        v.addWidget(tools)
        phr = self._card("İfade bankası")
        self.phrase_cat = QComboBox()
        self.phrase_cat.addItems(list(PHRASE_BANK))
        self.phrase_cat.currentTextChanged.connect(self._fill_phrases)
        phr.body.addWidget(self.phrase_cat)
        self.phrase_box = QVBoxLayout()
        phr.body.addLayout(self.phrase_box)
        v.addWidget(phr)
        self.tips_card = self._card("Bu tür için ipuçları")
        v.addWidget(self.tips_card)
        v.addStretch(1)
        self._fill_phrases(self.phrase_cat.currentText())
        self.timer = QTimer(self, singleShot=True, interval=500, timeout=self.refresh)
        editor.cursorPositionChanged.connect(self.timer.start)
        editor.documentReplaced.connect(self._doc_replaced)
        self._doc_replaced()

    def _doc_replaced(self):
        self.editor.document().contentsChanged.connect(self.timer.start)
        self.timer.start()

    def _card(self, title):
        f = QFrame()
        f.setObjectName("group")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(5)
        t = QLabel(title.upper())
        t.setObjectName("groupTitle")
        lay.addWidget(t)
        body = QVBoxLayout()
        body.setSpacing(4)
        lay.addLayout(body)
        f.body = body
        return f

    @staticmethod
    def _clear(layout):
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif it.layout() is not None:
                GuidePanel._clear(it.layout())

    def _label(self, text, muted=False):
        lb = QLabel(text)
        lb.setWordWrap(True)
        lb.setTextFormat(Qt.TextFormat.RichText)
        if muted:
            lb.setStyleSheet("color: gray;")
        return lb

    def _insert_row(self, text):
        row = QHBoxLayout()
        lb = self._label(f"<i>{text}</i>")
        b = QToolButton()
        b.setText("Ekle")
        b.setToolTip("İmlecin olduğu yere ekle")
        b.clicked.connect(lambda: self._insert(text))
        row.addWidget(lb, 1)
        row.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        return row

    def _insert(self, text):
        e = self.editor
        if e._selection_is_placeholder() and not e.textCursor().hasSelection():
            e._select_placeholder()
        e.type_text(text.replace("…", "").replace("  ", " ").strip() + " ")

    def _fill_phrases(self, cat):
        self._clear(self.phrase_box)
        for p in PHRASE_BANK.get(cat, []):
            self.phrase_box.addLayout(self._insert_row(p))

    def _kind_changed(self, _i):
        info = dict(getattr(self.editor, "doc_info", {}) or {})
        info["kind"] = self.kind.currentData()
        self.editor.doc_info = info
        self.editor.document().setModified(True)
        self.refresh()

    def current_section(self):
        pos = self.editor.textCursor().position()
        name = None
        for title, lvl, block, _ in sections(self.editor):
            if block.position() <= pos:
                name = title
            else:
                break
        return name

    def refresh(self):
        if not self.isVisible():
            return
        e = self.editor
        info_key = (getattr(e, "doc_info", {}) or {}).get("kind") or "bos"
        if info_key not in KINDS:
            info_key = "bos"
        idx = self.kind.findData(info_key)
        if idx >= 0 and idx != self.kind.currentIndex():
            self.kind.setCurrentIndex(idx)
        kind = KINDS[info_key]

        # Bölüm ipuçları
        body = self.section_card.body
        self._clear(body)
        sec = self.current_section()
        tips, examples = match_section(sec) if sec else (None, None)
        if sec:
            body.addWidget(self._label(f"<b>{sec}</b>"))
        if tips is None:
            hint = next((h for t, _, h in kind["sections"] if sec and _norm(t) == _norm(sec)), None)
            if hint:
                body.addWidget(self._label("• " + hint))
            elif not sec:
                body.addWidget(self._label("İmleci bir başlığın altına götürün; o bölüme özel ipuçları burada "
                                           "görünür.", True))
            else:
                body.addWidget(self._label("Bu bölüm için özel ipucu yok. Aşağıdaki ifade bankasından "
                                           "yararlanabilirsiniz.", True))
        else:
            for t in tips:
                body.addWidget(self._label("• " + t))
            if examples:
                body.addWidget(self._label("<b>Örnek cümleler</b>"))
                for ex in examples:
                    body.addLayout(self._insert_row(ex))

        # Kontrol listesi
        cb = self.check_card.body
        self._clear(cb)
        for ok, text in self.checks(kind, info_key):
            icon = "<span style='color:#2E7D32'>✔</span>" if ok else "<span style='color:#C77700'>●</span>"
            cb.addWidget(self._label(f"{icon} {text}"))

        tb = self.tips_card.body
        self._clear(tb)
        for t in kind.get("tips", []) + GENERAL_TIPS:
            tb.addWidget(self._label("• " + t, muted=False))

    def checks(self, kind, key):
        e = self.editor
        out = []
        text = e.document().toPlainText()
        words = len(WORD_RE.findall(text))
        out.append((True, f"{words} sözcük · yaklaşık {max(1, round(words / 230))} dk okuma"))
        secs = sections(e)
        have = {_norm(t) for t, *_ in secs}
        if kind["sections"]:
            missing = [t for t, _, _ in kind["sections"] if _norm(t) not in have]
            out.append((not missing, "Tüm bölümler var" if not missing else
                        "Eksik bölüm: " + ", ".join(missing[:4]) + ("…" if len(missing) > 4 else "")))
        ph = e.placeholder_count()
        out.append((ph == 0, "Doldurulmamış yer tutucu yok" if ph == 0 else f"{ph} yer tutucu henüz doldurulmadı"))
        for t, _, block, body in secs:
            n = _norm(t)
            if n in ("özet", "abstract"):
                w = sum(len(WORD_RE.findall(_text_without_placeholders(b))) for b in body
                        if not b.text().lower().startswith(("anahtar", "keywords")))
                lo, hi = (250, 500) if key == "tez" else (150, 250)
                if key in ("makale", "tez", "arastirma", "literatur", "proje"):
                    out.append((lo <= w <= hi, f"{t}: {w} sözcük (önerilen {lo}–{hi})"))
            if n.startswith(REF_HEADINGS):
                refs = [b for b in body if _text_without_placeholders(b).strip()]
                out.append((bool(refs), f"Kaynakça: {len(refs)} kaynak" if refs else "Kaynakça boş"))
        block = e.document().begin()
        while block.isValid():
            bt = block.text()
            if bt.lower().startswith(("anahtar kelimeler", "keywords")):
                vals = [x for x in _text_without_placeholders(block).split(":", 1)[-1].split(",") if x.strip()]
                out.append((3 <= len(vals) <= 5, f"Anahtar kelime sayısı: {len(vals)} (önerilen 3–5)"))
                break
            block = block.next()
        caps = len(e.fix_capitalization(apply=False))
        out.append((caps == 0, "Büyük harf hatası yok" if caps == 0 else f"{caps} olası büyük harf hatası"))
        sp = e.spell
        if sp is not None and sp.ready:
            bad = sum(1 for m in WORD_RE.finditer(text[:200000]) if not sp.check(m.group()))
            out.append((bad == 0, "Yazım hatası yok" if bad == 0 else f"{bad} olası yazım hatası (F7 ile gezin)"))
        return out

    def showEvent(self, ev):
        super().showEvent(ev)
        self.timer.start()
