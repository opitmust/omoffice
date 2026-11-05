"""Profesyonel belge şablonları.

Her şablon bir tasarım temasıyla (yazı tipi takımı + renk paleti + tipografi) kurulur.
Kapaklar ve süslemeler düzenlenebilir metin, tablo ve resimlerden oluşur; .docx'e aynen aktarılır.
"""
import datetime
import math
import uuid
from dataclasses import dataclass

from PySide6.QtCore import Qt, QPointF, QRectF, QUrl
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QTextBlockFormat,
    QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextFrameFormat, QTextImageFormat,
    QTextLength, QTextListFormat, QTextTableFormat,
)

from .common import STYLE_PROP, PLACEHOLDER_PROP, pt2px, mm2px, turkish_upper
from .guide import KINDS, match_section, format_reference, in_text

MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül",
          "Ekim", "Kasım", "Aralık"]
LH_PROP = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
LH_FIXED = QTextBlockFormat.LineHeightTypes.FixedHeight.value

# ------------------------------------------------------------------ tasarım sistemi
PALETTES = {
    # ad: (vurgu, koyu, açık ton)
    "Lacivert": ("#1F3B73", "#14264A", "#E9EEF7"),
    "Okyanus": ("#1D6E8C", "#12485C", "#E4F1F6"),
    "Zümrüt": ("#1C7A57", "#11513A", "#E3F2EB"),
    "Bordo": ("#8C1D2F", "#5C1320", "#F6E7EA"),
    "Mor": ("#5A3E95", "#3B2865", "#EEE9F7"),
    "Kehribar": ("#B0601C", "#743F12", "#FBEFE2"),
    "Grafit": ("#3A4049", "#22262C", "#ECEEF0"),
    "Siyah-Beyaz": ("#111111", "#000000", "#F0F0F0"),
}

FONT_SETS = {
    # ad: (başlık, gövde, kapak/başlık, gövde puntosu, satır aralığı %)
    "Klasik (Cambria)": ("Cambria", "Cambria", "Cambria", 11.0, 115),
    "Resmî (Times New Roman)": ("Times New Roman", "Times New Roman", "Times New Roman", 12.0, 150),
    "Modern (Segoe UI)": ("Segoe UI Semibold", "Segoe UI", "Segoe UI Light", 10.5, 120),
    "Zarif (Georgia)": ("Georgia", "Georgia", "Georgia", 11.0, 125),
    "Kitap (Garamond)": ("Garamond", "Garamond", "Garamond", 12.5, 120),
    "Ofis (Calibri)": ("Calibri Light", "Calibri", "Calibri Light", 11.0, 115),
    "Geometrik (Century Gothic)": ("Century Gothic", "Calibri", "Century Gothic", 11.0, 120),
    "Palatino": ("Palatino Linotype", "Palatino Linotype", "Palatino Linotype", 11.0, 125),
}

# Türe göre varsayılan tasarım (palet, yazı tipi takımı)
KIND_DESIGN = {
    "makale": ("Lacivert", "Klasik (Cambria)"),
    "arastirma": ("Okyanus", "Modern (Segoe UI)"),
    "tez": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "odev": ("Zümrüt", "Ofis (Calibri)"),
    "lab": ("Okyanus", "Ofis (Calibri)"),
    "proje": ("Mor", "Modern (Segoe UI)"),
    "ara_rapor": ("Lacivert", "Klasik (Cambria)"),
    "literatur": ("Bordo", "Klasik (Cambria)"),
    "deneme": ("Bordo", "Zarif (Georgia)"),
    "rapor": ("Grafit", "Modern (Segoe UI)"),
    "dilekce": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "mektup": ("Lacivert", "Zarif (Georgia)"),
    "toplanti": ("Zümrüt", "Modern (Segoe UI)"),
    "ozgecmis": ("Lacivert", "Modern (Segoe UI)"),
    "bos": ("Lacivert", "Ofis (Calibri)"),
}


@dataclass
class Theme:
    accent: str
    dark: str
    tint: str
    head: str
    body: str
    title_font: str
    size: float
    line: int
    text: str = "#1B1B1B"
    muted: str = "#6A6F78"
    border: str = "#C9CED6"
    justify: bool = False
    first_indent: float = 0.0     # mm
    numbered: bool = False
    heading_caps: str = ""        # "" | "upper" | "small"
    heading_color: str = ""       # boşsa koyu ton

    @property
    def h(self):
        return self.heading_color or self.dark


def make_theme(kind, palette=None, fontset=None):
    pal_name, font_name = KIND_DESIGN.get(kind, ("Lacivert", "Ofis (Calibri)"))
    accent, dark, tint = PALETTES.get(palette or pal_name, PALETTES[pal_name])
    head, body, title, size, line = FONT_SETS.get(fontset or font_name, FONT_SETS[font_name])
    t = Theme(accent, dark, tint, head, body, title, size, line)
    if kind in ("tez", "dilekce"):
        t.justify, t.first_indent = True, 12.5
    if kind in ("makale", "literatur", "arastirma", "deneme", "ara_rapor"):
        t.justify = True
    if kind in ("makale", "literatur", "arastirma", "proje", "rapor", "ara_rapor"):
        t.numbered = True
    if kind == "tez":
        t.heading_caps, t.heading_color = "upper", "#000000"
    if kind in ("ozgecmis", "deneme"):
        t.heading_caps = "small"
    return t


# ------------------------------------------------------------------ süsleme resimleri
def _img(w, h):
    img = QImage(int(w * 2), int(h * 2), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    return img, p


def art_band(theme, w, h, style="waves"):
    """Kapak için soyut, sade bir renk bandı (geometrik/dalga)."""
    img, p = _img(w, h)
    acc, dark, tint = QColor(theme.accent), QColor(theme.dark), QColor(theme.tint)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, dark)
    g.setColorAt(1, acc)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
    p.fillPath(path, QBrush(g))
    p.setClipPath(path)
    if style == "waves":
        for k, a in enumerate((40, 28, 18)):
            c = QColor(255, 255, 255, a)
            wp = QPainterPath()
            wp.moveTo(0, h * (0.55 + 0.12 * k))
            for x in range(0, int(w) + 20, 20):
                wp.lineTo(x, h * (0.55 + 0.12 * k) + math.sin(x / (55 + 20 * k) + k) * h * 0.12)
            wp.lineTo(w, h)
            wp.lineTo(0, h)
            wp.closeSubpath()
            p.fillPath(wp, c)
    elif style == "circles":
        for cx, cy, r, a in ((w * 0.85, h * 0.2, h * 0.9, 34), (w * 0.95, h * 0.95, h * 0.6, 26),
                             (w * 0.70, h * 1.05, h * 0.45, 20)):
            p.setBrush(QColor(255, 255, 255, a))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), r, r)
    else:  # "grid": nokta ızgarası + çapraz şeritler
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        for x in range(int(w * 0.55), int(w), 14):
            for y in range(8, int(h), 14):
                p.drawEllipse(QPointF(x, y), 1.6, 1.6)
        p.setPen(QPen(QColor(255, 255, 255, 30), 18))
        for k in range(4):
            p.drawLine(QPointF(w * 0.35 + k * 40, h + 10), QPointF(w * 0.55 + k * 40, -10))
    p.end()
    return img


def thin_band(theme, w, h=6):
    img, p = _img(w, h)
    g = QLinearGradient(0, 0, w, 0)
    g.setColorAt(0, QColor(theme.accent))
    g.setColorAt(1, QColor(theme.tint))
    p.fillRect(QRectF(0, 0, w, h), QBrush(g))
    p.end()
    return img


def logo_placeholder(theme, size=70, text="LOGO"):
    img, p = _img(size, size)
    p.setPen(QPen(QColor(theme.muted), 1.2, Qt.PenStyle.DashLine))
    p.setBrush(QColor(theme.tint))
    p.drawEllipse(QRectF(2, 2, size - 4, size - 4))
    f = QFont("Segoe UI", 1)
    f.setPixelSize(int(size * 0.17))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(theme.muted))
    p.drawText(QRectF(0, 0, size, size), int(Qt.AlignmentFlag.AlignCenter), text)
    p.end()
    return img


