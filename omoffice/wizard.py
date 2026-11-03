"""Başlangıç sihirbazı ve şablon kataloğu.

1. adım: ne yazılacağını sorar; her şablon gerçek kapağının küçük resmiyle gösterilir.
2. adım: birkaç soru + tasarım (renk teması, yazı tipi takımı) + canlı önizleme.
"""
import datetime
import os

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QListWidget, QListWidgetItem, QToolButton,
    QStackedWidget, QWidget, QScrollArea, QFrame, QPushButton, QLineEdit, QFormLayout, QComboBox,
    QCheckBox, QButtonGroup,
)

from .common import PageSetup
from .guide import KINDS, CATEGORIES, FIELD_LABELS, CITATION_STYLES
from .templates import _today, build_kind, PALETTES, FONT_SETS, KIND_DESIGN

THUMB_W, THUMB_H = 118, 167
SAMPLE = {"title": "Belgenizin Başlığı Buraya Gelecek", "author": "Ad Soyad", "institution": "Kurum Adı",
          "course": "Ders Adı", "degree": "Yüksek Lisans Tezi", "department": "Anabilim Dalı"}
_THUMBS = {}   # oturum boyunca küçük resim önbelleği


def _swatch(colors, w=42, h=16):
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    seg = w / len(colors)
    for i, c in enumerate(colors):
        p.fillRect(int(i * seg), 0, int(seg + 1), h, QColor(c))
    p.end()
    return QIcon(pm)


