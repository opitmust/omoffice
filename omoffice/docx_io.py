"""QTextDocument <-> .docx dönüşümü.

Desteklenenler: paragraf/karakter biçimleri, başlık stilleri, listeler (çok düzeyli),
tablolar (birleştirilmiş hücreler, hücre rengi, sütun genişlikleri), resimler,
bağlantılar, sayfa sonları, yatay çizgi, sekme durakları, değişiklik izleme
(w:ins / w:del), sayfa yapısı, üst/alt bilgi ve sayfa numarası alanları.
"""
import datetime
import io
import re
import struct

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING, WD_TAB_ALIGNMENT, WD_COLOR_INDEX
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls
from docx.shared import Pt, Mm, Emu, RGBColor
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from lxml import etree

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QImage, QRawFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextFormat, QTextImageFormat, QTextLength, QTextListFormat, QTextOption, QTextTableFormat,
    QTextFrame, QTextFrameFormat, QBrush,
)

from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.packuri import PackURI
from docx.opc.part import XmlPart
from docx.text.run import Run

from .common import (
    TC_TYPE, TC_AUTHOR, TC_DATE, STYLE_PROP, STYLES, DOCX_TO_STYLE, PageSetup,
    COMMENT_PROP, FOOTNOTE_PROP, IMAGE_SLOT_PREFIX, image_slot,
    px2pt, pt2px, DEFAULT_FONT, DEFAULT_SIZE,
)
from .editor import new_document
from .safety import open_word_package, safe_fromstring

import logging
log = logging.getLogger("omoffice")

EMU_PER_PX = 9525
VML_NS = 'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office"'
SECT_AFTER_PGMAR = ("w:paperSrc", "w:pgBorders", "w:lnNumType", "w:pgNumType", "w:cols", "w:formProt",
                    "w:vAlign", "w:noEndnote", "w:titlePg", "w:textDirection", "w:bidi", "w:rtlGutter",
                    "w:docGrid", "w:printerSettings", "w:sectPrChange")
WATERMARK_XML = (
    '<w:r {ns}><w:pict>'
    '<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" '
    'path="m@7,l@8,m@5,21600l@6,21600e"><v:formulas>'
    '<v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/>'
    '<v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/>'
    '<v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/>'
    '<v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/>'
    '<v:f eqn="sum @6 0 @5"/></v:formulas>'
    '<v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" '
    'o:connectangles="270,180,90,0"/><v:textpath on="t" fitshape="t"/>'
    '<v:handles><v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles>'
    '<o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>'
    '<v:shape id="PowerPlusWaterMarkObject1" o:spid="_x0000_s2049" type="#_x0000_t136" '
    'style="position:absolute;margin-left:0;margin-top:0;width:{w}pt;height:{h}pt;rotation:315;'
    'z-index:-251657216;mso-position-horizontal:center;mso-position-horizontal-relative:margin;'
    'mso-position-vertical:center;mso-position-vertical-relative:margin" o:allowincell="f" '
    'fillcolor="silver" stroked="f"><v:fill opacity=".5"/>'
    '<v:textpath style="font-family:&quot;Calibri&quot;;font-size:1pt" string="{text}"/>'
    '</v:shape></w:pict></w:r>')
LH = QTextBlockFormat.LineHeightTypes

HIGHLIGHTS = {
    "yellow": "#FFFF00", "green": "#00FF00", "cyan": "#00FFFF", "magenta": "#FF00FF",
    "blue": "#0000FF", "red": "#FF0000", "darkBlue": "#000080", "darkCyan": "#008080",
    "darkGreen": "#008000", "darkMagenta": "#800080", "darkRed": "#800000",
    "darkYellow": "#808000", "darkGray": "#808080", "lightGray": "#C0C0C0",
    "black": "#000000", "white": "#FFFFFF",
}
HIGHLIGHT_ENUM = {
    "#FFFF00": WD_COLOR_INDEX.YELLOW, "#00FF00": WD_COLOR_INDEX.BRIGHT_GREEN,
    "#00FFFF": WD_COLOR_INDEX.TURQUOISE, "#FF00FF": WD_COLOR_INDEX.PINK,
    "#0000FF": WD_COLOR_INDEX.BLUE, "#FF0000": WD_COLOR_INDEX.RED,
    "#000080": WD_COLOR_INDEX.DARK_BLUE, "#008080": WD_COLOR_INDEX.TEAL,
    "#008000": WD_COLOR_INDEX.GREEN, "#800080": WD_COLOR_INDEX.VIOLET,
    "#800000": WD_COLOR_INDEX.DARK_RED, "#808000": WD_COLOR_INDEX.DARK_YELLOW,
    "#808080": WD_COLOR_INDEX.GRAY_50, "#C0C0C0": WD_COLOR_INDEX.GRAY_25,
    "#000000": WD_COLOR_INDEX.BLACK,
}

LIST_FMT = {
    QTextListFormat.Style.ListDisc: ("bullet", "•"),
    QTextListFormat.Style.ListCircle: ("bullet", "◦"),
    QTextListFormat.Style.ListSquare: ("bullet", "▪"),
    QTextListFormat.Style.ListDecimal: ("decimal", None),
    QTextListFormat.Style.ListLowerAlpha: ("lowerLetter", None),
    QTextListFormat.Style.ListUpperAlpha: ("upperLetter", None),
    QTextListFormat.Style.ListLowerRoman: ("lowerRoman", None),
    QTextListFormat.Style.ListUpperRoman: ("upperRoman", None),
}
FMT_TO_LIST = {
    "decimal": QTextListFormat.Style.ListDecimal,
    "decimalZero": QTextListFormat.Style.ListDecimal,
    "lowerLetter": QTextListFormat.Style.ListLowerAlpha,
    "upperLetter": QTextListFormat.Style.ListUpperAlpha,
    "lowerRoman": QTextListFormat.Style.ListLowerRoman,
    "upperRoman": QTextListFormat.Style.ListUpperRoman,
}
BULLET_BY_LEVEL = [QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle,
                   QTextListFormat.Style.ListSquare]

PPR_AFTER_PBDR = ("w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
                  "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi",
                  "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
                  "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection",
                  "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId",
                  "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")
RPR_AFTER_SHD = ("w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang",
                 "w:eastAsianLayout", "w:specVanish", "w:oMath")


def twips2px(v):
    return pt2px(float(v) / 20.0)


def _hex(color):
    return "%02X%02X%02X" % (color.red(), color.green(), color.blue())


# ================================================================ SATIR YÜKSEKLİĞİ
_LINE_CACHE = {}


def _line_pair(font):
    """(Qt'nin %100'de paragraf içi satır adımı px, paragraftan paragrafa adımı px, Word'ün 'tek' satırı pt).

    Qt satır yüksekliğini piksele yuvarlar (ve iki adım negatif 'leading'li yazı tiplerinde farklıdır);
    Word yazı tipinin hhea ölçüsünü (ascent-descent+lineGap) kesirli kullanır. 'Katlı' satır aralığı
    bu oranla çevrilince paragraflar iki programda aynı yükseklikte olur."""
    if font.pointSizeF() <= 0:
        font = QFont(font)
        font.setPointSizeF(DEFAULT_SIZE)
    key = (font.family(), round(font.pointSizeF(), 2), font.bold(), font.italic())
    if key not in _LINE_CACHE:
        doc = QTextDocument()
        doc.setUseDesignMetrics(True)
        doc.setDocumentMargin(0)
        doc.setDefaultFont(font)
        doc.setPlainText("Ağ Ağ\nAğ")
        lay = doc.documentLayout()
        first, second = doc.firstBlock(), doc.lastBlock()
        lay.blockBoundingRect(second)
        fm = QFontMetricsF(font)
        lines = first.layout()
        inner = lines.lineAt(1).y() - lines.lineAt(0).y() if lines.lineCount() > 1 else fm.lineSpacing()
        outer = lay.blockBoundingRect(second).top() - lay.blockBoundingRect(first).top() - inner
        word = px2pt(fm.lineSpacing())
        raw = QRawFont.fromFont(font)
        hhea, head = bytes(raw.fontTable("hhea")), bytes(raw.fontTable("head"))
        if len(hhea) >= 10 and len(head) >= 20:
            upm = struct.unpack(">H", head[18:20])[0]
            asc, desc, gap = struct.unpack(">hhh", hhea[4:10])
            if upm and asc - desc + gap > 0:
                word = (asc - desc + gap) / upm * font.pointSizeF()
        _LINE_CACHE[key] = (inner, outer, word)
    return _LINE_CACHE[key]


def _block_fonts(block, default):
    fonts = []
    it = block.begin()
    while not it.atEnd():
        cf = it.fragment().charFormat()
        if not cf.isImageFormat():
            fonts.append(cf.font().resolve(default))
        it += 1
    return fonts or [block.charFormat().font().resolve(default)]


def _line_ratio(block, default):
    """Word 'katı' / Qt yüzdesi oranı: Word'de katsayı = Qt yüzdesi / 100 * bu oran.
    Blok yerleşmiş olmalı (satır sayısı paragrafın ortalama satır adımını belirler)."""
    m = [_line_pair(f) for f in _block_fonts(block, default)]
    inner, outer, word = (max(x[i] for x in m) for i in range(3))
    n = max(1, block.layout().lineCount() if block.layout() else 1)
    qt = ((n - 1) * inner + outer) / n
    return px2pt(qt) / word if word > 0 else 1.0


def _half_pt(size):
    """Word yazı boyutunu yarım punto adımlarıyla tutar; aşağı kesmek yerine en yakına yuvarla."""
    return max(1.0, round(size * 2) / 2)


def _mark_rpr(para, inner):
    """Paragraf işaretinin (¶) karakter biçimini yazar."""
    pPr = para._p.get_or_add_pPr()
    for old in pPr.findall(qn("w:rPr")):
        pPr.remove(old)
    pPr.append(parse_xml(f'<w:rPr {nsdecls("w")}>{inner}</w:rPr>'))