def photo_placeholder(theme, size=96):
    img, p = _img(size, size)
    circle = QPainterPath()
    circle.addEllipse(QRectF(1, 1, size - 2, size - 2))
    p.fillPath(circle, QColor(theme.tint))
    p.setClipPath(circle)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(theme.accent).lighter(150))
    p.drawEllipse(QPointF(size / 2, size * 0.40), size * 0.18, size * 0.18)
    p.drawEllipse(QPointF(size / 2, size * 0.98), size * 0.36, size * 0.30)
    p.setClipping(False)
    p.setPen(QPen(QColor(theme.accent), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    p.end()
    return img


def ornament(theme, w=160, h=18):
    img, p = _img(w, h)
    p.setPen(QPen(QColor(theme.accent), 1))
    p.drawLine(QPointF(0, h / 2), QPointF(w / 2 - 14, h / 2))
    p.drawLine(QPointF(w / 2 + 14, h / 2), QPointF(w, h / 2))
    p.setBrush(QColor(theme.accent))
    path = QPainterPath()
    cx, cy = w / 2, h / 2
    path.moveTo(cx, cy - 6)
    path.lineTo(cx + 6, cy)
    path.lineTo(cx, cy + 6)
    path.lineTo(cx - 6, cy)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return img


# ------------------------------------------------------------------ kurucu
class Builder:
    def __init__(self, editor, theme):
        self.e = editor
        self.t = theme
        self.doc = editor.document()
        self.c = QTextCursor(self.doc)
        self.c.movePosition(QTextCursor.MoveOperation.End)
        self.fresh = self.c.block().length() <= 1 and self.c.block().blockNumber() == 0
        df = QFont(theme.body)
        df.setPointSizeF(theme.size)
        self.doc.setDefaultFont(df)
        self.tw = editor.text_width()

    # ---- biçimler
    def cf(self, font=None, size=None, bold=False, italic=False, color=None, caps="", spacing=None,
           underline=False, sup=False, placeholder=False, weight=None):
        t = self.t
        f = QTextCharFormat()
        f.setFontFamilies([font or t.body])
        # Word yalnızca yarım punto adımlarını saklar; OmOffice'te de aynı boyut görünsün
        f.setFontPointSize(round((size or t.size) * 2) / 2)
        if weight is not None:
            f.setFontWeight(weight)
        else:
            f.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
        f.setFontItalic(italic or placeholder)
        f.setForeground(QColor(t.muted if placeholder and not color else (color or t.text)))
        if caps == "upper":
            f.setFontCapitalization(QFont.Capitalization.AllUppercase)
        elif caps == "small":
            f.setFontCapitalization(QFont.Capitalization.SmallCaps)
        if spacing:
            f.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
            f.setFontLetterSpacing(spacing)
        if underline:
            f.setFontUnderline(True)
        if sup:
            f.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
        if placeholder:
            f.setProperty(PLACEHOLDER_PROP, True)
        return f

    def bf(self, align=None, before=0.0, after=None, line=None, first=None, left=0.0, right=0.0, shade=None,
           style="Normal", heading=0, page_break=False, rule=False, fixed=None):
        t = self.t
        b = QTextBlockFormat()
        if align is None:
            align = Qt.AlignmentFlag.AlignJustify if t.justify and not heading else Qt.AlignmentFlag.AlignLeft
        b.setAlignment(align)
        b.setTopMargin(pt2px(before))
        b.setBottomMargin(pt2px(t.size * 0.7 if after is None else after))
        if fixed:
            b.setLineHeight(fixed, LH_FIXED)
        else:
            b.setLineHeight(line or t.line, LH_PROP)
        if first is None:
            first = t.first_indent if (style == "Normal" and not heading and align == Qt.AlignmentFlag.AlignJustify) else 0
        b.setTextIndent(mm2px(first))
        b.setLeftMargin(mm2px(left))
        b.setRightMargin(mm2px(right))
        b.setHeadingLevel(heading)
        b.setProperty(STYLE_PROP, style)
        if shade:
            b.setBackground(QColor(shade))
        if page_break:
            b.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        if rule:
            b.setProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth,
                          QTextLength(QTextLength.Type.PercentageLength, 100))
        return b

    @staticmethod
    def _split(kw):
        ckeys = {"font", "size", "bold", "italic", "color", "caps", "spacing", "underline", "sup",
                 "placeholder", "weight"}
        return {k: v for k, v in kw.items() if k in ckeys}, {k: v for k, v in kw.items() if k not in ckeys}

    def _emit(self, cursor, first, parts, bfmt):
        cf0 = parts[0][1] if parts else self.cf()
        if first:
            # sayfa sonu bloğunu yeniden kullanırken sayfa sonu özelliği korunsun
            if cursor.blockFormat().pageBreakPolicy() & QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore:
                bfmt.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
            cursor.setBlockFormat(bfmt)
            cursor.setBlockCharFormat(cf0)
        else:
            cursor.insertBlock(bfmt, cf0)
        for text, f in parts:
            if text:
                cursor.insertText(text, f)

    # ---- paragraflar
    def p(self, text="", **kw):
        ck, bk = self._split(kw)
        if ck.get("placeholder") and text and not text.startswith("["):
            text = f"[{text}]"
        self._emit(self.c, self.fresh, [(text, self.cf(**ck))], self.bf(**bk))
        self.fresh = False
        return self

    def runs(self, parts, **bk):
        """parts: [(metin, {biçim})]"""
        self._emit(self.c, self.fresh, [(t, self.cf(**k)) for t, k in parts], self.bf(**bk))
        self.fresh = False
        return self

    def ph(self, text, **kw):
        kw.setdefault("placeholder", True)
        return self.p(text, **kw)

    def spacer(self, pt):
        return self.p("", size=2, fixed=pt2px(pt), after=0, first=0)

    def page_break(self):
        self._emit(self.c, self.fresh, [("", self.cf(size=2))], self.bf(page_break=True, fixed=1, after=0))
        self.fresh = True  # boş blok bir sonraki paragraf olsun (sayfa sonu özelliği korunur)
        return self

    def heading(self, text, level=1, number=None, align=None, before=None, page_break=False, rule=None,
                caps=None, color=None):
        t = self.t
        size = {1: t.size * 1.55, 2: t.size * 1.22, 3: t.size * 1.08}[min(level, 3)]
        label = f"{number}  {text}" if number and t.numbered else text
        caps = t.heading_caps if caps is None else caps
        if caps == "upper" and level > 1:
            caps = ""
        bfmt = self.bf(align=align or Qt.AlignmentFlag.AlignLeft, heading=min(level, 3),
                       style=f"Başlık {min(level, 3)}", before=(18 if level == 1 else 12) if before is None else before,
                       after=6 if level == 1 else 4, page_break=page_break,
                       rule=(level == 1 and t.numbered) if rule is None else rule, line=110, first=0)
        f = self.cf(font=t.head, size=size, bold=level > 1 or t.head not in ("Segoe UI Semibold", "Calibri Light"),
                    color=color or (t.h if level == 1 else t.accent), caps=caps,
                    spacing=0.6 if caps == "small" else None)
        if t.head == "Calibri Light" and level == 1:
            f.setFontWeight(QFont.Weight.Normal)
        self._emit(self.c, self.fresh, [(label, f)], bfmt)
        self.fresh = False
        return self

    def label(self, text, **kw):
        """Küçük, aralıklı, vurgu renkli etiket (ör. ARAŞTIRMA MAKALESİ)."""
        kw.setdefault("size", self.t.size * 0.78)
        kw.setdefault("color", self.t.accent)
        kw.setdefault("bold", True)
        kw.setdefault("spacing", 1.6)
        kw.setdefault("after", 2)
        return self.p(turkish_upper(text), **kw)

    def items(self, texts, numbered=False, placeholder=False, style=None):
        lst = None
        for txt in texts:
            self.p(txt, placeholder=placeholder, after=3, first=0,
                   align=Qt.AlignmentFlag.AlignLeft)
            if lst is None:
                lf = QTextListFormat()
                lf.setStyle(style or (QTextListFormat.Style.ListDecimal if numbered else QTextListFormat.Style.ListDisc))
                lf.setIndent(1)
                lst = self.c.createList(lf)
            else:
                lst.add(self.c.block())
        return self

    # ---- resim
    def image(self, img, w_px, h_px, align=Qt.AlignmentFlag.AlignHCenter, after=6):
        name = f"tpl-{uuid.uuid4().hex[:10]}.png"
        self.doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
        self._emit(self.c, self.fresh, [("", self.cf())], self.bf(align=align, after=after, first=0, line=100))
        self.fresh = False
        fmt = QTextImageFormat()
        fmt.setName(name)
        fmt.setWidth(w_px)
        fmt.setHeight(h_px)
        self.c.insertImage(fmt)
        return self

    # ---- tablolar
    def _table(self, rows, cols, widths=None, border=1.0, padding=5, spacing=0, width=100):
        if self.fresh:
            # tablodan önce kalan boş satır görünmesin (sayfa sonu varsa korunur)
            keep = self.c.blockFormat().pageBreakPolicy() & QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
            self.c.setBlockFormat(self.bf(fixed=1, after=0, first=0, page_break=bool(keep)))
            self.c.setBlockCharFormat(self.cf(size=1))
        tf = QTextTableFormat()
        tf.setBorder(border)
        tf.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        tf.setBorderBrush(QBrush(QColor(self.t.border)))
        tf.setBorderCollapse(spacing == 0)
        tf.setCellPadding(padding)
        tf.setCellSpacing(spacing)
        tf.setMargin(0)
        tf.setBottomMargin(pt2px(8))
        if widths:
            tf.setColumnWidthConstraints([QTextLength(QTextLength.Type.PercentageLength, w) for w in widths])
        tf.setWidth(QTextLength(QTextLength.Type.PercentageLength, width))
        t = self.c.insertTable(rows, cols, tf)
        return t

    def _after_table(self, t):
        self.c.setPosition(t.lastPosition() + 1)
        self.fresh = True

    def _fill(self, cell, paras, bg=None):
        """paras: [(metin|[(metin, cf_kw)], kw)]"""
        cur = cell.firstCursorPosition()
        first = True
        for content, kw in paras:
            ck, bk = self._split(kw)
            bk.setdefault("after", 2)
            bk.setdefault("first", 0)
            if bk.get("align") is None:
                bk["align"] = Qt.AlignmentFlag.AlignLeft
            if isinstance(content, list):
                parts = [(tx, self.cf(**{**ck, **k})) for tx, k in content]
            else:
                if ck.get("placeholder") and content and not content.startswith("["):
                    content = f"[{content}]"
                parts = [(content, self.cf(**ck))]
            self._emit(cur, first, parts, self.bf(**bk))
            first = False
        # Hücre biçimi ilk paragrafın karakter biçiminde tutulur; rengi metinden SONRA ver
        if bg:
            f = cell.format().toTableCellFormat()
            f.setBackground(QColor(bg))
            cell.setFormat(f)

    def table(self, rows, widths=None, header=True, zebra=True, size=None, align_right=(), bold_last=False):
        t = self._table(len(rows), len(rows[0]), widths)
        sz = size or self.t.size * 0.92
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                is_h = header and r == 0
                bg = self.t.accent if is_h else (self.t.tint if zebra and r % 2 == 0 and r > 0 else None)
                al = Qt.AlignmentFlag.AlignRight if c in align_right and not is_h else Qt.AlignmentFlag.AlignLeft
                ph = isinstance(val, str) and val.startswith("[") and val.endswith("]")
                txt = val[1:-1] if ph else val
                self._fill(t.cellAt(r, c), [(txt, dict(size=sz, bold=is_h or (bold_last and r == len(rows) - 1),
                                                       color="#FFFFFF" if is_h else None, placeholder=ph,
                                                       align=al))], bg)
        self._after_table(t)
        return self

    def caption(self, text, above=True):
        """'Tablo 4.1. Açıklama' → kalın numara + italik açıklama."""
        import re
        m = re.match(r"^((?:Tablo|Şekil)\s+[\d.]*\d\.?)\s*(.*)$", text)
        num, rest = (m.group(1), m.group(2)) if m else ("", text)
        return self.runs([(num + " ", dict(bold=True, size=self.t.size * 0.9)),
                          (rest, dict(italic=True, size=self.t.size * 0.9))],
                         after=3 if above else 10, first=0, align=Qt.AlignmentFlag.AlignLeft)

    def band(self, paras, bg=None, padding=16):
        t = self._table(1, 1, border=0, padding=padding)
        self._fill(t.cellAt(0, 0), paras, bg or self.t.accent)
        self._after_table(t)
        return self

    def info_grid(self, pairs, label_w=32):
        t = self._table(len(pairs), 2, [label_w, 100 - label_w], border=1.0, padding=6)
        for r, (lab, val) in enumerate(pairs):
            self._fill(t.cellAt(r, 0), [(lab, dict(bold=True, size=self.t.size * 0.88, color=self.t.dark))],
                       self.t.tint)
            if val:
                self._fill(t.cellAt(r, 1), [(val, dict(size=self.t.size * 0.95))])
            else:
                self._fill(t.cellAt(r, 1), [("…", dict(placeholder=True, size=self.t.size * 0.95))])
        self._after_table(t)
        return self

    def stat_boxes(self, items):
        t = self._table(1, len(items), [100 / len(items)] * len(items), border=0, padding=10, spacing=6)
        for c, (value, label) in enumerate(items):
            self._fill(t.cellAt(0, c), [(value, dict(font=self.t.title_font, size=self.t.size * 2.1, bold=True,
                                                     color=self.t.accent, after=0)),
                                        (label, dict(size=self.t.size * 0.82, color=self.t.muted, after=0))],
                       self.t.tint)
        self._after_table(t)
        return self

    def callout(self, title, body, placeholder=True):
        paras = [(turkish_upper(title), dict(bold=True, size=self.t.size * 0.82, color=self.t.accent, spacing=1.4,
                                             after=4))]
        if isinstance(body, list):
            paras += body
        else:
            paras.append((body, dict(placeholder=placeholder, after=2,
                                     align=Qt.AlignmentFlag.AlignJustify if self.t.justify else None)))
        return self.band(paras, bg=self.t.tint, padding=12)

    def signature_table(self, rows, cols=("Unvanı, Adı Soyadı", "Kurumu", "İmza")):
        data = [list(cols)] + [list(r) for r in rows]
        t = self._table(len(data), len(cols), [40, 40, 20], border=1.0, padding=8)
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                hdr = r == 0
                ph = not hdr and val.startswith("[")
                self._fill(t.cellAt(r, c), [(val.strip("[]") if ph else val,
                                             dict(bold=hdr, size=self.t.size * 0.9, placeholder=ph))],
                           self.t.tint if hdr else None)
        self._after_table(t)
        return self

    # ---- sayfa yapısı
    def setup(self, margins=None, header="", header_align="right", footer="{SAYFA}", footer_align="center",
              different_first=False):
        s = self.e.setup.copy()
        if margins:
            s.top_mm, s.bottom_mm, s.left_mm, s.right_mm = margins
        s.header_text, s.header_align = header, header_align
        s.footer_text, s.footer_align = footer, footer_align
        s.different_first = different_first
        self.e.setup = s
        self.e.apply_page_setup()
        self.tw = self.e.text_width()

    def toc_here(self):
        """İçindekiler için yer ayırır; tüm bölümler yazıldıktan sonra doldurulur."""
        self.p("", after=0, first=0)
        self.toc_cursor = QTextCursor(self.c)
        # aynı noktaya sonradan eklenen metin bu imleci ileri itmesin
        self.toc_cursor.setKeepPositionOnInsert(True)
        return self


def _today():
    now = datetime.datetime.now()
    return f"{now.day} {MONTHS[now.month - 1]} {now.year}"


def _year():
    return str(datetime.datetime.now().year)


def _sections(kind):
    return KINDS[kind]["sections"]


def _section_body(b, kind, heading, hint, opts):
    if opts.get("placeholders", True):
        b.ph(hint)
    if opts.get("examples"):
        _, ex = match_section(heading)
        if ex:
            b.ph("Örnek: " + ex[0])


def _references(b, opts):
    style = opts.get("citation") or ""
    if not style:
        return
    samples = [
        {"type": "Dergi makalesi", "authors": "Yılmaz, Ayşe; Demir, Can", "year": "2023",
         "title": "Öğrenme analitiğinin akademik başarıya etkisi", "source": "Eğitim ve Bilim",
         "volume": "48", "issue": "214", "pages": "1-22", "doi": "10.15390/EB.2023.0000"},
        {"type": "Kitap", "authors": "Karasar, Niyazi", "year": "2020", "title": "Bilimsel araştırma yöntemi",
         "publisher": "Nobel Yayıncılık"},
    ]
    b.ph(f"{style} stilinde kaynaklar. Aşağıdaki iki örnek biçimi gösterir; silip kendi kaynaklarınızı "
         f"Rehber › Kaynak ekle ile ekleyin.", first=0)
    for i, r in enumerate(samples, 1):
        txt = format_reference(style, r).replace("*", "")
        if style.startswith("IEEE"):
            txt = f"[{i}] {txt}"
        b.p(txt, placeholder=True, left=12.5, first=-12.5, align=Qt.AlignmentFlag.AlignLeft, after=6)


# ------------------------------------------------------------------ türlere özel şablonlar
def _makale(b, a, opts, kind="makale"):
    t = b.t
    short = a("title")[:60] if a("title") else "Kısa Başlık"
    b.setup((25, 25, 25, 25), header=short, header_align="right", footer="{SAYFA}", different_first=True)
    b.image(thin_band(t, b.tw, 5), b.tw, 5, after=8)
    b.runs([("ARAŞTIRMA MAKALESİ" if kind == "makale" else "DERLEME MAKALESİ",
             dict(bold=True, size=t.size * 0.78, color=t.accent, spacing=1.8)),
            ("     ·     Cilt [—]  Sayı [—]  ·  " + _year(), dict(size=t.size * 0.78, color=t.muted))],
           align=Qt.AlignmentFlag.AlignLeft, after=18, first=0)
    if a("title"):
        b.p(a("title"), font=t.title_font, size=t.size * 2.0, bold=True, color=t.dark, style="Konu Başlığı",
            align=Qt.AlignmentFlag.AlignLeft, after=6, line=105, first=0)
    else:
        b.ph("Makale başlığı (10–15 sözcük)", font=t.title_font, size=t.size * 2.0, style="Konu Başlığı",
             align=Qt.AlignmentFlag.AlignLeft, after=6, first=0)
    b.ph("İngilizce başlık (English title)", size=t.size * 1.15, align=Qt.AlignmentFlag.AlignLeft, after=14, first=0)
    authors = [x.strip() for x in (a("author") or "").split(";") if x.strip()] or ["Yazar Adı Soyadı"]
    parts = []
    for i, au in enumerate(authors, 1):
        parts += [(au, dict(bold=True, size=t.size * 1.05, color=t.text)), (str(i), dict(sup=True, color=t.accent)),
                  (",  " if i < len(authors) else "", dict())]
    b.runs(parts, align=Qt.AlignmentFlag.AlignLeft, after=4, first=0)
    for i, _ in enumerate(authors, 1):
        b.runs([(str(i), dict(sup=True, color=t.accent, size=t.size * 0.82)),
                (" " + (a("institution") or ""), dict(italic=True, size=t.size * 0.82, color=t.muted)),
                (" [Bölüm, Şehir, Ülke · e-posta · ORCID: 0000-0000-0000-0000]",
                 dict(italic=True, size=t.size * 0.82, placeholder=True))],
               align=Qt.AlignmentFlag.AlignLeft, after=1, first=0)
    b.runs([("Geliş: ", dict(bold=True, size=t.size * 0.78, color=t.muted)),
            ("[gg.aa.yyyy]", dict(size=t.size * 0.78, placeholder=True)),
            ("   Kabul: ", dict(bold=True, size=t.size * 0.78, color=t.muted)),
            ("[gg.aa.yyyy]", dict(size=t.size * 0.78, placeholder=True)),
            ("   DOI: ", dict(bold=True, size=t.size * 0.78, color=t.muted)),
            ("[10.xxxx/xxxx]", dict(size=t.size * 0.78, placeholder=True))],
           align=Qt.AlignmentFlag.AlignLeft, before=6, after=14, first=0)
    secs = _sections(kind)
    n = 0
    for heading, level, hint in secs:
        low = heading.lower()
        if low in ("özet", "abstract"):
            kw_label = "Anahtar Kelimeler:" if low == "özet" else "Keywords:"
            kw_val = a("keywords") if low == "özet" else ""
            b.heading(heading, 2, before=4, rule=False, caps="small", color=t.accent)
            b.band([
                (hint, dict(placeholder=True, align=Qt.AlignmentFlag.AlignJustify, size=t.size * 0.95, after=6)),
                ([(kw_label + " ", dict(bold=True, size=t.size * 0.9, color=t.dark)),
                  (kw_val or "[3–5 kavram, virgülle]", dict(size=t.size * 0.9, placeholder=not kw_val))], dict(after=0)),
            ], bg=t.tint, padding=12)
            continue
        if low == "kaynakça":
            b.heading(heading, 1, number=None)
            _references(b, opts)
            continue
        n += 1
        b.heading(heading, 1, number=f"{n}.")
        _section_body(b, kind, heading, hint, opts)
        if low == "yöntem":
            for k, sub in enumerate(("Araştırma Deseni", "Katılımcılar", "Veri Toplama Araçları", "Veri Analizi"), 1):
                b.heading(sub, 2, number=f"{n}.{k}.")
                b.ph({1: "Çalışmanın nicel/nitel/karma desenini ve gerekçesini yazın.",
                      2: "Kimlerle çalışıldığını, sayısını ve seçim yöntemini açıklayın.",
                      3: "Ölçek/görüşme formu; geçerlik ve güvenirlik bilgileri.",
                      4: "Kullanılan analiz teknikleri, yazılım ve anlamlılık düzeyi."}[k])
        if low in ("bulgular", "temalar ve bulgular"):
            b.caption("Tablo 1. Katılımcıların demografik özellikleri")
            b.table([["Değişken", "Grup", "n", "%"], ["Cinsiyet", "Kadın", "[—]", "[—]"],
                     ["", "Erkek", "[—]", "[—]"], ["Yaş", "18–25", "[—]", "[—]"], ["", "26 ve üzeri", "[—]", "[—]"]],
                    widths=[30, 34, 18, 18], align_right=(2, 3))
            if kind == "literatur":
                b.caption("Tablo 2. İncelenen çalışmaların özeti")
                b.table([["Yazar (Yıl)", "Örneklem", "Yöntem", "Temel bulgu"], ["[—]", "[—]", "[—]", "[—]"],
                         ["[—]", "[—]", "[—]", "[—]"], ["[—]", "[—]", "[—]", "[—]"]], widths=[22, 20, 20, 38])
    b.heading("Beyanlar", 2, before=18, color=t.accent)
    for lab, txt in (("Etik Kurul Onayı: ", "Kurul adı, tarih ve sayı."),
                     ("Çıkar Çatışması: ", "Yazarlar çıkar çatışması olmadığını beyan eder."),
                     ("Yazar Katkıları: ", "Fikir, tasarım, veri toplama, analiz, yazım.")):
        b.runs([(lab, dict(bold=True, size=t.size * 0.88)), (f"[{txt}]", dict(size=t.size * 0.88, placeholder=True))],
               after=3, first=0)


def _tez(b, a, opts):
    t = b.t
    C = Qt.AlignmentFlag.AlignHCenter
    b.setup((30, 25, 35, 25), footer="{SAYFA}", different_first=True)
    big = t.size + 2
    if opts.get("cover", True):
        b.p("T.C.", bold=True, size=big, align=C, after=2, first=0)
        b.p(turkish_upper(a("institution")) if a("institution") else "[ÜNİVERSİTE ADI]", bold=True, size=big, align=C,
            after=2, first=0, placeholder=not a("institution"))
        b.p("[… BİLİMLERİ ENSTİTÜSÜ]", bold=True, size=big, align=C, after=2, first=0, placeholder=True)
        b.p(turkish_upper(a("department")) + " ANABİLİM DALI" if a("department") else "[… ANABİLİM DALI]",
            bold=True, size=big, align=C, after=24, first=0, placeholder=not a("department"))
        b.image(logo_placeholder(t, 96, "LOGO"), 96, 96, after=36)
        if a("title"):
            b.p(turkish_upper(a("title")), bold=True, size=big + 2, align=C, after=36, first=0, line=130)
        else:
            b.ph("TEZİN BAŞLIĞI (BÜYÜK HARFLE)", bold=True, size=big + 2, align=C, after=36, first=0)
        b.p(turkish_upper(a("degree")) if a("degree") else "YÜKSEK LİSANS TEZİ", bold=True, size=big, align=C,
            after=48, first=0)
        b.p(turkish_upper(a("author")) if a("author") else "[AD SOYAD]", bold=True, size=big, align=C, after=48,
            first=0, placeholder=not a("author"))
        b.p("Danışman", size=t.size, align=C, after=2, first=0)
        b.p(a("advisor") or "[Unvan Ad SOYAD]", bold=True, size=t.size, align=C, after=60, first=0,
            placeholder=not a("advisor"))
        b.runs([("[ŞEHİR]", dict(bold=True, placeholder=True)), (f" – {_year()}", dict(bold=True))],
               align=C, after=0, first=0)
        b.page_break()
        # İç kapak
        b.p("KABUL VE ONAY", bold=True, size=big, align=C, after=18, first=0, style="Normal")
        b.ph(f"{a('author') or '…'} tarafından hazırlanan “{a('title') or '…'}” başlıklı bu çalışma, "
             f"[gg.aa.yyyy] tarihinde yapılan savunma sınavı sonucunda oybirliği/oyçokluğu ile başarılı bulunarak "
             f"jürimiz tarafından {a('degree') or 'Yüksek Lisans Tezi'} olarak kabul edilmiştir.")
        b.spacer(10)
        b.signature_table([["[Prof. Dr. Ad SOYAD] (Danışman)", "[Kurum]", ""],
                           ["[Doç. Dr. Ad SOYAD]", "[Kurum]", ""], ["[Dr. Öğr. Üyesi Ad SOYAD]", "[Kurum]", ""]])
        b.spacer(18)
        b.ph("Yukarıdaki imzaların adı geçen öğretim üyelerine ait olduğunu onaylarım.", align=C, first=0)
        b.p("[Unvan Ad SOYAD]", placeholder=True, align=Qt.AlignmentFlag.AlignRight, after=0, first=0)
        b.p("Enstitü Müdürü", align=Qt.AlignmentFlag.AlignRight, first=0)
        b.page_break()
        b.p("ETİK BEYAN", bold=True, size=big, align=C, after=18, first=0)
        b.p("Bu tezin yazılmasında bilimsel ahlak kurallarına uyulduğunu, başkalarının eserlerinden yararlanılması "
            "durumunda bilimsel normlara uygun olarak atıfta bulunulduğunu, kullanılan verilerde herhangi bir tahrifat "
            "yapılmadığını, tezin herhangi bir kısmının bu üniversite veya başka bir üniversitedeki başka bir tez "
            "çalışması olarak sunulmadığını beyan ederim.")
        b.spacer(24)
        b.p(a("author") or "[Ad SOYAD]", placeholder=not a("author"), align=Qt.AlignmentFlag.AlignRight, first=0, after=0)
        b.p("İmza", color=t.muted, align=Qt.AlignmentFlag.AlignRight, first=0)
    front = {"Önsöz", "Özet", "Abstract"}
    chapter_words = ["BİRİNCİ", "İKİNCİ", "ÜÇÜNCÜ", "DÖRDÜNCÜ", "BEŞİNCİ", "ALTINCI", "YEDİNCİ"]
    subs = {
        "1. Giriş": ["Problem Durumu", "Araştırmanın Amacı", "Araştırmanın Önemi", "Varsayımlar", "Sınırlılıklar",
                     "Tanımlar"],
        "3. Yöntem": ["Araştırma Modeli", "Evren ve Örneklem", "Veri Toplama Araçları", "Verilerin Toplanması",
                      "Verilerin Analizi"],
        "6. Sonuç ve Öneriler": ["Sonuçlar", "Öneriler"],
    }
    ch = 0
    toc_done = False
    for heading, level, hint in _sections("tez"):
        if heading not in front and not toc_done and opts.get("toc", True):
            b.page_break()
            b.toc_here()
            toc_done = True
            b.page_break()
            b.heading("Kısaltmalar", 1, align=C, page_break=False)
            b.table([["Kısaltma", "Açıklama"], ["APA", "American Psychological Association"], ["[—]", "[—]"],
                     ["vb.", "ve benzeri"], ["vd.", "ve diğerleri"]], widths=[25, 75])
        if heading in front:
            b.page_break()
            b.heading(heading, 1, align=C)
            _section_body(b, "tez", heading, hint, opts)
            if heading == "Özet":
                b.runs([("Anahtar Kelimeler: ", dict(bold=True)), ("[3–5 kavram, virgülle]", dict(placeholder=True))],
                       first=0)
            if heading == "Abstract":
                b.runs([("Keywords: ", dict(bold=True)), ("[3–5 keywords]", dict(placeholder=True))], first=0)
            continue
        b.page_break()
        if heading[0].isdigit() and ch < len(chapter_words):
            b.p(f"{chapter_words[ch]} BÖLÜM", bold=True, align=C, size=t.size, after=6, first=0, spacing=1.2)
            ch += 1
            b.heading(heading, 1, align=C)
        else:
            b.heading(heading, 1, align=C)
        _section_body(b, "tez", heading, hint, opts)
        for k, sub in enumerate(subs.get(heading, []), 1):
            num = heading.split(".")[0]
            b.heading(f"{num}.{k}. {sub}", 2)
            b.ph("Bu alt başlıkta ilgili açıklamayı yazın.")
        if heading == "4. Bulgular":
            b.caption("Tablo 4.1. Değişkenlere ilişkin betimsel istatistikler")
            b.table([["Değişken", "n", "Ort.", "ss", "Min.", "Maks."], ["[—]", "", "", "", "", ""],
                     ["[—]", "", "", "", "", ""], ["[—]", "", "", "", "", ""]],
                    widths=[34, 11, 13, 13, 14, 15], align_right=(1, 2, 3, 4, 5))
        if heading == "Kaynakça":
            _references(b, opts)
    return True


def _cover_modern(b, a, kind_label, subtitle_ph, info_pairs, art="waves"):
    t = b.t
    b.image(art_band(t, b.tw, 150, art), b.tw, 150, after=26)
    b.label(f"{kind_label}  ·  {_year()}")
    if a("title"):
        b.p(a("title"), font=t.title_font, size=t.size * 2.6, color=t.dark, style="Konu Başlığı", after=8, line=100,
            first=0, align=Qt.AlignmentFlag.AlignLeft)
    else:
        b.ph("Başlık", font=t.title_font, size=t.size * 2.6, style="Konu Başlığı", after=8, first=0,
             align=Qt.AlignmentFlag.AlignLeft)
    b.ph(subtitle_ph, size=t.size * 1.25, after=30, first=0, align=Qt.AlignmentFlag.AlignLeft)
    b.info_grid(info_pairs)
    b.spacer(70)
    b.image(thin_band(t, b.tw * 0.35, 4), b.tw * 0.35, 4, align=Qt.AlignmentFlag.AlignLeft, after=4)
    b.p(a("institution") or "[Kurum adı]", bold=True, color=t.dark, placeholder=not a("institution"), first=0,
        align=Qt.AlignmentFlag.AlignLeft, after=0)
    b.p(_today(), color=t.muted, first=0, align=Qt.AlignmentFlag.AlignLeft)


def _numbered_sections(b, kind, opts, hook=None):
    n = 0
    for heading, level, hint in _sections(kind):
        if heading in ("Kaynakça", "Ekler"):
            b.heading(heading, 1)
            if heading == "Kaynakça":
                _references(b, opts)
            else:
                b.ph(hint)
            continue
        if level == 1:
            n += 1
            sub = 0
            b.heading(heading, 1, number=f"{n}.")
        else:
            sub += 1
            b.heading(heading, 2, number=f"{n}.{sub}.")
        _section_body(b, kind, heading, hint, opts)
        if hook:
            hook(heading)


def _arastirma(b, a, opts):
    t = b.t
    title = a("title") or "Araştırma Raporu"
    b.setup((25, 25, 25, 25), header=title[:70], header_align="left", footer="Sayfa {SAYFA} / {TOPLAM}",
            footer_align="right", different_first=True)
    if opts.get("cover", True):
        _cover_modern(b, a, "Araştırma Raporu", "Alt başlık: araştırmanın kapsamı tek cümleyle",
                      [("Hazırlayan", a("author")), ("Kurum", a("institution")), ("Tarih", a("date") or _today()),
                       ("Rapor No", ""), ("Anahtar kelimeler", a("keywords"))], art="waves")
        b.page_break()
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()

    def hook(h):
        if h == "Özet":
            b.p("Öne çıkan bulgular", bold=True, color=t.accent, size=t.size * 0.95, before=6, first=0,
                align=Qt.AlignmentFlag.AlignLeft)
            b.stat_boxes([("%—", "[temel oran / değişim]"), ("n = —", "[örneklem büyüklüğü]"),
                          ("—", "[öne çıkan gösterge]")])
        if h == "Bulgular":
            b.caption("Tablo 1. Alt problemlere ilişkin bulguların özeti")
            b.table([["Alt problem", "Analiz", "Sonuç", "p"], ["1", "[—]", "[—]", "[—]"], ["2", "[—]", "[—]", "[—]"],
                     ["3", "[—]", "[—]", "[—]"]], widths=[18, 30, 38, 14], align_right=(3,))
        if h == "Sonuç ve Öneriler":
            b.callout("Öneriler", [("[Uygulayıcılara yönelik öneri]", dict(placeholder=True)),
                                   ("[Politika yapıcılara yönelik öneri]", dict(placeholder=True)),
                                   ("[Sonraki araştırmalara yönelik öneri]", dict(placeholder=True))])
    _numbered_sections(b, "arastirma", opts, hook)


def _odev(b, a, opts, kind="odev"):
    t = b.t
    C = Qt.AlignmentFlag.AlignHCenter
    b.setup((25, 25, 25, 25), header=(a("course") or "")[:60], header_align="right", footer="{SAYFA}",
            different_first=True)
    if opts.get("cover", True):
        b.image(logo_placeholder(t, 72), 72, 72, after=10)
        b.p(turkish_upper(a("institution")) if a("institution") else "[ÜNİVERSİTE / OKUL ADI]", bold=True,
            color=t.dark, size=t.size * 1.15, align=C, first=0, after=2, placeholder=not a("institution"))
        b.ph("Fakülte / Bölüm", align=C, first=0, after=14, size=t.size * 0.95)
        b.image(ornament(t, 180, 16), 180, 16, after=60)
        b.p(a("course") or "[Ders Adı]", color=t.accent, size=t.size * 1.1, caps="small", spacing=1.0, align=C,
            first=0, after=8, placeholder=not a("course"))
        if a("title"):
            b.p(a("title"), font=t.title_font, size=t.size * 2.3, color=t.dark, align=C, first=0, after=8,
                style="Konu Başlığı", line=105)
        else:
            b.ph("Ödevin Başlığı", font=t.title_font, size=t.size * 2.3, align=C, first=0, after=8,
                 style="Konu Başlığı")
        b.p(KINDS[kind]["name"].split(" (")[0], color=t.muted, align=C, first=0, after=80)
        b.info_grid([("Hazırlayan", a("author")), ("Öğrenci No", a("student_no")), ("Ders", a("course")),
                      ("Öğretim Üyesi", a("instructor")), ("Teslim Tarihi", a("date") or _today())], label_w=35)
        b.spacer(30)
        b.ph(f"{_year()}–{int(_year()) + 1} Eğitim-Öğretim Yılı · Güz Dönemi", align=C, first=0)
        b.page_break()
    for i, (heading, level, hint) in enumerate(_sections(kind), 1):
        b.heading(heading, min(level, 2))
        if kind == "lab" and heading == "Deneyin Amacı":
            b.band([(hint, dict(placeholder=True))], bg=t.tint, padding=12)
            continue
        if heading == "Teorik Bilgi":
            _section_body(b, kind, heading, hint, opts)
            b.p("F = m · a", italic=True, size=t.size * 1.2, align=C, first=0, after=2)
            b.p("(1)", color=t.muted, align=Qt.AlignmentFlag.AlignRight, first=0, after=8)
            continue
        if heading == "Kullanılan Araç ve Gereçler":
            b.items(["Malzeme 1 (adet / özellik)", "Malzeme 2", "Ölçüm cihazı (duyarlılık)"], placeholder=True)
            continue
        if heading == "Deneyin Yapılışı":
            b.items(["Düzeneği şekildeki gibi kurduk.", "Ölçümü … kez tekrarladık.", "Verileri tabloya kaydettik."],
                    numbered=True, placeholder=True)
            continue
        if heading == "Veriler ve Hesaplamalar":
            b.caption("Tablo 1. Ölçüm sonuçları")
            b.table([["Deneme", "Ölçülen (birim)", "Hesaplanan (birim)", "Bağıl hata (%)"],
                     ["1", "[—]", "[—]", "[—]"], ["2", "[—]", "[—]", "[—]"], ["3", "[—]", "[—]", "[—]"],
                     ["Ortalama", "", "", ""]], widths=[18, 27, 27, 28], align_right=(1, 2, 3), bold_last=True)
            b.p("Bağıl hata = |deneysel − teorik| / teorik × 100", italic=True, align=C, first=0)
            continue
        _section_body(b, kind, heading, hint, opts)
        if heading == "Kaynakça":
            _references(b, opts)


def _proje(b, a, opts):
    t = b.t
    b.setup((25, 25, 25, 25), header=(a("title") or "Proje Önerisi")[:70], header_align="left",
            footer="Sayfa {SAYFA} / {TOPLAM}", footer_align="right", different_first=True)
    if opts.get("cover", True):
        _cover_modern(b, a, "Proje Önerisi", "Projenin tek cümlelik özeti",
                      [("Proje Yürütücüsü", a("author")), ("Araştırmacılar", ""), ("Kurum", a("institution")),
                       ("Destek Programı", ""), ("Süre", "12 ay"), ("Toplam Bütçe", "— TL")], art="circles")
        b.page_break()
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()

    def hook(h):
        if h == "Amaç ve Hedefler":
            b.table([["Kod", "Hedef", "Başarı ölçütü"], ["H1", "[Ölçülebilir hedef]", "[Gösterge ve hedef değer]"],
                     ["H2", "[—]", "[—]"], ["H3", "[—]", "[—]"]], widths=[10, 50, 40])
        if h == "İş-Zaman Çizelgesi":
            months = [str(m) for m in range(1, 13)]
            rows = [["İş Paketi"] + months]
            plan = {"İP1 Literatür ve hazırlık": range(1, 4), "İP2 Veri toplama": range(3, 8),
                    "İP3 Analiz": range(7, 11), "İP4 Raporlama ve yaygınlaştırma": range(10, 13)}
            for name in plan:
                rows.append([name] + [""] * 12)
            b.table(rows, widths=[28] + [6] * 12, zebra=False, size=t.size * 0.8)
            tbl = _last_table(b)
            if tbl is not None:
                for r, (name, rng) in enumerate(plan.items(), 1):
                    for m in rng:
                        cell = tbl.cellAt(r, m)
                        f = cell.format().toTableCellFormat()
                        f.setBackground(QColor(t.accent))
                        cell.setFormat(f)
        if h == "Bütçe ve Gerekçesi":
            b.table([["Bütçe kalemi", "Gerekçe", "Tutar (TL)"], ["Makine-teçhizat", "[—]", "[—]"],
                     ["Sarf malzemesi", "[—]", "[—]"], ["Hizmet alımı", "[—]", "[—]"],
                     ["Seyahat", "[—]", "[—]"], ["TOPLAM", "", "[—]"]],
                    widths=[30, 50, 20], align_right=(2,), bold_last=True)
        if h == "Risk Yönetimi":
            b.table([["Risk", "Olasılık", "Etki", "B planı"], ["[Veri toplamada gecikme]", "Orta", "Yüksek", "[—]"],
                     ["[Ekipman arızası]", "Düşük", "Orta", "[—]"]], widths=[34, 14, 14, 38])
        if h == "Yaygın Etki":
            b.table([["Çıktı türü", "Açıklama"], ["Bilimsel", "[Makale, bildiri]"], ["Ekonomik", "[Patent, ürün]"],
                     ["Toplumsal", "[Eğitim, farkındalık]"]], widths=[25, 75])
    _numbered_sections(b, "proje", opts, hook)


def _ara_rapor(b, a, opts):
    t = b.t
    C = Qt.AlignmentFlag.AlignHCenter
    b.setup((25, 25, 25, 25), header=((a("title") or "Proje")[:55] + " · Ara Rapor"), header_align="right",
            footer="Sayfa {SAYFA} / {TOPLAM}", footer_align="center", different_first=True)
    if opts.get("cover", True):
        b.p("T.C.", bold=True, color=t.dark, align=C, first=0, after=2)
        b.p(turkish_upper(a("institution")) if a("institution") else "[ÜNİVERSİTE ADI]", bold=True, color=t.dark,
            size=t.size * 1.15, align=C, first=0, after=2, placeholder=not a("institution"))
        b.ph("… Fakültesi / … Enstitüsü", align=C, first=0, after=2, size=t.size * 0.95)
        b.p(turkish_upper(a("department")) + " BÖLÜMÜ" if a("department") else "[… BÖLÜMÜ / ANABİLİM DALI]",
            align=C, first=0, after=14, size=t.size * 0.95, placeholder=not a("department"))
        b.image(logo_placeholder(t, 80), 80, 80, after=14)
        b.image(ornament(t, 180, 16), 180, 16, after=70)
        if a("title"):
            b.p(a("title"), font=t.title_font, size=t.size * 2.1, color=t.dark, align=C, first=0, after=10,
                style="Konu Başlığı", line=110, bold=True)
        else:
            b.ph("Proje / Tez Başlığı", font=t.title_font, size=t.size * 2.1, align=C, first=0, after=10,
                 style="Konu Başlığı")
        b.band([("1. ARA RAPOR", dict(bold=True, size=t.size * 1.15, color="#FFFFFF", spacing=2.0, after=0,
                                      align=C))], bg=t.accent, padding=8)
        b.ph("Bitirme Projesi / BAP Projesi / Yüksek Lisans Tezi", align=C, first=0, after=70, size=t.size * 0.95)
        b.info_grid([("Hazırlayan", a("author")), ("Öğrenci No", a("student_no")), ("Danışman", a("advisor")),
                     ("Proje No", ""), ("Rapor Dönemi", ""), ("Teslim Tarihi", a("date") or _today())], label_w=32)
        b.spacer(110)
        b.runs([("[ŞEHİR]", dict(bold=True, placeholder=True)), (f" – {_year()}", dict(bold=True))],
               align=C, after=0, first=0)
        b.page_break()
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()

    def hook(h):
        if h == "Özet":
            b.runs([("Anahtar Kelimeler: ", dict(bold=True)),
                    (a("keywords") or "[3–5 kavram, virgülle]", dict(placeholder=not a("keywords")))], first=0)
            b.stat_boxes([("%—", "[genel ilerleme]"), ("—/—", "[tamamlanan iş paketi]"),
                          ("—", "[dönemin öne çıkan çıktısı]")])
        if h == "İş-Zaman Çizelgesine Göre İlerleme":
            b.caption("Tablo 1. İş paketlerinin planlanan ve gerçekleşen durumu")
            b.table([["İP", "İş paketi", "Planlanan süre", "Gerçekleşme (%)", "Durum"],
                     ["İP1", "[Literatür taraması]", "[1.–2. ay]", "[100]", "Tamamlandı"],
                     ["İP2", "[Veri toplama / tasarım]", "[2.–5. ay]", "[60]", "Sürüyor"],
                     ["İP3", "[Analiz / uygulama]", "[5.–8. ay]", "[0]", "Başlamadı"],
                     ["İP4", "[Raporlama]", "[8.–9. ay]", "[0]", "Başlamadı"]],
                    widths=[9, 37, 18, 18, 18], align_right=(3,))
        if h == "Elde Edilen Ön Bulgular":
            b.caption("Tablo 2. Ön bulguların özeti")
            b.table([["Ölçüt / değişken", "Beklenen", "Elde edilen", "Açıklama"], ["[—]", "[—]", "[—]", "[—]"],
                     ["[—]", "[—]", "[—]", "[—]"]], widths=[30, 18, 18, 34])
        if h == "Karşılaşılan Sorunlar ve Çözüm Önerileri":
            b.table([["Sorun", "Etkisi", "Çözüm / alınan önlem"],
                     ["[Malzeme tedarikinde gecikme]", "[İP2 ~1 ay gecikti]", "[Alternatif tedarikçi]"],
                     ["[—]", "[—]", "[—]"]], widths=[34, 26, 40])
        if h == "Bütçe Kullanımı":
            b.caption("Tablo 3. Bütçe kullanım durumu")
            b.table([["Bütçe kalemi", "Onaylanan (TL)", "Harcanan (TL)", "Kalan (TL)"],
                     ["Makine-teçhizat", "[—]", "[—]", "[—]"], ["Sarf malzemesi", "[—]", "[—]", "[—]"],
                     ["Hizmet alımı", "[—]", "[—]", "[—]"], ["Seyahat", "[—]", "[—]", "[—]"],
                     ["TOPLAM", "[—]", "[—]", "[—]"]],
                    widths=[34, 22, 22, 22], align_right=(1, 2, 3), bold_last=True)
        if h == "Sonraki Dönem Çalışma Planı":
            b.table([["Yapılacak iş", "Başlangıç", "Bitiş", "Beklenen çıktı"],
                     ["[—]", "[gg.aa]", "[gg.aa]", "[—]"], ["[—]", "[gg.aa]", "[gg.aa]", "[—]"]],
                    widths=[38, 15, 15, 32])
            # Onay bölümü bölünmesin. Sayfa sonu tablodan sonraki boş bloğa değil yeni bir bloğa gitsin:
            # Qt tablodan hemen sonraki paragrafın üst boşluğunu yok sayar, Word saymaz.
            b.fresh = False
            b.page_break()
        if h == "Danışman Görüşü ve Onay":
            b.callout("Danışman görüşü", [("[Çalışmanın ilerleyişine ilişkin değerlendirme]",
                                          dict(placeholder=True, after=6)),
                                         ("☐ Çalışmalar plana uygun yürütülmektedir.", dict(after=2)),
                                         ("☐ Çalışmalar gecikmeli yürütülmektedir; telafi planı uygundur.",
                                          dict(after=2)),
                                         ("☐ İlerleme yetersizdir.", dict(after=0))])
            b.spacer(8)
            b.signature_table([["Hazırlayan", a("author") or "[Ad SOYAD]", ""],
                               ["Danışman", a("advisor") or "[Unvan Ad SOYAD]", ""]],
                              cols=("Görevi", "Unvanı, Adı Soyadı", "İmza / Tarih"))
    _numbered_sections(b, "ara_rapor", opts, hook)


def _last_table(b):
    c = QTextCursor(b.c)
    c.movePosition(QTextCursor.MoveOperation.PreviousBlock)
    return c.currentTable()


def _deneme(b, a, opts):
    t = b.t
    C = Qt.AlignmentFlag.AlignHCenter
    b.setup((30, 30, 30, 30), footer="{SAYFA}", different_first=True)
    b.spacer(40)
    if a("title"):
        b.p(a("title"), font=t.title_font, size=t.size * 2.4, italic=True, color=t.dark, align=C, first=0, after=10,
            style="Konu Başlığı")
    else:
        b.ph("Denemenin Başlığı", font=t.title_font, size=t.size * 2.4, align=C, first=0, after=10,
             style="Konu Başlığı")
    b.p(a("author") or "[Yazar]", caps="small", spacing=1.5, color=t.accent, align=C, first=0, after=4,
        placeholder=not a("author"))
    b.p(" · ".join(x for x in (a("course"), a("date") or _today()) if x), color=t.muted, size=t.size * 0.9,
        align=C, first=0, after=14)
    b.image(ornament(t, 200, 18), 200, 18, after=24)
    for i, (heading, level, hint) in enumerate(_sections("deneme")):
        if i == 0:
            b.heading(heading, 2, rule=False)
            # Kitap geleneği: açılış sözcükleri küçük büyük harf ve vurgu renginde
            b.runs([("Yazının ilk cümlesi", dict(caps="small", spacing=0.8, color=t.accent, bold=True)),
                    (" okuru içeri çekmeli. ", dict()),
                    ("[" + hint + "]", dict(placeholder=True))], first=0, after=8)
            continue
        b.heading(heading, 2, rule=False)
        _section_body(b, "deneme", heading, hint, opts)
    b.image(ornament(t, 120, 14), 120, 14, after=0)


def _rapor(b, a, opts):
    t = b.t
    b.setup((22, 22, 22, 22), header=(a("title") or "Faaliyet Raporu")[:70], header_align="left",
            footer="Sayfa {SAYFA} / {TOPLAM}", footer_align="right", different_first=True)
    _cover_modern(b, a, "Faaliyet Raporu", "Dönem: 2026 · 3. Çeyrek",
                  [("Hazırlayan", a("author")), ("Birim", a("institution")), ("Tarih", a("date") or _today()),
                   ("Dağıtım", "Yönetim Kurulu"), ("Gizlilik", "Kurum içi")], art="grid")
    b.page_break()
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()

    def hook(h):
        if h == "Yönetici Özeti":
            b.stat_boxes([("₺ —", "[Gelir / bütçe]"), ("%—", "[Büyüme]"), ("—", "[Müşteri / kullanıcı]"),
                          ("—", "[Memnuniyet]")])
        if h == "Bulgular":
            b.caption("Tablo 1. Temel performans göstergeleri")
            b.table([["Gösterge", "Hedef", "Gerçekleşen", "Durum"], ["[—]", "[—]", "[—]", "▲"],
                     ["[—]", "[—]", "[—]", "▼"], ["[—]", "[—]", "[—]", "●"]], widths=[40, 20, 20, 20],
                    align_right=(1, 2))
        if h == "Öneriler":
            b.table([["Öneri", "Sorumlu", "Termin", "Öncelik"], ["[Somut eylem]", "[—]", "[gg.aa]", "Yüksek"],
                     ["[—]", "[—]", "[—]", "Orta"]], widths=[46, 20, 16, 18])
    _numbered_sections(b, "rapor", opts, hook)


def _dilekce(b, a, opts):
    t = b.t
    R, C = Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignHCenter
    b.setup((25, 25, 25, 20), header="", footer="")
    b.p(a("date") or _today(), align=R, first=0, after=30)
    rec = a("recipient")
    b.p(turkish_upper(rec) if rec else "[… MÜDÜRLÜĞÜNE / DEKANLIĞINA]", bold=True, align=C, first=0, after=4,
        placeholder=not rec)
    b.p("[ŞEHİR]", bold=True, align=R, first=0, after=28, placeholder=True)
    if a("subject"):
        b.runs([("Konu: ", dict(bold=True)), (a("subject"), dict())], first=0, after=12)
    b.ph("Kendinizi tanıtın (bölüm, öğrenci / T.C. kimlik no). Talebinizi ve gerekçesini "
         "açık, kısa ve saygılı bir dille yazın.")
    b.ph("Gerekirse ikinci paragrafta ek açıklama ve ekleri belirtin.")
    b.p("Gereğini bilgilerinize arz ederim.", after=40)
    b.p(a("date") or _today(), align=R, first=0, after=2)
    b.p(a("author") or "[Ad SOYAD]", align=R, bold=True, first=0, after=2, placeholder=not a("author"))
    b.p("İmza", align=R, color=t.muted, first=0, after=40)
    for lab, ph in (("Adres:", "Açık adres"), ("Telefon:", "05xx xxx xx xx"), ("E-posta:", "ad.soyad@ornek.com")):
        b.runs([(lab + " ", dict(bold=True)), (f"[{ph}]", dict(placeholder=True))], first=0, after=2,
               align=Qt.AlignmentFlag.AlignLeft)
    b.p("EKLER:", bold=True, before=14, first=0, after=2, align=Qt.AlignmentFlag.AlignLeft)
    b.items(["Belge adı", "Belge adı"], numbered=True, placeholder=True)


def _mektup(b, a, opts):
    t = b.t
    R = Qt.AlignmentFlag.AlignRight
    b.setup((25, 22, 25, 25), header="", footer="")
    b.p(a("author") or "[Ad Soyad]", font=t.title_font, size=t.size * 2.4, color=t.accent, first=0, after=2,
        placeholder=not a("author"), align=Qt.AlignmentFlag.AlignLeft)
    b.runs([("[Unvan / meslek]", dict(placeholder=True, caps="small", spacing=1.0))], first=0, after=6,
           align=Qt.AlignmentFlag.AlignLeft)
    b.runs([("✉ ", dict(color=t.accent)), ("[e-posta]", dict(placeholder=True, size=t.size * 0.9)),
            ("     ☎ ", dict(color=t.accent)), ("[telefon]", dict(placeholder=True, size=t.size * 0.9)),
            ("     ⌂ ", dict(color=t.accent)), ("[adres]", dict(placeholder=True, size=t.size * 0.9))],
           first=0, after=6, align=Qt.AlignmentFlag.AlignLeft)
    b.image(thin_band(t, b.tw, 3), b.tw, 3, after=26)
    b.p(a("date") or _today(), align=R, first=0, after=20)
    b.p(a("recipient") or "[Alıcı adı / kurum]", bold=True, first=0, after=2, placeholder=not a("recipient"),
        align=Qt.AlignmentFlag.AlignLeft)
    b.ph("Alıcı adresi", first=0, after=18, align=Qt.AlignmentFlag.AlignLeft)
    b.runs([("Konu: ", dict(bold=True)), (a("subject") or "[Mektubun konusu]", dict(placeholder=not a("subject")))],
           first=0, after=14, align=Qt.AlignmentFlag.AlignLeft)
    b.p("Sayın [Ad Soyad],", first=0, after=10)
    b.ph("Giriş: yazma amacınızı ilk cümlede açıkça belirtin.", after=8)
    b.ph("Gelişme: ayrıntılar, gerekçeler ve talepler.", after=8)
    b.ph("Kapanış: beklediğiniz eylemi ve teşekkürünüzü yazın.", after=22)
    b.p("Saygılarımla,", first=0, after=36)
    b.p(a("author") or "[Ad Soyad]", bold=True, first=0, after=0, placeholder=not a("author"))
    b.ph("Unvan", first=0)


def _toplanti(b, a, opts):
    t = b.t
    b.setup((22, 22, 22, 22), header="Toplantı Notları", header_align="right", footer="{SAYFA}")
    b.band([("TOPLANTI NOTLARI", dict(bold=True, color="#FFFFFF", size=t.size * 0.82, spacing=1.8, after=4)),
            (a("title") or "[Toplantının adı]", dict(font=t.title_font, size=t.size * 2.0, color="#FFFFFF",
                                                       placeholder=False, after=0))], bg=t.accent, padding=18)
    b.info_grid([("Tarih", a("date") or _today()), ("Saat", ""), ("Yer / Bağlantı", ""), ("Yöneten", ""),
                 ("Not alan", "")], label_w=26)
    b.heading("Katılımcılar", 2)
    b.items(["Ad Soyad — Birim", "Ad Soyad — Birim"], placeholder=True)
    b.heading("Gündem", 2)
    b.items(["Açılış ve önceki toplantı kararlarının takibi", "Gündem maddesi", "Gündem maddesi",
             "Dilek ve öneriler"], numbered=True)
    b.heading("Görüşmeler", 2)
    b.ph("Her gündem maddesi için kısa özet: kim ne önerdi, hangi seçenekler konuşuldu.")
    b.heading("Kararlar", 2)
    b.table([["No", "Karar", "Sorumlu"], ["1", "[—]", "[—]"], ["2", "[—]", "[—]"]], widths=[8, 67, 25])
    b.heading("Yapılacaklar", 2)
    b.table([["", "Görev", "Sorumlu", "Son tarih"], ["☐", "[—]", "[—]", "[gg.aa]"], ["☐", "[—]", "[—]", "[gg.aa]"],
             ["☐", "[—]", "[—]", "[gg.aa]"]], widths=[6, 54, 22, 18])
    b.callout("Bir sonraki toplantı", "Tarih, saat ve ön gündem.")


def _ozgecmis(b, a, opts):
    t = b.t
    b.setup((16, 16, 18, 18), header="", footer="")
    hdr = b._table(1, 2, [20, 80], border=0, padding=4)
    img = photo_placeholder(t, 104)
    res = f"tpl-{uuid.uuid4().hex[:10]}.png"
    b.doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(res), img)
    cur = hdr.cellAt(0, 0).firstCursorPosition()
    fmt = QTextImageFormat()
    fmt.setName(res)
    fmt.setWidth(104)
    fmt.setHeight(104)
    cur.insertImage(fmt)
    b._fill(hdr.cellAt(0, 1), [
        (a("author") or "Ad Soyad", dict(font=t.title_font, size=t.size * 2.7, color=t.dark, after=0,
                                         placeholder=not a("author"))),
        ("[Hedef pozisyon / Unvan]", dict(color=t.accent, size=t.size * 1.25, placeholder=True, after=6)),
        ([("✉ ", dict(color=t.accent)), ("[e-posta]", dict(placeholder=True, size=t.size * 0.9)),
          ("   ☎ ", dict(color=t.accent)), ("[telefon]", dict(placeholder=True, size=t.size * 0.9)),
          ("   ⌖ ", dict(color=t.accent)), ("[şehir]", dict(placeholder=True, size=t.size * 0.9)),
          ("   in ", dict(color=t.accent, bold=True)), ("[linkedin.com/in/…]", dict(placeholder=True, size=t.size * 0.9))],
         dict(after=0)),
    ])
    b._after_table(hdr)
    b.image(thin_band(t, b.tw, 3), b.tw, 3, after=6)

    def section(title):
        b.heading(title, 1, before=12, rule=False, caps="small", color=t.accent)

    section("Profil")
    b.ph("Deneyiminizi, uzmanlık alanınızı ve hedefinizi 2–3 cümlede özetleyin. Ölçülebilir bir başarı ekleyin.",
         first=0)

    def timeline(rows):
        tb = b._table(len(rows), 2, [24, 76], border=0, padding=5)
        for r, (when, where, role, bullets) in enumerate(rows):
            b._fill(tb.cellAt(r, 0), [(when, dict(bold=True, size=t.size * 0.88, color=t.dark, after=0)),
                                      (where, dict(size=t.size * 0.82, color=t.muted, after=0))])
            paras = [(role, dict(bold=True, after=0)), (bullets[0], dict(color=t.accent, size=t.size * 0.92, after=3))]
            paras += [("•  " + x, dict(placeholder=True, size=t.size * 0.92, after=1)) for x in bullets[1:]]
            b._fill(tb.cellAt(r, 1), paras)
        b._after_table(tb)

    section("Deneyim")
    timeline([("[Ay Yıl – Günümüz]", "[Şehir]", "[Pozisyon]", ["[Şirket adı]", "Sorumluluk ya da başarı (%, sayı)",
                                                                "Kullandığınız araçlar ve sonuç"]),
              ("[Ay Yıl – Ay Yıl]", "[Şehir]", "[Pozisyon]", ["[Şirket adı]", "Başarı", "Başarı"])])
    section("Eğitim")
    timeline([("[Yıl – Yıl]", "[Şehir]", "[Bölüm, Derece]", ["[Üniversite]", "Not ortalaması / derece",
                                                              "Bitirme projesi"])])
    section("Beceriler")
    skills = ["[Beceri]", "[Beceri]", "[Beceri]", "[Beceri]", "[Beceri]"]
    tb = b._table(1, len(skills), [20] * len(skills), border=0, padding=6, spacing=5)
    for i, s_ in enumerate(skills):
        b._fill(tb.cellAt(0, i), [(s_.strip("[]"), dict(placeholder=True, size=t.size * 0.9,
                                                        align=Qt.AlignmentFlag.AlignHCenter))], t.tint)
    b._after_table(tb)
    section("Diller")
    b.table([["Dil", "Seviye"], ["Türkçe", "Ana dil"], ["İngilizce", "[C1 · okuma, yazma, konuşma]"]], widths=[30, 70])
    section("Sertifikalar ve Ödüller")
    b.items(["Sertifika adı — Kurum, Yıl", "Ödül adı — Kurum, Yıl"], placeholder=True)
    section("Referanslar")
    b.p("İstendiğinde sunulacaktır.", italic=True, color=t.muted, first=0)


