"""İletişim kutuları."""
import re

from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QTextCursor, QTextDocument, QTextBlockFormat, QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QPushButton, QTabWidget, QWidget,
    QPlainTextEdit, QGroupBox, QRadioButton, QTextEdit, QToolButton,
)

from .common import PAPER_SIZES, MARGIN_PRESETS, pt2px, px2pt, mm2px, px2mm

LH = QTextBlockFormat.LineHeightTypes


def _buttons(dlg, layout):
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("Tamam")
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    layout.addWidget(bb)


def _mm_spin(value, maximum=600.0):
    s = QDoubleSpinBox()
    s.setRange(0, maximum)
    s.setDecimals(1)
    s.setSuffix(" mm")
    s.setValue(value)
    return s


class PageSetupDialog(QDialog):
    def __init__(self, setup, parent=None, tab=0):
        super().__init__(parent)
        self.setWindowTitle("Sayfa Yapısı")
        self.setup = setup.copy()
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)

        # Kağıt
        w = QWidget()
        f = QFormLayout(w)
        self.paper = QComboBox()
        self.paper.addItems(list(PAPER_SIZES) + ["Özel"])
        self.width = _mm_spin(setup.width_mm, 1000)
        self.height = _mm_spin(setup.height_mm, 1000)
        self.portrait = QRadioButton("Dikey")
        self.landscape = QRadioButton("Yatay")
        (self.landscape if setup.landscape else self.portrait).setChecked(True)
        ori = QHBoxLayout()
        ori.addWidget(self.portrait)
        ori.addWidget(self.landscape)
        f.addRow("Kağıt boyutu:", self.paper)
        f.addRow("Genişlik:", self.width)
        f.addRow("Yükseklik:", self.height)
        f.addRow("Yönlendirme:", ori)
        self._sync_paper_combo()
        self.paper.currentTextChanged.connect(self._paper_changed)
        self.portrait.toggled.connect(self._orientation_changed)
        tabs.addTab(w, "Kağıt")

        # Kenar boşlukları
        w = QWidget()
        f = QFormLayout(w)
        self.preset = QComboBox()
        self.preset.addItems(["(seçin)"] + list(MARGIN_PRESETS))
        self.top = _mm_spin(setup.top_mm)
        self.bottom = _mm_spin(setup.bottom_mm)
        self.left = _mm_spin(setup.left_mm)
        self.right = _mm_spin(setup.right_mm)
        f.addRow("Hazır ayar:", self.preset)
        f.addRow("Üst:", self.top)
        f.addRow("Alt:", self.bottom)
        f.addRow("Sol:", self.left)
        f.addRow("Sağ:", self.right)
        self.preset.currentTextChanged.connect(self._preset)
        tabs.addTab(w, "Kenar Boşlukları")

        # Üst/alt bilgi
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("Alan kodları: <b>{SAYFA}</b> = sayfa numarası, <b>{TOPLAM}</b> = toplam sayfa"))
        self.header = QPlainTextEdit(setup.header_text)
        self.header.setMaximumHeight(70)
        self.footer = QPlainTextEdit(setup.footer_text)
        self.footer.setMaximumHeight(70)
        self.header_align = self._align_combo(setup.header_align)
        self.footer_align = self._align_combo(setup.footer_align)
        g = QGridLayout()
        g.addWidget(QLabel("Üst bilgi:"), 0, 0)
        g.addWidget(self.header, 0, 1)
        g.addWidget(self.header_align, 0, 2, Qt.AlignmentFlag.AlignTop)
        g.addWidget(QLabel("Alt bilgi:"), 1, 0)
        g.addWidget(self.footer, 1, 1)
        g.addWidget(self.footer_align, 1, 2, Qt.AlignmentFlag.AlignTop)
        v.addLayout(g)
        row = QHBoxLayout()
        for label, text in (("Sayfa X", "Sayfa {SAYFA}"), ("Sayfa X / Y", "Sayfa {SAYFA} / {TOPLAM}"),
                            ("Yalnız numara", "{SAYFA}")):
            b = QPushButton(f"Alt bilgiye: {label}")
            b.clicked.connect(lambda _=False, t=text: self.footer.setPlainText(t))
            row.addWidget(b)
        v.addLayout(row)
        self.diff_first = QCheckBox("İlk sayfada üst/alt bilgi gösterme")
        self.diff_first.setChecked(setup.different_first)
        v.addWidget(self.diff_first)
        self.clear_pages = False
        n_over = len([k for k, ov in setup.hf_pages.items() if ov])
        info = QLabel("Buradaki metinler <b>varsayılandır</b> (tüm sayfalar). Tek bir sayfayı değiştirmek ya da "
                      "silmek için belgede o sayfanın üst/alt bilgisinin üzerine gelin: ✎ düzenle, ✕ sil."
                      + (f"<br><b>{n_over}</b> sayfada sayfaya özel ayar var." if n_over else ""))
        info.setWordWrap(True)
        info.setProperty("hint", True)
        v.addWidget(info)
        if n_over:
            clr = QPushButton("Sayfaya özel ayarların hepsini temizle")
            clr.clicked.connect(lambda: (setattr(self, "clear_pages", True), clr.setEnabled(False),
                                         clr.setText("Temizlenecek (Tamam'a basın)")))
            v.addWidget(clr)
        tabs.addTab(w, "Üst / Alt Bilgi")
        tabs.setCurrentIndex(tab)
        _buttons(self, lay)

    @staticmethod
    def _align_combo(value):
        c = QComboBox()
        for label, key in (("Sola", "left"), ("Ortaya", "center"), ("Sağa", "right")):
            c.addItem(label, key)
        c.setCurrentIndex({"left": 0, "center": 1, "right": 2}.get(value, 1))
        return c

    def _sync_paper_combo(self):
        w, h = sorted((self.width.value(), self.height.value()))
        for name, (pw, ph) in PAPER_SIZES.items():
            if abs(pw - w) < 0.6 and abs(ph - h) < 0.6:
                self.paper.setCurrentText(name)
                return
        self.paper.setCurrentText("Özel")

    def _paper_changed(self, name):
        if name in PAPER_SIZES:
            w, h = PAPER_SIZES[name]
            if self.landscape.isChecked():
                w, h = h, w
            self.width.setValue(w)
            self.height.setValue(h)

    def _orientation_changed(self):
        w, h = self.width.value(), self.height.value()
        if self.landscape.isChecked() != (w > h):
            self.width.setValue(h)
            self.height.setValue(w)

    def _preset(self, name):
        if name in MARGIN_PRESETS:
            t, b, l, r = MARGIN_PRESETS[name]
            self.top.setValue(t)
            self.bottom.setValue(b)
            self.left.setValue(l)
            self.right.setValue(r)

    def result_setup(self):
        s = self.setup
        s.width_mm, s.height_mm = self.width.value(), self.height.value()
        s.top_mm, s.bottom_mm = self.top.value(), self.bottom.value()
        s.left_mm, s.right_mm = self.left.value(), self.right.value()
        s.header_text = self.header.toPlainText()
        s.footer_text = self.footer.toPlainText()
        s.header_align = self.header_align.currentData()
        s.footer_align = self.footer_align.currentData()
        s.different_first = self.diff_first.isChecked()
        if self.clear_pages:
            s.hf_pages = {}
        return s