def _page_top_gap(block):
    """Sayfa sonuyla başlayan paragrafın OmOffice'te sayfa tepesinde bıraktığı boşluk (px): Qt kendi 'önce'
    boşluğu ile önceki paragrafın 'sonra' boşluğundan büyüğünü yeni sayfaya taşır."""
    gap = block.blockFormat().topMargin()
    prev = block.previous()
    if prev.isValid() and QTextCursor(prev).currentTable() is None:
        gap = max(gap, prev.blockFormat().bottomMargin())
    return gap


def _split_break(block):
    """Word sayfa sonundan sonraki ilk paragrafın 'önce' boşluğunu yok sayar, OmOffice göstermeye devam eder.
    Böyle paragraflarda sayfa sonu, önüne konan görünmez bir paragrafa taşınır."""
    bf = block.blockFormat()
    return bool(bf.pageBreakPolicy() & QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore) and _page_top_gap(block) > 0


def _is_break_para(p_el):
    """_break_para'nın yazdığı paragraf mı (boş, önceden sayfa sonu, ≤0,1 pt sabit satır)?"""
    pPr = p_el.find(qn("w:pPr"))
    if pPr is None or p_el.find(f'.//{qn("w:t")}') is not None or p_el.find(f'.//{qn("w:drawing")}') is not None:
        return False
    pbb = pPr.find(qn("w:pageBreakBefore"))
    sp = pPr.find(qn("w:spacing"))
    return (pbb is not None and pbb.get(qn("w:val")) not in ("0", "false") and sp is not None
            and sp.get(qn("w:lineRule")) == "exact" and int(sp.get(qn("w:line")) or 999) <= 2)


def _break_para(para):
    pf = para.paragraph_format
    pf.page_break_before = True
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(0.1)
    _mark_rpr(para, '<w:sz w:val="2"/>')


def _table_of(frame):
    """QTextFrame'i QTextTable'a çevirir (tablo değilse None)."""
    if not frame.format().isTableFormat():
        return None
    c = frame.firstCursorPosition()
    return c.currentTable()


# =============================================================== DIŞA AKTARIM
class _Sink:
    def __init__(self, container, reuse_first=False):
        self.c = container
        self.pending = container.paragraphs[0] if reuse_first else None

    def paragraph(self):
        if self.pending is not None:
            p, self.pending = self.pending, None
            return p
        return self.c.add_paragraph()

    def table(self, rows, cols, width):
        if isinstance(self.c, _Cell):
            t = self.c.add_table(rows, cols)
            self.pending = self.c.paragraphs[-1]
        else:
            if self.pending is not None:
                # boş kalan ilk paragrafı kullanmadan tabloyu önüne ekle
                t = self.c.add_table(rows, cols)
                self.pending._p.addnext(t._tbl)
                self.pending._p.getparent().remove(self.pending._p)
                self.pending = None
            else:
                t = self.c.add_table(rows, cols)
        return t