def _bos(b, a, opts):
    b.setup((25, 25, 25, 25), footer="", header="")
    b.p("", first=0)


BUILDERS = {
    "makale": _makale, "literatur": lambda b, a, o: _makale(b, a, o, "literatur"), "arastirma": _arastirma,
    "tez": _tez, "odev": _odev, "lab": lambda b, a, o: _odev(b, a, o, "lab"), "proje": _proje,
    "ara_rapor": _ara_rapor,
    "deneme": _deneme, "rapor": _rapor, "dilekce": _dilekce, "mektup": _mektup, "toplanti": _toplanti,
    "ozgecmis": _ozgecmis, "bos": _bos,
}


def build_kind(editor, kind, answers, opts):
    """Sihirbaz yanıtlarından tasarımlı belge oluşturur.

    answers: alan -> değer; opts: placeholders, examples, toc, cover, citation, palette, fontset
    """
    theme = make_theme(kind, opts.get("palette"), opts.get("fontset"))
    b = Builder(editor, theme)
    b.toc_cursor = None

    def a(k):
        return (answers.get(k) or "").strip()

    BUILDERS.get(kind, _bos)(b, a, opts)
    if b.toc_cursor is not None:
        c = QTextCursor(editor.document())  # normal (sabitlenmemiş) imleç
        c.setPosition(b.toc_cursor.position())
        editor.setTextCursor(c)
        editor.insert_toc()
    editor.doc_info = {"kind": kind, "citation": opts.get("citation") or "", "title": a("title"),
                       "author": a("author"), "palette": opts.get("palette") or KIND_DESIGN.get(kind, ("",))[0],
                       "fontset": opts.get("fontset") or KIND_DESIGN.get(kind, ("", ""))[1]}
    c = editor.textCursor()
    c.movePosition(QTextCursor.MoveOperation.Start)
    editor.setTextCursor(c)
    editor.document().clearUndoRedoStacks()
    editor.document().setModified(False)


# Eski adlarla çağrılan şablonlar (geri uyumluluk)
_NAMES = {"Mektup": "mektup", "Özgeçmiş": "ozgecmis", "Rapor": "rapor", "Toplantı notları": "toplanti"}


def build(editor, name):
    build_kind(editor, _NAMES.get(name, "bos"), {"title": "", "date": _today()},
               {"placeholders": True, "toc": True, "cover": True})