class HeaderFooterDialog(QDialog):
    """Tek bir sayfanın üst/alt bilgisini düzenleme; kapsam seçilebilir."""

    def __init__(self, which, page_no, total, text, align, scope="page", parent=None):
        super().__init__(parent)
        name = "Üst Bilgi" if which == "header" else "Alt Bilgi"
        self.setWindowTitle(f"{name} — {page_no}. sayfa")
        self.removed = False
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{name}</b> &nbsp;<span>{page_no}. sayfa / toplam {total}</span>"))
        self.text = QPlainTextEdit(text)
        self.text.setMinimumSize(420, 80)
        lay.addWidget(self.text)
        row = QHBoxLayout()
        for label, token in (("+ Sayfa no", "{SAYFA}"), ("+ Toplam sayfa", "{TOPLAM}"),
                             ("+ Sayfa X / Y", "Sayfa {SAYFA} / {TOPLAM}")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, t=token: self.text.insertPlainText(t))
            row.addWidget(b)
        row.addStretch(1)
        self.align = QComboBox()
        for lbl, key in (("Sola", "left"), ("Ortaya", "center"), ("Sağa", "right")):
            self.align.addItem(lbl, key)
        self.align.setCurrentIndex({"left": 0, "center": 1, "right": 2}.get(align, 1))
        row.addWidget(QLabel("Hizalama:"))
        row.addWidget(self.align)
        lay.addLayout(row)
        box = QGroupBox("Nerede uygulansın?")
        bl = QVBoxLayout(box)
        self.r_page = QRadioButton(f"Yalnızca bu sayfada ({page_no}. sayfa)")
        self.r_from = QRadioButton(f"Bu sayfa ve sonrasında ({page_no}. sayfadan itibaren)")
        self.r_all = QRadioButton("Tüm sayfalarda (sayfaya özel ayarlar silinir)")
        for r in (self.r_page, self.r_from, self.r_all):
            bl.addWidget(r)
        {"page": self.r_page, "from": self.r_from, "all": self.r_all}.get(scope, self.r_page).setChecked(True)
        lay.addWidget(box)
        hint = QLabel("İpucu: Sayfadaki üst/alt bilginin üzerine gelince çıkan ✕ ile o sayfadan hemen "
                      "silebilirsiniz; sağ tıkla daha fazla seçenek var.")
        hint.setWordWrap(True)
        hint.setProperty("hint", True)
        hint.setStyleSheet("font-size: 8pt;")
        lay.addWidget(hint)
        bb = QHBoxLayout()
        rm = QPushButton("Bu sayfadan kaldır")
        rm.clicked.connect(self._remove)
        bb.addWidget(rm)
        bb.addStretch(1)
        cancel = QPushButton("İptal")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Uygula")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bb.addWidget(cancel)
        bb.addWidget(ok)
        lay.addLayout(bb)
        self.text.setFocus()

    def _remove(self):
        self.removed = True
        self.accept()

    def scope(self):
        return "from" if self.r_from.isChecked() else "all" if self.r_all.isChecked() else "page"


