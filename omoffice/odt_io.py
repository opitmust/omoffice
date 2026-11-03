"""OpenDocument metni (.odt) içe aktarma: paragraf, başlık, liste, tablo, temel biçimler, resim."""
import re
import zipfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QColor, QFont, QImage, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextImageFormat,
    QTextLength, QTextListFormat, QTextTableFormat, QTextFrameFormat, QBrush,
)

from .common import PageSetup, STYLES, STYLE_PROP, pt2px, DEFAULT_SIZE
from .editor import new_document
from .safety import check_zip, safe_fromstring

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
}


def q(tag):
    p, t = tag.split(":")
    return f"{{{NS[p]}}}{t}"


def _length_mm(v):
    m = re.match(r"([\d.]+)\s*(cm|mm|in|pt)?", v or "")
    if not m:
        return None
    n = float(m.group(1))
    return {"cm": n * 10, "mm": n, "in": n * 25.4, "pt": n * 25.4 / 72}.get(m.group(2) or "cm", n)


class _Styles:
    def __init__(self, *roots):
        self.s = {}
        for root in roots:
            if root is None:
                continue
            for st in root.iter(q("style:style")):
                self.s[st.get(q("style:name"))] = st

    def props(self, name):
        """Stil zincirindeki metin/paragraf özellikleri (alt stil üstün)."""
        chain, seen = [], set()
        while name and name in self.s and name not in seen:
            seen.add(name)
            st = self.s[name]
            chain.append(st)
            name = st.get(q("style:parent-style-name"))
        tp, pp = {}, {}
        for st in reversed(chain):
            for el in st.findall(q("style:text-properties")):
                tp.update({k.split("}")[1]: v for k, v in el.attrib.items()})
            for el in st.findall(q("style:paragraph-properties")):
                pp.update({k.split("}")[1]: v for k, v in el.attrib.items()})
        return tp, pp, [c.get(q("style:name")) for c in chain]


def _char(tp, base=None):
    cf = QTextCharFormat(base) if base is not None else QTextCharFormat()
    if tp.get("font-weight") in ("bold", "600", "700", "800", "900"):
        cf.setFontWeight(QFont.Weight.Bold)
    if tp.get("font-style") == "italic":
        cf.setFontItalic(True)
    if tp.get("text-underline-style") not in (None, "none"):
        cf.setFontUnderline(True)
    if tp.get("text-line-through-style") not in (None, "none"):
        cf.setFontStrikeOut(True)
    if tp.get("font-size", "").endswith("pt"):
        cf.setFontPointSize(float(tp["font-size"][:-2]))
    if tp.get("color", "").startswith("#"):
        cf.setForeground(QColor(tp["color"]))
    if tp.get("background-color", "").startswith("#"):
        cf.setBackground(QColor(tp["background-color"]))
    if tp.get("font-name"):
        cf.setFontFamilies([tp["font-name"]])
    pos = tp.get("text-position", "")
    if pos.startswith("super") or pos.startswith("33%"):
        cf.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSuperScript)
    elif pos.startswith("sub") or pos.startswith("-33%"):
        cf.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignSubScript)
    return cf


