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

from .common import STYLE_PROP, PLACEHOLDER_PROP, IMAGE_SLOT_PREFIX, KEEP_NEXT_PROP, pt2px, mm2px, turkish_upper
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
# Evrensel varsayılanlar: akademik belgeler APA / üniversite yazım kılavuzları (Times New Roman 12 pt,
# 1,5 satır, siyah numaralı başlıklar, yalnızca yatay çizgili tablolar); iş belgeleri Calibri 11 pt;
# resmî yazışma Times New Roman 12 pt tek satır aralığı. Renk ve yazı tipi sihirbazda değiştirilebilir.
ACADEMIC = {"makale", "arastirma", "tez", "odev", "lab", "proje", "ara_rapor", "literatur", "deneme"}
KIND_DESIGN = {
    "makale": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "arastirma": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "tez": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "odev": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "lab": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "proje": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "ara_rapor": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "literatur": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "deneme": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "rapor": ("Lacivert", "Ofis (Calibri)"),
    "dilekce": ("Siyah-Beyaz", "Resmî (Times New Roman)"),
    "mektup": ("Lacivert", "Resmî (Times New Roman)"),
    "toplanti": ("Lacivert", "Ofis (Calibri)"),
    "ozgecmis": ("Lacivert", "Ofis (Calibri)"),
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
    academic: bool = False        # siyah, kalın, numaralı başlıklar; APA tabloları; süs yok
    table_style: str = "clean"    # "apa" (yalnızca yatay çizgiler) | "clean" (iş: açık başlık satırı)

    @property
    def h(self):
        return self.heading_color or self.dark


def make_theme(kind, palette=None, fontset=None):
    pal_name, font_name = KIND_DESIGN.get(kind, ("Lacivert", "Ofis (Calibri)"))
    accent, dark, tint = PALETTES.get(palette or pal_name, PALETTES[pal_name])
    head, body, title, size, line = FONT_SETS.get(fontset or font_name, FONT_SETS[font_name])
    t = Theme(accent, dark, tint, head, body, title, size, line)
    if kind in ACADEMIC:
        t.academic, t.table_style = True, "apa"
        t.justify, t.first_indent = True, 12.5
        t.numbered = kind != "deneme"
        t.heading_color = dark
        if kind == "tez":
            t.heading_caps = "upper"
        if kind == "deneme":
            t.line = 200           # MLA: çift satır aralığı
    if kind == "dilekce":
        t.justify, t.first_indent, t.line = True, 12.5, 115
    if kind == "mektup":
        t.line = 115
    if kind in ("rapor", "toplanti"):
        t.numbered = kind == "rapor"
    if kind == "ozgecmis":
        t.heading_caps, t.size, t.line = "small", min(t.size, 10.5), 110
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


def logo_placeholder(theme, size=70, text="Logo ekle"):
    """Tıklanınca resim seçilen logo alanı: kesik çizgili yuvarlak kutu, ortada + ve "Logo ekle"."""
    img, p = _img(size, size)
    r = size * 0.16
    p.setPen(QPen(QColor(theme.muted), 1.2, Qt.PenStyle.DashLine))
    p.setBrush(QColor(theme.tint))
    p.drawRoundedRect(QRectF(2, 2, size - 4, size - 4), r, r)
    plus = QPen(QColor(theme.accent), max(1.5, size * 0.035))
    plus.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(plus)
    cx, cy, k = size / 2, size * 0.40, size * 0.1
    p.drawLine(QPointF(cx - k, cy), QPointF(cx + k, cy))
    p.drawLine(QPointF(cx, cy - k), QPointF(cx, cy + k))
    f = QFont("Segoe UI", 1)
    f.setPixelSize(max(8, int(size * 0.16)))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(theme.muted))
    p.drawText(QRectF(0, size * 0.54, size, size * 0.24), int(Qt.AlignmentFlag.AlignCenter), text)
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
           style="Normal", heading=0, page_break=False, rule=False, fixed=None, keep=False):
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
        if keep:
            b.setProperty(KEEP_NEXT_PROP, True)
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
        lvl = min(level, 3)
        label = f"{number}  {text}" if number and t.numbered else text
        caps = t.heading_caps if caps is None else caps
        if caps == "upper" and level > 1:
            caps = ""
        if t.academic:
            # APA / yazım kılavuzu: 1. düzey 14 pt kalın, 2. düzey 12 pt kalın, 3. düzey 12 pt kalın italik; siyah
            size = {1: t.size + 2, 2: t.size, 3: t.size}[lvl]
            bfmt = self.bf(align=align or Qt.AlignmentFlag.AlignLeft, heading=lvl, style=f"Başlık {lvl}",
                           before=(18 if lvl == 1 else 12) if before is None else before, after=6,
                           page_break=page_break, rule=bool(rule), line=115, first=0)
            f = self.cf(font=t.head, size=size, bold=True, italic=lvl == 3, color=color or t.h, caps=caps)
            self._emit(self.c, self.fresh, [(label, f)], bfmt)
            self.fresh = False
            return self
        size = {1: t.size * 1.55, 2: t.size * 1.22, 3: t.size * 1.08}[lvl]
        bfmt = self.bf(align=align or Qt.AlignmentFlag.AlignLeft, heading=lvl,
                       style=f"Başlık {lvl}", before=(18 if level == 1 else 12) if before is None else before,
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
    def image(self, img, w_px, h_px, align=Qt.AlignmentFlag.AlignHCenter, after=6, slot=None):
        """slot: "logo"/"photo" ise tıklanınca resim seçilen şablon alanı olur."""
        prefix = f"{IMAGE_SLOT_PREFIX}{slot}-" if slot else "tpl-"
        name = f"{prefix}{uuid.uuid4().hex[:10]}.png"
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

    def table(self, rows, widths=None, header=True, zebra=None, size=None, align_right=(), bold_last=False,
              style=None):
        """Veri tablosu. style: "apa" (yalnızca üst, başlık altı ve alt çizgi; renk yok), "clean" (iş belgesi:
        açık başlık satırı, ince yatay çizgiler) ya da "grid" (her hücre çizgili; çizelge ve formlar)."""
        style = style or self.t.table_style
        t = self._table(len(rows), len(rows[0]), widths, border=0, padding=4 if style == "apa" else 5)
        sz = size or self.t.size * 0.92
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                is_h = header and r == 0
                bg = self.t.tint if is_h and style == "clean" else None
                al = Qt.AlignmentFlag.AlignRight if c in align_right and not is_h else Qt.AlignmentFlag.AlignLeft
                ph = isinstance(val, str) and val.startswith("[") and val.endswith("]")
                txt = val[1:-1] if ph else val
                self._fill(t.cellAt(r, c), [(txt, dict(size=sz, bold=is_h or (bold_last and r == len(rows) - 1),
                                                       color=self.t.dark if is_h else None, placeholder=ph,
                                                       align=al))], bg)
        self.rule_table(t, style, header=header, total=bold_last)
        self._after_table(t)
        return self

    def rule_table(self, t, style=None, header=True, total=False):
        """Tablo çizgilerini hücre kenarlıklarıyla çizer (Word'e tcBorders olarak aynen gider)."""
        style = style or self.t.table_style
        dark, light = QColor(self.t.dark), QColor(self.t.border)
        heavy, thin = pt2px(1.0), pt2px(0.5)
        rows, cols = t.rows(), t.columns()
        for r in range(rows):
            for c in range(cols):
                sides = {}
                if style == "grid":
                    sides = {k: (thin, dark) for k in ("top", "bottom", "left", "right")}
                elif style == "apa":
                    if r == 0:
                        sides["top"] = (heavy, dark)
                    if header and r == 0:
                        sides["bottom"] = (thin, dark)
                    if total and r == rows - 1:
                        sides["top"] = (thin, dark)
                    if r == rows - 1:
                        sides["bottom"] = (heavy, dark)
                else:  # clean
                    sides["bottom"] = (heavy if (header and r == 0) or r == rows - 1 else thin,
                                       dark if (header and r == 0) or r == rows - 1 else light)
                    if total and r == rows - 1:
                        sides["top"] = (thin, dark)
                self._cell_borders(t.cellAt(r, c), sides)

    @staticmethod
    def _cell_borders(cell, sides):
        if not sides:
            return
        f = cell.format().toTableCellFormat()
        solid = QTextFrameFormat.BorderStyle.BorderStyle_Solid
        for side, (w, col) in sides.items():
            S = side.title()
            getattr(f, f"set{S}Border")(w)
            getattr(f, f"set{S}BorderStyle")(solid)
            getattr(f, f"set{S}BorderBrush")(QBrush(col))
        cell.setFormat(f)

    def caption(self, text, above=True):
        """'Tablo 4.1. Açıklama' → kalın numara + italik açıklama (APA: tablonun üstünde)."""
        import re
        m = re.match(r"^((?:Tablo|Şekil)\s+[\d.]*\d\.?)\s*(.*)$", text)
        num, rest = (m.group(1), m.group(2)) if m else ("", text)
        sz = self.t.size if self.t.academic else self.t.size * 0.9
        return self.runs([(num + " ", dict(bold=True, size=sz)), (rest, dict(italic=True, size=sz))],
                         before=6, after=3 if above else 10, first=0, align=Qt.AlignmentFlag.AlignLeft,
                         line=115, keep=above)

    def band(self, paras, bg=None, padding=16):
        t = self._table(1, 1, border=0, padding=padding)
        self._fill(t.cellAt(0, 0), paras, bg or self.t.accent)
        self._after_table(t)
        return self

    def info_grid(self, pairs, label_w=32):
        """Kapak/üst bilgi tablosu: etiket | değer, ince yatay çizgiler, dolgu yok."""
        t = self._table(len(pairs), 2, [label_w, 100 - label_w], border=0, padding=5)
        for r, (lab, val) in enumerate(pairs):
            self._fill(t.cellAt(r, 0), [(lab, dict(bold=True, size=self.t.size * 0.9, color=self.t.dark))])
            if val:
                self._fill(t.cellAt(r, 1), [(val, dict(size=self.t.size * 0.95))])
            else:
                self._fill(t.cellAt(r, 1), [("…", dict(placeholder=True, size=self.t.size * 0.95))])
        light, dark = QColor(self.t.border), QColor(self.t.dark)
        for r in range(len(pairs)):
            for c in range(2):
                sides = {"bottom": (pt2px(0.5), light)}
                if r == 0:
                    sides["top"] = (pt2px(1.0), dark)
                if r == len(pairs) - 1:
                    sides["bottom"] = (pt2px(1.0), dark)
                self._cell_borders(t.cellAt(r, c), sides)
        self._after_table(t)
        return self

    def info_lines(self, pairs, align=Qt.AlignmentFlag.AlignHCenter, size=None):
        """Resmî kapaklardaki ortalı bilgi satırları: 'Hazırlayan: Ad Soyad'."""
        sz = size or self.t.size
        for lab, val in pairs:
            self.runs([(f"{lab}: ", dict(bold=True, size=sz)),
                       (val or f"[{lab}]", dict(size=sz, placeholder=not val))],
                      align=align, first=0, after=2, line=115)
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
        """İmza tablosu (form): tüm hücreler ince çizgili, dolgu yok."""
        data = [list(cols)] + [list(r) for r in rows]
        t = self._table(len(data), len(cols), [40, 40, 20], border=0, padding=8)
        for r, row in enumerate(data):
            for c, val in enumerate(row):
                hdr = r == 0
                ph = not hdr and val.startswith("[")
                self._fill(t.cellAt(r, c), [(val.strip("[]") if ph else val,
                                             dict(bold=hdr, size=self.t.size * 0.92, placeholder=ph))])
        self.rule_table(t, "grid")
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
    """Dergiye gönderim düzeni (APA 7 / yaygın dergi kılavuzları): ortalı başlık, yazar ve kurum bilgisi,
    girintili öz, numaralı bölümler, APA tabloları, beyanlar ve kaynakça."""
    t = b.t
    C, L = Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignLeft
    short = a("title")[:60] if a("title") else "Kısa Başlık"
    b.setup((25, 25, 25, 25), header=short, header_align="right", footer="{SAYFA}", different_first=True)
    if a("title"):
        b.p(a("title"), font=t.title_font, size=t.size + 4, bold=True, style="Konu Başlığı", align=C,
            after=6, line=115, first=0)
    else:
        b.ph("Makale başlığı (10–15 sözcük)", font=t.title_font, size=t.size + 4, bold=True, style="Konu Başlığı",
             align=C, after=6, line=115, first=0)
    b.ph("İngilizce başlık (English title)", size=t.size, align=C, after=14, first=0, line=115)
    authors = [x.strip() for x in (a("author") or "").split(";") if x.strip()] or ["[Yazar Adı Soyadı]"]
    parts = []
    for i, au in enumerate(authors, 1):
        ph = au.startswith("[")
        parts += [(au, dict(size=t.size, placeholder=ph)), (str(i), dict(sup=True)),
                  (", " if i < len(authors) else "", dict())]
    b.runs(parts, align=C, after=4, first=0, line=115)
    for i, _ in enumerate(authors, 1):
        b.runs([(str(i), dict(sup=True, size=t.size - 1)),
                (" " + (a("institution") or ""), dict(italic=True, size=t.size - 1)),
                (" [Bölüm, Şehir, Ülke]", dict(size=t.size - 1, placeholder=True))],
               align=C, after=0, first=0, line=115)
    b.runs([("Sorumlu yazar: ", dict(size=t.size - 1)),
            ("[e-posta · ORCID 0000-0000-0000-0000]", dict(size=t.size - 1, placeholder=True))],
           align=C, before=4, after=14, first=0, line=115)
    n = 0
    for heading, level, hint in _sections(kind):
        low = heading.lower()
        if low in ("özet", "abstract"):
            kw_label = "Anahtar Kelimeler:" if low == "özet" else "Keywords:"
            kw_val = a("keywords") if low == "özet" else ""
            b.heading(heading, 2, align=C, before=6)
            b.ph(hint, size=t.size - 1, left=7, right=7, first=0, line=115, after=4,
                 align=Qt.AlignmentFlag.AlignJustify)
            b.runs([(kw_label + " ", dict(bold=True, size=t.size - 1)),
                    (kw_val or "[3–5 kavram, virgülle]", dict(size=t.size - 1, placeholder=not kw_val))],
                   left=7, right=7, first=0, line=115, after=10, align=L)
            continue
        if low == "kaynakça":
            b.heading("Beyanlar", 1)
            for lab, txt in (("Etik kurul onayı: ", "Kurul adı, tarih ve sayı."),
                             ("Çıkar çatışması: ", "Yazarlar çıkar çatışması olmadığını beyan eder."),
                             ("Yazar katkıları: ", "Fikir, tasarım, veri toplama, analiz, yazım."),
                             ("Veri erişilebilirliği: ", "Verilere nasıl ulaşılabileceği.")):
                b.runs([(lab, dict(bold=True)), (f"[{txt}]", dict(placeholder=True))], after=2, first=0,
                       align=L)
            b.heading(heading, 1)
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
        b.image(logo_placeholder(t, 96), 96, 96, after=36, slot="logo")
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


def _cover_formal(b, a, kind_label, info_pairs, tc=True, subtitle=None, above_title=None):
    """Resmî (üniversite/kurum) kapağı: her şey ortalı, süs yok; logo alanı tıklanınca resim seçilir."""
    t = b.t
    C = Qt.AlignmentFlag.AlignHCenter
    big = t.size + 1
    if tc:
        b.p("T.C.", bold=True, size=big, align=C, first=0, after=0, line=115)
    inst = a("institution")
    b.p(turkish_upper(inst) if inst else "[ÜNİVERSİTE / KURUM ADI]", bold=True, size=big, align=C, first=0,
        after=0, line=115, placeholder=not inst)
    dep = a("department")
    if dep:
        b.p(turkish_upper(dep), bold=True, size=big, align=C, first=0, after=0, line=115)
    else:
        b.ph("… Fakültesi / … Bölümü", size=t.size, align=C, first=0, after=0, line=115)
    b.spacer(40)
    b.image(logo_placeholder(t, 84), 84, 84, after=0, slot="logo")
    b.spacer(84)
    if above_title is not None:
        b.p(above_title or "[Ders Adı]", size=t.size + 1, align=C, first=0, after=8, line=115,
            placeholder=not above_title)
    if a("title"):
        b.p(a("title"), font=t.title_font, size=t.size + 6, bold=True, align=C, first=0, after=10, line=115,
            style="Konu Başlığı")
    else:
        b.ph("Başlık", font=t.title_font, size=t.size + 6, bold=True, align=C, first=0, after=10, line=115,
             style="Konu Başlığı")
    if subtitle:
        b.ph(subtitle, size=t.size, align=C, first=0, after=8, line=115)
    b.p(turkish_upper(kind_label), bold=True, size=big, align=C, first=0, after=0, line=115)
    b.spacer(120)
    b.info_lines(info_pairs)
    b.spacer(110)
    b.runs([("[ŞEHİR]", dict(bold=True, placeholder=True)), (f" – {_year()}", dict(bold=True))],
           align=C, after=0, first=0)
    b.page_break()


def _cover_business(b, a, kind_label, subtitle_ph, info_pairs):
    """Kurumsal rapor kapağı: logo, küçük etiket, büyük başlık, ince vurgu çizgisi, bilgi tablosu."""
    t = b.t
    L = Qt.AlignmentFlag.AlignLeft
    b.image(logo_placeholder(t, 72), 72, 72, align=L, after=0, slot="logo")
    b.spacer(150)
    b.label(f"{kind_label}  ·  {_year()}", align=L, first=0)
    if a("title"):
        b.p(a("title"), font=t.title_font, size=t.size * 2.5, color=t.dark, style="Konu Başlığı", after=8,
            line=105, first=0, align=L)
    else:
        b.ph("Raporun Başlığı", font=t.title_font, size=t.size * 2.5, style="Konu Başlığı", after=8, first=0,
             align=L)
    b.ph(subtitle_ph, size=t.size * 1.2, after=14, first=0, align=L)
    b.image(thin_band(t, b.tw * 0.25, 3), b.tw * 0.25, 3, align=L, after=0)
    b.spacer(170)
    b.info_grid(info_pairs, label_w=28)
    b.page_break()


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
    title = a("title") or "Araştırma Raporu"
    b.setup((25, 25, 25, 25), header=title[:70], header_align="right", footer="{SAYFA}", different_first=True)
    if opts.get("cover", True):
        _cover_formal(b, a, "Araştırma Raporu", [("Hazırlayan", a("author")), ("Rapor No", ""),
                                                 ("Tarih", a("date") or _today())],
                      tc=False, subtitle="Alt başlık: araştırmanın kapsamı tek cümleyle")
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()

    def hook(h):
        if h == "Özet":
            b.runs([("Anahtar Kelimeler: ", dict(bold=True)),
                    (a("keywords") or "[3–5 kavram, virgülle]", dict(placeholder=not a("keywords")))], first=0,
                   align=Qt.AlignmentFlag.AlignLeft)
        if h == "Bulgular":
            b.caption("Tablo 1. Alt problemlere ilişkin bulguların özeti")
            b.table([["Alt problem", "Analiz", "Sonuç", "p"], ["1", "[—]", "[—]", "[—]"], ["2", "[—]", "[—]", "[—]"],
                     ["3", "[—]", "[—]", "[—]"]], widths=[18, 30, 38, 14], align_right=(3,))
        if h == "Sonuç ve Öneriler":
            b.items(["Uygulayıcılara yönelik öneri", "Politika yapıcılara yönelik öneri",
                     "Sonraki araştırmalara yönelik öneri"], numbered=True, placeholder=True)
    _numbered_sections(b, "arastirma", opts, hook)


def _odev(b, a, opts, kind="odev"):
    t = b.t
    C = Qt.AlignmentFlag.AlignHCenter
    b.setup((25, 25, 25, 25), header=(a("course") or "")[:60], header_align="right", footer="{SAYFA}",
            different_first=True)
    if opts.get("cover", True):
        _cover_formal(b, a, "Dönem Ödevi" if kind == "odev" else "Deney Raporu",
                      [("Hazırlayan", a("author")), ("Öğrenci No", a("student_no")),
                       ("Öğretim Üyesi", a("instructor")), ("Teslim Tarihi", a("date") or _today())],
                      tc=True, above_title=a("course"))
    n = 0
    for heading, level, hint in _sections(kind):
        if heading == "Kaynakça":
            b.heading(heading, 1)
            _section_body(b, kind, heading, hint, opts)
            _references(b, opts)
            continue
        n += 1
        b.heading(heading, 1, number=f"{n}.")
        if heading == "Teorik Bilgi":
            _section_body(b, kind, heading, hint, opts)
            b.p("F = m · a", italic=True, align=C, first=0, after=0)
            b.p("(1)", align=Qt.AlignmentFlag.AlignRight, first=0, after=8)
            continue
        if heading == "Kullanılan Araç ve Gereçler":
            b.items(["Malzeme 1 (adet / özellik)", "Malzeme 2", "Ölçüm cihazı (duyarlılık)"], placeholder=True)
            continue
        if heading == "Deneyin Yapılışı":
            b.items(["Düzeneği şekildeki gibi kurduk.", "Ölçümü … kez tekrarladık.", "Verileri tabloya kaydettik."],
                    numbered=True, placeholder=True)
            continue
        if heading == "Veriler ve Hesaplamalar":
            _section_body(b, kind, heading, hint, opts)
            b.caption("Tablo 1. Ölçüm sonuçları")
            b.table([["Deneme", "Ölçülen (birim)", "Hesaplanan (birim)", "Bağıl hata (%)"],
                     ["1", "[—]", "[—]", "[—]"], ["2", "[—]", "[—]", "[—]"], ["3", "[—]", "[—]", "[—]"],
                     ["Ortalama", "", "", ""]], widths=[18, 27, 27, 28], align_right=(1, 2, 3), bold_last=True)
            b.p("Bağıl hata = |deneysel − teorik| / teorik × 100", italic=True, align=C, first=0)
            continue
        _section_body(b, kind, heading, hint, opts)


def _proje(b, a, opts):
    t = b.t
    b.setup((25, 25, 25, 25), header=(a("title") or "Proje Önerisi")[:70], header_align="right",
            footer="Sayfa {SAYFA} / {TOPLAM}", footer_align="center", different_first=True)
    if opts.get("cover", True):
        _cover_formal(b, a, "Proje Önerisi",
                      [("Proje Yürütücüsü", a("author")), ("Araştırmacılar", ""), ("Destek Programı", ""),
                       ("Süre", "12 ay"), ("Toplam Bütçe", ""), ("Tarih", a("date") or _today())],
                      tc=False, subtitle="Projenin tek cümlelik özeti")
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()

    def hook(h):
        if h == "Amaç ve Hedefler":
            b.caption("Tablo 1. Proje hedefleri ve başarı ölçütleri")
            b.table([["Kod", "Hedef", "Başarı ölçütü"], ["H1", "[Ölçülebilir hedef]", "[Gösterge ve hedef değer]"],
                     ["H2", "[—]", "[—]"], ["H3", "[—]", "[—]"]], widths=[10, 50, 40])
        if h == "İş-Zaman Çizelgesi":
            months = [str(m) for m in range(1, 13)]
            rows = [["İş Paketi"] + months]
            plan = {"İP1 Literatür ve hazırlık": range(1, 4), "İP2 Veri toplama": range(3, 8),
                    "İP3 Analiz": range(7, 11), "İP4 Raporlama ve yaygınlaştırma": range(10, 13)}
            for name in plan:
                rows.append([name] + [""] * 12)
            b.caption("Tablo 2. İş-zaman çizelgesi (aylar)")
            b.table(rows, widths=[28] + [6] * 12, size=t.size * 0.8, style="grid")
            tbl = _last_table(b)
            if tbl is not None:
                fill = QColor("#8C8C8C") if QColor(t.accent).lightness() < 40 else QColor(t.accent)
                for r, (name, rng) in enumerate(plan.items(), 1):
                    for m in rng:
                        cell = tbl.cellAt(r, m)
                        f = cell.format().toTableCellFormat()
                        f.setBackground(fill)
                        cell.setFormat(f)
        if h == "Bütçe ve Gerekçesi":
            b.caption("Tablo 3. Bütçe ve gerekçesi")
            b.table([["Bütçe kalemi", "Gerekçe", "Tutar (TL)"], ["Makine-teçhizat", "[—]", "[—]"],
                     ["Sarf malzemesi", "[—]", "[—]"], ["Hizmet alımı", "[—]", "[—]"],
                     ["Seyahat", "[—]", "[—]"], ["Toplam", "", "[—]"]],
                    widths=[30, 50, 20], align_right=(2,), bold_last=True)
        if h == "Risk Yönetimi":
            b.caption("Tablo 4. Riskler ve B planları")
            b.table([["Risk", "Olasılık", "Etki", "B planı"], ["[Veri toplamada gecikme]", "Orta", "Yüksek", "[—]"],
                     ["[Ekipman arızası]", "Düşük", "Orta", "[—]"]], widths=[34, 14, 14, 38])
        if h == "Yaygın Etki":
            b.caption("Tablo 5. Beklenen çıktılar")
            b.table([["Çıktı türü", "Açıklama"], ["Bilimsel", "[Makale, bildiri]"], ["Ekonomik", "[Patent, ürün]"],
                     ["Toplumsal", "[Eğitim, farkındalık]"]], widths=[25, 75])
    _numbered_sections(b, "proje", opts, hook)


def _ara_rapor(b, a, opts):
    b.setup((25, 25, 25, 25), header=((a("title") or "Proje")[:55] + " · Ara Rapor"), header_align="right",
            footer="{SAYFA}", footer_align="center", different_first=True)
    if opts.get("cover", True):
        _cover_formal(b, a, "1. Ara Rapor",
                      [("Hazırlayan", a("author")), ("Öğrenci No", a("student_no")), ("Danışman", a("advisor")),
                       ("Proje No", ""), ("Rapor Dönemi", ""), ("Teslim Tarihi", a("date") or _today())],
                      tc=True, subtitle="Bitirme Projesi / BAP Projesi / Yüksek Lisans Tezi")
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()
    L = Qt.AlignmentFlag.AlignLeft

    def hook(h):
        if h == "Özet":
            b.runs([("Anahtar Kelimeler: ", dict(bold=True)),
                    (a("keywords") or "[3–5 kavram, virgülle]", dict(placeholder=not a("keywords")))], first=0,
                   align=L)
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
            b.caption("Tablo 3. Karşılaşılan sorunlar ve alınan önlemler")
            b.table([["Sorun", "Etkisi", "Çözüm / alınan önlem"],
                     ["[Malzeme tedarikinde gecikme]", "[İP2 ~1 ay gecikti]", "[Alternatif tedarikçi]"],
                     ["[—]", "[—]", "[—]"]], widths=[34, 26, 40])
        if h == "Bütçe Kullanımı":
            b.caption("Tablo 4. Bütçe kullanım durumu")
            b.table([["Bütçe kalemi", "Onaylanan (TL)", "Harcanan (TL)", "Kalan (TL)"],
                     ["Makine-teçhizat", "[—]", "[—]", "[—]"], ["Sarf malzemesi", "[—]", "[—]", "[—]"],
                     ["Hizmet alımı", "[—]", "[—]", "[—]"], ["Seyahat", "[—]", "[—]", "[—]"],
                     ["Toplam", "[—]", "[—]", "[—]"]],
                    widths=[34, 22, 22, 22], align_right=(1, 2, 3), bold_last=True)
        if h == "Sonraki Dönem Çalışma Planı":
            b.caption("Tablo 5. Sonraki dönem çalışma planı")
            b.table([["Yapılacak iş", "Başlangıç", "Bitiş", "Beklenen çıktı"],
                     ["[—]", "[gg.aa]", "[gg.aa]", "[—]"], ["[—]", "[gg.aa]", "[gg.aa]", "[—]"]],
                    widths=[38, 15, 15, 32])
            # Onay bölümü bölünmesin. Sayfa sonu tablodan sonraki boş bloğa değil yeni bir bloğa gitsin:
            # Qt tablodan hemen sonraki paragrafın üst boşluğunu yok sayar, Word saymaz.
            b.fresh = False
            b.page_break()
        if h == "Danışman Görüşü ve Onay":
            for line in ("☐ Çalışmalar plana uygun yürütülmektedir.",
                         "☐ Çalışmalar gecikmeli yürütülmektedir; telafi planı uygundur.",
                         "☐ İlerleme yetersizdir."):
                b.p(line, first=0, after=2, align=L)
            b.ph("Danışmanın değerlendirmesi", before=6, after=10)
            b.signature_table([["Hazırlayan", a("author") or "[Ad SOYAD]", ""],
                               ["Danışman", a("advisor") or "[Unvan Ad SOYAD]", ""]],
                              cols=("Görevi", "Unvanı, Adı Soyadı", "İmza / Tarih"))
    _numbered_sections(b, "ara_rapor", opts, hook)


def _last_table(b):
    c = QTextCursor(b.c)
    c.movePosition(QTextCursor.MoveOperation.PreviousBlock)
    return c.currentTable()


def _deneme(b, a, opts):
    """MLA 9 düzeni: sol üstte ad / öğretim üyesi / ders / tarih, ortalı başlık, çift satır aralığı,
    ara başlıksız paragraflar (giriş – gelişme – sonuç)."""
    t = b.t
    L, C = Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter
    b.setup((25, 25, 25, 25), footer="{SAYFA}", footer_align="right")
    for val, ph in ((a("author"), "Ad Soyad"), (a("instructor"), "Öğretim üyesi"), (a("course"), "Ders adı"),
                    (a("date") or _today(), "")):
        b.p(val or f"[{ph}]", placeholder=not val, align=L, first=0, after=0)
    if a("title"):
        b.p(a("title"), align=C, first=0, after=0, style="Konu Başlığı")
    else:
        b.ph("Denemenin Başlığı", align=C, first=0, after=0, style="Konu Başlığı")
    for text in ("Giriş: dikkat çekici bir açılış yapın; paragrafın sonunda tez cümlenizi (ana iddianızı) yazın.",
                 "Birinci gelişme paragrafı: konu cümlesi, kanıt ya da örnek ve bunun teze nasıl bağlandığı.",
                 "İkinci gelişme paragrafı: farklı bir açıdan ikinci gerekçe ve kanıtı.",
                 "Karşı görüş: olası bir itirazı adil biçimde sunun ve yanıtlayın.",
                 "Sonuç: tezi farklı sözcüklerle yeniden vurgulayın ve düşündürücü bir kapanış yapın."):
        b.ph(text, align=L, after=0)


def _rapor(b, a, opts):
    b.setup((22, 22, 22, 22), header=(a("title") or "Faaliyet Raporu")[:70], header_align="left",
            footer="Sayfa {SAYFA} / {TOPLAM}", footer_align="right", different_first=True)
    _cover_business(b, a, "Faaliyet Raporu", "Dönem: 2026 · 3. Çeyrek",
                    [("Hazırlayan", a("author")), ("Birim", a("institution")), ("Tarih", a("date") or _today()),
                     ("Dağıtım", "Yönetim Kurulu"), ("Gizlilik", "Kurum içi")])
    if opts.get("toc", True):
        b.toc_here()
        b.page_break()

    def hook(h):
        if h == "Yönetici Özeti":
            b.items(["Öne çıkan sonuç 1 (rakamla)", "Öne çıkan sonuç 2", "Öne çıkan öneri"], placeholder=True)
        if h == "Bulgular":
            b.caption("Tablo 1. Temel performans göstergeleri")
            b.table([["Gösterge", "Hedef", "Gerçekleşen", "Değişim"], ["[—]", "[—]", "[—]", "[+%—]"],
                     ["[—]", "[—]", "[—]", "[−%—]"], ["[—]", "[—]", "[—]", "[%—]"]], widths=[40, 20, 20, 20],
                    align_right=(1, 2, 3))
        if h == "Öneriler":
            b.caption("Tablo 2. Eylem planı")
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
    """Blok düzende iş mektubu: antet (logo, ad, iletişim), tarih, alıcı, konu, hitap, gövde, kapanış."""
    t = b.t
    R, L = Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft
    b.setup((25, 22, 25, 25), header="", footer="")
    b.image(logo_placeholder(t, 56), 56, 56, align=L, after=6, slot="logo")
    b.p(a("author") or "[Ad Soyad / Kurum Adı]", bold=True, size=t.size + 4, color=t.dark, first=0, after=0,
        placeholder=not a("author"), align=L, line=110)
    b.ph("Adres · Telefon · E-posta", size=t.size - 1, first=0, after=4, align=L)
    b.image(thin_band(t, b.tw, 2), b.tw, 2, after=24)
    b.p(a("date") or _today(), align=R, first=0, after=18)
    b.p(a("recipient") or "[Alıcı adı / kurum]", bold=True, first=0, after=0, placeholder=not a("recipient"),
        align=L)
    b.ph("Alıcı adresi", first=0, after=16, align=L)
    b.runs([("Konu: ", dict(bold=True)), (a("subject") or "[Mektubun konusu]", dict(placeholder=not a("subject")))],
           first=0, after=14, align=L)
    b.p("Sayın [Ad Soyad],", first=0, after=10, align=L)
    b.ph("Giriş: yazma amacınızı ilk cümlede açıkça belirtin.", after=8, align=L, first=0)
    b.ph("Gelişme: ayrıntılar, gerekçeler ve talepler.", after=8, align=L, first=0)
    b.ph("Kapanış: beklediğiniz eylemi ve teşekkürünüzü yazın.", after=20, align=L, first=0)
    b.p("Saygılarımla,", first=0, after=36, align=L)
    b.p(a("author") or "[Ad Soyad]", bold=True, first=0, after=0, placeholder=not a("author"), align=L)
    b.ph("Unvan", first=0, align=L)


def _toplanti(b, a, opts):
    t = b.t
    L = Qt.AlignmentFlag.AlignLeft
    b.setup((20, 20, 22, 22), header="", footer="{SAYFA}")
    b.label("Toplantı Notları", align=L, first=0)
    if a("title"):
        b.p(a("title"), font=t.title_font, size=t.size * 2.0, color=t.dark, first=0, after=8, align=L, line=105)
    else:
        b.ph("Toplantının adı", font=t.title_font, size=t.size * 2.0, first=0, after=8, align=L)
    b.info_grid([("Tarih", a("date") or _today()), ("Saat", ""), ("Yer / Bağlantı", ""), ("Yöneten", ""),
                 ("Not alan", "")], label_w=24)

    def head(text):
        b.heading(text, 2, before=10)

    head("Katılımcılar")
    b.ph("Ad Soyad (Birim), Ad Soyad (Birim), …", first=0, align=L)
    head("Gündem")
    b.items(["Açılış ve önceki toplantı kararlarının takibi", "Gündem maddesi", "Gündem maddesi",
             "Dilek ve öneriler"], numbered=True)
    head("Görüşmeler")
    b.ph("Her gündem maddesi için kısa özet: kim ne önerdi, hangi seçenekler konuşuldu.", first=0, align=L)
    head("Kararlar")
    b.table([["No", "Karar", "Sorumlu"], ["1", "[—]", "[—]"], ["2", "[—]", "[—]"]], widths=[8, 67, 25])
    head("Yapılacaklar")
    b.table([["Görev", "Sorumlu", "Son tarih", "Durum"], ["[—]", "[—]", "[gg.aa]", "Açık"],
             ["[—]", "[—]", "[gg.aa]", "Açık"]], widths=[52, 22, 14, 12])
    head("Bir Sonraki Toplantı")
    b.ph("Tarih, saat ve ön gündem.", first=0, align=L)


def _ozgecmis(b, a, opts):
    """Tek sayfalık özgeçmiş: ad ve iletişim, profil, deneyim, eğitim, beceriler, diller."""
    t = b.t
    L = Qt.AlignmentFlag.AlignLeft
    b.setup((16, 16, 18, 18), header="", footer="")
    hdr = b._table(1, 2, [17, 83], border=0, padding=3)
    img = photo_placeholder(t, 88)
    res = f"{IMAGE_SLOT_PREFIX}photo-{uuid.uuid4().hex[:10]}.png"
    b.doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(res), img)
    cur = hdr.cellAt(0, 0).firstCursorPosition()
    fmt = QTextImageFormat()
    fmt.setName(res)
    fmt.setWidth(88)
    fmt.setHeight(88)
    cur.insertImage(fmt)
    b._fill(hdr.cellAt(0, 1), [
        (a("author") or "Ad Soyad", dict(font=t.title_font, size=t.size * 2.4, color=t.dark, after=0,
                                         placeholder=not a("author"))),
        ("[Hedef pozisyon / Unvan]", dict(color=t.accent, size=t.size * 1.2, placeholder=True, after=4)),
        ("[e-posta] · [telefon] · [şehir] · [linkedin.com/in/…]", dict(placeholder=True, size=t.size * 0.95,
                                                                      after=0)),
    ])
    b._after_table(hdr)
    b.image(thin_band(t, b.tw, 2), b.tw, 2, after=2)

    def section(title):
        b.heading(title, 1, before=10, rule=False, caps="small", color=t.dark)

    section("Profil")
    b.ph("Deneyiminizi, uzmanlık alanınızı ve hedefinizi 2–3 cümlede özetleyin. Ölçülebilir bir başarı ekleyin.",
         first=0, align=L)

    def timeline(rows):
        tb = b._table(len(rows), 2, [22, 78], border=0, padding=4)
        for r, (when, where, role, bullets) in enumerate(rows):
            b._fill(tb.cellAt(r, 0), [(when, dict(bold=True, size=t.size * 0.92, color=t.dark, after=0)),
                                      (where, dict(size=t.size * 0.88, color=t.muted, after=0))])
            paras = [(role, dict(bold=True, after=0)), (bullets[0], dict(italic=True, size=t.size * 0.95, after=2))]
            paras += [("•  " + x, dict(placeholder=True, size=t.size * 0.95, after=1)) for x in bullets[1:]]
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
    b.ph("Beceri · Beceri · Beceri · Beceri · Beceri", first=0, align=L)
    section("Diller")
    b.runs([("Türkçe: ", dict(bold=True)), ("Ana dil", dict())], first=0, after=1, align=L)
    b.runs([("İngilizce: ", dict(bold=True)), ("[C1 · okuma, yazma, konuşma]", dict(placeholder=True))],
           first=0, align=L)
    section("Sertifikalar ve Ödüller")
    b.items(["Sertifika adı — Kurum, Yıl", "Ödül adı — Kurum, Yıl"], placeholder=True)
    section("Referanslar")
    b.p("İstendiğinde sunulacaktır.", italic=True, color=t.muted, first=0, align=L)


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

    editor.toc_title_style = (theme.h, theme.size + 2 if theme.academic else 16)
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
    editor.apply_keep_with_next()
    editor.document().clearUndoRedoStacks()
    editor.document().setModified(False)


# Eski adlarla çağrılan şablonlar (geri uyumluluk)
_NAMES = {"Mektup": "mektup", "Özgeçmiş": "ozgecmis", "Rapor": "rapor", "Toplantı notları": "toplanti"}


def build(editor, name):
    build_kind(editor, _NAMES.get(name, "bos"), {"title": "", "date": _today()},
               {"placeholders": True, "toc": True, "cover": True})