class ParagraphDialog(QDialog):
    def __init__(self, bf, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paragraf")
        self.bf = QTextBlockFormat(bf)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.align = QComboBox()
        for label, a in (("Sola", Qt.AlignmentFlag.AlignLeft), ("Ortala", Qt.AlignmentFlag.AlignHCenter),
                         ("Sağa", Qt.AlignmentFlag.AlignRight), ("İki yana", Qt.AlignmentFlag.AlignJustify)):
            self.align.addItem(label, a)
        al = bf.alignment()
        self.align.setCurrentIndex(1 if al & Qt.AlignmentFlag.AlignHCenter else 3 if al & Qt.AlignmentFlag.AlignJustify
                                   else 2 if al & Qt.AlignmentFlag.AlignRight else 0)
        self.left = self._cm(px2mm(bf.leftMargin()) / 10)
        self.right = self._cm(px2mm(bf.rightMargin()) / 10)
        self.first = self._cm(px2mm(bf.textIndent()) / 10, -20)
        self.before = self._pt(px2pt(bf.topMargin()))
        self.after = self._pt(px2pt(bf.bottomMargin()))
        self.spacing = QComboBox()
        self.spacing.addItems(["Tek (1,0)", "1,15", "1,5 satır", "Çift (2,0)", "Özel %"])
        self.custom = QSpinBox()
        self.custom.setRange(50, 500)
        self.custom.setSuffix(" %")
        lh = bf.lineHeight() if bf.lineHeightType() == LH.ProportionalHeight.value else 100
        self.custom.setValue(int(lh))
        idx = {100: 0, 115: 1, 150: 2, 200: 3}.get(int(round(lh)), 4)
        self.spacing.setCurrentIndex(idx)
        self.spacing.currentIndexChanged.connect(
            lambda i: self.custom.setValue([100, 115, 150, 200][i]) if i < 4 else None)
        self.keep = QCheckBox("Önce sayfa sonu")
        self.keep.setChecked(bool(bf.pageBreakPolicy() & QTextBlockFormat.PageBreakFlag.PageBreak_AlwaysBefore))
        f.addRow("Hizalama:", self.align)
        f.addRow("Sol girinti:", self.left)
        f.addRow("Sağ girinti:", self.right)
        f.addRow("İlk satır (negatif = asılı):", self.first)
        f.addRow("Önce:", self.before)
        f.addRow("Sonra:", self.after)
        f.addRow("Satır aralığı:", self.spacing)
        f.addRow("", self.custom)
        f.addRow("", self.keep)
        lay.addLayout(f)
        _buttons(self, lay)

    @staticmethod
    def _cm(v, minimum=0):
        s = QDoubleSpinBox()
        s.setRange(minimum, 30)
        s.setDecimals(2)
        s.setSingleStep(0.25)
        s.setSuffix(" cm")
        s.setValue(v)
        return s

    @staticmethod
    def _pt(v):
        s = QDoubleSpinBox()
        s.setRange(0, 200)
        s.setDecimals(1)
        s.setSuffix(" nk")
        s.setValue(v)
        return s

    def result_format(self):
        bf = QTextBlockFormat()
        bf.setAlignment(self.align.currentData())
        bf.setLeftMargin(mm2px(self.left.value() * 10))
        bf.setRightMargin(mm2px(self.right.value() * 10))
        bf.setTextIndent(mm2px(self.first.value() * 10))
        bf.setTopMargin(pt2px(self.before.value()))
        bf.setBottomMargin(pt2px(self.after.value()))
        bf.setLineHeight(self.custom.value(), LH.ProportionalHeight.value)
        bf.setPageBreakPolicy(QTextBlockFormat.PageBreakFlag.PageBreak_AlwaysBefore if self.keep.isChecked()
                              else QTextBlockFormat.PageBreakFlag.PageBreak_Auto)
        return bf


class TableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tablo Ekle")
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.rows = QSpinBox()
        self.rows.setRange(1, 500)
        self.rows.setValue(3)
        self.cols = QSpinBox()
        self.cols.setRange(1, 63)
        self.cols.setValue(3)
        f.addRow("Satır sayısı:", self.rows)
        f.addRow("Sütun sayısı:", self.cols)
        lay.addLayout(f)
        _buttons(self, lay)


class ImageSizeDialog(QDialog):
    def __init__(self, w, h, natural, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resim Boyutu")
        self.ratio = h / w if w else 1
        self.natural = natural
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.w = QDoubleSpinBox()
        self.h = QDoubleSpinBox()
        for s, v in ((self.w, w), (self.h, h)):
            s.setRange(1, 5000)
            s.setDecimals(1)
            s.setSuffix(" mm")
            s.setValue(px2mm(v))
        self.lock = QCheckBox("En-boy oranını koru")
        self.lock.setChecked(True)
        self.w.valueChanged.connect(lambda v: self._sync(self.h, v * self.ratio))
        self.h.valueChanged.connect(lambda v: self._sync(self.w, v / self.ratio if self.ratio else v))
        reset = QPushButton("Özgün boyut")
        reset.clicked.connect(self._reset)
        f.addRow("Genişlik:", self.w)
        f.addRow("Yükseklik:", self.h)
        f.addRow("", self.lock)
        f.addRow("", reset)
        lay.addLayout(f)
        _buttons(self, lay)
        self._busy = False

    def _sync(self, other, value):
        if self.lock.isChecked() and not getattr(self, "_busy", False):
            self._busy = True
            other.setValue(value)
            self._busy = False

    def _reset(self):
        self._busy = True
        self.w.setValue(px2mm(self.natural[0]))
        self.h.setValue(px2mm(self.natural[1]))
        self._busy = False

    def size_px(self):
        return mm2px(self.w.value()), mm2px(self.h.value())


class LinkDialog(QDialog):
    def __init__(self, text="", url="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bağlantı Ekle")
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.text = QLineEdit(text)
        self.url = QLineEdit(url or "https://")
        f.addRow("Görüntülenecek metin:", self.text)
        f.addRow("Adres:", self.url)
        lay.addLayout(f)
        _buttons(self, lay)


SYMBOLS = ("© ® ™ § ¶ † ‡ • · … – — ‘ ’ “ ” « » ‹ › ° ± × ÷ ≈ ≠ ≤ ≥ ∞ √ ∑ ∏ ∫ ∂ ∆ π Ω µ "
           "α β γ δ ε θ λ σ φ ψ ω € £ ¥ ₺ ¢ $ ½ ⅓ ¼ ¾ ² ³ ¹ → ← ↑ ↓ ↔ ⇒ ⇔ ✓ ✔ ✗ ✘ ★ ☆ ♥ ♦ ♣ ♠ "
           "☐ ☑ ☒ ● ○ ■ □ ▲ △ ▼ ▽ ◆ ◇ ♪ ☎ ✉ ☀ ☁ ☂ ☺ ⚠ ∈ ∉ ∩ ∪ ⊂ ⊃ ∀ ∃ ¬ ∧ ∨").split()


class SymbolDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Simge Ekle")
        self.choice = None
        lay = QVBoxLayout(self)
        g = QGridLayout()
        g.setSpacing(2)
        for i, s in enumerate(SYMBOLS):
            b = QToolButton()
            b.setText(s)
            b.setFixedSize(34, 34)
            f = b.font()
            f.setPointSize(13)
            b.setFont(f)
            b.clicked.connect(lambda _=False, s=s: self._pick(s))
            g.addWidget(b, i // 14, i % 14)
        lay.addLayout(g)

    def _pick(self, s):
        self.choice = s
        self.accept()


class FindReplaceDialog(QDialog):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Bul ve Değiştir")
        self.setWindowFlag(Qt.WindowType.Tool)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.find = QLineEdit()
        self.repl = QLineEdit()
        f.addRow("Aranan:", self.find)
        f.addRow("Yeni değer:", self.repl)
        lay.addLayout(f)
        opts = QHBoxLayout()
        self.case = QCheckBox("Büyük/küçük harf duyarlı")
        self.whole = QCheckBox("Sözcüğün tamamı")
        self.regex = QCheckBox("Düzenli ifade")
        for w in (self.case, self.whole, self.regex):
            opts.addWidget(w)
        lay.addLayout(opts)
        btns = QHBoxLayout()
        for label, fn in (("Öncekini Bul", lambda: self.find_next(False)), ("Sonrakini Bul", self.find_next),
                          ("Değiştir", self.replace_one), ("Tümünü Değiştir", self.replace_all)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            btns.addWidget(b)
        lay.addLayout(btns)
        self.status = QLabel("")
        lay.addWidget(self.status)
        self.find.textChanged.connect(self.highlight_all)
        self.find.returnPressed.connect(self.find_next)

    def _pattern(self):
        text = self.find.text()
        if not text:
            return None
        pat = text if self.regex.isChecked() else QRegularExpression.escape(text)
        if self.whole.isChecked():
            pat = rf"\b{pat}\b"
        opts = QRegularExpression.PatternOption.UseUnicodePropertiesOption
        if not self.case.isChecked():
            opts |= QRegularExpression.PatternOption.CaseInsensitiveOption
        rx = QRegularExpression(pat, opts)
        return rx if rx.isValid() else None

    def highlight_all(self):
        rx = self._pattern()
        sels = []
        count = 0
        if rx is not None:
            doc = self.editor.document()
            c = doc.find(rx, 0)
            while not c.isNull() and count < 5000:
                if c.hasSelection():
                    sel = QTextEdit.ExtraSelection()
                    sel.cursor = c
                    fmt = QTextCharFormat()
                    fmt.setBackground(QColor("#FFE58A"))
                    sel.format = fmt
                    sels.append(sel)
                    count += 1
                    nxt = doc.find(rx, c)
                else:
                    nxt = doc.find(rx, c.position() + 1)
                c = nxt
        self.editor.setExtraSelections(sels)
        self.status.setText(f"{count} eşleşme" if self.find.text() else "")
        return count

    def find_next(self, forward=True):
        rx = self._pattern()
        if rx is None:
            return False
        doc = self.editor.document()
        flags = QTextDocument.FindFlag(0) if forward else QTextDocument.FindFlag.FindBackward
        c = doc.find(rx, self.editor.textCursor(), flags)
        if c.isNull():
            c = doc.find(rx, 0 if forward else doc.characterCount() - 1, flags)
        if c.isNull():
            self.status.setText("Bulunamadı")
            return False
        self.editor.setTextCursor(c)
        self.editor.ensureCursorVisible()
        return True

    def _replacement(self, matched):
        if self.regex.isChecked():
            try:
                flags = 0 if self.case.isChecked() else re.IGNORECASE
                return re.sub(self.find.text(), self.repl.text(), matched, count=1, flags=flags)
            except re.error:
                pass
        return self.repl.text()

    def replace_one(self):
        c = self.editor.textCursor()
        rx = self._pattern()
        if rx is not None and c.hasSelection() and rx.match(c.selectedText()).hasMatch():
            self.editor.type_text(self._replacement(c.selectedText()), c)
        self.find_next()
        self.highlight_all()

    def replace_all(self):
        rx = self._pattern()
        if rx is None:
            return
        doc = self.editor.document()
        cursors = []
        c = doc.find(rx, 0)
        while not c.isNull() and c.hasSelection():
            cursors.append(QTextCursor(c))
            c = doc.find(rx, c)
        edit = QTextCursor(doc)
        edit.beginEditBlock()
        for c in reversed(cursors):
            self.editor.type_text(self._replacement(c.selectedText()), c)
        edit.endEditBlock()
        self.highlight_all()
        self.status.setText(f"{len(cursors)} değiştirme yapıldı")

    def closeEvent(self, e):
        self.editor.setExtraSelections([])
        super().closeEvent(e)