class _OdtReader:
    def __init__(self, z, content, styles_root):
        self.z = z
        self.st = _Styles(styles_root, content)
        self.doc = new_document()
        self.cur = QTextCursor(self.doc)
        self.first = True
        self.img = 0

    def new_block(self, bf, cf):
        if self.first:
            self.cur.setBlockFormat(bf)
            self.cur.setBlockCharFormat(cf)
            self.first = False
        else:
            self.cur.insertBlock(bf, cf)

    def para(self, el, heading=0):
        tp, pp, names = self.st.props(el.get(q("text:style-name")))
        bf = QTextBlockFormat()
        bf.setBottomMargin(pt2px(6))
        al = pp.get("text-align")
        bf.setAlignment({"center": Qt.AlignmentFlag.AlignHCenter, "end": Qt.AlignmentFlag.AlignRight,
                         "right": Qt.AlignmentFlag.AlignRight, "justify": Qt.AlignmentFlag.AlignJustify}
                        .get(al, Qt.AlignmentFlag.AlignLeft))
        if pp.get("break-before") == "page":
            bf.setPageBreakPolicy(QTextBlockFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        cf = _char(tp)
        if heading:
            name = "Konu Başlığı" if any(n and n.lower() == "title" for n in names) else f"Başlık {min(3, heading)}"
            lvl, size, bold, italic, color, _ = STYLES[name]
            bf.setHeadingLevel(lvl)
            bf.setProperty(STYLE_PROP, name)
            bf.setTopMargin(pt2px(10))
            cf.setFontPointSize(size or DEFAULT_SIZE)
            cf.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
            if color:
                cf.setForeground(QColor(color))
        else:
            bf.setProperty(STYLE_PROP, "Normal")
        self.new_block(bf, cf)
        self.inline(el, cf)
        return self.cur.block()

    def inline(self, el, cf):
        if el.text:
            self.cur.insertText(el.text, cf)
        for ch in el:
            tag = ch.tag
            if tag == q("text:span"):
                tp, _, _ = self.st.props(ch.get(q("text:style-name")))
                self.inline(ch, _char(tp, cf))
            elif tag == q("text:a"):
                f = QTextCharFormat(cf)
                href = ch.get(q("xlink:href")) or ""
                if href:
                    f.setAnchor(True)
                    f.setAnchorHref(href)
                    f.setForeground(QColor("#0563C1"))
                    f.setFontUnderline(True)
                self.inline(ch, f)
            elif tag == q("text:s"):
                self.cur.insertText(" " * int(ch.get(q("text:c"), "1")), cf)
            elif tag == q("text:tab"):
                self.cur.insertText("\t", cf)
            elif tag == q("text:line-break"):
                self.cur.insertText(" ", cf)
            elif tag == q("draw:frame"):
                self.image(ch)
            elif tag in (q("text:note"),):
                pass
            else:
                self.inline(ch, cf)
            if ch.tail:
                self.cur.insertText(ch.tail, cf)

    def image(self, frame):
        im = frame.find(q("draw:image"))
        if im is None:
            return
        href = im.get(q("xlink:href")) or ""
        if href.startswith(("http", "/", "\\")) or ".." in href:
            return  # dış/uzak resimler yüklenmez
        try:
            data = self.z.read(href)
        except KeyError:
            return
        img = QImage.fromData(data)
        if img.isNull():
            return
        self.img += 1
        name = f"odt-img-{self.img}.png"
        self.doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
        fmt = QTextImageFormat()
        fmt.setName(name)
        w = _length_mm(frame.get(q("svg:width")))
        h = _length_mm(frame.get(q("svg:height")))
        fmt.setWidth(w * 96 / 25.4 if w else img.width())
        fmt.setHeight(h * 96 / 25.4 if h else img.height())
        self.cur.insertImage(fmt)

    def lst(self, el, level=1, numbered=None):
        style_name = el.get(q("text:style-name")) or ""
        if numbered is None:
            numbered = self._is_numbered(style_name)
        qlist = None
        for item in el.findall(q("text:list-item")):
            for ch in item:
                if ch.tag in (q("text:p"), q("text:h")):
                    self.para(ch)
                    if qlist is None:
                        lf = QTextListFormat()
                        lf.setStyle(QTextListFormat.Style.ListDecimal if numbered else
                                    [QTextListFormat.Style.ListDisc, QTextListFormat.Style.ListCircle,
                                     QTextListFormat.Style.ListSquare][(level - 1) % 3])
                        lf.setIndent(level)
                        qlist = self.cur.createList(lf)
                    else:
                        qlist.add(self.cur.block())
                elif ch.tag == q("text:list"):
                    self.lst(ch, level + 1, numbered)

    def _is_numbered(self, name):
        for root in (self.content_root,):
            for ls in root.iter(q("text:list-style")):
                if ls.get(q("style:name")) == name:
                    return ls.find(q("text:list-level-style-number")) is not None
        return False

    def table(self, el):
        rows = el.findall(".//" + q("table:table-row"))
        if not rows:
            return
        ncols = max(sum(int(c.get(q("table:number-columns-spanned"), "1"))
                        for c in r.findall(q("table:table-cell")) + r.findall(q("table:covered-table-cell")))
                    for r in rows)
        tf = QTextTableFormat()
        tf.setBorder(1)
        tf.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
        tf.setBorderBrush(QBrush(QColor("#808080")))
        tf.setBorderCollapse(True)
        tf.setCellPadding(4)
        tf.setCellSpacing(0)
        tf.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        if self.first:
            self.first = False
        t = self.cur.insertTable(len(rows), max(1, ncols), tf)
        for r, row in enumerate(rows):
            c = 0
            for cell in row:
                if cell.tag == q("table:covered-table-cell"):
                    c += 1
                    continue
                if cell.tag != q("table:table-cell"):
                    continue
                span_c = int(cell.get(q("table:number-columns-spanned"), "1"))
                span_r = int(cell.get(q("table:number-rows-spanned"), "1"))
                if span_c > 1 or span_r > 1:
                    t.mergeCells(r, c, span_r, span_c)
                saved, saved_first = self.cur, self.first
                self.cur = t.cellAt(r, c).firstCursorPosition()
                self.first = True
                for p in cell:
                    self.block_el(p)
                self.cur, self.first = saved, saved_first
                c += span_c
        self.cur.setPosition(t.lastPosition() + 1)
        self.first = True

    def block_el(self, el):
        tag = el.tag
        if tag == q("text:p"):
            self.para(el)
        elif tag == q("text:h"):
            self.para(el, heading=int(el.get(q("text:outline-level"), "1")))
        elif tag == q("text:list"):
            self.lst(el)
        elif tag == q("table:table"):
            self.table(el)
        elif tag in (q("text:section"), q("text:table-of-content"), q("text:index-body")):
            for ch in el:
                self.block_el(ch)


def import_odt(path):
    warnings = check_zip(path)
    with zipfile.ZipFile(path) as z:
        try:
            content = safe_fromstring(z.read("content.xml"))
        except KeyError:
            raise ValueError("Geçerli bir OpenDocument metni değil (content.xml yok).")
        try:
            styles_root = safe_fromstring(z.read("styles.xml"))
        except KeyError:
            styles_root = None
        r = _OdtReader(z, content, styles_root)
        r.content_root = content
        body = content.find(q("office:body"))
        text = body.find(q("office:text")) if body is not None else None
        if text is None:
            raise ValueError("Bu OpenDocument dosyası metin belgesi değil.")
        for el in text:
            r.block_el(el)
    setup = PageSetup()
    if styles_root is not None:
        pl = next(styles_root.iter(q("style:page-layout-properties")), None)
        if pl is not None:
            for attr, field in (("page-width", "width_mm"), ("page-height", "height_mm"),
                                ("margin-top", "top_mm"), ("margin-bottom", "bottom_mm"),
                                ("margin-left", "left_mm"), ("margin-right", "right_mm")):
                v = _length_mm(pl.get(q("fo:" + attr)))
                if v:
                    setattr(setup, field, v)
    r.doc.setModified(False)
    r.doc.clearUndoRedoStacks()
    return r.doc, setup, {"warnings": warnings}
