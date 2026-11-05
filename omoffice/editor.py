"""Sayfalı metin düzenleyici: A4 sayfa görünümü, üst/alt bilgi, değişiklik izleme."""
import datetime
import os
import re
import uuid

from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QUrl, Signal, QBuffer, QIODevice, QByteArray
from PySide6.QtGui import (
    QAbstractTextDocumentLayout, QColor, QDesktopServices, QFont, QImage, QPainter,
    QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextFormat, QTextImageFormat, QTextLength, QTextListFormat, QTextOption,
    QTextTableFormat, QTextFrameFormat, QBrush, QPen, QFontMetricsF,
)
from PySide6.QtWidgets import QTextEdit, QFrame, QMenu

from .common import (
    TC_TYPE, TC_AUTHOR, TC_DATE, STYLE_PROP, STYLES, DEFAULT_FONT, DEFAULT_SIZE,
    COMMENT_PROP, FOOTNOTE_PROP, TOC_PROP, PLACEHOLDER_PROP, IMAGE_SLOT_KINDS, image_slot,
    PageSetup, mm2px, pt2px, turkish_upper, turkish_lower, turkish_title, turkish_sort_key,
)
from .spell import DocHighlighter
from .safety import is_safe_link

PAGE_GAP = 18          # sayfalar arası boşluk (px)
TC_PROPS = (TC_TYPE, TC_AUTHOR, TC_DATE)

# Otomatik düzeltme: yazarken sözcük sonunda uygulanır
AUTOCORRECT = {
    "birşey": "bir şey", "herşey": "her şey", "hiçbirşey": "hiçbir şey", "yanlız": "yalnız",
    "malesef": "maalesef", "şuan": "şu an", "teşekürler": "teşekkürler", "teşekkürler.": "teşekkürler.",
    "yalnış": "yanlış", "herkez": "herkes", "orjinal": "orijinal", "eşortman": "eşofman",
    "kirpit": "kibrit", "sürpriz": "sürpriz", "tabiki": "tabii ki", "tabi ki": "tabii ki",
    "ingilizce": "İngilizce", "türkçe": "Türkçe", "istanbul": "İstanbul", "ankara": "Ankara",
    "türkiye": "Türkiye", "izmir": "İzmir",
    "(c)": "©", "(r)": "®", "(tm)": "™", "--": "—", "->": "→", "<-": "←", "=>": "⇒", "<=>": "⇔",
    "1/2": "½", "1/4": "¼", "3/4": "¾", "...": "…", "+-": "±", "!=": "≠", ">=": "≥", "<=": "≤",
}
AUTOCORRECT_TRIGGERS = " .,;:!?)\t"

BULLET_STYLES = [QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle,
                 QTextListFormat.Style.ListSquare]
NUMBER_STYLES = [QTextListFormat.Style.ListDecimal, QTextListFormat.Style.ListLowerAlpha,
                 QTextListFormat.Style.ListLowerRoman]


def clean_tc(fmt):
    """Yeni yazılan metnin devralmaması gereken işaretleri temizler."""
    f = QTextCharFormat(fmt)
    for p in TC_PROPS:
        f.clearProperty(p)
    if f.hasProperty(FOOTNOTE_PROP):
        f.clearProperty(FOOTNOTE_PROP)
        f.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
    if f.hasProperty(PLACEHOLDER_PROP):
        f.clearProperty(PLACEHOLDER_PROP)
        f.setFontItalic(False)
        f.setForeground(QColor("#000000"))
    return f


class OmOfficeDocument(QTextDocument):
    """Dış kaynak yüklemeyen belge.

    Qt varsayılan olarak bilinmeyen resim adlarını yerel dosya (UNC ağ yolları dahil)
    olarak okumaya çalışır; bu, kötü niyetli bir belgenin ağ kimlik bilgisi sızdırmasına
    yol açabilir. Burada yalnızca belgeye gömülü kaynaklar ve data: adresleri kullanılır.
    """

    def loadResource(self, rtype, url):
        if url.scheme() == "data":
            return super().loadResource(rtype, url)
        return None