class StartWizard(QDialog):
    def __init__(self, recent, icon_fn, author="", parent=None, catalog=False):
        super().__init__(parent)
        self.setWindowTitle("Şablon Kataloğu" if catalog else "OmOffice — Başlarken")
        self.icon_fn = icon_fn
        self.choice = None
        self.kind = None
        self.default_author = author
        self.cards = {}
        self.preview_page = 0
        self._renderer = None
        self.resize(1180, 760)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        root.addWidget(self.stack)
        self.stack.addWidget(self._page_kinds(recent, catalog))
        self.form_page = QWidget()
        self.stack.addWidget(self.form_page)
        self.preview_timer = QTimer(self, singleShot=True, interval=280, timeout=self._render_preview)
        self.thumb_queue = [k for k in KINDS if k not in _THUMBS]
        self.thumb_timer = QTimer(self, interval=15, timeout=self._next_thumb)
        QTimer.singleShot(60, self.thumb_timer.start)

    # ---- gizli çizici (önizleme ve küçük resimler için)
    def renderer(self):
        if self._renderer is None:
            from .editor import PageEdit
            self._renderer = PageEdit(None)
            self._renderer.hide()
        return self._renderer

    def done(self, r):
        self.thumb_timer.stop()
        self.preview_timer.stop()
        if self._renderer is not None:
            self._renderer.deleteLater()
            self._renderer = None
        super().done(r)

    def _build(self, kind, answers, opts, page, width):
        from .editor import new_document
        e = self.renderer()
        e.set_document(new_document(), PageSetup())
        build_kind(e, kind, answers, opts)
        n = e.page_count()
        return e.render_page_image(min(page, n - 1), width), n

    def _next_thumb(self):
        if not self.thumb_queue:
            self.thumb_timer.stop()
            return
        key = self.thumb_queue.pop(0)
        try:
            img, _ = self._build(key, SAMPLE, {"cover": True, "toc": False, "placeholders": True}, 0, THUMB_W * 2)
            p = QPainter(img)  # beyaz sayfa beyaz kartta kaybolmasın: ince çerçeve
            p.setPen(QColor("#C3C8D0"))
            p.drawRect(0, 0, img.width() - 1, img.height() - 1)
            p.end()
            _THUMBS[key] = QPixmap.fromImage(img)
        except Exception as exc:  # küçük resim yapılamazsa simge kalır
            print("küçük resim:", key, exc)
            return
        b = self.cards.get(key)
        if b is not None:
            b.setIcon(QIcon(_THUMBS[key]))
            b.setIconSize(QSize(THUMB_W, THUMB_H))

    # ------------------------------------------------------------- adım 1
    def _page_kinds(self, recent, catalog):
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(26, 22, 26, 18)
        hour = datetime.datetime.now().hour
        greet = "Günaydın" if 5 <= hour < 12 else "İyi günler" if hour < 18 else "İyi akşamlar"
        head = QLabel(f"<span style='font-size:20pt;font-weight:600'>{'Şablon Kataloğu' if catalog else greet}</span>"
                      "<br><span style='font-size:11pt'>Ne yazmak istiyorsunuz?</span> "
                      "<span style='color:gray'>Bir şablon seçin; birkaç soru sorup belgeyi kapağı, bölümleri, "
                      "ipuçları ve örnekleriyle hazırlayalım. Renkleri ve yazı tiplerini sonraki adımda "
                      "değiştirebilirsiniz.</span>")
        head.setWordWrap(True)
        outer.addWidget(head)
        outer.addSpacing(10)
        body = QHBoxLayout()
        outer.addLayout(body, 1)
        self.cats = QListWidget()
        self.cats.setFixedWidth(140)
        for c in ["Tümü"] + CATEGORIES:
            self.cats.addItem(c)
        self.cats.currentTextChanged.connect(self._fill_cards)
        body.addWidget(self.cats)
        self.card_area = QScrollArea()
        self.card_area.setWidgetResizable(True)
        self.card_area.setFrameShape(QFrame.Shape.NoFrame)
        body.addWidget(self.card_area, 4)
        right = QVBoxLayout()
        self.desc = QLabel("Soldan bir şablon seçin.")
        self.desc.setWordWrap(True)
        self.desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.desc.setMinimumWidth(260)
        self.desc.setObjectName("descBox")
        right.addWidget(self.desc, 1)
        if not catalog:
            right.addWidget(QLabel("<b>Son belgeler</b>"))
            self.recent = QListWidget()
            self.recent.setMaximumHeight(150)
            for f in recent:
                it = QListWidgetItem(os.path.basename(f))
                it.setToolTip(f)
                it.setData(Qt.ItemDataRole.UserRole, f)
                self.recent.addItem(it)
            if not recent:
                it = QListWidgetItem("(henüz yok)")
                it.setFlags(Qt.ItemFlag.NoItemFlags)
                self.recent.addItem(it)
            self.recent.itemActivated.connect(self._open_recent)
            self.recent.itemDoubleClicked.connect(self._open_recent)
            right.addWidget(self.recent)
            row = QHBoxLayout()
            b = QPushButton("Bilgisayardan aç…")
            b.clicked.connect(lambda: self._finish(("browse", None)))
            row.addWidget(b)
            r = QPushButton("Kurtarılan belgeler…")
            r.clicked.connect(lambda: self._finish(("recover", None)))
            row.addWidget(r)
            right.addLayout(row)
        body.addLayout(right, 2)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        skip = QPushButton("Boş belgeyle başla")
        skip.clicked.connect(lambda: self._finish(("kind", "bos", {}, {})))
        bottom.addWidget(skip)
        self.next_btn = QPushButton("Devam  →")
        self.next_btn.setObjectName("primary")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self._to_form)
        bottom.addWidget(self.next_btn)
        outer.addLayout(bottom)
        self.cats.setCurrentRow(1)
        return w

    def _open_recent(self, it):
        path = it.data(Qt.ItemDataRole.UserRole)
        if path:
            self._finish(("open", path))

    def _fill_cards(self, cat):
        host = QWidget()
        g = QGridLayout(host)
        g.setSpacing(14)
        g.setContentsMargins(4, 4, 4, 4)
        self.card_group = QButtonGroup(host)
        self.cards = {}
        n = 0
        for key, info in KINDS.items():
            if cat != "Tümü" and info["category"] != cat:
                continue
            b = QToolButton()
            b.setObjectName("kindCard")
            b.setCheckable(True)
            b.setText(info["name"].split(" (")[0])
            if key in _THUMBS:
                b.setIcon(QIcon(_THUMBS[key]))
                b.setIconSize(QSize(THUMB_W, THUMB_H))
            else:
                b.setIcon(self.icon_fn(info["icon"]))
                b.setIconSize(QSize(40, 40))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFixedSize(150, 212)
            b.setToolTip(info["desc"])
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            b.mouseDoubleClickEvent = lambda _e, k=key: (self._pick(k), self._to_form())
            self.card_group.addButton(b)
            if key == self.kind:
                b.setChecked(True)
            self.cards[key] = b
            g.addWidget(b, n // 3, n % 3)
            n += 1
        g.setRowStretch(n // 3 + 1, 1)
        g.setColumnStretch(3, 1)
        self.card_area.setWidget(host)

    def _pick(self, key):
        self.kind = key
        info = KINDS[key]
        pal, fonts = KIND_DESIGN.get(key, ("", ""))
        secs = "".join(f"<li>{'&nbsp;' * 4 * (lvl - 1)}{t}</li>" for t, lvl, _ in info["sections"][:12])
        tips = "".join(f"<li>{t}</li>" for t in info.get("tips", [])[:2])
        self.desc.setText(
            f"<div style='font-size:13pt;font-weight:600'>{info['name']}</div>"
            f"<p>{info['desc']}</p>"
            f"<p style='color:gray'>Varsayılan tasarım: {pal} · {fonts}</p>"
            + (f"<b>Bölümler</b><ul style='margin-left:-20px'>{secs}</ul>" if secs else "")
            + (f"<b>İpuçları</b><ul style='margin-left:-20px'>{tips}</ul>" if tips else ""))
        self.next_btn.setEnabled(True)

    # ------------------------------------------------------------- adım 2
    def _to_form(self):
        if not self.kind:
            return
        if self.kind == "bos":
            self._finish(("kind", "bos", {}, {}))
            return
        info = KINDS[self.kind]
        old = self.form_page.layout()
        if old is not None:
            QWidget().setLayout(old)
        root = QHBoxLayout(self.form_page)
        root.setContentsMargins(30, 22, 24, 18)
        root.setSpacing(24)
        v = QVBoxLayout()
        root.addLayout(v, 3)
        v.addWidget(QLabel(f"<span style='font-size:17pt;font-weight:600'>{info['name']}</span><br>"
                           "<span style='color:gray'>Bildiklerinizi doldurun; boş bıraktıklarınız belgede "
                           "gri yer tutucu olarak kalır, sonra tıklayıp yazabilirsiniz.</span>"))
        v.addSpacing(8)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.inputs = {}
        for f in info["fields"]:
            e = QLineEdit()
            e.setMinimumWidth(340)
            if f == "date":
                e.setText(_today())
            elif f == "author":
                e.setText(self.default_author)
                e.setPlaceholderText("Ad Soyad (birden çoksa noktalı virgülle ayırın)")
            elif f == "keywords":
                e.setPlaceholderText("ör. yapay zekâ, eğitim, öğrenme analitiği")
            elif f == "recipient":
                e.setPlaceholderText("ör. Bilgisayar Mühendisliği Bölüm Başkanlığı")
            e.textChanged.connect(self.preview_timer.start)
            self.inputs[f] = e
            form.addRow(FIELD_LABELS.get(f, f) + ":", e)
        self.cite = None
        if info.get("citation"):
            self.cite = QComboBox()
            self.cite.addItems(CITATION_STYLES + ["Kaynakça yok"])
            self.cite.currentIndexChanged.connect(self.preview_timer.start)
            form.addRow("Atıf stili:", self.cite)
            hint = QLabel("APA: sosyal bilimler, eğitim · IEEE: mühendislik, bilgisayar · MLA: dil-edebiyat")
            hint.setStyleSheet("color: gray; font-size: 8pt;")
            form.addRow("", hint)
        v.addLayout(form)
        v.addSpacing(10)
        v.addWidget(QLabel("<b>Tasarım</b>"))
        df = QFormLayout()
        pal_default, font_default = KIND_DESIGN.get(self.kind, ("Lacivert", "Ofis (Calibri)"))
        self.palette = QComboBox()
        for name, cols in PALETTES.items():
            self.palette.addItem(_swatch(cols), "  " + name, name)
        self.palette.setIconSize(QSize(42, 16))
        self.palette.setCurrentIndex(list(PALETTES).index(pal_default))
        self.fontset = QComboBox()
        for name, (head, body, title, size, line) in FONT_SETS.items():
            self.fontset.addItem(f"{name}  ·  {size:g} nk", name)
        self.fontset.setCurrentIndex(list(FONT_SETS).index(font_default))
        self.palette.currentIndexChanged.connect(self.preview_timer.start)
        self.fontset.currentIndexChanged.connect(self.preview_timer.start)
        df.addRow("Renk teması:", self.palette)
        df.addRow("Yazı tipi takımı:", self.fontset)
        v.addLayout(df)
        v.addSpacing(8)
        self.opt_cover = QCheckBox("Kapak sayfası ekle")
        self.opt_cover.setChecked(bool(info.get("cover")))
        self.opt_cover.setVisible(bool(info.get("cover")))
        self.opt_toc = QCheckBox("İçindekiler tablosu ekle")
        self.opt_toc.setChecked(bool(info.get("toc")))
        self.opt_toc.setVisible(bool(info.get("toc")))
        self.opt_ph = QCheckBox("Her bölüme ne yazacağımı anlatan yönerge ekle (gri yer tutucu)")
        self.opt_ph.setChecked(True)
        self.opt_ex = QCheckBox("Her bölüme örnek bir cümle ekle")
        self.opt_guide = QCheckBox("Yazarken sağda Rehber panelini aç (bölüme göre ipuçları ve örnekler)")
        self.opt_guide.setChecked(True)
        for cb in (self.opt_cover, self.opt_toc, self.opt_ph, self.opt_ex, self.opt_guide):
            cb.toggled.connect(self.preview_timer.start)
            v.addWidget(cb)
        v.addStretch(1)
        row = QHBoxLayout()
        back = QPushButton("←  Geri")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        row.addWidget(back)
        row.addStretch(1)
        go = QPushButton("Belgeyi oluştur")
        go.setObjectName("primary")
        go.clicked.connect(self._create)
        row.addWidget(go)
        v.addLayout(row)

        # canlı önizleme
        pv = QVBoxLayout()
        root.addLayout(pv, 2)
        cap = QLabel("<b>Canlı önizleme</b> <span style='color:gray'>— yazdıkça ve seçtikçe güncellenir</span>")
        pv.addWidget(cap)
        self.preview = QLabel("Hazırlanıyor…")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedSize(340, 482)
        self.preview.setStyleSheet("background: #D7DBE1; border-radius: 8px;")
        pv.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignHCenter)
        nav = QHBoxLayout()
        prev_b = QPushButton("‹")
        next_b = QPushButton("›")
        prev_b.setFixedWidth(40)
        next_b.setFixedWidth(40)
        self.page_lbl = QLabel("")
        self.page_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prev_b.clicked.connect(lambda: self._turn(-1))
        next_b.clicked.connect(lambda: self._turn(1))
        nav.addStretch(1)
        nav.addWidget(prev_b)
        nav.addWidget(self.page_lbl)
        nav.addWidget(next_b)
        nav.addStretch(1)
        pv.addLayout(nav)
        pv.addStretch(1)
        self.preview_page = 0
        self.stack.setCurrentIndex(1)
        self.preview_timer.start()
        first = next(iter(self.inputs.values()), None)
        if first is not None:
            first.setFocus()

    def _turn(self, d):
        self.preview_page = max(0, self.preview_page + d)
        self._render_preview()

    def _current(self):
        answers = {k: e.text().strip() for k, e in self.inputs.items()}
        cite = self.cite.currentText() if self.cite is not None else ""
        opts = {
            "cover": self.opt_cover.isChecked(), "toc": self.opt_toc.isChecked(),
            "placeholders": self.opt_ph.isChecked(), "examples": self.opt_ex.isChecked(),
            "guide": self.opt_guide.isChecked(),
            "citation": "" if cite in ("", "Kaynakça yok") else cite,
            "citation_section": cite != "Kaynakça yok",
            "palette": self.palette.currentData(), "fontset": self.fontset.currentData(),
        }
        return answers, opts

    def _render_preview(self):
        if self.stack.currentIndex() != 1 or not self.kind:
            return
        answers, opts = self._current()
        dpr = self.devicePixelRatioF()
        img, n = self._build(self.kind, answers, opts, self.preview_page, int(332 * dpr))
        self.preview_page = min(self.preview_page, n - 1)
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self.preview.setPixmap(pm)
        self.page_lbl.setText(f"  Sayfa {self.preview_page + 1} / {n}  ")

    def _create(self):
        answers, opts = self._current()
        self._finish(("kind", self.kind, answers, opts))

    def _finish(self, choice):
        self.choice = choice
        self.accept()