class _Exporter:
    def __init__(self, d, editor):
        self.d = d
        self.editor = editor
        self.qdoc = editor.document()
        self.nums = {}
        self.change_id = 1
        self.text_width = editor.text_width()
        self.comment_runs = {}     # id -> [ilk Run, son Run]
        self.footnote_order = []   # dışa aktarılan dipnot kimlikleri (sırayla)
        self.fn_part = None
        self.top_paras = []        # (blok konumu, uzunluk, Paragraph) — yalnızca gövde düzeyi
        self.gap_before = None     # az önce yazılan tablonun alt boşluğu (pt)
        self.image_only = False    # yazılan paragraf yalnızca resimden mi oluşuyor
        self.after_table = False   # yazılan paragraf bir tablonun hemen ardından mı geliyor

    # ---- numaralandırma
    def num_id_for(self, lst):
        key = lst.item(0).blockNumber() if lst.count() else id(lst)
        if key in self.nums:
            return self.nums[key]
        numbering = self.d.part.numbering_part.element
        aids = [int(a.get(qn("w:abstractNumId"))) for a in numbering.findall(qn("w:abstractNum"))]
        nids = [int(n.get(qn("w:numId"))) for n in numbering.findall(qn("w:num"))]
        aid = max(aids + [0]) + 1
        nid = max(nids + [0]) + 1
        lf = lst.format()
        my_lvl = max(0, min(8, lf.indent() - 1))
        kind, bullet = LIST_FMT.get(lf.style(), ("bullet", "•"))
        numbered = kind != "bullet"
        levels = []
        for i in range(9):
            if i == my_lvl:
                fmt, sym = kind, bullet
            elif numbered:
                fmt, sym = ("decimal", "lowerLetter", "lowerRoman")[i % 3], None
            else:
                fmt, sym = "bullet", "•◦▪"[i % 3]
            text = sym if fmt == "bullet" else f"%{i + 1}."
            levels.append(
                f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/>'
                f'<w:lvlText w:val="{text}"/><w:lvlJc w:val="left"/>'
                f'<w:pPr><w:ind w:left="{360 * (i + 1)}" w:hanging="360"/></w:pPr></w:lvl>')
        abstract = parse_xml(f'<w:abstractNum {nsdecls("w")} w:abstractNumId="{aid}">'
                             f'<w:multiLevelType w:val="hybridMultilevel"/>{"".join(levels)}</w:abstractNum>')
        first_num = numbering.find(qn("w:num"))
        if first_num is not None:
            first_num.addprevious(abstract)
        else:
            numbering.append(abstract)
        numbering.append(parse_xml(f'<w:num {nsdecls("w")} w:numId="{nid}">'
                                   f'<w:abstractNumId w:val="{aid}"/></w:num>'))
        self.nums[key] = nid
        return nid

    # ---- yapı
    def write_iter(self, it, sink):
        items = []
        while not it.atEnd():
            items.append(it.currentFrame() or it.currentBlock())
            it += 1
        for i, item in enumerate(items):
            if isinstance(item, QTextFrame):
                table = _table_of(item)
                if table is not None:
                    self.write_table(table, sink)
                else:
                    self.write_iter(item.begin(), sink)
                continue
            if _split_break(item):
                _break_para(sink.paragraph())
            para = sink.paragraph()
            prev = items[i - 1] if i else None
            self.after_table = isinstance(prev, QTextFrame) and _table_of(prev) is not None
            self.write_block(item, para)
            self.after_table = False
            nxt = items[i + 1] if i + 1 < len(items) else None
            table = _table_of(nxt) if isinstance(nxt, QTextFrame) else None
            if table is not None:
                self._before_table(item, para, table)
            if sink.c is self.d:
                self.top_paras.append((item.position(), item.length(), para))

    def _before_table(self, block, para, table):
        """Qt tablodan hemen önceki paragrafın 'sonra' boşluğunu yok sayar, boşsa paragrafın kendisi de
        yer kaplamaz; Word'de de öyle olsun. 'Sonra' yerine tablonun üst boşluğu (Word'de karşılığı yok) yazılır."""
        pf = para.paragraph_format
        pf.space_after = Pt(round(px2pt(table.format().topMargin()), 1))
        if not block.text():
            # 'önce' aralığı kalır: az önce bir tablo bittiyse onun alt boşluğunu taşır
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(0.1)
            _mark_rpr(para, '<w:sz w:val="2"/>')

    def write_table(self, t, sink):
        rows, cols = t.rows(), t.columns()
        dt = sink.table(rows, cols, self.text_width)
        tf = t.format()
        tblPr = dt._tbl.tblPr
        # Kenarlık: Qt'deki kalınlık ve renk aynen; 0 ise Word'de de kenarlıksız
        if tf.border() > 0:
            col = _hex(tf.borderBrush().color()) if tf.borderBrush().style() != Qt.BrushStyle.NoBrush else "808080"
            sz = max(2, int(round(px2pt(tf.border()) * 8)))
            sides = "".join(f'<w:{k} w:val="single" w:sz="{sz}" w:space="0" w:color="{col}"/>'
                            for k in ("top", "left", "bottom", "right", "insideH", "insideV"))
        else:
            sides = "".join(f'<w:{k} w:val="nil"/>' for k in ("top", "left", "bottom", "right", "insideH", "insideV"))
        tblPr.insert_element_before(parse_xml(f'<w:tblBorders {nsdecls("w")}>{sides}</w:tblBorders>'),
                                    "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook", "w:tblCaption",
                                    "w:tblDescription")
        if tf.cellSpacing() > 0:
            # Word'deki değer hücreler arası boşluğun yarısıdır
            tblPr.insert_element_before(parse_xml(
                f'<w:tblCellSpacing {nsdecls("w")} w:w="{int(round(px2pt(tf.cellSpacing()) * 10))}" w:type="dxa"/>'),
                "w:tblInd", "w:tblBorders", "w:shd", "w:tblLayout", "w:tblCellMar", "w:tblLook")
        pad = int(round(px2pt(tf.cellPadding()) * 20))
        tblPr.insert_element_before(parse_xml(
            f'<w:tblCellMar {nsdecls("w")}><w:top w:w="{pad}" w:type="dxa"/><w:left w:w="{pad}" w:type="dxa"/>'
            f'<w:bottom w:w="{pad}" w:type="dxa"/><w:right w:w="{pad}" w:type="dxa"/></w:tblCellMar>'),
            "w:tblLook", "w:tblCaption", "w:tblDescription")
        cons = t.format().columnWidthConstraints()
        widths = []
        for i in range(cols):
            w = self.text_width / cols
            if len(cons) == cols:
                ln = cons[i]
                if ln.type() == QTextLength.Type.FixedLength:
                    w = ln.rawValue()
                elif ln.type() == QTextLength.Type.PercentageLength:
                    w = ln.rawValue() / 100.0 * self.text_width
            widths.append(w)
        dt.autofit = False
        for i, w in enumerate(widths):
            dt.columns[i].width = Emu(int(w * EMU_PER_PX))
            for r in range(rows):
                dt.cell(r, i).width = Emu(int(w * EMU_PER_PX))
        for r in range(rows):
            for c in range(cols):
                cell = t.cellAt(r, c)
                if cell.row() != r or cell.column() != c:
                    continue
                rs, cs = cell.rowSpan(), cell.columnSpan()
                dc = dt.cell(r, c)
                if rs > 1 or cs > 1:
                    dc = dc.merge(dt.cell(r + rs - 1, c + cs - 1))
                bg = cell.format().background()
                if bg.style() != Qt.BrushStyle.NoBrush:
                    tcPr = dc._tc.get_or_add_tcPr()
                    tcPr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" '
                                          f'w:fill="{_hex(bg.color())}"/>'))
                self.write_iter(cell.begin(), _Sink(dc, reuse_first=True))
                self.gap_before = None
                # Qt hücredeki ilk paragrafın 'önce', son paragrafın 'sonra' boşluğunu iç boşlukla birleştirir
                dc.paragraphs[0].paragraph_format.space_before = Pt(0)
                dc.paragraphs[-1].paragraph_format.space_after = Pt(0)
        self._row_heights(t, dt)
        # Tablonun alt boşluğu Word'de yok: sonraki paragrafın 'önce' aralığına eklenir
        self.gap_before = px2pt(tf.bottomMargin())

    def _row_heights(self, t, dt):
        """Satırlar Word'de OmOffice'teki yükseklikten kısa kalmasın (en az bu kadar).
        Word'ün trHeight değerine hücre iç boşlukları ayrıca eklenir; yalnızca içerik yüksekliği yazılır.
        İçerik yüksekliği Qt'nin satır konumlarından ölçülür (satır aralığı ve piksel yuvarlaması dahil)."""
        lay = self.qdoc.documentLayout()
        tf = t.format()
        between = 2 * tf.cellPadding() + tf.border() + tf.cellSpacing()
        tops = []
        for r in range(t.rows()):
            ys = []
            for c in range(t.columns()):
                cell = t.cellAt(r, c)
                if cell.row() != r or cell.column() != c:
                    continue
                first = cell.firstCursorPosition().block()
                if first.layout().lineCount():
                    ys.append(lay.blockBoundingRect(first).top())
            tops.append(min(ys) if ys else None)
        # son satır için 'sonraki satırın metin üstü' yerine tablodan sonraki bloktan hesaplanan eşdeğeri
        after = self.qdoc.findBlock(t.lastPosition() + 1)
        tops.append(lay.blockBoundingRect(after).top() - tf.bottomMargin() + tf.cellPadding()
                    if after.isValid() else None)
        _, ph = self.editor.page_px()
        for r in range(t.rows()):
            if tops[r] is None or tops[r + 1] is None:
                continue
            if int(tops[r] // ph) != int((tops[r + 1] - between) // ph):
                continue  # satır sayfa sonuna denk geliyor: ölçü sayfa boşluğunu da içerir
            h = tops[r + 1] - tops[r] - between
            if h <= 0:
                continue
            trPr = dt.rows[r]._tr.get_or_add_trPr()
            trPr.append(parse_xml(f'<w:trHeight {nsdecls("w")} w:val="{int(px2pt(h) * 20)}" '
                                  f'w:hRule="atLeast"/>'))

    def write_block(self, block, para):
        bf = block.blockFormat()
        style = bf.property(STYLE_PROP)
        lvl = bf.headingLevel()
        docx_style = STYLES[style][5] if style in STYLES else (f"Heading {lvl}" if lvl else None)
        if lvl and docx_style == "Normal":
            docx_style = f"Heading {lvl}"
        if docx_style and docx_style != "Normal":
            try:
                para.style = self.d.styles[docx_style]
            except KeyError:
                pass
        pf = para.paragraph_format
        al = bf.alignment()
        if al & Qt.AlignmentFlag.AlignHCenter:
            pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif al & Qt.AlignmentFlag.AlignJustify:
            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        elif al & Qt.AlignmentFlag.AlignRight:
            pf.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif style not in (None, "Normal") or lvl:
            pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        lst = block.textList()
        left = bf.leftMargin() + (0 if lst is not None else bf.indent() * self.qdoc.indentWidth())
        if left:
            pf.left_indent = Pt(px2pt(left))
        if bf.rightMargin():
            pf.right_indent = Pt(px2pt(bf.rightMargin()))
        if bf.textIndent():
            pf.first_line_indent = Pt(px2pt(bf.textIndent()))
        # Qt tablodan hemen sonraki paragrafın 'önce' boşluğunu yok sayar, yerine tablonun alt boşluğunu koyar
        before = px2pt(bf.topMargin()) if self.gap_before is None else self.gap_before
        if _split_break(block):
            before = max(before, px2pt(_page_top_gap(block)))
        pf.space_before = Pt(round(before, 1))
        self.gap_before = None
        pf.space_after = Pt(round(px2pt(bf.bottomMargin()), 1))
        lht = bf.lineHeightType()
        # Qt yalnızca resim içeren satırın yüksekliğini resimden alır, yazı tipini katmaz
        self.image_only = bool(block.text()) and not block.text().replace("￼", "")
        if self.image_only and lht in (LH.ProportionalHeight.value, LH.SingleHeight.value):
            pf.line_spacing = 1.0
        elif self.after_table and not block.text():
            # Qt tablodan hemen sonraki boş paragrafa yer ayırmaz (satır yüksekliği ne olursa olsun)
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(0.1)
        elif lht == LH.ProportionalHeight.value:
            pf.line_spacing = round(bf.lineHeight() / 100.0 * _line_ratio(block, self.qdoc.defaultFont()), 4)
        elif lht == LH.FixedHeight.value:
            pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            pf.line_spacing = Pt(px2pt(bf.lineHeight()))
        elif lht == LH.MinimumHeight.value:
            pf.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
            pf.line_spacing = Pt(px2pt(bf.lineHeight()))
        else:
            pf.line_spacing = round(_line_ratio(block, self.qdoc.defaultFont()), 4)
        policy = bf.pageBreakPolicy()
        if policy & QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore and not _split_break(block):
            pf.page_break_before = True
        # OmOffice'te 'sonrakiyle birlikte tut' ve dul/öksüz satır denetimi yok; Word'ün başlık stillerindeki
        # bu ayarlar sayfa sonlarını kaydırmasın
        pf.keep_with_next = False
        pf.widow_control = False
        for tab in bf.tabPositions():
            align = {QTextOption.TabType.RightTab: WD_TAB_ALIGNMENT.RIGHT,
                     QTextOption.TabType.CenterTab: WD_TAB_ALIGNMENT.CENTER}.get(tab.type, WD_TAB_ALIGNMENT.LEFT)
            pf.tab_stops.add_tab_stop(Pt(px2pt(tab.position)), align)
        pPr = para._p.get_or_add_pPr()
        if bf.hasProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth):
            # Qt çizgiyi yer ayırmadan çizer; Word'de çizgi + 1 pt boşluk ~2 pt yer kaplar
            if pf.space_after is not None:
                pf.space_after = Pt(max(0.0, round(pf.space_after.pt - 2, 1)))
            pPr.insert_element_before(parse_xml(
                f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="8" w:space="1" w:color="808080"/></w:pBdr>'),
                *PPR_AFTER_PBDR)
        elif docx_style in ("Title", "Heading 1"):
            # Word'ün hazır Title/Heading stillerindeki alt çizgi OmOffice'te yok; birebir görünüm için kapat
            pPr.insert_element_before(parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="nil"/></w:pBdr>'),
                                      *PPR_AFTER_PBDR)
        if bf.background().style() != Qt.BrushStyle.NoBrush:
            pPr.insert_element_before(parse_xml(
                f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{_hex(bf.background().color())}"/>'),
                *PPR_AFTER_PBDR[1:])
        if lst is not None:
            numPr = pPr.get_or_add_numPr()
            numPr.get_or_add_ilvl().val = max(0, min(8, lst.format().indent() - 1))
            numPr.get_or_add_numId().val = self.num_id_for(lst)

        it = block.begin()
        last_cf = block.charFormat()
        while not it.atEnd():
            last_cf = it.fragment().charFormat()
            self.write_fragment(para, it.fragment())
            it += 1
        # Word paragraf işaretinin (¶) yazı tipini son satırın yüksekliğine katar, Qt katmaz:
        # işarete son parçanın (boş paragrafta blok biçiminin) yazı tipini ver
        f = last_cf.font().resolve(self.qdoc.defaultFont())
        sz = 2 if self.image_only else max(2, int(round(f.pointSizeF() * 2)))
        _mark_rpr(para, f"<w:rFonts w:ascii=\"{_esc(f.family())}\" w:hAnsi=\"{_esc(f.family())}\"/>"
                        f"<w:sz w:val=\"{sz}\"/>")
        self.image_only = False
        if policy & QTextFormat.PageBreakFlag.PageBreak_AlwaysAfter:
            para.add_run().add_break(WD_BREAK.PAGE)

    def footnote_part(self):
        if self.fn_part is None:
            xml = (f'<w:footnotes {nsdecls("w")}>'
                   '<w:footnote w:type="separator" w:id="-1"><w:p><w:pPr><w:spacing w:after="0" w:line="240" '
                   'w:lineRule="auto"/></w:pPr><w:r><w:separator/></w:r></w:p></w:footnote>'
                   '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:pPr><w:spacing w:after="0" '
                   'w:line="240" w:lineRule="auto"/></w:pPr><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
                   '</w:footnotes>')
            self.fn_part = XmlPart(PackURI("/word/footnotes.xml"), CT.WML_FOOTNOTES, parse_xml(xml),
                                   self.d.part.package)
            self.d.part.relate_to(self.fn_part, RT.FOOTNOTES)
        return self.fn_part

    def write_footnote_ref(self, para, fid):
        self.footnote_order.append(fid)
        n = len(self.footnote_order)
        text = self.editor.footnotes.get(fid, "")
        body = "".join(
            f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>'
            + (f'<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:footnoteRef/></w:r>'
               f'<w:r><w:t xml:space="preserve"> </w:t></w:r>' if i == 0 else "")
            + f'<w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:t xml:space="preserve">{_esc(line)}</w:t></w:r></w:p>'
            for i, line in enumerate(text.split("\n") or [""]))
        self.footnote_part().element.append(parse_xml(f'<w:footnote {nsdecls("w")} w:id="{n}">{body}</w:footnote>'))
        r = parse_xml(f'<w:r {nsdecls("w")}><w:rPr><w:vertAlign w:val="superscript"/></w:rPr>'
                      f'<w:footnoteReference w:id="{n}"/></w:r>')
        para._p.append(r)
        return Run(r, para)

    def write_fragment(self, para, frag):
        cf = frag.charFormat()
        fid = cf.property(FOOTNOTE_PROP)
        if fid:
            # Başvuru metni (numara) aynı dipnota ait parçalarda tekrarlanmasın
            if not self.footnote_order or self._last_fn_pos != frag.position():
                self.write_footnote_ref(para, str(fid))
            self._last_fn_pos = frag.position() + frag.length()
            return
        kind = cf.property(TC_TYPE)
        wrapper = None
        if kind in ("ins", "del"):
            wrapper = OxmlElement("w:" + kind)
            wrapper.set(qn("w:id"), str(self.change_id))
            self.change_id += 1
            wrapper.set(qn("w:author"), str(cf.property(TC_AUTHOR) or "OmOffice"))
            date = cf.property(TC_DATE)
            if date:
                wrapper.set(qn("w:date"), str(date) + ("" if str(date).endswith("Z") else "Z"))
            para._p.append(wrapper)
        if cf.isAnchor() and cf.anchorHref():
            href = cf.anchorHref()
            link = OxmlElement("w:hyperlink")
            if href.startswith("#"):
                link.set(qn("w:anchor"), href[1:])
            else:
                link.set(qn("r:id"), para.part.relate_to(href, RT.HYPERLINK, is_external=True))
            (wrapper if wrapper is not None else para._p).append(link)
            wrapper = link
        if cf.isImageFormat():
            run = para.add_run()
            imf = cf.toImageFormat()
            data, img = self.editor.image_bytes(imf.name())
            if data:
                w = imf.width() if imf.width() > 0 else img.width()
                h = imf.height() if imf.height() > 0 else img.height() * (w / max(1, img.width()))
                shape = run.add_picture(io.BytesIO(data), width=Emu(int(w * EMU_PER_PX)),
                                        height=Emu(int(h * EMU_PER_PX)))
                slot = image_slot(imf.name())
                if slot:  # şablon alanı: yeniden açınca "Logo ekle" alanı olarak tanınsın
                    shape._inline.docPr.set("descr", f"OmOffice:{slot}")
            # resim taban çizgisine oturur; alt boşluğu (descent) OmOffice'teki yazı boyutuyla aynı olsun
            f = cf.font().resolve(self.qdoc.defaultFont())
            run.font.size = Pt(1 if self.image_only else _half_pt(f.pointSizeF()))
        else:
            text = frag.text().replace(" ", "\n").replace("￼", "")
            run = para.add_run(text)
            self.format_run(run, cf)
        if wrapper is not None:
            wrapper.append(run._r)
        for cid in str(cf.property(COMMENT_PROP) or "").split(","):
            if cid and cid in self.editor.comments:
                rr = self.comment_runs.setdefault(cid, [run, run])
                rr[1] = run
        if kind == "del":
            for t in run._r.iter(qn("w:t")):
                t.tag = qn("w:delText")

    def format_run(self, run, cf):
        font = run.font
        P = QTextFormat.Property
        if cf.hasProperty(P.FontFamilies):
            fams = cf.fontFamilies()
            if fams:
                font.name = fams[0]
        elif cf.hasProperty(P.FontFamily) and cf.fontFamily():
            font.name = cf.fontFamily()
        if cf.fontPointSize() > 0:
            font.size = Pt(_half_pt(cf.fontPointSize()))
        if cf.hasProperty(P.FontWeight):
            font.bold = cf.fontWeight() >= 600
        if cf.hasProperty(P.FontItalic):
            font.italic = cf.fontItalic()
        if cf.fontUnderline():
            font.underline = True
        if cf.fontStrikeOut():
            font.strike = True
        va = cf.verticalAlignment()
        if va == QTextCharFormat.VerticalAlignment.AlignSuperScript:
            font.superscript = True
        elif va == QTextCharFormat.VerticalAlignment.AlignSubScript:
            font.subscript = True
        if cf.hasProperty(P.FontCapitalization):
            if cf.fontCapitalization() == QFont.Capitalization.AllUppercase:
                font.all_caps = True
            elif cf.fontCapitalization() == QFont.Capitalization.SmallCaps:
                font.small_caps = True
        if cf.hasProperty(P.FontLetterSpacing) and cf.fontLetterSpacingType() == QFont.SpacingType.AbsoluteSpacing \
                and cf.fontLetterSpacing():
            rPr = run._r.get_or_add_rPr()
            rPr.insert_element_before(parse_xml(
                f'<w:spacing {nsdecls("w")} w:val="{int(round(px2pt(cf.fontLetterSpacing()) * 20))}"/>'),
                "w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u", "w:effect", "w:bdr",
                "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang", "w:eastAsianLayout",
                "w:specVanish", "w:oMath")
        if cf.hasProperty(P.ForegroundBrush) and cf.foreground().style() != Qt.BrushStyle.NoBrush:
            c = cf.foreground().color()
            font.color.rgb = RGBColor(c.red(), c.green(), c.blue())
        if cf.hasProperty(P.BackgroundBrush) and cf.background().style() != Qt.BrushStyle.NoBrush:
            c = cf.background().color()
            if c.alpha() > 0:
                h = "#" + _hex(c)
                if h in HIGHLIGHT_ENUM:
                    font.highlight_color = HIGHLIGHT_ENUM[h]
                else:
                    rPr = run._r.get_or_add_rPr()
                    rPr.insert_element_before(parse_xml(
                        f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{_hex(c)}"/>'),
                        *RPR_AFTER_SHD)


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _write_hf(hf, text, align):
    hf.is_linked_to_previous = False
    lines = text.split("\n")
    paras = hf.paragraphs
    for i, line in enumerate(lines):
        p = paras[0] if i == 0 and paras else hf.add_paragraph()
        p.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "right": WD_ALIGN_PARAGRAPH.RIGHT}.get(
            align, WD_ALIGN_PARAGRAPH.CENTER)
        for part in re.split(r"(\{SAYFA\}|\{TOPLAM\})", line):
            if not part:
                continue
            if part in ("{SAYFA}", "{TOPLAM}"):
                instr = " PAGE " if part == "{SAYFA}" else " NUMPAGES "
                p._p.append(parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr="{instr}">'
                                      f'<w:r><w:rPr><w:sz w:val="18"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple>'))
            else:
                r = p.add_run(part)
                r.font.size = Pt(9)


def _add_watermark(hdr, editor, text):
    hdr.is_linked_to_previous = False
    p = hdr.add_paragraph()
    w_pt = px2pt(editor.text_width())
    p._p.append(parse_xml(WATERMARK_XML.format(ns=nsdecls("w") + " " + VML_NS, w=round(w_pt, 1),
                                               h=round(w_pt / max(3, len(text) * 0.6), 1), text=_esc(text))))


def _write_section_hf(section, editor, header, footer):
    """Bir Word bölümüne kendi üst/alt bilgisini yazar ("" = bu bölümde yok; öncekinden devralmaz)."""
    from docx.enum.section import WD_SECTION
    section.start_type = WD_SECTION.CONTINUOUS
    section.different_first_page_header_footer = False
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    if header[0]:
        _write_hf(section.header, *header)
    if footer[0]:
        _write_hf(section.footer, *footer)
    if editor.setup.watermark:
        _add_watermark(section.header, editor, editor.setup.watermark)


def _write_page_sections(d, editor, ex, body_section):
    """Sayfaya özel üst/alt bilgiyi Word bölümlerine çevirir.

    Word'de üst/alt bilgi bölüme bağlıdır ve bir sayfa, tepesindeki bölümün üst/alt bilgisini gösterir.
    Bu yüzden her farklılık başlangıcında, o sayfanın tepesindeki paragraftan hemen önce
    'sürekli' bölüm sonu konur (sayfa düzeni değişmez).
    """
    import copy as _copy
    from docx.section import Section
    st = editor.setup
    total = editor.page_count()
    vals = []
    for n in range(1, total + 1):
        h = st.hf_for("header", n)
        f = st.hf_for("footer", n)
        vals.append(((h[0], h[1] if h[0] else ""), (f[0], f[1] if f[0] else "")))
    segs = []
    for n, v in enumerate(vals, 1):
        if not segs or segs[-1][1] != v:
            segs.append((n, v))
    paras = [(editor.page_of_position(pos), editor.page_of_position(pos + max(0, ln - 2)), para)
             for pos, ln, para in ex.top_paras]
    body_sectPr = body_section._sectPr
    for tag in ("w:headerReference", "w:footerReference", "w:titlePg"):
        for el in body_sectPr.findall(qn(tag)):
            body_sectPr.remove(el)
    used = set()
    breaks = []
    for k in range(1, len(segs)):
        n = segs[k][0]
        idx = next((i for i, (_, ep, _) in enumerate(paras) if ep >= n), None)
        if idx is None or idx == 0 or idx in used:
            continue
        used.add(idx)
        breaks.append((paras[idx - 1][2], segs[k - 1][1]))
    if not breaks:
        segs = [segs[-1]]
    for para, (header, footer) in breaks:
        new = _copy.deepcopy(body_sectPr)
        para._p.get_or_add_pPr().append(new)
        _write_section_hf(Section(new, d.part), editor, header, footer)
    _write_section_hf(body_section, editor, *segs[-1][1])


def _modern_defaults(d):
    """python-docx şablonu Word 2010 uyumluluk modunda ve 'sonra 10 pt, 1,15 satır' varsayılanıyla gelir.
    Word belgeyi güncel yerleşim motoruyla açsın, açıkça yazılmamış aralıklar OmOffice'teki gibi 0 olsun."""
    for cs in d.settings.element.iter(qn("w:compatSetting")):
        if cs.get(qn("w:name")) == "compatibilityMode":
            cs.set(qn("w:val"), "15")
    spacing = d.styles.element.find(f'{qn("w:docDefaults")}/{qn("w:pPrDefault")}/{qn("w:pPr")}/{qn("w:spacing")}')
    if spacing is not None:
        spacing.set(qn("w:after"), "0")
        spacing.set(qn("w:line"), "240")


def export_docx(editor, path):
    qdoc = editor.document()
    s = editor.setup
    d = Document()
    _modern_defaults(d)
    body = d.element.body
    for p in list(body.iterchildren(qn("w:p"))):
        body.remove(p)
    sec = d.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE if s.landscape else WD_ORIENT.PORTRAIT
    sec.page_width = Mm(s.width_mm)
    sec.page_height = Mm(s.height_mm)
    sec.top_margin, sec.bottom_margin = Mm(s.top_mm), Mm(s.bottom_mm)
    sec.left_margin, sec.right_margin = Mm(s.left_mm), Mm(s.right_mm)
    sec.header_distance = sec.footer_distance = Mm(10)
    segmented = s.has_page_overrides()
    if not segmented:
        if s.different_first:
            sec.different_first_page_header_footer = True
        if s.header_text:
            _write_hf(sec.header, s.header_text, s.header_align)
        if s.footer_text:
            _write_hf(sec.footer, s.footer_text, s.footer_align)
    normal = d.styles["Normal"]
    df = qdoc.defaultFont()
    normal.font.name = df.family()
    normal.font.size = Pt(_half_pt(df.pointSizeF() if df.pointSizeF() > 0 else DEFAULT_SIZE))
    if s.watermark and not segmented:
        hdr = sec.header
        hdr.is_linked_to_previous = False
        p = hdr.paragraphs[0] if hdr.paragraphs and not s.header_text else hdr.add_paragraph()
        w_pt = px2pt(editor.text_width())
        p._p.append(parse_xml(WATERMARK_XML.format(ns=nsdecls("w") + " " + VML_NS, w=round(w_pt, 1),
                                                   h=round(w_pt / max(3, len(s.watermark) * 0.6), 1),
                                                   text=_esc(s.watermark))))
        if s.different_first:
            fh = sec.first_page_header
            fp = fh.paragraphs[0] if fh.paragraphs else fh.add_paragraph()
            fp._p.append(parse_xml(WATERMARK_XML.format(ns=nsdecls("w") + " " + VML_NS, w=round(w_pt, 1),
                                                        h=round(w_pt / max(3, len(s.watermark) * 0.6), 1),
                                                        text=_esc(s.watermark))))
    sectPr = sec._sectPr
    if s.page_border:
        sides = "".join(f'<w:{k} w:val="single" w:sz="12" w:space="24" w:color="404040"/>'
                        for k in ("top", "left", "bottom", "right"))
        sectPr.insert_element_before(parse_xml(f'<w:pgBorders {nsdecls("w")} w:offsetFrom="page">{sides}</w:pgBorders>'),
                                     *SECT_AFTER_PGMAR[2:])
    if s.line_numbers:
        sectPr.insert_element_before(parse_xml(f'<w:lnNumType {nsdecls("w")} w:countBy="1" w:restart="continuous"/>'),
                                     *SECT_AFTER_PGMAR[3:])
    if s.page_color:
        d.element.insert(0, parse_xml(f'<w:background {nsdecls("w")} w:color="{s.page_color.lstrip("#").upper()}"/>'))
        settings = d.settings.element
        settings.insert(0, parse_xml(f'<w:displayBackgroundShape {nsdecls("w")}/>'))
    info = getattr(editor, "doc_info", {}) or {}
    cp = d.core_properties
    cp.author = info.get("author") or editor.author
    cp.title = info.get("title", "")
    cp.comments = ""
    if info.get("kind"):
        cp.category = f"OmOffice:{info.get('kind')}|{info.get('citation', '')}"
    cp.last_modified_by = editor.author
    ex = _Exporter(d, editor)
    ex._last_fn_pos = -1
    ex.write_iter(qdoc.rootFrame().begin(), _Sink(d))
    if segmented:
        _write_page_sections(d, editor, ex, sec)
    for cid, (first, last) in ex.comment_runs.items():
        info = editor.comments[cid]
        if info.get("resolved"):
            continue
        author = info.get("author") or "OmOffice"
        initials = "".join(w[:1] for w in author.split()[:2]).upper() or "O"
        d.add_comment([first, last] if first is not last else first, text=info.get("text", ""),
                      author=author, initials=initials)
    d.save(path)


# ================================================================ İÇE AKTARIM
def _on(el):
    if el is None:
        return False
    return el.get(qn("w:val")) not in ("0", "false", "off", "none")


class _Importer:
    def __init__(self, d):
        self.d = d
        self.pending_break = False   # atlanan sayfa sonu paragrafının sayfa sonu sonraki paragrafa
        self.last_table = None       # az önce yazılan tablo (alt boşluğu sonraki paragraftan alınır)
        self.styles = {}
        self.default_para_style = None
        self.default_char_style = None
        for st in d.styles.element.findall(qn("w:style")):
            sid = st.get(qn("w:styleId"))
            self.styles[sid] = st
            if st.get(qn("w:default")) in ("1", "true"):
                if st.get(qn("w:type")) == "paragraph":
                    self.default_para_style = sid
                elif st.get(qn("w:type")) == "character":
                    self.default_char_style = sid
        dd = d.styles.element.find(qn("w:docDefaults"))
        self.default_rpr = dd.find(qn("w:rPrDefault") + "/" + qn("w:rPr")) if dd is not None else None
        self.default_ppr = dd.find(qn("w:pPrDefault") + "/" + qn("w:pPr")) if dd is not None else None
        self.theme = {"minor": DEFAULT_FONT, "major": DEFAULT_FONT}
        self._load_theme()
        self.abstract = {}
        self.nums = {}
        self._load_numbering()
        self.lists = {}
        self.img_count = 0
        self.qdoc = new_document()
        self.active_comments = []
        self.section_ends = []
        self.comments = {}
        self.footnote_texts = {}
        self.footnotes = {}
        self._load_comments()
        self._load_footnotes()

    def _load_theme(self):
        try:
            for rel in self.d.part.rels.values():
                if rel.reltype.endswith("/theme"):
                    root = safe_fromstring(rel.target_part.blob)
                    a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
                    for kind in ("minor", "major"):
                        latin = root.find(f".//{a}{kind}Font/{a}latin")
                        if latin is not None and latin.get("typeface"):
                            self.theme[kind] = latin.get("typeface")
        except Exception as exc:  # bozuk/eksik bölüm işlemi durdurmasın
            log.debug("yok sayılan hata: %s", exc)

    def _load_comments(self):
        try:
            for c in self.d.comments:
                ts = getattr(c, "timestamp", None)
                self.comments[str(c.comment_id)] = {
                    "author": c.author or "", "text": c.text or "", "resolved": False,
                    "date": ts.replace(tzinfo=None).isoformat() if ts else ""}
        except Exception as exc:  # bozuk/eksik bölüm işlemi durdurmasın
            log.debug("yok sayılan hata: %s", exc)

    def _load_footnotes(self):
        try:
            for rel in self.d.part.rels.values():
                if rel.reltype == RT.FOOTNOTES:
                    part = rel.target_part
                    root = part.element if hasattr(part, "element") else safe_fromstring(part.blob)
                    for fn in root.findall(qn("w:footnote")):
                        fid = fn.get(qn("w:id"))
                        if fn.get(qn("w:type")) in ("separator", "continuationSeparator", "continuationNotice"):
                            continue
                        lines = ["".join(t.text or "" for t in p.iter(qn("w:t"))).strip()
                                 for p in fn.findall(qn("w:p"))]
                        self.footnote_texts[fid] = "\n".join(l for l in lines if l)
        except Exception as exc:
            print("Dipnotlar okunamadı:", exc)

    def _load_numbering(self):
        try:
            numel = self.d.part.numbering_part.element
        except Exception:
            return
        for an in numel.findall(qn("w:abstractNum")):
            levels = {}
            for lvl in an.findall(qn("w:lvl")):
                fmt = lvl.find(qn("w:numFmt"))
                levels[int(lvl.get(qn("w:ilvl")))] = fmt.get(qn("w:val")) if fmt is not None else "bullet"
            self.abstract[an.get(qn("w:abstractNumId"))] = levels
        for num in numel.findall(qn("w:num")):
            a = num.find(qn("w:abstractNumId"))
            if a is not None:
                self.nums[num.get(qn("w:numId"))] = a.get(qn("w:val"))

    # ---- stil zinciri
    def style_chain(self, sid):
        out, seen = [], set()
        while sid and sid not in seen and sid in self.styles:
            seen.add(sid)
            st = self.styles[sid]
            out.append(st)
            b = st.find(qn("w:basedOn"))
            sid = b.get(qn("w:val")) if b is not None else None
        return out

    def para_style_id(self, p_el):
        pPr = p_el.find(qn("w:pPr"))
        if pPr is not None:
            ps = pPr.find(qn("w:pStyle"))
            if ps is not None:
                return ps.get(qn("w:val"))
        return self.default_para_style

    @staticmethod
    def _find(chain, tag):
        for el in chain:
            if el is not None:
                c = el.find(qn(tag))
                if c is not None:
                    return c
        return None

    @staticmethod
    def _attr(chain, tag, *attrs):
        for el in chain:
            if el is None:
                continue
            c = el.find(qn(tag))
            if c is None:
                continue
            for a in attrs:
                v = c.get(qn(a))
                if v is not None:
                    return v
        return None

    def char_format(self, r_el, pchain):
        rPr = r_el.find(qn("w:rPr"))
        cid = None
        if rPr is not None:
            rs = rPr.find(qn("w:rStyle"))
            cid = rs.get(qn("w:val")) if rs is not None else None
        chain = [rPr]
        chain += [st.find(qn("w:rPr")) for st in self.style_chain(cid or self.default_char_style)]
        chain += [st.find(qn("w:rPr")) for st in pchain]
        chain.append(self.default_rpr)
        if _on(self._find(chain, "w:vanish")):
            return None
        cf = QTextCharFormat()
        fonts = self._find(chain, "w:rFonts")
        if fonts is not None:
            name = fonts.get(qn("w:ascii")) or fonts.get(qn("w:hAnsi"))
            theme = fonts.get(qn("w:asciiTheme")) or fonts.get(qn("w:hAnsiTheme"))
            if not name and theme:
                name = self.theme["major" if theme.startswith("major") else "minor"]
            if name:
                cf.setFontFamilies([name])
        sz = self._attr(chain, "w:sz", "w:val")
        cf.setFontPointSize(float(sz) / 2 if sz else DEFAULT_SIZE)
        cf.setFontWeight(QFont.Weight.Bold if _on(self._find(chain, "w:b")) else QFont.Weight.Normal)
        cf.setFontItalic(_on(self._find(chain, "w:i")))
        u = self._find(chain, "w:u")
        if u is not None and u.get(qn("w:val")) != "none":
            cf.setFontUnderline(True)
        if _on(self._find(chain, "w:strike")) or _on(self._find(chain, "w:dstrike")):
            cf.setFontStrikeOut(True)
        if _on(self._find(chain, "w:caps")):
            cf.setFontCapitalization(QFont.Capitalization.AllUppercase)
        elif _on(self._find(chain, "w:smallCaps")):
            cf.setFontCapitalization(QFont.Capitalization.SmallCaps)
        sp = self._attr(chain, "w:spacing", "w:val")
        if sp and sp.lstrip("-").isdigit() and int(sp):
            cf.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
            cf.setFontLetterSpacing(twips2px(sp))
        va = self._attr(chain, "w:vertAlign", "w:val")
        if va == "superscript":
            cf.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
        elif va == "subscript":
            cf.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
        color = self._attr(chain, "w:color", "w:val")
        if color and color != "auto" and len(color) == 6:
            cf.setForeground(QColor("#" + color))
        hl = self._attr(chain, "w:highlight", "w:val")
        if hl in HIGHLIGHTS:
            cf.setBackground(QColor(HIGHLIGHTS[hl]))
        else:
            fill = self._attr([rPr], "w:shd", "w:fill")
            if fill and fill != "auto" and len(fill) == 6:
                cf.setBackground(QColor("#" + fill))
        return cf

    # ---- yapı
    def iter_items(self, parent_el, parent_obj):
        for child in parent_el.iterchildren():
            if child.tag == qn("w:p"):
                yield "p", child, Paragraph(child, parent_obj)
            elif child.tag == qn("w:tbl"):
                yield "t", child, Table(child, parent_obj)
            elif child.tag in (qn("w:sdt"), qn("w:customXml")):
                inner = child.find(qn("w:sdtContent")) if child.tag == qn("w:sdt") else child
                if inner is not None:
                    yield from self.iter_items(inner, parent_obj)

    def write_items(self, cursor, items, first):
        fresh = first
        for kind, el, obj in items:
            if kind == "p" and _is_break_para(el):
                self.pending_break = True  # OmOffice'in görünmez sayfa sonu paragrafı: sonrakine geri ver
                continue
            if kind == "p":
                self.write_paragraph(cursor, el, obj, fresh)
                fresh = False
            else:
                self.write_table(cursor, el, obj)
                fresh = True

    def block_format(self, p_el):
        sid = self.para_style_id(p_el)
        pchain = self.style_chain(sid)
        chain = [p_el.find(qn("w:pPr"))] + [st.find(qn("w:pPr")) for st in pchain] + [self.default_ppr]
        bf = QTextBlockFormat()
        jc = self._attr(chain, "w:jc", "w:val")
        bf.setAlignment({"center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight,
                         "end": Qt.AlignmentFlag.AlignRight, "both": Qt.AlignmentFlag.AlignJustify,
                         "distribute": Qt.AlignmentFlag.AlignJustify}.get(jc, Qt.AlignmentFlag.AlignLeft))
        left = self._attr(chain, "w:ind", "w:left", "w:start")
        right = self._attr(chain, "w:ind", "w:right", "w:end")
        first_line = self._attr(chain, "w:ind", "w:firstLine")
        hanging = self._attr(chain, "w:ind", "w:hanging")
        num_el = self._find(chain, "w:numPr")
        is_list = False
        nid = ilvl = None
        if num_el is not None:
            ne = num_el.find(qn("w:numId"))
            le = num_el.find(qn("w:ilvl"))
            nid = ne.get(qn("w:val")) if ne is not None else None
            ilvl = int(le.get(qn("w:val"))) if le is not None else 0
            if nid is None:
                for el in chain:
                    if el is not None and el.find(qn("w:numPr") + "/" + qn("w:numId")) is not None:
                        nid = el.find(qn("w:numPr") + "/" + qn("w:numId")).get(qn("w:val"))
                        break
            is_list = nid not in (None, "0")
        if left and not is_list:
            bf.setLeftMargin(twips2px(left))
        if right:
            bf.setRightMargin(twips2px(right))
        if first_line and not is_list:
            bf.setTextIndent(twips2px(first_line))
        elif hanging and not is_list:
            bf.setTextIndent(-twips2px(hanging))
        before = self._attr(chain, "w:spacing", "w:before")
        after = self._attr(chain, "w:spacing", "w:after")
        bf.setTopMargin(twips2px(before) if before else 0)
        bf.setBottomMargin(twips2px(after) if after else 0)
        line = self._attr(chain, "w:spacing", "w:line")
        rule = self._attr(chain, "w:spacing", "w:lineRule") or "auto"
        if line:
            if rule == "auto":
                bf.setLineHeight(float(line) / 240.0 * 100.0, LH.ProportionalHeight.value)
            elif rule == "exact":
                bf.setLineHeight(twips2px(line), LH.FixedHeight.value)
            else:
                bf.setLineHeight(twips2px(line), LH.MinimumHeight.value)
        if _on(self._find(chain, "w:pageBreakBefore")):
            bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        pbdr = self._find([chain[0]], "w:pBdr")
        bottom = pbdr.find(qn("w:bottom")) if pbdr is not None else None
        if bottom is not None and bottom.get(qn("w:val")) not in ("nil", "none"):
            bf.setProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth,
                           QTextLength(QTextLength.Type.PercentageLength, 100))
            # Word'de çizgi + boşluğu ~2 pt yer kaplar, Qt'nin çizgisi yer kaplamaz
            bf.setBottomMargin(bf.bottomMargin() + pt2px(2))
        fill = self._attr([chain[0]], "w:shd", "w:fill")
        if fill and fill != "auto" and len(fill) == 6:
            bf.setBackground(QColor("#" + fill))
        tabs = self._find([chain[0]] + [st.find(qn("w:pPr")) for st in pchain], "w:tabs")
        if tabs is not None:
            qtabs = []
            for tab in tabs.findall(qn("w:tab")):
                val, pos = tab.get(qn("w:val")), tab.get(qn("w:pos"))
                if pos is None or val == "clear":
                    continue
                tt = {"right": QTextOption.TabType.RightTab, "end": QTextOption.TabType.RightTab,
                      "center": QTextOption.TabType.CenterTab}.get(val, QTextOption.TabType.LeftTab)
                qtabs.append(QTextOption.Tab(twips2px(pos), tt))
            if qtabs:
                bf.setTabPositions(qtabs)
        # stil adı / başlık düzeyi
        style_name = None
        for st in pchain:
            nm = st.find(qn("w:name"))
            if nm is not None:
                key = nm.get(qn("w:val")).lower()
                if key in DOCX_TO_STYLE:
                    style_name = DOCX_TO_STYLE[key]
                    break
                m = re.match(r"(heading|başlık)\s*(\d)", key)
                if m:
                    style_name = f"Başlık {m.group(2)}" if int(m.group(2)) <= 3 else None
                    bf.setHeadingLevel(int(m.group(2)))
                    break
        if style_name:
            bf.setProperty(STYLE_PROP, style_name)
            bf.setHeadingLevel(STYLES[style_name][0])
        outline = self._attr(chain[:1], "w:outlineLvl", "w:val")
        if outline is not None and outline.isdigit() and int(outline) < 9 and not bf.headingLevel():
            bf.setHeadingLevel(int(outline) + 1)
        return bf, pchain, (nid if is_list else None), ilvl

    def list_for(self, nid, ilvl):
        key = (nid, ilvl)
        if key in self.lists:
            return self.lists[key], None
        aid = self.nums.get(nid)
        fmt = self.abstract.get(aid, {}).get(ilvl, "bullet")
        lf = QTextListFormat()
        lf.setStyle(FMT_TO_LIST.get(fmt, BULLET_BY_LEVEL[ilvl % 3]))
        lf.setIndent(ilvl + 1)
        return None, lf

    def write_paragraph(self, cursor, p_el, para, first):
        bf, pchain, nid, ilvl = self.block_format(p_el)
        if self.pending_break:
            bf.setPageBreakPolicy(bf.pageBreakPolicy() | QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
            self.pending_break = False
        if self.last_table is not None and first:
            # boşluk tabloya taşınır (iki tablo arasındaki boş paragrafta Qt onu ayrıca uygular)
            tf = self.last_table.format()
            tf.setBottomMargin(bf.topMargin())
            self.last_table.setFormat(tf)
            bf.setTopMargin(0)
        self.last_table = None
        if first:
            cursor.setBlockFormat(bf)
        else:
            cursor.insertBlock(bf, QTextCharFormat())
        if nid is not None:
            lst, lf = self.list_for(nid, ilvl)
            if lst is not None:
                lst.add(cursor.block())
            else:
                self.lists[(nid, ilvl)] = cursor.createList(lf)
        self.cur_bf = bf
        self.cur_pchain = pchain
        self.write_runs(cursor, p_el, para, pchain, {})
        if p_el.find(qn("w:pPr") + "/" + qn("w:sectPr")) is not None:
            self.section_ends.append(cursor.block().blockNumber())
        if cursor.block().length() <= 1:
            # boş paragraf: paragraf işaretinin yazı tipini kullan
            rpr = p_el.find(qn("w:pPr") + "/" + qn("w:rPr"))
            fake = OxmlElement("w:r")
            if rpr is not None:
                fake.append(etree.fromstring(etree.tostring(rpr)))
            cf = self.char_format(fake, pchain)
            if cf is not None:
                cursor.setBlockCharFormat(cf)
                cursor.setCharFormat(cf)

    def write_runs(self, cursor, el, para, pchain, ctx):
        for child in el.iterchildren():
            tag = child.tag
            if tag == qn("w:r"):
                self.write_run(cursor, child, para, pchain, ctx)
            elif tag == qn("w:hyperlink"):
                href = None
                rid = child.get(qn("r:id"))
                if rid:
                    try:
                        href = para.part.rels[rid].target_ref
                    except Exception:
                        href = None
                if not href and child.get(qn("w:anchor")):
                    href = "#" + child.get(qn("w:anchor"))
                self.write_runs(cursor, child, para, pchain, dict(ctx, href=href))
            elif tag in (qn("w:ins"), qn("w:del"), qn("w:moveTo"), qn("w:moveFrom")):
                kind = "ins" if tag in (qn("w:ins"), qn("w:moveTo")) else "del"
                date = (child.get(qn("w:date")) or "").rstrip("Z")
                self.write_runs(cursor, child, para, pchain,
                                dict(ctx, tc=kind, author=child.get(qn("w:author")) or "", date=date))
            elif tag in (qn("w:smartTag"), qn("w:fldSimple"), qn("w:customXml")):
                self.write_runs(cursor, child, para, pchain, ctx)
            elif tag == qn("w:commentRangeStart"):
                cid = child.get(qn("w:id"))
                if cid in self.comments and cid not in self.active_comments:
                    self.active_comments.append(cid)
            elif tag == qn("w:commentRangeEnd"):
                cid = child.get(qn("w:id"))
                if cid in self.active_comments:
                    self.active_comments.remove(cid)
            elif tag == qn("w:sdt"):
                inner = child.find(qn("w:sdtContent"))
                if inner is not None:
                    self.write_runs(cursor, inner, para, pchain, ctx)

    def _apply_ctx(self, cf, ctx):
        if self.active_comments:
            cf.setProperty(COMMENT_PROP, ",".join(self.active_comments))
        if ctx.get("href"):
            cf.setAnchor(True)
            cf.setAnchorHref(ctx["href"])
        if ctx.get("tc"):
            cf.setProperty(TC_TYPE, ctx["tc"])
            cf.setProperty(TC_AUTHOR, ctx.get("author", ""))
            cf.setProperty(TC_DATE, ctx.get("date", ""))

    def write_run(self, cursor, r_el, para, pchain, ctx):
        cf = self.char_format(r_el, pchain)
        if cf is None:
            return
        self._apply_ctx(cf, ctx)
        buf = []

        def flush():
            if buf:
                cursor.insertText("".join(buf), cf)
                buf.clear()

        for child in r_el.iterchildren():
            tag = child.tag
            if tag in (qn("w:t"), qn("w:delText")):
                buf.append(child.text or "")
            elif tag == qn("w:tab"):
                buf.append("\t")
            elif tag == qn("w:br"):
                if child.get(qn("w:type")) == "page":
                    flush()
                    bf = QTextBlockFormat(self.cur_bf)
                    bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
                    cursor.insertBlock(bf, cf)
                elif child.get(qn("w:type")) != "column":
                    buf.append(" ")
            elif tag == qn("w:cr"):
                buf.append(" ")
            elif tag == qn("w:noBreakHyphen"):
                buf.append("‑")
            elif tag == qn("w:sym"):
                code = int(child.get(qn("w:char"), "20"), 16)
                if code >= 0xF000:
                    code -= 0xF000
                buf.append({0xB7: "•", 0xA7: "▪", 0xD8: "➢", 0xFC: "✓"}.get(code, chr(code)))
            elif tag in (qn("w:drawing"), qn("w:pict"), qn("w:object")):
                flush()
                self.write_image(cursor, child, para, ctx)
            elif tag == qn("w:footnoteReference"):
                flush()
                src = child.get(qn("w:id"))
                fid = str(len(self.footnotes) + 1)
                self.footnotes[fid] = self.footnote_texts.get(src, "")
                ff = QTextCharFormat(cf)
                ff.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
                ff.setProperty(FOOTNOTE_PROP, fid)
                cursor.insertText(fid, ff)
        flush()

    def write_image(self, cursor, el, para, ctx):
        rid, w, h = None, None, None
        for blip in el.iter(qn("a:blip")):
            rid = blip.get(qn("r:embed"))
            break
        for ext in el.iter(qn("wp:extent")):
            w, h = int(ext.get("cx")) / EMU_PER_PX, int(ext.get("cy")) / EMU_PER_PX
            break
        if rid is None:
            for im in el.iter("{urn:schemas-microsoft-com:vml}imagedata"):
                rid = im.get(qn("r:id"))
                shape = im.getparent()
                style = shape.get("style", "") if shape is not None else ""
                mw = re.search(r"width:([\d.]+)pt", style)
                mh = re.search(r"height:([\d.]+)pt", style)
                if mw and mh:
                    w, h = pt2px(float(mw.group(1))), pt2px(float(mh.group(1)))
                break
        if rid is None:
            return
        try:
            rel = para.part.rels[rid]
            if rel.is_external:
                return
            blob = rel.target_part.blob
        except Exception:
            return
        img = QImage.fromData(blob)
        if img.isNull():
            cf = QTextCharFormat()
            cf.setForeground(QColor("#888888"))
            cursor.insertText("[desteklenmeyen resim]", cf)
            return
        self.img_count += 1
        name = f"docx-img-{self.img_count}.png"
        for pr in el.iter(qn("wp:docPr")):
            descr = pr.get("descr") or ""
            if descr.startswith("OmOffice:") and image_slot(f"{IMAGE_SLOT_PREFIX}{descr[9:]}-x"):
                name = f"{IMAGE_SLOT_PREFIX}{descr[9:]}-{self.img_count}.png"
            break
        self.qdoc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
        fmt = QTextImageFormat()
        fmt.setName(name)
        fmt.setWidth(w or img.width())
        fmt.setHeight(h or img.height())
        self._apply_ctx(fmt, ctx)
        cursor.insertImage(fmt)

    def write_table(self, cursor, tbl_el, table):
        trs = tbl_el.findall(qn("w:tr"))
        grid = tbl_el.find(qn("w:tblGrid"))
        gcols = [int(g.get(qn("w:w"), "0") or 0) for g in grid.findall(qn("w:gridCol"))] if grid is not None else []
        recs = []
        ncols = len(gcols)
        for r, tr in enumerate(trs):
            c = 0
            gb = tr.find(qn("w:trPr") + "/" + qn("w:gridBefore"))
            if gb is not None:
                c += int(gb.get(qn("w:val"), "0"))
            for tc in tr.findall(qn("w:tc")):
                tcPr = tc.find(qn("w:tcPr"))
                span, vm = 1, None
                if tcPr is not None:
                    gs = tcPr.find(qn("w:gridSpan"))
                    if gs is not None:
                        span = int(gs.get(qn("w:val"), "1"))
                    v = tcPr.find(qn("w:vMerge"))
                    if v is not None:
                        vm = v.get(qn("w:val")) or "continue"
                recs.append((r, c, span, tc, vm))
                c += span
            ncols = max(ncols, c)
        rows = len(trs)
        if not rows or not ncols:
            return
        tf = QTextTableFormat()
        borders = tbl_el.find(qn("w:tblPr") + "/" + qn("w:tblBorders"))
        no_border = borders is not None and all(
            (b.get(qn("w:val")) in ("nil", "none")) for b in borders)
        szs = [int(b.get(qn("w:sz"))) for b in (borders if borders is not None else [])
               if (b.get(qn("w:sz")) or "").isdigit()]
        tf.setBorder(0 if no_border else max(1.0, round(pt2px(max(szs) / 8))) if szs else 1)
        tf.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        bcol = "#808080"
        if borders is not None and not no_border:
            first = next((b for b in borders if b.get(qn("w:color")) not in (None, "auto")), None)
            if first is not None and len(first.get(qn("w:color"))) == 6:
                bcol = "#" + first.get(qn("w:color"))
        tf.setBorderBrush(QBrush(QColor(bcol)))
        tf.setBorderCollapse(True)
        mar = tbl_el.find(qn("w:tblPr") + "/" + qn("w:tblCellMar") + "/" + qn("w:left"))
        tf.setCellPadding(twips2px(mar.get(qn("w:w"))) if mar is not None and (mar.get(qn("w:w")) or "").isdigit()
                          else 4)
        spacing = tbl_el.find(qn("w:tblPr") + "/" + qn("w:tblCellSpacing"))
        sp_w = spacing.get(qn("w:w")) if spacing is not None else None
        tf.setCellSpacing(twips2px(int(sp_w) * 2) if sp_w and sp_w.isdigit() else 0)  # Word: aralığın yarısı
        tf.setBorderCollapse(tf.cellSpacing() == 0)
        # Qt tablodan hemen önceki paragrafın 'sonra' ve sonraki paragrafın 'önce' boşluğunu yok sayar;
        # bu boşluklar tablonun üst/alt boşluğu olarak taşınır (alt boşluk sonraki paragraf okununca)
        tf.setTopMargin(cursor.blockFormat().bottomMargin())
        tf.setBottomMargin(0)
        pre = cursor.blockFormat()
        pre.setBottomMargin(0)
        cursor.setBlockFormat(pre)
        if gcols and len(gcols) == ncols and all(gcols):
            tf.setColumnWidthConstraints([QTextLength(QTextLength.Type.FixedLength, twips2px(w)) for w in gcols])
        else:
            tf.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        t = cursor.insertTable(rows, ncols, tf)
        starts = {(r, c): (span, tc, vm) for r, c, span, tc, vm in recs}
        for r, c, span, tc, vm in recs:
            if vm == "continue":
                continue
            rs = 1
            while (r + rs, c) in starts and starts[(r + rs, c)][2] == "continue":
                rs += 1
            if rs > 1 or span > 1:
                t.mergeCells(r, c, rs, min(span, ncols - c))
        for r, c, span, tc, vm in recs:
            if vm == "continue" or c >= ncols:
                continue
            cell = t.cellAt(r, c)
            fill = self._attr([tc.find(qn("w:tcPr"))], "w:shd", "w:fill")
            if fill and fill != "auto" and len(fill) == 6:
                f = cell.format().toTableCellFormat()
                f.setBackground(QColor("#" + fill))
                cell.setFormat(f)
            cc = cell.firstCursorPosition()
            self.write_items(cc, self.iter_items(tc, _Cell(tc, table)), True)
        cursor.setPosition(t.lastPosition() + 1)
        self.last_table = t

    # ---- üst/alt bilgi
    def hf_text(self, hf):
        lines, align = [], None
        for p_el in hf._element.iter(qn("w:p")):
            parts, state, token = [], None, None
            for el in p_el.iter():
                tag = el.tag
                if tag == qn("w:fldSimple"):
                    instr = (el.get(qn("w:instr")) or "").upper()
                    tok = "{TOPLAM}" if "NUMPAGES" in instr else "{SAYFA}" if "PAGE" in instr else None
                    if tok:
                        parts.append(tok)
                        el.set("_omoffice_token", "1")
                elif tag == qn("w:fldChar"):
                    ft = el.get(qn("w:fldCharType"))
                    if ft == "begin":
                        state, token = "instr", ""
                    elif ft == "separate":
                        up = token.upper()
                        tok = "{TOPLAM}" if "NUMPAGES" in up else "{SAYFA}" if " PAGE" in " " + up else None
                        if tok:
                            parts.append(tok)
                            state = "skip"
                        else:
                            state = "result"
                    elif ft == "end":
                        state = None
                elif tag == qn("w:instrText"):
                    if state == "instr":
                        token += el.text or ""
                elif tag == qn("w:t"):
                    if state in ("skip", "instr") or any(
                            a.get("_omoffice_token") for a in el.iterancestors(qn("w:fldSimple"))):
                        continue
                    parts.append(el.text or "")
                elif tag == qn("w:tab"):
                    parts.append("\t")
            line = "".join(parts)
            if line.strip() and align is None:
                jc = p_el.find(qn("w:pPr") + "/" + qn("w:jc"))
                frame = p_el.find(qn("w:pPr") + "/" + qn("w:framePr"))
                v = jc.get(qn("w:val")) if jc is not None else "left"
                if frame is not None and frame.get(qn("w:xAlign")):
                    v = frame.get(qn("w:xAlign"))
                align = {"center": "center", "right": "right", "end": "right"}.get(v, "left")
            lines.append(line)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines).strip("\n"), align or "center"

    def _fit_line_heights(self, setup):
        """Word'ün 'katlı' satır aralığını Qt yüzdesine çevirir (dışa aktarmadaki dönüşümün tersi),
        böylece satırlar OmOffice'te Word'deki adımla dizilir ve kaydet-aç döngüsünde kayma olmaz."""
        default = self.qdoc.defaultFont()
        # satır sayıları için sayfa genişliğinde yerleştir (editör sonra kendi sayfa boyutunu verir)
        self.qdoc.setTextWidth(pt2px((setup.width_mm - setup.left_mm - setup.right_mm) * 72 / 25.4))
        lay = self.qdoc.documentLayout()
        block = self.qdoc.begin()
        while block.isValid():
            lay.blockBoundingRect(block)
            bf = block.blockFormat()
            lht = bf.lineHeightType()
            image_only = bool(block.text()) and not block.text().replace("￼", "")
            if lht in (LH.ProportionalHeight.value, LH.SingleHeight.value) and not image_only:
                pct = bf.lineHeight() if lht == LH.ProportionalHeight.value else 100.0
                nf = QTextBlockFormat()
                nf.setLineHeight(round(pct / _line_ratio(block, default), 2), LH.ProportionalHeight.value)
                QTextCursor(block).mergeBlockFormat(nf)
            block = block.next()

    def run(self):
        d = self.d
        setup = PageSetup()
        sec = d.sections[0] if len(d.sections) else None
        if sec is not None:
            def mm(v, default):
                return v.mm if v is not None else default
            setup.width_mm = mm(sec.page_width, 210.0)
            setup.height_mm = mm(sec.page_height, 297.0)
            setup.top_mm = abs(mm(sec.top_margin, 25.0))
            setup.bottom_mm = abs(mm(sec.bottom_margin, 25.0))
            setup.left_mm = mm(sec.left_margin, 25.0)
            setup.right_mm = mm(sec.right_margin, 25.0)
            try:
                for el in sec.header._element.iter("{urn:schemas-microsoft-com:vml}textpath"):
                    if el.get("string"):
                        setup.watermark = el.get("string")
                        break
            except Exception as exc:  # bozuk/eksik bölüm işlemi durdurmasın
                log.debug("yok sayılan hata: %s", exc)
            sp = sec._sectPr
            setup.page_border = sp.find(qn("w:pgBorders")) is not None
            setup.line_numbers = sp.find(qn("w:lnNumType")) is not None
            bg = d.element.find(qn("w:background"))
            if bg is not None and bg.get(qn("w:color")) not in (None, "auto", "FFFFFF"):
                setup.page_color = "#" + bg.get(qn("w:color"))
            try:
                setup.different_first = bool(sec.different_first_page_header_footer)
                setup.header_text, setup.header_align = self.hf_text(sec.header)
                setup.footer_text, setup.footer_align = self.hf_text(sec.footer)
            except Exception as exc:  # bozuk/eksik bölüm işlemi durdurmasın
                log.debug("yok sayılan hata: %s", exc)
        # varsayılan yazı tipi
        fake = OxmlElement("w:r")
        cf = self.char_format(fake, self.style_chain(self.default_para_style))
        if cf is not None:
            fams = cf.fontFamilies() or [DEFAULT_FONT]
            f = QFont(fams[0])
            f.setPointSizeF(cf.fontPointSize() or DEFAULT_SIZE)
            self.qdoc.setDefaultFont(f)
        cursor = QTextCursor(self.qdoc)
        self.write_items(cursor, self.iter_items(d.element.body, d._body), True)
        self._fit_line_heights(setup)
        self.qdoc.setModified(False)
        self.qdoc.clearUndoRedoStacks()
        info = {}
        try:
            cp = d.core_properties
            cat = cp.category or ""
            if cat.startswith(("OmOffice:", "Kalem:")):  # "Kalem:" programın eski adıyla kaydedilmiş belgeler
                kind, _, cite = cat.partition(":")[2].partition("|")
                info = {"kind": kind, "citation": cite}
            info["title"] = cp.title or ""
            info["author"] = cp.author or ""
        except Exception as exc:  # bozuk/eksik bölüm işlemi durdurmasın
            log.debug("yok sayılan hata: %s", exc)
        meta = {"comments": self.comments, "footnotes": self.footnotes, "info": info}
        if self.section_ends and len(d.sections) == len(self.section_ends) + 1:
            secs = []
            for section, end in zip(d.sections, self.section_ends + [None]):
                try:
                    item = {"end_block": end, "header": self.hf_text(section.header),
                            "footer": self.hf_text(section.footer),
                            "title_pg": bool(section.different_first_page_header_footer)}
                    if item["title_pg"]:
                        item["first_header"] = self.hf_text(section.first_page_header)
                        item["first_footer"] = self.hf_text(section.first_page_footer)
                    secs.append(item)
                except Exception as exc:  # bozuk bölüm: tek tip üst/alt bilgiyle devam
                    log.debug("bölüm okunamadı: %s", exc)
                    secs = []
                    break
            if len({(x["header"], x["footer"], x["title_pg"]) for x in secs}) > 1 or \
                    any(x["title_pg"] for x in secs[1:]):
                meta["sections"] = secs
        return self.qdoc, setup, meta


def import_docx(path):
    stream, warnings = open_word_package(path)
    doc, setup, meta = _Importer(Document(stream)).run()
    meta["warnings"] = warnings
    return doc, setup, meta