def new_document(parent=None):
    doc = OmOfficeDocument(parent)
    # Glif genişlikleri piksele yuvarlanmasın: satırlar Word'dekine çok daha yakın yerden kırılır
    doc.setUseDesignMetrics(True)
    doc.setDefaultFont(QFont(DEFAULT_FONT, int(DEFAULT_SIZE)))
    doc.setIndentWidth(pt2px(18))
    doc.setUndoRedoEnabled(True)
    c = QTextCursor(doc)
    bf = QTextBlockFormat()
    bf.setBottomMargin(pt2px(8))
    bf.setLineHeight(108, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    bf.setProperty(STYLE_PROP, "Normal")
    c.setBlockFormat(bf)
    cf = QTextCharFormat()
    cf.setFontFamilies([DEFAULT_FONT])
    cf.setFontPointSize(DEFAULT_SIZE)
    c.setBlockCharFormat(cf)
    c.setCharFormat(cf)
    doc.setModified(False)
    doc.clearUndoRedoStacks()
    return doc


class PageEdit(QTextEdit):
    pageInfoChanged = Signal()
    headerFooterRequested = Signal()
    imageEditRequested = Signal(int)
    formatPainterDone = Signal()
    selectionFinished = Signal()
    footnoteEditRequested = Signal(str)
    commentsChanged = Signal()
    cursorVisibilityRequested = Signal()
    documentReplaced = Signal()
    newCommentRequested = Signal()
    hfEditRequested = Signal(int, str)    # sayfa_no, "header" | "footer"
    imageReplaceRequested = Signal(int)
    hfChanged = Signal()

    def __init__(self, spell=None, parent=None):
        super().__init__(parent)
        self.setup = PageSetup()
        self.spell = spell
        self.track_changes = False
        self.author = os.environ.get("USERNAME", "Kullanıcı")
        self.painter_format = None
        self.highlighter = None
        self._doc = None
        self.bg_color = QColor("#E4E7EC")
        self.comments = {}      # id -> {"author", "date", "text", "resolved"}
        self.footnotes = {}     # id -> metin
        self.active_comment = None
        self.autocorrect = True
        self.page_step = lambda: 600
        self._fn_cache = None
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptRichText(True)
        # Kaydırma ve yakınlaştırma dıştaki grafik görünümünde yapılır; bu widget belgenin tamamı boyundadır.
        self.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Text, QColor("#000000"))
        pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
        self.setPalette(pal)
        self.setCursorWidth(2)
        self.set_document(new_document(self), PageSetup())
        self.cursorPositionChanged.connect(self.pageInfoChanged)
        self.currentCharFormatChanged.connect(self._clean_current_format)
        self._hf_hover = None   # (sayfa_dizini, "header"|"footer")
        self.viewport().setMouseTracking(True)

    def _clean_current_format(self, fmt):
        # İmleç izlenen bir değişikliğin yanına geldiğinde, yeni yazılan metin
        # o değişikliğin işaretini devralmasın.
        if (fmt.hasProperty(TC_TYPE) or fmt.hasProperty(PLACEHOLDER_PROP)) and not self.textCursor().hasSelection():
            self.setCurrentCharFormat(clean_tc(fmt))

    # ------------------------------------------------------------------ belge
    def set_document(self, doc, setup, meta=None):
        old = self._doc
        if self.highlighter is not None:
            self.highlighter.setDocument(None)
        doc.setParent(self)
        self._doc = doc
        self.setup = setup
        meta = meta or {}
        self.comments = dict(meta.get("comments", {}))
        self.footnotes = dict(meta.get("footnotes", {}))
        self.doc_info = dict(meta.get("info", {}))
        self.active_comment = None
        self.setDocument(doc)
        self.highlighter = DocHighlighter(doc, self.spell, True, self._comment_state)
        doc.contentsChanged.connect(self.pageInfoChanged)
        doc.contentsChanged.connect(self._invalidate)
        self._invalidate()
        self.apply_page_setup()
        if meta.get("sections"):
            self._apply_sections(meta["sections"])
        self.documentReplaced.emit()
        self.commentsChanged.emit()
        if old is not None and old is not doc:
            old.deleteLater()

    def _apply_sections(self, secs):
        """Word bölümlerindeki farklı üst/alt bilgileri sayfaya özel ayarlara çevirir.

        Bir sayfa, tepesindeki paragrafın bulunduğu bölümün üst/alt bilgisini gösterir (Word kuralı)."""
        doc = self.document()
        _, ph = self.page_px()
        total = self.page_count()
        lay = doc.documentLayout()
        top_block = {}
        block = doc.begin()
        while block.isValid():
            r = lay.blockBoundingRect(block)
            if r.height() > 0:
                for n in range(int(r.top() // ph) + 1, int((r.bottom() - 1) // ph) + 2):
                    top_block.setdefault(n, block.blockNumber())
            block = block.next()
        last_block = doc.blockCount() - 1

        def section_of(bn):
            for k, sec in enumerate(secs):
                if sec["end_block"] is None or bn <= sec["end_block"]:
                    return k
            return len(secs) - 1

        st = self.setup
        st.hf_pages = {}
        prev = None
        wanted = {}
        for n in range(1, total + 1):
            k = section_of(top_block.get(n, last_block))
            sec = secs[k]
            first = k != prev
            prev = k
            for which in ("header", "footer"):
                val = sec.get("first_" + which) if sec["title_pg"] and first else sec[which]
                wanted.setdefault(n, {})[which] = val or ("", "center")
        for n, d in wanted.items():
            for which, (text, align) in d.items():
                cur_text, cur_align = st.hf_for(which, n)
                if text != cur_text or (text and align != cur_align):
                    ov = st.hf_pages.setdefault(n, {})
                    ov[which] = text
                    ov[which + "_align"] = align
        self.viewport().update()

    def meta(self):
        return {"comments": self.comments, "footnotes": self.footnotes, "info": self.doc_info}

    def _invalidate(self):
        self._fn_cache = None

    def _comment_state(self, cid):
        info = self.comments.get(cid)
        if info is None or info.get("resolved"):
            return None
        return "active" if cid == self.active_comment else "open"

    def page_px(self):
        return mm2px(self.setup.width_mm), mm2px(self.setup.height_mm)

    def text_width(self):
        s = self.setup
        return mm2px(s.width_mm - s.left_mm - s.right_mm)

    def apply_page_setup(self):
        s = self.setup
        doc = self.document()
        rf = doc.rootFrame()
        ff = rf.frameFormat()
        ff.setTopMargin(mm2px(s.top_mm))
        ff.setBottomMargin(mm2px(s.bottom_mm))
        ff.setLeftMargin(mm2px(s.left_mm))
        ff.setRightMargin(mm2px(s.right_mm))
        ff.setPadding(0)
        ff.setBorder(0)
        rf.setFrameFormat(ff)
        pw, _ = self.page_px()
        self.setLineWrapColumnOrWidth(int(round(pw)))
        self._fix_page_size()
        self._invalidate()
        self.viewport().update()
        self.pageInfoChanged.emit()

    def _fix_page_size(self):
        # QTextEdit yeniden yerleşimde sayfa yüksekliğini -1 yapar; kararlı olana dek düzelt
        pw, ph = self.page_px()
        doc = self.document()
        for _ in range(4):
            if abs(doc.pageSize().height() - ph) <= 0.5 and abs(doc.pageSize().width() - pw) <= 0.5:
                break
            doc.setPageSize(QSizeF(pw, ph))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fix_page_size()

    def page_count(self):
        self._fix_page_size()
        doc = self.document()
        # Yerleşim tembel yapılır; sayfa sayısı için sona kadar zorla
        doc.documentLayout().blockBoundingRect(doc.lastBlock())
        return max(1, doc.pageCount())

    def page_of_position(self, pos, doc=None):
        if doc is None:
            self._fix_page_size()
            doc = self.document()
        block = doc.findBlock(pos)
        if not block.isValid():
            return 1
        y = doc.documentLayout().blockBoundingRect(block).top()
        lay = block.layout()
        if lay is not None and lay.lineCount():
            line = lay.lineForTextPosition(max(0, pos - block.position()))
            if line.isValid():
                y += line.y()
        _, ph = self.page_px()
        return int(y // ph) + 1

    def current_page(self):
        return self.page_of_position(self.textCursor().position())

    # ------------------------------------------------------------- çizim
    def paintEvent(self, e):
        self._fix_page_size()
        pw, ph = self.page_px()
        n = self.page_count()
        rect = e.rect()
        p = QPainter(self.viewport())
        p.fillRect(rect, self.bg_color)
        first = max(0, int(rect.top() // ph))
        last = min(n - 1, int(rect.bottom() // ph))
        g = PAGE_GAP / 2
        for i in range(first, last + 1):
            page = QRectF(0, i * ph, pw, ph)
            p.save()
            p.setClipRect(QRectF(0, i * ph + g, pw, ph - 2 * g))
            self.draw_page(p, self.document(), i, n, page)
            if self._hf_hover and self._hf_hover[0] == i:
                self.draw_hf_hover(p, i, page)
            p.restore()
        p.end()
        super().paintEvent(e)
        self._paint_image_handles()

    def draw_page(self, p, doc, index, total, page_rect, line_numbers=None):
        """Sayfanın metin dışındaki her şeyini çizer: zemin, kenarlık, filigran,
        üst/alt bilgi, dipnotlar, satır numaraları."""
        s = self.setup
        p.fillRect(page_rect, QColor(s.page_color or "#FFFFFF"))
        if s.page_border:
            inset = pt2px(24)
            p.save()
            p.setPen(QPen(QColor("#404040"), 1.5))
            p.drawRect(page_rect.adjusted(inset, inset, -inset, -inset))
            p.restore()
        if s.watermark:
            self.draw_watermark(p, page_rect, s.watermark)
        self.draw_header_footer(p, index, total, page_rect)
        self.draw_footnotes(p, doc, index, page_rect)
        if s.line_numbers:
            self.draw_line_numbers(p, doc, index, page_rect)

    @staticmethod
    def draw_watermark(p, page_rect, text):
        p.save()
        f = QFont("Calibri")
        f.setPixelSize(100)
        f.setBold(True)
        w = QFontMetricsF(f).horizontalAdvance(text) or 1
        diag = (page_rect.width() ** 2 + page_rect.height() ** 2) ** 0.5
        f.setPixelSize(max(10, int(100 * diag * 0.62 / w)))
        p.setFont(f)
        p.setPen(QColor(150, 150, 150, 70))
        p.translate(page_rect.center())
        p.rotate(-54)
        fm = QFontMetricsF(f)
        p.drawText(QPointF(-fm.horizontalAdvance(text) / 2, fm.ascent() / 2 - fm.descent()), text)
        p.restore()

    def hf_zone(self, which, page_rect):
        """Üst/alt bilginin sayfadaki tıklanabilir alanı."""
        st = self.setup
        x = page_rect.left() + mm2px(st.left_mm) - 6
        w = page_rect.width() - mm2px(st.left_mm) - mm2px(st.right_mm) + 12
        if which == "header":
            return QRectF(x, page_rect.top() + mm2px(5), w, max(mm2px(8), mm2px(st.top_mm) - mm2px(8)))
        h = max(mm2px(8), mm2px(st.bottom_mm) - mm2px(8))
        return QRectF(x, page_rect.bottom() - mm2px(5) - h, w, h)

    def hf_buttons(self, zone):
        """(düzenle, sil) düğmelerinin alanları."""
        size = 22
        y = zone.top() + 3
        return QRectF(zone.right() - 2 * size - 8, y, size, size), QRectF(zone.right() - size - 4, y, size, size)

    def draw_header_footer(self, p, index, total, page_rect):
        st = self.setup
        font = QFont(self.document().defaultFont())
        font.setPixelSize(int(round(pt2px(9))))
        p.save()
        p.setFont(font)
        p.setPen(QColor("#555555"))
        x = page_rect.left() + mm2px(st.left_mm)
        w = page_rect.width() - mm2px(st.left_mm) - mm2px(st.right_mm)
        aligns = {"left": Qt.AlignmentFlag.AlignLeft, "center": Qt.AlignmentFlag.AlignHCenter,
                  "right": Qt.AlignmentFlag.AlignRight}
        for which in ("header", "footer"):
            text, align = st.hf_for(which, index + 1)
            if not text:
                continue
            t = text.replace("{SAYFA}", str(index + 1)).replace("{TOPLAM}", str(total))
            if which == "header":
                rect = QRectF(x, page_rect.top() + mm2px(10), w, mm2px(max(5, st.top_mm - 12)))
                flags = Qt.AlignmentFlag.AlignTop
            else:
                h = mm2px(max(5, st.bottom_mm - 12))
                rect = QRectF(x, page_rect.bottom() - mm2px(10) - h, w, h)
                flags = Qt.AlignmentFlag.AlignBottom
            p.drawText(rect, int(flags | aligns.get(align, Qt.AlignmentFlag.AlignHCenter)
                                 | Qt.TextFlag.TextWordWrap), t)
        p.restore()

    def draw_hf_hover(self, p, index, page_rect):
        """Üzerine gelinen üst/alt bilgi: kesik çerçeve, ✎ ve ✕ düğmeleri (yalnızca ekranda)."""
        which = self._hf_hover[1]
        zone = self.hf_zone(which, page_rect)
        text, _ = self.setup.hf_for(which, index + 1)
        from .theme import CURRENT, ensure_contrast
        accent = QColor(ensure_contrast(CURRENT["accent"], "#FFFFFF", 4.5))  # sayfa her temada beyaz
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(accent, 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 14))
        p.drawRoundedRect(zone, 5, 5)
        label = ("Üst bilgi" if which == "header" else "Alt bilgi") + f" — sayfa {index + 1}"
        if self.setup.hf_pages.get(index + 1, {}).get(which) is not None:
            label += " (bu sayfaya özel)"
        f = QFont(self.font())
        f.setPixelSize(11)
        p.setFont(f)
        p.setPen(accent)
        lr = QRectF(zone.left() + 6, zone.top() + 2, zone.width() - 70, 16) if which == "header" else \
            QRectF(zone.left() + 6, zone.bottom() - 18, zone.width() - 70, 16)
        p.drawText(lr, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), label)
        if not text:
            p.setPen(QColor("#7F8EA8"))
            f.setPixelSize(12)
            p.setFont(f)
            p.drawText(zone, int(Qt.AlignmentFlag.AlignCenter),
                       "+ " + ("Üst" if which == "header" else "Alt") + " bilgi eklemek için tıklayın")
        edit_r, del_r = self.hf_buttons(zone)
        buttons = [(edit_r, "✎", accent)]
        if text:
            buttons.append((del_r, "✕", QColor("#C62828")))
        for r, ch, col in buttons:
            p.setPen(QPen(col, 1))
            p.setBrush(QColor("#FFFFFF"))
            p.drawRoundedRect(r, 5, 5)
            f.setPixelSize(13)
            f.setBold(True)
            p.setFont(f)
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), ch)
        p.restore()

    def hf_hit(self, pos):
        """Fare konumu bir üst/alt bilgi alanındaysa (sayfa_dizini, which, alan) döndürür."""
        pw, ph = self.page_px()
        y = pos.y()
        i = int(y // ph)
        if i < 0 or i >= self.page_count():
            return None
        page = QRectF(0, i * ph, pw, ph)
        for which in ("header", "footer"):
            zone = self.hf_zone(which, page)
            if zone.contains(QPointF(pos)):
                return i, which, zone
        return None

    def _set_hf_hover(self, value):
        if value != self._hf_hover:
            old = self._hf_hover
            self._hf_hover = value
            _, ph = self.page_px()
            for v in (old, value):
                if v is not None:
                    self.viewport().update(0, int(v[0] * ph), self.viewport().width(), int(ph) + 1)

    # ---- sayfaya özel üst/alt bilgi işlemleri
    def hf_set(self, page_no, which, text, align=None, scope="page"):
        """scope: "page" = yalnızca bu sayfa, "from" = bu sayfa ve sonrası, "all" = tüm sayfalar."""
        st = self.setup
        total = self.page_count()
        akey = which + "_align"
        if scope == "all":
            setattr(st, which + "_text", text)
            if align:
                setattr(st, akey, align)
            for ov in st.hf_pages.values():
                ov.pop(which, None)
                ov.pop(akey, None)
        elif scope == "from":
            for n in range(1, page_no):
                ov = st.hf_pages.setdefault(n, {})
                if which not in ov:
                    ov[which], ov[akey] = st.hf_for(which, n)
            for n in list(st.hf_pages):
                # sonraki sayfalardaki özel metinler yenisiyle değişir; ama açıkça kaldırılmış
                # sayfalar (ör. "6. sayfada olmasın") kaldırılmış kalır
                if n > page_no and st.hf_pages[n].get(which) == "" and text:
                    continue
                if n >= page_no:
                    st.hf_pages[n].pop(which, None)
                    st.hf_pages[n].pop(akey, None)
            setattr(st, which + "_text", text)
            if align:
                setattr(st, akey, align)
            if st.different_first and page_no > 1:
                ov = st.hf_pages.setdefault(1, {})
                ov.setdefault(which, "")
        else:
            ov = st.hf_pages.setdefault(page_no, {})
            ov[which] = text
            if align:
                ov[akey] = align
        st.hf_pages = {k: v for k, v in st.hf_pages.items() if v and k <= max(total, page_no) + 50}
        self._after_hf_change()

    def hf_reset_page(self, page_no, which=None):
        ov = self.setup.hf_pages.get(page_no)
        if ov:
            for w in ([which] if which else ["header", "footer"]):
                ov.pop(w, None)
                ov.pop(w + "_align", None)
            if not ov:
                self.setup.hf_pages.pop(page_no, None)
        self._after_hf_change()

    def _after_hf_change(self):
        self.viewport().update()
        self.document().setModified(True)
        self.hfChanged.emit()
        self.pageInfoChanged.emit()

    # ---- boş sayfa
    def _blocks_on_page(self, page_no):
        out = []
        block = self.document().begin()
        while block.isValid():
            pg = self.page_of_position(block.position())
            if pg == page_no:
                out.append(block)
            elif pg > page_no:
                break
            block = block.next()
        return out

    def page_is_empty(self, page_no):
        if page_no < 1 or self.page_count() <= 1:
            return False
        blocks = self._blocks_on_page(page_no)
        if not blocks:
            return False
        prev = blocks[0].previous()
        if prev.isValid() and self.page_of_position(prev.position() + prev.length() - 1) >= page_no:
            return False  # önceki paragraf bu sayfaya taşıyor
        for b in blocks:
            if b.text().strip() or QTextCursor(b).currentTable() is not None:
                return False
        return True

    def delete_empty_page(self, page_no):
        if not self.page_is_empty(page_no):
            return False
        blocks = self._blocks_on_page(page_no)
        first, last = blocks[0], blocks[-1]
        doc = self.document()
        c = QTextCursor(doc)
        c.beginEditBlock()
        start = first.position() - 1 if first.previous().isValid() else first.position()
        end = last.position() + last.length() - 1
        nxt = last.next()
        c.setPosition(start)
        c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        if not first.previous().isValid() and nxt.isValid():
            bf = QTextCursor(doc.begin()).blockFormat()
            bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_Auto)
            QTextCursor(doc.begin()).setBlockFormat(bf)
        c.endEditBlock()
        self.setup.hf_pages = {(k if k < page_no else k - 1): v for k, v in self.setup.hf_pages.items()
                               if k != page_no}
        self._after_hf_change()
        return True

    # ---- dipnot çizimi
    def footnote_refs(self, doc=None):
        """Belgedeki dipnot başvuruları, sırayla: [(başlangıç, bitiş, kimlik)]."""
        doc = doc or self.document()
        out = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fid = frag.charFormat().property(FOOTNOTE_PROP)
                if fid:
                    fid = str(fid)
                    if out and out[-1][2] == fid and out[-1][1] == frag.position():
                        out[-1] = (out[-1][0], frag.position() + frag.length(), fid)
                    else:
                        out.append((frag.position(), frag.position() + frag.length(), fid))
                it += 1
            block = block.next()
        return out

    def footnotes_by_page(self, doc=None):
        own = doc is None
        if own and self._fn_cache is not None:
            return self._fn_cache
        pages = {}
        for n, (a, _, fid) in enumerate(self.footnote_refs(doc), 1):
            pg = self.page_of_position(a, doc) - 1
            pages.setdefault(pg, []).append((n, self.footnotes.get(fid, "")))
        if own:
            self._fn_cache = pages
        return pages

    def draw_footnotes(self, p, doc, index, page_rect):
        notes = self.footnotes_by_page(None if doc is self.document() else doc).get(index)
        if not notes:
            return
        s = self.setup
        x = page_rect.left() + mm2px(s.left_mm)
        w = page_rect.width() - mm2px(s.left_mm) - mm2px(s.right_mm)
        y = page_rect.bottom() - mm2px(s.bottom_mm) + 6
        bottom = page_rect.bottom() - mm2px(10) - (pt2px(11) if s.footer_text else 0)
        f = QFont(self.document().defaultFont())
        f.setPixelSize(int(round(pt2px(8))))
        fm = QFontMetricsF(f)
        p.save()
        p.setFont(f)
        p.setPen(QPen(QColor("#777777"), 0.8))
        p.drawLine(QPointF(x, y), QPointF(x + min(w / 3, 160), y))
        p.setPen(QColor("#222222"))
        y += 3
        for num, text in notes:
            line = f"{num}  {text}"
            r = fm.boundingRect(QRectF(x, y, w, 1000), int(Qt.TextFlag.TextWordWrap), line)
            if y + min(r.height(), fm.height()) > bottom:
                p.drawText(QPointF(x, y + fm.ascent()), "…")
                break
            p.drawText(QRectF(x, y, w, r.height()), int(Qt.TextFlag.TextWordWrap), line)
            y += r.height() + 1
        p.restore()

    def draw_line_numbers(self, p, doc, index, page_rect):
        _, ph = self.page_px()
        top, bottom = index * ph, (index + 1) * ph
        lay = doc.documentLayout()
        f = QFont(self.document().defaultFont())
        f.setPixelSize(int(round(pt2px(8))))
        p.save()
        p.setFont(f)
        p.setPen(QColor("#8A8F98"))
        x = page_rect.left() + mm2px(self.setup.left_mm) - 40
        num = 0
        block = doc.begin()
        while block.isValid():
            tl = block.layout()
            br = lay.blockBoundingRect(block)
            in_table = QTextCursor(block).currentTable() is not None
            if tl is not None and not in_table:
                for i in range(tl.lineCount()):
                    num += 1
                    line = tl.lineAt(i)
                    y = br.top() + line.y()
                    if top <= y < bottom:
                        p.drawText(QRectF(x, page_rect.top() + y - top, 30, line.height()),
                                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), str(num))
            if br.top() > bottom:
                break
            block = block.next()
        p.restore()

    def render_pages(self, device):
        """Belgeyi PDF yazıcısına ya da yazıcıya sayfa sayfa çizer."""
        src = self.document()
        doc = src.clone(self)
        doc.setUseDesignMetrics(src.useDesignMetrics())  # PDF'te satırlar ekrandaki yerden kırılsın
        for name in self.image_names():
            res = src.resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name),
                            res if res is not None else QImage())
        doc.rootFrame().setFrameFormat(src.rootFrame().frameFormat())
        pw, ph = self.page_px()
        doc.setPageSize(QSizeF(pw, ph))
        hl = DocHighlighter(doc, None, True)
        hl.rehighlight()
        doc.documentLayout().blockBoundingRect(doc.lastBlock())
        n = max(1, doc.pageCount())
        sx = device.width() / pw
        sy = device.height() / ph
        p = QPainter(device)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(n):
            if i:
                device.newPage()
            p.save()
            p.scale(sx, sy)
            self.draw_page(p, doc, i, n, QRectF(0, 0, pw, ph))
            p.setClipRect(QRectF(0, 0, pw, ph))
            p.translate(0, -i * ph)
            ctx = QAbstractTextDocumentLayout.PaintContext()
            ctx.clip = QRectF(0, i * ph, pw, ph)
            pal = ctx.palette
            pal.setColor(QPalette.ColorRole.Text, QColor("#000000"))
            ctx.palette = pal
            doc.documentLayout().draw(p, ctx)
            p.restore()
        p.end()
        hl.setDocument(None)
        doc.deleteLater()
        return n

    def render_page_image(self, index, width):
        """Bir sayfayı (önizleme için) resme çizer."""
        pw, ph = self.page_px()
        n = self.page_count()
        index = max(0, min(index, n - 1))
        scale = width / pw
        img = QImage(int(width), int(ph * scale), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(QColor("#FFFFFF"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(scale, scale)
        self.draw_page(p, self.document(), index, n, QRectF(0, 0, pw, ph))
        p.setClipRect(QRectF(0, 0, pw, ph))
        p.translate(0, -index * ph)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        ctx.clip = QRectF(0, index * ph, pw, ph)
        pal = ctx.palette
        pal.setColor(QPalette.ColorRole.Text, QColor("#000000"))
        ctx.palette = pal
        self.document().documentLayout().draw(p, ctx)
        p.end()
        return img

    def replace_image(self, pos, image):
        """Konumdaki resmi yenisiyle değiştirir. Şablon alanıysa ("Logo ekle") resim alanın kutusuna oranı
        korunarak sığdırılır; sıradan resimde genişlik korunur, yükseklik sayfaya sığar."""
        fmt = self._image_at(pos)
        if fmt is None or image.isNull():
            return False
        name = f"omoffice-img-{uuid.uuid4().hex[:10]}.png"
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        iw, ih = max(1, image.width()), max(1, image.height())
        bw, bh = fmt.width() or iw, fmt.height() or ih
        if image_slot(fmt.name()):
            k = min(bw / iw, bh / ih)
        else:
            k = min(bw / iw, (self.page_px()[1] * 0.7) / ih)
        nf = QTextImageFormat(fmt)
        nf.setName(name)
        nf.setWidth(iw * k)
        nf.setHeight(ih * k)
        c = QTextCursor(self.document())
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        c.setCharFormat(nf)
        self._select_image(pos)
        return True

    # ---------------------------------------------------------- resim seçme ve boyutlandırma
    HANDLE = 8   # tutamaç kutusu (px)
    _HANDLE_CURSORS = {"tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
                       "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
                       "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
                       "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor}

    def image_rect(self, pos):
        """Satır içi resmin ekrandaki dikdörtgeni (görünüm koordinatları) ya da None."""
        fmt = self._image_at(pos)
        if fmt is None:
            return None
        c = QTextCursor(self.document())
        c.setPosition(pos)
        block = c.block()
        line = block.layout().lineForTextPosition(pos - block.position())
        if not line.isValid():
            return None
        cr = self.cursorRect(c)
        w, h = fmt.width(), fmt.height()
        top = cr.top() + line.ascent() - h
        return QRectF(cr.left(), top, w, h)

    def selected_image(self):
        """Seçim tam olarak bir resimse konumunu döndürür."""
        c = self.textCursor()
        if c.selectionEnd() - c.selectionStart() == 1 and self._image_at(c.selectionStart()) is not None:
            return c.selectionStart()
        return None

    def _select_image(self, pos):
        c = QTextCursor(self.document())
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(c)
        self.viewport().update()

    def image_at_point(self, pt):
        pt = QPointF(pt)
        c = self.cursorForPosition(pt.toPoint())
        for p in (c.position(), c.position() - 1):
            r = self.image_rect(p)
            if r is not None and r.adjusted(-2, -2, 2, 2).contains(pt):
                return p
        return None

    def _handles(self, r):
        """Sekiz tutamaç: köşeler oranı korur, kenarlar tek yönde uzatır."""
        pts = {"tl": r.topLeft(), "t": QPointF(r.center().x(), r.top()), "tr": r.topRight(),
               "r": QPointF(r.right(), r.center().y()), "br": r.bottomRight(),
               "b": QPointF(r.center().x(), r.bottom()), "bl": r.bottomLeft(), "l": QPointF(r.left(), r.center().y())}
        k = self.HANDLE
        return {name: QRectF(pt.x() - k / 2, pt.y() - k / 2, k, k) for name, pt in pts.items()}

    def _handle_at(self, pt):
        pos = self.selected_image()
        if pos is None:
            return None
        r = self.image_rect(pos)
        if r is None:
            return None
        for name, hr in self._handles(r).items():
            if hr.adjusted(-3, -3, 3, 3).contains(QPointF(pt)):
                return pos, name, r
        return None

    def _drag_rect(self, pt):
        d = self._img_drag
        r, name = QRectF(d["rect"]), d["handle"]
        dx, dy = pt.x() - d["start"].x(), pt.y() - d["start"].y()
        w0, h0 = r.width(), r.height()
        w, h = w0, h0
        if "r" in name:
            w = w0 + dx
        if "l" in name:
            w = w0 - dx
        if "b" in name:
            h = h0 + dy
        if name in ("t", "tl", "tr"):
            h = h0 - dy
        if len(name) == 2:   # köşe: oran korunur
            k = max(w / w0, h / h0)
            w, h = w0 * k, h0 * k
        w = max(16.0, min(w, self.text_width()))
        h = max(16.0, min(h, self.page_px()[1] * 0.85))
        if len(name) == 2:
            k = min(w / w0, h / h0)
            w, h = w0 * k, h0 * k
        x = r.right() - w if "l" in name else r.left()
        y = r.bottom() - h if name in ("t", "tl", "tr") else r.top()
        return QRectF(x, y, w, h)

    def _paint_image_handles(self):
        drag = getattr(self, "_img_drag", None)
        pos = drag["pos"] if drag else self.selected_image()
        if pos is None:
            return
        r = self.image_rect(pos)
        if r is None:
            return
        from .theme import CURRENT, ensure_contrast
        accent = QColor(ensure_contrast(CURRENT["accent"], "#FFFFFF", 3.0))
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if drag and drag.get("preview") is not None:
            pr = drag["preview"]
            p.setPen(QPen(accent, 1.5, Qt.PenStyle.DashLine))
            p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 25))
            p.drawRect(pr)
            label = f"{round(pr.width() * 25.4 / 96)} × {round(pr.height() * 25.4 / 96)} mm"
            f = QFont(self.font())
            f.setPixelSize(11)
            p.setFont(f)
            tr = QRectF(pr.left(), pr.bottom() + 4, 96, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 170))
            p.drawRoundedRect(tr, 4, 4)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(tr, int(Qt.AlignmentFlag.AlignCenter), label)
            r = pr
        p.setPen(QPen(accent, 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.setBrush(QColor("#FFFFFF"))
        for hr in self._handles(r).values():
            p.drawRect(hr)
        p.end()

    def image_names(self):
        names = set()
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                cf = it.fragment().charFormat()
                if cf.isImageFormat():
                    names.add(cf.toImageFormat().name())
                it += 1
            block = block.next()
        return names

    # -------------------------------------------------------------- olaylar
    def mousePressEvent(self, e):
        hit = self.hf_hit(e.position().toPoint())
        if hit is not None and e.button() == Qt.MouseButton.LeftButton:
            i, which, zone = hit
            edit_r, del_r = self.hf_buttons(zone)
            text, _ = self.setup.hf_for(which, i + 1)
            pt = QPointF(e.position())
            if text and del_r.contains(pt):
                self.hf_set(i + 1, which, "", scope="page")
                return
            if edit_r.contains(pt) or not text:
                self.hfEditRequested.emit(i + 1, which)
                return
        if e.button() == Qt.MouseButton.LeftButton:
            hit = self._handle_at(e.position())
            if hit is not None:
                pos, name, r = hit
                self._img_drag = {"pos": pos, "handle": name, "rect": r, "start": QPointF(e.position()),
                                  "preview": None}
                return
            pos = self.image_at_point(e.position())
            if pos is not None:
                self.setFocus()
                self._select_image(pos)                    # resme tıkla: seçilir, tutamaçlar çıkar
                if image_slot(self._image_at(pos).name()):
                    self.imageReplaceRequested.emit(pos)   # "Logo ekle" alanı: tek tıkla resim seç
                return
        super().mousePressEvent(e)

    def leaveEvent(self, e):
        self._set_hf_hover(None)
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        pos = e.position().toPoint()
        hit = self.hf_hit(pos)
        if hit is not None:
            self.hfEditRequested.emit(hit[0] + 1, hit[1])
            return
        c = self.cursorForPosition(pos)
        for p in (c.position(), c.position() - 1):
            if self._image_at(p) is not None:
                self.imageEditRequested.emit(p)
                return
        fid = self.footnote_at(c.position())
        if fid:
            self.footnoteEditRequested.emit(fid)
            return
        super().mouseDoubleClickEvent(e)

    def _image_at(self, pos):
        if pos < 0:
            return None
        c = QTextCursor(self.document())
        c.setPosition(pos)
        if c.atBlockEnd():
            return None
        c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        cf = c.charFormat()
        return cf.toImageFormat() if cf.isImageFormat() else None

    def mouseReleaseEvent(self, e):
        drag = getattr(self, "_img_drag", None)
        if drag is not None:
            self._img_drag = None
            pr = drag.get("preview")
            if pr is not None:
                self.resize_image(drag["pos"], pr.width(), pr.height())
            self.viewport().update()
            return
        super().mouseReleaseEvent(e)
        if self.painter_format is not None and self.textCursor().hasSelection():
            cf, bf = self.painter_format
            c = self.textCursor()
            c.beginEditBlock()
            c.mergeCharFormat(cf)
            c.mergeBlockFormat(bf)
            c.endEditBlock()
            self.painter_format = None
            self.viewport().unsetCursor()
            self.formatPainterDone.emit()
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            href = self.anchorAt(e.position().toPoint())
            if href:
                self.open_link(href)
        elif e.button() == Qt.MouseButton.LeftButton and not self.textCursor().hasSelection():
            self._select_placeholder()
        ids = self.comment_ids_at(self.textCursor().position())
        self.set_active_comment(ids[0] if ids else None)
        if e.button() == Qt.MouseButton.LeftButton and self.textCursor().hasSelection():
            self.selectionFinished.emit()

    def open_link(self, href):
        if href.startswith("#"):
            self.scrollToAnchor(href[1:])
            return
        if not is_safe_link(href):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Güvenlik", "Bu bağlantı güvenli bir web/e-posta adresi değil ve açılmadı:\n"
                                f"{href[:200]}")
            return
        QDesktopServices.openUrl(QUrl(href))

    def _select_placeholder(self):
        """Yer tutucuya tıklanınca tamamını seç; yazılınca yerine geçer."""
        pos = self.textCursor().position()
        for a, b, _, cf in self.tc_segments(max(0, pos - 1), pos + 1):
            if cf.hasProperty(PLACEHOLDER_PROP) and a <= pos <= b:
                # aynı yer tutucunun bitişik parçalarını da kapsa
                block = self.document().findBlock(a)
                start, end = a, b
                for a2, b2, _, cf2 in self.tc_segments(block.position(), block.position() + block.length() - 1):
                    if cf2.hasProperty(PLACEHOLDER_PROP) and (b2 == start or a2 == end or a2 <= start < b2):
                        start, end = min(start, a2), max(end, b2)
                c = self.textCursor()
                c.setPosition(start)
                c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(c)
                return True
        return False

    def placeholder_count(self):
        n, last = 0, -2
        for a, b, _, cf in self.tc_segments():
            if cf.hasProperty(PLACEHOLDER_PROP):
                if a != last:
                    n += 1
                last = b
        return n

    def wheelEvent(self, e):
        # Kaydırma/yakınlaştırmayı dıştaki görünüm yapar (QTextEdit'in Ctrl+tekerlek yazı büyütmesini engelle)
        e.ignore()

    def ensureCursorVisible(self):
        self.cursorVisibilityRequested.emit()

    def mouseMoveEvent(self, e):
        drag = getattr(self, "_img_drag", None)
        if drag is not None:
            drag["preview"] = self._drag_rect(QPointF(e.position()))
            self.viewport().update()
            return
        if not e.buttons():
            handle = self._handle_at(e.position())
            if handle is not None:
                self.viewport().setCursor(self._HANDLE_CURSORS[handle[1]])
                self.viewport().setToolTip("Sürükleyerek boyutlandırın (köşeler oranı korur)")
                return
            ip = self.image_at_point(e.position())
            if ip is not None:
                slot = image_slot(self._image_at(ip).name())
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                self.viewport().setToolTip(f"{IMAGE_SLOT_KINDS[slot]}: tıklayıp bir resim seçin" if slot else
                                           "Tıklayın: seçip köşelerinden boyutlandırın · çift tık: boyut ayarı")
                return
        super().mouseMoveEvent(e)
        pos = e.position().toPoint()
        hit = self.hf_hit(pos) if not e.buttons() else None
        self._set_hf_hover((hit[0], hit[1]) if hit else None)
        if hit:
            edit_r, del_r = self.hf_buttons(hit[2])
            over_btn = edit_r.contains(QPointF(pos)) or del_r.contains(QPointF(pos))
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if over_btn else Qt.CursorShape.ArrowCursor)
            self.viewport().setToolTip("Sağ tık: bu sayfada düzenle / kaldır, tüm sayfalarda değiştir…")
            return
        if self.painter_format is None:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        href = self.anchorAt(pos)
        self.viewport().setToolTip(f"{href}\nAçmak için Ctrl+tıklayın" if href else "")

    def start_format_painter(self):
        c = self.textCursor()
        self.painter_format = (clean_tc(c.charFormat()), c.blockFormat())
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)

    def keyPressEvent(self, e):
        key, mods, text = e.key(), e.modifiers(), e.text()
        cur = self.textCursor()
        ctrl_only = bool(mods & Qt.KeyboardModifier.ControlModifier) and not (mods & Qt.KeyboardModifier.AltModifier)
        if key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            r = self.cursorRect()
            dy = self.page_step() * (1 if key == Qt.Key.Key_PageDown else -1)
            c = self.cursorForPosition(r.center() + QPointF(0, dy).toPoint())
            mode = QTextCursor.MoveMode.KeepAnchor if mods & Qt.KeyboardModifier.ShiftModifier \
                else QTextCursor.MoveMode.MoveAnchor
            nc = self.textCursor()
            nc.setPosition(c.position(), mode)
            self.setTextCursor(nc)
            self.ensureCursorVisible()
            return
        if self.autocorrect and not cur.hasSelection() and not ctrl_only and (
                (text and text in AUTOCORRECT_TRIGGERS) or key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self._autocorrect(capitalize=text in (" ", "\t") or key in (Qt.Key.Key_Return, Qt.Key.Key_Enter))
            cur = self.textCursor()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (mods & Qt.KeyboardModifier.ShiftModifier):
            blk = cur.block()
            if blk.textList() is not None and not blk.text().strip() and not cur.hasSelection():
                self.change_list_level(-99)
                return
            style = self.current_style_name()
            at_end = cur.atBlockEnd()
            if self.track_changes and cur.hasSelection():
                self._tc_mark_deleted(cur, True)
                self.setTextCursor(cur)
            super().keyPressEvent(e)
            c = self.textCursor()
            bf = c.blockFormat()
            if bf.pageBreakPolicy() != QTextFormat.PageBreakFlag.PageBreak_Auto:
                bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_Auto)
                c.setBlockFormat(bf)
            if bf.hasProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth):
                bf.clearProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth)
                c.setBlockFormat(bf)
            if bf.hasProperty(TOC_PROP):
                bf.clearProperty(TOC_PROP)
                c.setBlockFormat(bf)
            if style not in ("Normal", "Alıntı") and at_end:
                self.apply_style("Normal")
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and cur.block().textList() is not None \
                and (cur.atBlockStart() or cur.hasSelection()):
            self.change_list_level(-1 if key == Qt.Key.Key_Backtab or mods & Qt.KeyboardModifier.ShiftModifier else 1)
            return
        table_key = key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not ctrl_only
        if table_key and not self.isReadOnly() and not self.track_changes \
                and self._table_key(cur, key == Qt.Key.Key_Backspace):
            return
        if not self.isReadOnly() and text and text.isprintable() and not ctrl_only:
            self._heal_block(cur)
        if not self.isReadOnly():
            if self.track_changes:
                if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                    self._tc_delete(key == Qt.Key.Key_Backspace, bool(mods & Qt.KeyboardModifier.ControlModifier))
                    return
                if text and text.isprintable() and not ctrl_only:
                    self.type_text(text)
                    return
            elif text and text.isprintable() and not ctrl_only and (
                    self.currentCharFormat().hasProperty(TC_TYPE) or self._selection_is_placeholder()):
                self.type_text(text)
                return
        super().keyPressEvent(e)

    def _selection_is_placeholder(self):
        c = self.textCursor()
        if not c.hasSelection():
            return self.currentCharFormat().hasProperty(PLACEHOLDER_PROP)
        p = QTextCursor(c)
        p.setPosition(c.selectionStart() + 1)
        return p.charFormat().hasProperty(PLACEHOLDER_PROP)

    def _case_fix(self, word, sentence_start):
        """Bir sözcüğün büyük/küçük harf düzeltmesi (yoksa None)."""
        letters = [ch for ch in word if ch.isalpha()]
        if len(letters) < 2 or not word[:1].isalpha():
            return None
        # İKi BAşharf → İki Başharf; İSTanbul → İstanbul (kısaltma+ek olmasın diye en az 3 küçük harf)
        caps = len(word) - len(word.lstrip("ABCÇDEFGĞHIİJKLMNOÖPQRSŞTUÜVWXYZ"))
        rest = word[caps:]
        if (caps == 2 and len(rest) >= 1 or caps == 3 and len(rest) >= 3) and rest.isalpha() and rest.islower():
            return word[0] + turkish_lower(word[1:])
        # cAPS LOCK kazası → Caps Lock
        if len(word) >= 3 and word[0].islower() and word[1:].isalpha() and word[1:].isupper():
            return turkish_upper(word[0]) + turkish_lower(word[1:])
        if word[0].islower():
            if sentence_start:
                return turkish_upper(word[0]) + word[1:]
            # Özel ad: sözlükte yalnız büyük harfle geçiyorsa (türkiye → Türkiye)
            sp = self.spell
            if sp is not None and sp.ready and word.isalpha() and not sp.check(word):
                cap = turkish_upper(word[0]) + word[1:]
                if sp.check(cap):
                    return cap
        return None

    def _autocorrect(self, capitalize):
        c = self.textCursor()
        block = c.block()
        before = block.text()[:c.positionInBlock()]
        m = re.search(r"(\S+)$", before)
        if not m:
            return
        word = m.group(1)
        repl = AUTOCORRECT.get(word)
        if repl is None:
            low = turkish_lower(word)
            if low in AUTOCORRECT and AUTOCORRECT[low][:1].islower():
                repl = AUTOCORRECT[low]
                if word[:1].isupper():
                    repl = turkish_upper(repl[:1]) + repl[1:]
        cur_word = repl or word
        if capitalize and "." not in word.rstrip(".,;:!?)")[1:] and "@" not in word and "/" not in word \
                and "://" not in before:
            prev = before[:m.start(1)].rstrip()
            start = (prev == "" and block.textList() is None and QTextCursor(block).currentTable() is None) \
                or (prev[-1:] in (".", "!", "?") and not prev.endswith(".."))
            core = cur_word.rstrip(".,;:!?)")
            fixed = self._case_fix(core, start)
            if fixed:
                repl = fixed + cur_word[len(core):]
        if repl and repl != word:
            rc = QTextCursor(self.document())
            start = block.position() + m.start(1)
            rc.setPosition(start)
            rc.setPosition(c.position(), QTextCursor.MoveMode.KeepAnchor)
            fmt = rc.charFormat()
            self.type_text(repl, rc)
            self.setTextCursor(rc)
            self.setCurrentCharFormat(clean_tc(fmt))

    def fix_capitalization(self, apply=True):
        """Belgedeki cümle başı, özel ad, İKi BAşharf ve cAPS LOCK hatalarını bulur/düzeltir."""
        doc = self.document()
        fixes = []
        block = doc.begin()
        while block.isValid():
            text = block.text()
            in_list = block.textList() is not None
            for m in re.finditer(r"[^\W\d_][\w'’-]*", text):
                word = m.group()
                prev = text[:m.start()].rstrip()
                start = (prev == "" and not in_list) or (prev[-1:] in (".", "!", "?") and not prev.endswith(".."))
                if prev.endswith(("http", "www", "@")) or "://" in text[max(0, m.start() - 12):m.start()]:
                    continue
                fixed = self._case_fix(word, start)
                if fixed and fixed != word:
                    fixes.append((block.position() + m.start(), word, fixed))
            block = block.next()
        if apply and fixes:
            c = QTextCursor(doc)
            c.beginEditBlock()
            for pos, word, fixed in reversed(fixes):
                r = QTextCursor(doc)
                r.setPosition(pos)
                r.setPosition(pos + len(word), QTextCursor.MoveMode.KeepAnchor)
                if self.track_changes:
                    self.type_text(fixed, r)
                else:
                    probe = QTextCursor(doc)
                    probe.setPosition(pos + 1)
                    r.insertText(fixed, probe.charFormat())
            c.endEditBlock()
        return fixes

    # ------------------------------------------------------ değişiklik izleme
    def _tc_format(self, kind):
        f = QTextCharFormat()
        f.setProperty(TC_TYPE, kind)
        f.setProperty(TC_AUTHOR, self.author)
        f.setProperty(TC_DATE, datetime.datetime.now().replace(microsecond=0).isoformat())
        return f

    def type_text(self, text, cursor=None):
        """Metni ekler; izleme açıksa ekleme olarak işaretler."""
        own = cursor is None
        c = self.textCursor() if own else cursor
        src = c.charFormat() if not own else self.currentCharFormat()
        if c.hasSelection():
            probe = QTextCursor(c)
            probe.setPosition(c.selectionStart() + 1)
            if probe.charFormat().hasProperty(PLACEHOLDER_PROP):
                src = probe.charFormat()
        base = clean_tc(src)
        c.beginEditBlock()
        if c.hasSelection():
            if self.track_changes:
                self._tc_mark_deleted(c, True)
            else:
                c.removeSelectedText()
        if self.track_changes:
            base.merge(self._tc_format("ins"))
        c.insertText(text, base)
        c.endEditBlock()
        if own:
            self.setTextCursor(c)
            self.ensureCursorVisible()

    def tc_segments(self, start=0, end=None):
        doc = self.document()
        if end is None:
            end = doc.characterCount()
        segs = []
        block = doc.findBlock(start)
        while block.isValid() and block.position() < end:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fs = frag.position()
                fe = fs + frag.length()
                a, b = max(fs, start), min(fe, end)
                if a < b:
                    cf = frag.charFormat()
                    segs.append((a, b, cf.property(TC_TYPE) or None, cf))
                it += 1
            block = block.next()
        return segs

    def _tc_mark_deleted(self, cursor, to_end):
        s, e = cursor.selectionStart(), cursor.selectionEnd()
        removed = 0
        c = QTextCursor(self.document())
        mark = self._tc_format("del")
        for a, b, kind, _ in reversed(self.tc_segments(s, e)):
            c.setPosition(a)
            c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            if kind == "ins":
                c.removeSelectedText()
                removed += b - a
            elif kind != "del":
                c.mergeCharFormat(mark)
        cursor.setPosition(e - removed if to_end else s)

    def _tc_delete(self, back, word):
        c = self.textCursor()
        c.beginEditBlock()
        to_end = False
        if not c.hasSelection():
            if back:
                op = QTextCursor.MoveOperation.PreviousWord if word else QTextCursor.MoveOperation.PreviousCharacter
            else:
                op = QTextCursor.MoveOperation.NextWord if word else QTextCursor.MoveOperation.NextCharacter
                to_end = True
            c.movePosition(op, QTextCursor.MoveMode.KeepAnchor)
        if c.hasSelection():
            self._tc_mark_deleted(c, to_end)
        c.endEditBlock()
        self.setTextCursor(c)

    def insertFromMimeData(self, source):
        c = self.textCursor()
        self._heal_block(c)
        c.beginEditBlock()
        if self.track_changes and c.hasSelection():
            self._tc_mark_deleted(c, True)
            self.setTextCursor(c)
        start = c.position()
        image_files = [u.toLocalFile() for u in source.urls() if u.isLocalFile() and
                       os.path.splitext(u.toLocalFile())[1].lower() in
                       (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")] if source.hasUrls() else []
        if image_files:
            for f in image_files:
                img = QImage(f)
                if not img.isNull():
                    self.insert_image(img)
        elif source.hasImage() and not source.hasHtml():
            img = QImage(source.imageData())
            if not img.isNull():
                self.insert_image(img)
        else:
            super().insertFromMimeData(source)
        end = self.textCursor().position()
        m = QTextCursor(self.document())
        m.setPosition(start)
        m.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        if self.track_changes:
            m.mergeCharFormat(self._tc_format("ins"))
        else:
            for a, b, kind, cf in reversed(self.tc_segments(start, end)):
                if kind:
                    m.setPosition(a)
                    m.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                    m.setCharFormat(clean_tc(cf))
        c.endEditBlock()

    def tc_resolve(self, accept, start=0, end=None):
        segs = [s for s in self.tc_segments(start, end) if s[2]]
        if not segs:
            return 0
        c = QTextCursor(self.document())
        c.beginEditBlock()
        for a, b, kind, cf in reversed(segs):
            c.setPosition(a)
            c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            if (kind == "ins") == accept:
                c.setCharFormat(clean_tc(cf))
            else:
                c.removeSelectedText()
        c.endEditBlock()
        return len(segs)

    def tc_at_cursor(self):
        pos = self.textCursor().position()
        for a, b, kind, cf in self.tc_segments(max(0, pos - 1), pos + 1):
            if kind:
                return a, b, kind, cf
        return None

    def tc_resolve_current(self, accept):
        c = self.textCursor()
        if c.hasSelection():
            return self.tc_resolve(accept, c.selectionStart(), c.selectionEnd())
        seg = self.tc_at_cursor()
        if seg:
            return self.tc_resolve(accept, seg[0], seg[1])
        return 0

    def tc_goto(self, forward=True):
        pos = self.textCursor().selectionEnd() if forward else self.textCursor().selectionStart()
        segs = [s for s in self.tc_segments() if s[2]]
        # Bitişik aynı türden parçaları birleştir
        merged = []
        for a, b, k, _ in segs:
            if merged and merged[-1][2] == k and merged[-1][1] == a:
                merged[-1] = (merged[-1][0], b, k)
            else:
                merged.append((a, b, k))
        cand = [m for m in merged if m[0] >= pos] if forward else [m for m in merged if m[1] <= pos]
        if not cand:
            return False
        a, b, _ = cand[0] if forward else cand[-1]
        c = self.textCursor()
        c.setPosition(a)
        c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(c)
        self.ensureCursorVisible()
        return True

    def has_changes(self):
        return any(s[2] for s in self.tc_segments())

    # ------------------------------------------------------------ stiller
    def current_style_name(self):
        bf = self.textCursor().blockFormat()
        name = bf.property(STYLE_PROP)
        if name in STYLES:
            return name
        lvl = bf.headingLevel()
        if 1 <= lvl <= 3:
            return f"Başlık {lvl}"
        return "Normal"

    def _blocks_in(self, cursor):
        doc = self.document()
        block = doc.findBlock(cursor.selectionStart())
        endb = doc.findBlock(cursor.selectionEnd())
        while block.isValid():
            yield block
            if block == endb:
                break
            block = block.next()

    def apply_style(self, name, cursor=None):
        lvl, size, bold, italic, color, _ = STYLES[name]
        c = cursor or self.textCursor()
        c.beginEditBlock()
        cf = QTextCharFormat()
        cf.setFontPointSize(size or DEFAULT_SIZE)
        cf.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        cf.setFontItalic(italic)
        cf.setForeground(QColor(color or "#000000"))
        for block in list(self._blocks_in(c)):
            bc = QTextCursor(block)
            bf = bc.blockFormat()
            bf.setHeadingLevel(lvl)
            bf.setProperty(STYLE_PROP, name)
            if lvl:
                bf.setTopMargin(pt2px(12 if lvl == 1 else 8))
                bf.setBottomMargin(pt2px(4))
            elif name == "Konu Başlığı":
                bf.setTopMargin(0)
                bf.setBottomMargin(pt2px(10))
            else:
                bf.setTopMargin(0)
                bf.setBottomMargin(pt2px(8))
            if name == "Alıntı":
                bf.setLeftMargin(pt2px(36))
                bf.setRightMargin(pt2px(36))
            elif block.blockFormat().property(STYLE_PROP) == "Alıntı":
                bf.setLeftMargin(0)
                bf.setRightMargin(0)
            bc.setBlockFormat(bf)
            bc.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            bc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            bc.mergeCharFormat(cf)
            bc.mergeBlockCharFormat(cf)
        c.endEditBlock()
        if cursor is None:
            self.mergeCurrentCharFormat(cf)

    def merge_format(self, cf):
        self.mergeCurrentCharFormat(cf)

    def clear_formatting(self):
        c = self.textCursor()
        if not c.hasSelection():
            c.select(QTextCursor.SelectionType.BlockUnderCursor)
        c.beginEditBlock()
        m = QTextCursor(self.document())
        for a, b, kind, cf in reversed(self.tc_segments(c.selectionStart(), c.selectionEnd())):
            f = QTextCharFormat()
            f.setFontFamilies([DEFAULT_FONT])
            f.setFontPointSize(DEFAULT_SIZE)
            if cf.isImageFormat():
                continue
            for p in TC_PROPS:
                if cf.hasProperty(p):
                    f.setProperty(p, cf.property(p))
            m.setPosition(a)
            m.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            m.setCharFormat(f)
        self.apply_style("Normal", c)
        c.endEditBlock()

    def change_case(self, mode):
        c = self.textCursor()
        if not c.hasSelection():
            return
        fn = {"upper": turkish_upper, "lower": turkish_lower, "title": turkish_title,
              "sentence": lambda s: turkish_upper(s[:1]) + turkish_lower(s[1:])}[mode]
        c.beginEditBlock()
        m = QTextCursor(self.document())
        first = True
        for a, b, kind, cf in self.tc_segments(c.selectionStart(), c.selectionEnd()):
            if cf.isImageFormat():
                continue
            m.setPosition(a)
            m.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            t = m.selectedText()
            nt = fn(t) if (mode != "sentence" or first) else turkish_lower(t)
            first = False
            if nt != t:
                m.insertText(nt, cf)
        c.endEditBlock()

    # -------------------------------------------------------------- listeler
    def toggle_list(self, style):
        c = self.textCursor()
        lst = c.currentList()
        c.beginEditBlock()
        if lst is not None and lst.format().style() == style:
            for block in list(self._blocks_in(c)):
                bl = block.textList()
                if bl is not None:
                    bl.remove(block)
                    bc = QTextCursor(block)
                    bf = bc.blockFormat()
                    bf.setIndent(0)
                    bc.setBlockFormat(bf)
        else:
            lf = QTextListFormat()
            lf.setStyle(style)
            lf.setIndent(lst.format().indent() if lst is not None else 1)
            c.createList(lf)
        c.endEditBlock()

    def change_list_level(self, delta):
        c = self.textCursor()
        c.beginEditBlock()
        for block in list(self._blocks_in(c)):
            lst = block.textList()
            bc = QTextCursor(block)
            if lst is None:
                bf = bc.blockFormat()
                bf.setIndent(max(0, bf.indent() + delta))
                bc.setBlockFormat(bf)
                continue
            lvl = lst.format().indent() + delta
            if lvl < 1:
                lst.remove(block)
                bf = bc.blockFormat()
                bf.setIndent(0)
                bc.setBlockFormat(bf)
                continue
            lvl = min(lvl, 9)
            numbered = lst.format().style() in NUMBER_STYLES
            target = None
            prev = block.previous()
            while prev.isValid() and prev.textList() is not None:
                pl = prev.textList()
                pi = pl.format().indent()
                if pi == lvl and (pl.format().style() in NUMBER_STYLES) == numbered:
                    target = pl
                    break
                if pi < lvl:
                    break
                prev = prev.previous()
            if target is not None:
                target.add(block)
            else:
                lf = QTextListFormat(lst.format())
                lf.setIndent(lvl)
                lf.setStyle((NUMBER_STYLES if numbered else BULLET_STYLES)[(lvl - 1) % 3])
                bc.createList(lf)
        c.endEditBlock()

    # -------------------------------------------------------------- ekleme
    def insert_image(self, image, name=None):
        doc = self.document()
        name = name or f"omoffice-img-{uuid.uuid4().hex[:10]}.png"
        doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        w, h = float(image.width()), float(image.height())
        tw = self.text_width()
        if w > tw:
            h *= tw / w
            w = tw
        fmt = QTextImageFormat()
        fmt.setName(name)
        fmt.setWidth(w)
        fmt.setHeight(h)
        if self.track_changes:
            fmt.merge(self._tc_format("ins"))
        c = self.textCursor()
        c.insertImage(fmt)
        self.setTextCursor(c)

    def delete_image(self, pos):
        if self._image_at(pos) is None:
            return False
        c = QTextCursor(self.document())
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        self.setTextCursor(c)
        return True

    def resize_image(self, pos, w, h):
        fmt = self._image_at(pos)
        if fmt is None:
            return False
        nf = QTextImageFormat(fmt)
        nf.setWidth(round(w, 1))
        nf.setHeight(round(h, 1))
        c = QTextCursor(self.document())
        c.setPosition(pos)
        c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        c.setCharFormat(nf)
        self._select_image(pos)
        return True

    def image_bytes(self, name):
        res = self.document().resource(QTextDocument.ResourceType.ImageResource, QUrl(name))
        img = QImage(res) if res is not None else QImage(name)
        if img.isNull():
            return None, None
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        return bytes(ba.data()), img

    def insert_table(self, rows, cols):
        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        tf.setBorderBrush(QBrush(QColor("#808080")))
        tf.setBorderCollapse(True)
        tf.setCellPadding(5)
        tf.setCellSpacing(0)
        tf.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        c = self.textCursor()
        c.insertTable(rows, cols, tf)
        self.setTextCursor(c)

    def insert_page_break(self):
        c = self.textCursor()
        c.beginEditBlock()
        c.insertBlock()
        bf = c.blockFormat()
        bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        c.setBlockFormat(bf)
        c.endEditBlock()
        self.setTextCursor(c)

    def insert_horizontal_rule(self):
        c = self.textCursor()
        c.beginEditBlock()
        c.insertBlock()
        bf = c.blockFormat()
        bf.setProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth,
                       QTextLength(QTextLength.Type.PercentageLength, 100))
        c.setBlockFormat(bf)
        c.insertBlock()
        bf.clearProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth)
        c.setBlockFormat(bf)
        c.endEditBlock()
        self.setTextCursor(c)

    def insert_link(self, text, url):
        c = self.textCursor()
        base = clean_tc(self.currentCharFormat())
        cf = QTextCharFormat(base)
        cf.setAnchor(True)
        cf.setAnchorHref(url)
        cf.setForeground(QColor("#0563C1"))
        cf.setFontUnderline(True)
        if self.track_changes:
            cf.merge(self._tc_format("ins"))
        c.beginEditBlock()
        if c.hasSelection():
            if self.track_changes:
                self._tc_mark_deleted(c, True)
            else:
                c.removeSelectedText()
        c.insertText(text or url, cf)
        c.endEditBlock()
        plain = QTextCharFormat(base)
        plain.setAnchor(False)
        plain.clearProperty(QTextFormat.Property.AnchorHref)
        plain.setForeground(QColor("#000000"))
        plain.setFontUnderline(False)
        self.setTextCursor(c)
        self.setCurrentCharFormat(plain)

    def headings(self):
        out = []
        block = self.document().begin()
        while block.isValid():
            lvl = block.blockFormat().headingLevel()
            if lvl and block.text().strip():
                out.append((lvl, block.text().strip(), block.position()))
            block = block.next()
        return out

    def toc_range(self):
        """Var olan içindekiler bloklarının (başlangıç, bitiş) konumu."""
        block = self.document().begin()
        start = end = None
        while block.isValid():
            if block.blockFormat().hasProperty(TOC_PROP):
                if start is None:
                    start = block.position()
                end = block.position() + block.length()
            elif start is not None:
                break
            block = block.next()
        return (start, end) if start is not None else None

    def update_toc(self):
        rng = self.toc_range()
        if rng is None:
            return self.insert_toc()
        c = QTextCursor(self.document())
        c.beginEditBlock()
        c.setPosition(rng[0])
        c.setPosition(min(rng[1], self.document().characterCount() - 1), QTextCursor.MoveMode.KeepAnchor)
        c.removeSelectedText()
        bf = c.blockFormat()
        bf.clearProperty(TOC_PROP)
        c.setBlockFormat(bf)
        ok = self.insert_toc(c)
        c.endEditBlock()
        return ok

    def insert_toc(self, cursor=None):
        heads = self.headings()
        doc = self.document()
        if not heads:
            return False
        anchors = []
        for _, _, pos in heads:
            ac = QTextCursor(doc)
            ac.setPosition(pos)
            anchors.append(ac)
        c = QTextCursor(cursor) if cursor is not None else self.textCursor()
        c.beginEditBlock()
        c.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        tbf = QTextBlockFormat()
        tbf.setBottomMargin(pt2px(8))
        tbf.setProperty(STYLE_PROP, "Normal")
        tbf.setProperty(TOC_PROP, True)
        tcf = QTextCharFormat()
        tcf.setFontPointSize(16)
        tcf.setFontWeight(QFont.Weight.Bold)
        tcf.setForeground(QColor("#2F5496"))
        c.insertBlock(tbf, tcf)
        c.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        c.insertText("İçindekiler", tcf)
        c.movePosition(QTextCursor.MoveOperation.NextBlock)
        entries = []
        tw = self.text_width()
        for lvl, text, _ in heads:
            bf = QTextBlockFormat()
            bf.setLeftMargin(pt2px(14 * (lvl - 1)))
            bf.setBottomMargin(pt2px(3))
            bf.setProperty(TOC_PROP, True)
            bf.setTabPositions([QTextOption.Tab(tw - pt2px(14 * (lvl - 1)) - 2, QTextOption.TabType.RightTab)])
            cf = QTextCharFormat()
            cf.setFontPointSize(DEFAULT_SIZE)
            cf.setFontWeight(QFont.Weight.Bold if lvl == 1 else QFont.Weight.Normal)
            cf.setForeground(QColor("#000000"))
            c.insertText(f"{text}\t0", cf)
            ec = QTextCursor(c)
            # satır başına al: aksi halde hemen ardından eklenen blok bu imleci bir sonraki satıra iter
            ec.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            entries.append(ec)
            c.insertBlock(bf, cf)
            c.movePosition(QTextCursor.MoveOperation.PreviousBlock)
            c.setBlockFormat(bf)
            c.movePosition(QTextCursor.MoveOperation.NextBlock)
        # Sayfa numaralarını içindekiler eklendikten sonraki yerleşime göre yaz
        doc.documentLayout().documentSize()
        for ec, ac in zip(entries, anchors):
            block = ec.block()
            t = block.text()
            tab = t.rfind("\t")
            if tab < 0:
                continue
            nc = QTextCursor(block)
            nc.setPosition(block.position() + tab + 1)
            nc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            nc.insertText(str(self.page_of_position(ac.position())))
        c.endEditBlock()
        return True

    # ------------------------------------------------------------ açıklamalar
    def add_comment(self, text):
        c = self.textCursor()
        if not c.hasSelection():
            c.select(QTextCursor.SelectionType.WordUnderCursor)
            if not c.hasSelection():
                return None
        cid = str(max([int(k) for k in self.comments if str(k).isdigit()] + [0]) + 1)
        self.comments[cid] = {"author": self.author, "text": text, "resolved": False,
                              "date": datetime.datetime.now().replace(microsecond=0).isoformat()}
        m = QTextCursor(self.document())
        m.beginEditBlock()
        for a, b, _, cf in reversed(self.tc_segments(c.selectionStart(), c.selectionEnd())):
            ids = [i for i in str(cf.property(COMMENT_PROP) or "").split(",") if i]
            f = QTextCharFormat()
            f.setProperty(COMMENT_PROP, ",".join(ids + [cid]))
            m.setPosition(a)
            m.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            m.mergeCharFormat(f)
        m.endEditBlock()
        self.active_comment = cid
        self.commentsChanged.emit()
        return cid

    def comment_ranges(self):
        """Belgede bağlı metni olan açıklamalar: id -> (başlangıç, bitiş), metindeki sırayla."""
        out = {}
        for a, b, _, cf in self.tc_segments():
            for cid in str(cf.property(COMMENT_PROP) or "").split(","):
                if cid:
                    s0, e0 = out.get(cid, (a, b))
                    out[cid] = (min(s0, a), max(e0, b))
        return dict(sorted(out.items(), key=lambda kv: kv[1][0]))

    def comment_ids_at(self, pos):
        for a, b, _, cf in self.tc_segments(max(0, pos - 1), pos + 1):
            ids = [i for i in str(cf.property(COMMENT_PROP) or "").split(",") if i in self.comments]
            if ids:
                return ids
        return []

    def set_active_comment(self, cid):
        if cid != self.active_comment:
            self.active_comment = cid
            self.highlighter.rehighlight()
            self.commentsChanged.emit()

    def select_comment(self, cid):
        rng = self.comment_ranges().get(cid)
        if rng:
            c = self.textCursor()
            c.setPosition(rng[0])
            c.setPosition(rng[1], QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(c)
            self.ensureCursorVisible()
        self.set_active_comment(cid)

    def delete_comment(self, cid):
        m = QTextCursor(self.document())
        m.beginEditBlock()
        for a, b, _, cf in reversed(self.tc_segments()):
            ids = [i for i in str(cf.property(COMMENT_PROP) or "").split(",") if i]
            if cid in ids:
                f = QTextCharFormat(cf)
                rest = [i for i in ids if i != cid]
                if rest:
                    f.setProperty(COMMENT_PROP, ",".join(rest))
                else:
                    f.clearProperty(COMMENT_PROP)
                m.setPosition(a)
                m.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                m.setCharFormat(f)
        m.endEditBlock()
        self.comments.pop(cid, None)
        if self.active_comment == cid:
            self.active_comment = None
        self.document().setModified(True)
        self.commentsChanged.emit()

    def resolve_comment(self, cid, resolved=True):
        if cid in self.comments:
            self.comments[cid]["resolved"] = resolved
            self.highlighter.rehighlight()
            self.document().setModified(True)
            self.commentsChanged.emit()

    def edit_comment(self, cid, text):
        if cid in self.comments:
            self.comments[cid]["text"] = text
            self.document().setModified(True)
            self.commentsChanged.emit()

    # --------------------------------------------------------------- dipnotlar
    def insert_footnote(self, text):
        fid = str(max([int(k) for k in self.footnotes if str(k).isdigit()] + [0]) + 1)
        self.footnotes[fid] = text
        cf = clean_tc(self.currentCharFormat())
        cf.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
        cf.setProperty(FOOTNOTE_PROP, fid)
        if self.track_changes:
            cf.merge(self._tc_format("ins"))
        c = self.textCursor()
        c.beginEditBlock()
        if c.hasSelection():
            c.setPosition(c.selectionEnd())
        c.insertText("#", cf)
        self.renumber_footnotes()
        c.endEditBlock()
        self.setTextCursor(c)
        self.setCurrentCharFormat(clean_tc(cf))
        return fid

    def renumber_footnotes(self):
        changed = False
        for n, (a, b, fid) in reversed(list(enumerate(self.footnote_refs(), 1))):
            c2 = QTextCursor(self.document())
            c2.setPosition(a)
            c2.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            if c2.selectedText() != str(n):
                fmt = c2.charFormat()
                c2.insertText(str(n), fmt)
                changed = True
        self._invalidate()
        return changed

    def footnote_at(self, pos):
        for a, b, fid in self.footnote_refs():
            if a <= pos <= b:
                return fid
        return None

    def delete_footnote(self, fid):
        c = QTextCursor(self.document())
        c.beginEditBlock()
        for a, b, f in reversed(self.footnote_refs()):
            if f == fid:
                c.setPosition(a)
                c.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                c.removeSelectedText()
        self.renumber_footnotes()
        c.endEditBlock()
        self.footnotes.pop(fid, None)
        self.viewport().update()

    # ------------------------------------------------------------- paragraf
    def sort_paragraphs(self, descending=False):
        c = self.textCursor()
        blocks = list(self._blocks_in(c))
        if len(blocks) < 2:
            return False
        if any(QTextCursor(b).currentTable() is not None for b in blocks):
            return False
        frags = []
        for b in blocks:
            bc = QTextCursor(b)
            bc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            frags.append((b.text(), bc.selection()))
        order = sorted(range(len(frags)), key=lambda i: turkish_sort_key(frags[i][0]), reverse=descending)
        if order == list(range(len(frags))):
            return True
        targets = []
        for b in blocks:
            tc = QTextCursor(b)
            tc.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            targets.append(tc)
        m = QTextCursor(self.document())
        m.beginEditBlock()
        for tc, i in zip(targets, order):
            tc.removeSelectedText()
            tc.insertFragment(frags[i][1])
        m.endEditBlock()
        return True

    def set_paragraph_shading(self, color):
        c = self.textCursor()
        c.beginEditBlock()
        for b in list(self._blocks_in(c)):
            bc = QTextCursor(b)
            bf = bc.blockFormat()
            if color is None:
                bf.clearBackground()
            else:
                bf.setBackground(QColor(color))
            bc.setBlockFormat(bf)
        c.endEditBlock()

    def set_show_marks(self, on):
        doc = self.document()
        opt = doc.defaultTextOption()
        flags = QTextOption.Flag.ShowTabsAndSpaces | QTextOption.Flag.ShowLineAndParagraphSeparators
        opt.setFlags(opt.flags() | flags if on else opt.flags() & ~flags)
        doc.setDefaultTextOption(opt)

    # ---------------------------------------------------------------- tablo
    def table_op(self, op):
        c = self.textCursor()
        t = c.currentTable()
        if t is None:
            return False
        cell = t.cellAt(c)
        r, col = cell.row(), cell.column()
        if op == "row_above":
            t.insertRows(r, 1)
        elif op == "row_below":
            t.insertRows(r + cell.rowSpan(), 1)
        elif op == "col_left":
            t.insertColumns(col, 1)
        elif op == "col_right":
            t.insertColumns(col + cell.columnSpan(), 1)
        elif op == "del_row":
            if c.hasComplexSelection():
                fr, nr, _, _ = c.selectedTableCells()
                t.removeRows(fr, nr)
            else:
                t.removeRows(r, 1)
        elif op == "del_col":
            if c.hasComplexSelection():
                _, _, fc, nc = c.selectedTableCells()
                t.removeColumns(fc, nc)
            else:
                t.removeColumns(col, 1)
        elif op == "merge":
            t.mergeCells(c)
        elif op == "split":
            t.splitCell(r, col, 1, 1)
        elif op == "delete":
            self._delete_table(t)
        elif op == "select":
            self._select_table(t)
        return True

    # Word'deki gibi: tablonun tamamı seçiliyken Backspace/Delete tabloyu, tam satırlar seçiliyken
    # satırları, tam sütunlar seçiliyken sütunları siler. Tablonun hemen altında Backspace (ya da hemen
    # üstünde Delete) önce tabloyu seçer; ikinci basış siler.
    def _table_key(self, cur, backspace):
        chosen = getattr(self, "_chosen_table", None)
        if chosen is not None and cur.hasSelection() and chosen[1] == (cur.anchor(), cur.position()):
            # _select_table ile seçilmiş tablo (1×1 kutularda Qt bunu hücre içi seçim sayar)
            t = cur.currentTable()
            if t is not None:
                self._delete_table(t)
                return True
        if cur.hasComplexSelection():
            t = cur.currentTable()
            if t is None:
                return False
            fr, nr, fc, nc = cur.selectedTableCells()
            if nr == t.rows() and nc == t.columns():
                self._delete_table(t)
            elif nc == t.columns():
                t.removeRows(fr, nr)
            elif nr == t.rows():
                t.removeColumns(fc, nc)
            else:
                return False   # birkaç hücre: Qt içeriklerini temizler
            return True
        if cur.hasSelection():
            # tabloyu tümüyle içine alan sıradan bir seçim (tablo + çevresi) Qt'de zaten silinir;
            # ardından kalan görünmez satırları onar
            if self._selection_has_table(cur):
                c = QTextCursor(cur)
                c.beginEditBlock()
                c.removeSelectedText()
                self._heal_around(c)
                c.endEditBlock()
                self.setTextCursor(c)
                return True
            return False
        block = cur.block()
        if backspace and cur.atBlockStart():
            near = block.previous()
        elif not backspace and cur.atBlockEnd():
            near = block.next()
        else:
            return False
        if not near.isValid():
            return False
        t = QTextCursor(near).currentTable()
        if t is None or cur.currentTable() is t:
            return False
        self._select_table(t)
        return True

    def _selection_has_table(self, cur):
        start, end = cur.selectionStart(), cur.selectionEnd()
        it = self.document().rootFrame().begin()
        while not it.atEnd():
            f = it.currentFrame()
            if f is not None and start < f.firstPosition() and f.lastPosition() < end:
                return True
            it += 1
        return False

    def _select_table(self, t):
        last = t.cellAt(t.rows() - 1, t.columns() - 1)
        c = QTextCursor(self.document())
        c.setPosition(t.cellAt(0, 0).firstPosition())
        c.setPosition(last.lastPosition(), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(c)
        self._chosen_table = (t, (c.anchor(), c.position()))

    def _delete_table(self, t):
        self._chosen_table = None
        c = QTextCursor(self.document())
        c.beginEditBlock()
        at = t.firstPosition() - 1
        t.removeRows(0, t.rows())
        c.setPosition(max(0, min(at, self.document().characterCount() - 1)))
        self._heal_around(c)
        c.endEditBlock()
        self.setTextCursor(c)

    @staticmethod
    def _is_spacer(block):
        """Şablonların tablo önüne/ardına koyduğu neredeyse sıfır yükseklikli satır."""
        bf = block.blockFormat()
        fixed = bf.lineHeightType() == QTextBlockFormat.LineHeightTypes.FixedHeight.value
        tiny_line = fixed and bf.lineHeight() < pt2px(6)
        tiny_font = 0 < block.charFormat().fontPointSize() < 4
        return tiny_line or tiny_font

    def _heal_block(self, cur):
        """Görünmez satıra yazı yazılacaksa satırı normal boyuta döndürür (sayfa sonu korunur)."""
        block = cur.block()
        if block.text() or not self._is_spacer(block):
            return
        c = QTextCursor(block)
        bf = block.blockFormat()
        bf.setLineHeight(100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        bf.setBottomMargin(pt2px(DEFAULT_SIZE * 0.6))
        c.setBlockFormat(bf)
        cf = QTextCharFormat()
        cf.setFontPointSize(self.document().defaultFont().pointSizeF() or DEFAULT_SIZE)
        c.setBlockCharFormat(cf)
        self.setCurrentCharFormat(cf)

    def _heal_around(self, c):
        """Tablo silindikten sonra imlecin kaldığı görünmez satırı normal boş satıra çevirir.
        Diğer görünmez satırlar sıfır yükseklikte kaldıkları için zararsızdır."""
        block = c.block()
        for b in (block, block.next(), block.previous()):
            if b.isValid() and not b.text() and QTextCursor(b).currentTable() is None and self._is_spacer(b):
                c.setPosition(b.position())
                self._heal_block(c)
                return

    def set_cell_background(self, color):
        c = self.textCursor()
        t = c.currentTable()
        if t is None:
            return
        if c.hasComplexSelection():
            fr, nr, fc, nc = c.selectedTableCells()
        else:
            cell = t.cellAt(c)
            fr, nr, fc, nc = cell.row(), 1, cell.column(), 1
        for r in range(fr, fr + nr):
            for col in range(fc, fc + nc):
                cell = t.cellAt(r, col)
                f = cell.format().toTableCellFormat()
                if color is None:
                    f.clearBackground()
                else:
                    f.setBackground(QColor(color))
                cell.setFormat(f)

    # ---------------------------------------------------------- bağlam menüsü
    def _hf_menu(self, e, page_index, which):
        n = page_index + 1
        name = "üst bilgi" if which == "header" else "alt bilgi"
        text, _ = self.setup.hf_for(which, n)
        menu = QMenu(self)
        menu.addAction(f"{name.capitalize()} — sayfa {n}").setEnabled(False)
        menu.addAction("Bu sayfada düzenle…", lambda: self.hfEditRequested.emit(n, which))
        if text:
            menu.addAction(f"Bu sayfadan kaldır", lambda: self.hf_set(n, which, "", scope="page"))
            menu.addAction(f"Bu sayfadan itibaren kaldır ({n}. sayfa ve sonrası)",
                           lambda: self.hf_set(n, which, "", scope="from"))
        if self.setup.hf_pages.get(n, {}).get(which) is not None:
            menu.addAction("Bu sayfayı varsayılana döndür", lambda: self.hf_reset_page(n, which))
        menu.addSeparator()
        menu.addAction(f"Tüm sayfalarda {name} değiştir…", lambda: self.hfEditRequested.emit(-n, which))
        if any(self.setup.hf_for(which, k)[0] for k in range(1, self.page_count() + 1)):
            menu.addAction(f"Tüm sayfalardan {name} kaldır", lambda: self.hf_set(n, which, "", scope="all"))
        if self.page_is_empty(n):
            menu.addSeparator()
            menu.addAction(f"Bu boş sayfayı sil ({n}. sayfa)", lambda: self.delete_empty_page(n))
        menu.exec(e.globalPos())

    def contextMenuEvent(self, e):
        hit = self.hf_hit(e.pos())
        if hit is not None:
            self._hf_menu(e, hit[0], hit[1])
            return
        menu = QMenu(self)
        _, ph = self.page_px()
        page_no = int(e.pos().y() // ph) + 1
        if self.page_is_empty(page_no):
            menu.addAction(f"Bu boş sayfayı sil ({page_no}. sayfa)", lambda: self.delete_empty_page(page_no))
            menu.addSeparator()
        c = self.cursorForPosition(e.pos())
        cur = self.textCursor()
        if not cur.hasSelection() or not (cur.selectionStart() <= c.position() <= cur.selectionEnd()):
            self.setTextCursor(c)
            cur = c
        # Yazım önerileri
        if self.spell is not None and self.spell.ready:
            wc = QTextCursor(c)
            wc.select(QTextCursor.SelectionType.WordUnderCursor)
            word = wc.selectedText()
            if word and word.isalpha() and not self.spell.check(word):
                sugg = self.spell.suggest(word)
                for s in sugg:
                    act = menu.addAction(s)
                    f = act.font()
                    f.setBold(True)
                    act.setFont(f)
                    act.triggered.connect(lambda _=False, s=s, wc=wc: self._replace_word(wc, s))
                if not sugg:
                    menu.addAction("(öneri yok)").setEnabled(False)
                menu.addAction("Yoksay", lambda w=word: (self.spell.ignore(w), self.highlighter.rehighlight()))
                menu.addAction("Sözlüğe ekle", lambda w=word: (self.spell.add_to_dictionary(w),
                                                               self.highlighter.rehighlight()))
                menu.addSeparator()
        seg = self.tc_at_cursor()
        if seg:
            kind = "Ekleme" if seg[2] == "ins" else "Silme"
            menu.addAction(f"{kind} — {seg[3].property(TC_AUTHOR)}").setEnabled(False)
            menu.addAction("Değişikliği kabul et", lambda: self.tc_resolve_current(True))
            menu.addAction("Değişikliği reddet", lambda: self.tc_resolve_current(False))
            menu.addSeparator()
        menu.addAction("Yeni açıklama…", self.newCommentRequested.emit)
        ids = self.comment_ids_at(c.position())
        if ids:
            menu.addAction("Açıklamayı sil", lambda cid=ids[0]: self.delete_comment(cid))
        fid = self.footnote_at(c.position())
        if fid:
            menu.addAction("Dipnotu düzenle…", lambda: self.footnoteEditRequested.emit(fid))
            menu.addAction("Dipnotu sil", lambda: self.delete_footnote(fid))
        menu.addSeparator()
        menu.addAction("Kes", self.cut).setEnabled(cur.hasSelection())
        menu.addAction("Kopyala", self.copy).setEnabled(cur.hasSelection())
        menu.addAction("Yapıştır", self.paste).setEnabled(self.canPaste())
        menu.addSeparator()
        href = self.anchorAt(e.pos())
        if href:
            menu.addAction("Bağlantıyı aç", lambda: self.open_link(href))
            menu.addAction("Bağlantıyı kopyala", lambda: self._copy_text(href))
            menu.addSeparator()
        for p in (c.position(), c.position() - 1):
            if self._image_at(p) is not None:
                slot = image_slot(self._image_at(p).name())
                menu.addAction(f"{IMAGE_SLOT_KINDS[slot]}…" if slot else "Resmi değiştir…",
                               lambda p=p: self.imageReplaceRequested.emit(p))
                menu.addAction("Resim boyutu…", lambda p=p: self.imageEditRequested.emit(p))
                menu.addAction("Resmi sil", lambda p=p: self.delete_image(p))
                menu.addSeparator()
                break
        if cur.currentTable() is not None:
            menu.addAction("Tabloyu sil", lambda: self.table_op("delete"))
            menu.addAction("Satırı sil", lambda: self.table_op("del_row"))
            menu.addAction("Tabloyu seç", lambda: self.table_op("select"))
            tm = menu.addMenu("Tablo")
            for label, op in (("Üste satır ekle", "row_above"), ("Alta satır ekle", "row_below"),
                              ("Sola sütun ekle", "col_left"), ("Sağa sütun ekle", "col_right"),
                              (None, None), ("Satırı sil", "del_row"), ("Sütunu sil", "del_col"),
                              (None, None), ("Hücreleri birleştir", "merge"), ("Hücreyi böl", "split"),
                              (None, None), ("Tabloyu sil", "delete")):
                if label is None:
                    tm.addSeparator()
                else:
                    tm.addAction(label, lambda op=op: self.table_op(op))
        menu.addAction("Tümünü seç", self.selectAll)
        menu.exec(e.globalPos())

    def _replace_word(self, wc, text):
        self.type_text(text, QTextCursor(wc))

    def _copy_text(self, text):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
