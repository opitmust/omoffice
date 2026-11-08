"""PDF içe aktarma: metni paragraflar hâlinde, yazı tipi / punto / kalın / italik / renk korunarak alır.

PDF bir "çizim" biçimidir; Word'deki gibi paragraf yapısı yoktur. pdfminer.six ile harfler
satırlara ve metin kutularına gruplanır, her kutu bir paragraf olur. Görseller ve metni
çıkarılamayan (taranmış / gömülü yazı tipi eşlemesi olmayan) sayfalar QtPdf ile resim olarak
çizilip belgeye eklenir; böylece hiçbir zaman bozuk karakter gösterilmez.
"""
import os
import re
from collections import Counter

from PySide6.QtCore import QSize, QUrl, Qt
from PySide6.QtGui import (
    QColor, QFontDatabase, QImage, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextFormat, QTextImageFormat,
)

from .common import DEFAULT_FONT, PageSetup, STYLE_PROP, pt2px
from .editor import new_document

MAX_BYTES = 200 * 1024 * 1024
MAX_PAGES = 1000
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
             "ﬅ": "st", "ﬆ": "st", "­": ""}
PT_MM = 25.4 / 72.0


class PdfImportError(ValueError):
    pass


# ---------------------------------------------------------------- yazı tipi

_families = None


def _family(fontname):
    """'ABCDEF+TimesNewRomanPS-BoldMT' -> ('Times New Roman', kalın, italik)."""
    global _families
    if _families is None:
        _families = {re.sub(r"[^a-z0-9]", "", f.lower()): f for f in QFontDatabase.families()}
    name = (fontname or "").split("+", 1)[-1]
    low = name.lower()
    bold = bool(re.search(r"bold|black|heavy|semibold|demi|,b$|-b$", low))
    italic = bool(re.search(r"italic|oblique|,i$|-i$|-it$", low))
    base = re.split(r"[-,]", name, 1)[0]
    base = re.sub(r"(PS)?(MT|PSMT|Std|Pro|LT)$", "", base)
    key = re.sub(r"[^a-z0-9]", "", base.lower())
    for k in (key, re.sub(r"(regular|roman|book|medium)$", "", key)):
        if k in _families:
            return _families[k], bold, italic
    aliases = {"arialmt": "Arial", "helvetica": "Arial", "helv": "Arial", "times": "Times New Roman",
               "timesroman": "Times New Roman", "timesnewroman": "Times New Roman",
               "courier": "Courier New", "symbol": "Symbol", "zapfdingbats": "Wingdings"}
    for k, fam in aliases.items():
        if key.startswith(k) and fam.lower().replace(" ", "") in _families:
            return _families[fam.lower().replace(" ", "")], bold, italic
    return DEFAULT_FONT, bold, italic


def _color(gs):
    try:
        c = gs.ncolor
    except AttributeError:
        return None
    if c is None:
        return None
    if isinstance(c, (int, float)):
        c = (c,)
    try:
        c = [float(v) for v in c]
    except (TypeError, ValueError):
        return None
    if len(c) == 1:
        v = int(max(0.0, min(1.0, c[0])) * 255)
        rgb = (v, v, v)
    elif len(c) == 3:
        rgb = tuple(int(max(0.0, min(1.0, v)) * 255) for v in c)
    elif len(c) == 4:
        cc, m, y, k = (max(0.0, min(1.0, v)) for v in c)
        rgb = tuple(int(255 * (1 - x) * (1 - k)) for x in (cc, m, y))
    else:
        return None
    if max(rgb) < 40:      # neredeyse siyah -> otomatik renk bırak
        return None
    return QColor(*rgb)


def _clean(s):
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return s


# ---------------------------------------------------------------- PDF okuma

def _layout_items(page):
    """Sayfadaki metin kutuları ve görselleri okuma sırasıyla döndürür."""
    from pdfminer.layout import LTFigure, LTImage, LTTextBox, LTTextLine

    items = []

    def images_in(obj):
        if isinstance(obj, LTImage):
            return [obj]
        if isinstance(obj, LTFigure):
            return [i for ch in obj for i in images_in(ch)]
        return []

    for obj in page:
        if isinstance(obj, (LTTextBox, LTTextLine)):
            if obj.get_text().strip():      # yalnız boşluktan oluşan kutular boş satır yığını yapar
                items.append(("text", obj if isinstance(obj, LTTextBox) else [obj]))
        elif isinstance(obj, (LTImage, LTFigure)):
            imgs = images_in(obj)
            if imgs and obj.width > 12 and obj.height > 12:
                items.append(("image", obj))
            elif isinstance(obj, LTFigure):
                # Form XObject içinde metin olabilir
                for ch in obj:
                    if isinstance(ch, LTTextBox) and ch.get_text().strip():
                        items.append(("text", ch))
    if not _two_columns(items, page.width):
        # Tek sütunlu sayfa: yukarıdan aşağıya sırala (pdfminer bazen sağa yaslı kutuyu öne alır)
        items.sort(key=lambda it: (-round(_bbox(it[1])[3] / 3), _bbox(it[1])[0]))
    return items


def _bbox(obj):
    return obj.bbox if hasattr(obj, "bbox") else obj[0].bbox


def _two_columns(items, width):
    """Sayfanın sol ve sağ yarısında, ortayı geçmeyen çok satırlı metin kutuları varsa iki sütun say."""
    left = right = 0
    for kind, obj in items:
        if kind != "text":
            continue
        x0, y0, x1, y1 = _bbox(obj)
        if y1 - y0 < 40:
            continue
        if x1 < width * 0.55:
            left += 1
        elif x0 > width * 0.45:
            right += 1
    return left >= 2 and right >= 2


def _lines(box):
    from pdfminer.layout import LTChar, LTTextLine
    out = []
    for line in box:
        if not isinstance(line, LTTextLine):
            continue
        chars = []
        for ch in line:
            if isinstance(ch, LTChar):
                chars.append((ch.get_text(), ch))
            else:   # LTAnno: pdfminer'in eklediği boşluk / satır sonu
                t = ch.get_text()
                if t and t != "\n":
                    chars.append((t, None))
        if chars:
            out.append((line, chars))
    return out


def _bad_text(text):
    """Yazı tipinde Unicode eşlemesi yoksa pdfminer '(cid:12)' ya da özel alan karakterleri üretir."""
    if not text.strip():
        return False
    cid = len(re.findall(r"\(cid:\d+\)", text))
    pua = sum(1 for c in text if 0xE000 <= ord(c) <= 0xF8FF or c == "�")
    ctrl = sum(1 for c in text if ord(c) < 32 and c not in "\n\t")
    n = max(1, len(text))
    return cid * 6 / n > 0.15 or (pua + ctrl) / n > 0.15


class _Renderer:
    """QtPdf ile sayfayı ya da bir bölgesini resim olarak çizer."""

    def __init__(self, path):
        self.doc = None
        try:
            from PySide6.QtPdf import QPdfDocument
            d = QPdfDocument()
            d.load(path)
            if d.status() == QPdfDocument.Status.Ready:
                self.doc = d
        except Exception:
            self.doc = None
        self.cache = {}

    def page(self, idx, w_pt, h_pt, scale=2.0):
        if self.doc is None:
            return None
        if idx not in self.cache:
            img = self.doc.render(idx, QSize(int(w_pt * scale), int(h_pt * scale)))
            self.cache = {idx: img}          # tek sayfa tut, bellek şişmesin
        img = self.cache[idx]
        return None if img is None or img.isNull() else img

    def crop(self, idx, w_pt, h_pt, bbox):
        img = self.page(idx, w_pt, h_pt)
        if img is None:
            return None
        sx, sy = img.width() / w_pt, img.height() / h_pt
        x0, y0, x1, y1 = bbox
        r = (int(max(0, x0) * sx), int(max(0, h_pt - y1) * sy),
             int((min(w_pt, x1) - max(0, x0)) * sx), int((min(h_pt, y1) - max(0, y0)) * sy))
        if r[2] < 4 or r[3] < 4:
            return None
        return img.copy(*r)


class _Writer:
    def __init__(self):
        self.doc = new_document()
        self.cur = QTextCursor(self.doc)
        self.first = True
        self.img = 0
        self.pages = []
        base = QTextCharFormat(self.cur.charFormat())
        self.base_cf = base

    def block(self, page_break=False, top_px=0.0, align=None, indent_px=0.0, first_px=0.0):
        bf = QTextBlockFormat()
        bf.setProperty(STYLE_PROP, "Normal")
        bf.setLineHeight(100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        bf.setTopMargin(max(0.0, top_px))
        bf.setBottomMargin(0)
        if indent_px > 1:
            bf.setLeftMargin(indent_px)
        if abs(first_px) > 1:
            bf.setTextIndent(first_px)
        if align is not None:
            bf.setAlignment(align)
        if page_break and not self.first:
            bf.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        if self.first:
            self.cur.setBlockFormat(bf)
            self.first = False
        else:
            self.cur.insertBlock(bf, self.base_cf)
        if page_break or not self.pages:
            self.pages.append([])
        self.pages[-1].append(self.cur.block().blockNumber())

    def fit_pages(self, text_w_px, text_h_px):
        """Her PDF sayfası tek sayfaya sığsın: taşan sayfada paragraflar arası boşlukları küçült."""
        doc = self.doc
        doc.setTextWidth(text_w_px)
        lay = doc.documentLayout()
        for nums in self.pages:
            blocks = [doc.findBlockByNumber(n) for n in nums]
            # sayfanın son paragrafından sonraki (resim vb.) blokları da say
            last = blocks[-1].next()
            while last.isValid() and last.blockNumber() not in self._starts():
                blocks.append(last)
                last = last.next()
            for _ in range(3):
                gaps = sum(b.blockFormat().topMargin() for b in blocks)
                total = gaps + sum(lay.blockBoundingRect(b).height() for b in blocks)
                excess = total - text_h_px + 6
                if excess <= 0 or gaps <= 0:
                    break
                f = max(0.0, (gaps - excess) / gaps)
                for b in blocks:
                    bf = b.blockFormat()
                    if bf.topMargin() > 0:
                        bf.setTopMargin(bf.topMargin() * f)
                        QTextCursor(b).setBlockFormat(bf)
            # boşluklar bitti ama hâlâ taşıyor: satır aralığını sıkılaştır (en az %80)
            lh = 100.0
            for _ in range(3):
                gaps = sum(b.blockFormat().topMargin() for b in blocks)
                total = gaps + sum(lay.blockBoundingRect(b).height() for b in blocks)
                if total <= text_h_px - 6 or lh <= 80.0:
                    break
                lh = max(80.0, lh * (text_h_px - 6 - gaps) / max(1.0, total - gaps))
                for b in blocks:
                    bf = b.blockFormat()
                    bf.setLineHeight(lh, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                    QTextCursor(b).setBlockFormat(bf)
        doc.setTextWidth(-1)

    def _starts(self):
        if not hasattr(self, "_start_set"):
            self._start_set = {p[0] for p in self.pages}
        return self._start_set

    def text(self, s, cf):
        self.cur.insertText(s, cf)

    def image(self, img, w_pt, h_pt, max_w_px):
        self.img += 1
        name = f"pdf-img-{self.img}.png"
        self.doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
        fmt = QTextImageFormat()
        fmt.setName(name)
        w, h = pt2px(w_pt), pt2px(h_pt)
        if w > max_w_px:
            h, w = h * max_w_px / w, max_w_px
        fmt.setWidth(w)
        fmt.setHeight(h)
        self.cur.insertImage(fmt)


def import_pdf(path, password=""):
    try:
        from pdfminer.layout import LAParams
        from pdfminer.pdfdocument import PDFDocument, PDFPasswordIncorrect
        from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
        from pdfminer.converter import PDFPageAggregator
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdfparser import PDFParser
        from pdfminer.pdfdocument import PDFEncryptionError
    except ImportError as exc:
        raise PdfImportError("PDF desteği için 'pdfminer.six' paketi gerekli.") from exc

    if os.path.getsize(path) > MAX_BYTES:
        raise PdfImportError("PDF dosyası çok büyük (200 MB üstü).")
    with open(path, "rb") as f:
        if b"%PDF" not in f.read(1024):
            raise PdfImportError("Bu dosya geçerli bir PDF değil.")

    warnings = []
    renderer = _Renderer(path)
    w = _Writer()
    setup = PageSetup()
    laparams = LAParams(line_margin=0.5, char_margin=2.0, word_margin=0.1, boxes_flow=0.5)

    with open(path, "rb") as fp:
        parser = PDFParser(fp)
        try:
            pdoc = PDFDocument(parser, password)
        except PDFPasswordIncorrect:
            raise PdfImportError("Bu PDF parolayla korunuyor.")
        except PDFEncryptionError as exc:
            raise PdfImportError(f"Bu PDF'in şifrelemesi desteklenmiyor: {exc}")
        if not pdoc.is_extractable:
            warnings.append("PDF sahibi metin kopyalamayı kısıtlamış; yine de içe aktarıldı.")
        rsrc = PDFResourceManager(caching=True)
        dev = PDFPageAggregator(rsrc, laparams=laparams)
        interp = PDFPageInterpreter(rsrc, dev)

        pages_done = 0
        image_pages = 0
        lost_images = 0
        sizes = Counter()
        layouts = []
        for idx, page in enumerate(PDFPage.create_pages(pdoc)):
            if idx >= MAX_PAGES:
                warnings.append(f"Yalnızca ilk {MAX_PAGES} sayfa aktarıldı.")
                break
            interp.process_page(page)
            lt = dev.get_result()
            layouts.append((idx, lt, _layout_items(lt)))
            for kind, obj in layouts[-1][2]:
                if kind == "text":
                    for _line, chars in _lines(obj):
                        for t, ch in chars:
                            if ch is not None and t.strip():
                                sizes[round(ch.size * 2) / 2] += 1

        body = sizes.most_common(1)[0][0] if sizes else 11.0

        # Sayfa boyutu ve kenar boşlukları ilk sayfadan
        if layouts:
            lt = layouts[0][1]
            setup.width_mm = round(lt.width * PT_MM, 1)
            setup.height_mm = round(lt.height * PT_MM, 1)
            same = [(pl, its) for _i, pl, its in layouts if abs(pl.width - lt.width) < 2]
            lines = [ln.bbox for _pl, its in same for k, o in its if k == "text"
                     for ln, _c in _lines(o)]
            if lines:
                # Tek bir aykırı satır kenar boşluğunu bozmasın: en sık satır başı = sol kenar,
                # geniş satırların en sık bitişi = sağ kenar, sayfa uçlarının ortancası = üst/alt.
                x0 = Counter(round(b[0]) for b in lines).most_common(1)[0][0]
                wide = [round(b[2]) for b in lines if b[2] - b[0] > lt.width * 0.5]
                x1 = max(wide) if wide else max(b[2] for b in lines)
                tops = sorted(max(_bbox(o)[3] for k, o in its if k == "text") for _pl, its in same
                              if any(k == "text" for k, _o in its))
                bots = sorted(min(_bbox(o)[1] for k, o in its if k == "text") for _pl, its in same
                              if any(k == "text" for k, _o in its))
                y1, y0 = tops[-1], bots[0]      # en dolu sayfa da sığsın
                clamp = lambda v: max(10.0, min(35.0, round(v * PT_MM, 1)))
                setup.left_mm = clamp(x0)
                setup.right_mm = clamp(lt.width - x1)
                setup.top_mm = clamp(lt.height - y1)
                setup.bottom_mm = clamp(y0)
        left_pt = setup.left_mm / PT_MM

        for idx, lt, items in layouts:
            pw, ph = lt.width, lt.height
            text_w_pt = max(72.0, pw - (setup.left_mm + setup.right_mm) / PT_MM)
            all_text = "".join(
                t for k, o in items if k == "text" for _l, chars in _lines(o) for t, _c in chars)
            page_start = True
            if not all_text.strip() or _bad_text(all_text):
                # Taranmış sayfa ya da çözülemeyen yazı tipi: sayfayı resim olarak koy
                img = renderer.page(idx, pw, ph)
                if img is not None:
                    w.block(page_break=True, align=Qt.AlignmentFlag.AlignHCenter)
                    w.image(img, pw, ph, pt2px(text_w_pt))
                    image_pages += 1
                elif all_text.strip():
                    warnings.append(f"{idx + 1}. sayfanın metni çözülemedi.")
                pages_done += 1
                continue

            prev_bottom = None
            for kind, obj in items:
                if kind == "image":
                    img = renderer.crop(idx, pw, ph, obj.bbox)
                    if img is None:
                        lost_images += 1
                        continue
                    w.block(page_break=page_start, top_px=pt2px(6),
                            align=Qt.AlignmentFlag.AlignHCenter)
                    w.image(img, obj.width, obj.height, pt2px(text_w_pt))
                    page_start = False
                    prev_bottom = obj.bbox[1]
                    continue
                lines = _lines(obj)
                if not lines:
                    continue
                bx0, by0, bx1, by1 = _bbox(obj)
                if prev_bottom is None:
                    # sayfanın ilk paragrafı: üst kenar boşluğundan sonraki boşluğu koru
                    gap = max(0.0, min(300.0, ph - setup.top_mm / PT_MM - by1))
                else:
                    gap = max(0.0, min(300.0, prev_bottom - by1 - 2))
                prev_bottom = by0
                # Hizalama: dar ve sayfa ortasında duran kutu -> ortala; sağa yaslı -> sağ
                bw = bx1 - bx0
                align = None
                text_mid = left_pt + text_w_pt / 2
                line_boxes = [ln.bbox for ln, _c in lines]
                centered = (max(lb[0] for lb in line_boxes) - left_pt > 24 and
                            min(lb[0] for lb in line_boxes) - left_pt > 8 and
                            all(abs((lb[0] + lb[2]) / 2 - text_mid) < 20 for lb in line_boxes) and
                            all(lb[2] - lb[0] < text_w_pt * 0.97 for lb in line_boxes))
                if centered:
                    align = Qt.AlignmentFlag.AlignHCenter
                elif bw < text_w_pt * 0.6 and abs(bx1 - (left_pt + text_w_pt)) < 10 and bx0 - left_pt > 60:
                    align = Qt.AlignmentFlag.AlignRight
                elif len(lines) > 2 and bw > text_w_pt * 0.9:
                    align = Qt.AlignmentFlag.AlignJustify
                indent = pt2px(bx0 - left_pt) if align is None and bx0 - left_pt > 6 else 0.0
                first = 0.0
                if align in (None, Qt.AlignmentFlag.AlignJustify) and len(lines) > 1:
                    fx = lines[0][0].bbox[0] - bx0
                    if fx > 6:
                        first = pt2px(fx)
                w.block(page_break=page_start, top_px=pt2px(gap), align=align,
                        indent_px=indent, first_px=first)
                page_start = False
                _write_lines(w, lines, body)
            pages_done += 1

    if image_pages:
        warnings.append(f"{image_pages} sayfanın metni okunamadığı için (taranmış PDF ya da gömülü "
                        "yazı tipi) bu sayfalar resim olarak eklendi.")
    if lost_images:
        warnings.append(f"{lost_images} görsel aktarılamadı.")
    if not pages_done:
        raise PdfImportError("PDF'te aktarılacak sayfa bulunamadı.")
    mm_px = lambda mm: pt2px(mm / PT_MM)
    w.fit_pages(mm_px(setup.width_mm - setup.left_mm - setup.right_mm),
                mm_px(setup.height_mm - setup.top_mm - setup.bottom_mm))
    w.doc.setModified(False)
    w.doc.clearUndoRedoStacks()
    notice = (f"PDF içe aktarıldı ({pages_done} sayfa). PDF'te paragraf/tablo yapısı olmadığından "
              "düzen birebir aynı olmayabilir. Kaydederken Word (.docx) olarak kaydedilecek.")
    return w.doc, setup, {"warnings": warnings, "notice": notice}


def _write_lines(w, lines, body):
    """Kutunun satırlarını tek paragrafa birleştirir (satır sonu tirelerini kaldırarak)."""
    run_text, run_key, run_cf = [], None, None

    def flush():
        nonlocal run_text
        if run_text:
            w.text(_clean("".join(run_text)), run_cf)
            run_text = []

    last_cf = QTextCharFormat(w.base_cf)
    for li, (_line, chars) in enumerate(lines):
        # satır sonundaki boşlukları at
        while chars and chars[-1][1] is None and not chars[-1][0].strip():
            chars = chars[:-1]
        for t, ch in chars:
            if ch is None:
                cf = last_cf
                key = run_key
            else:
                fam, bold, italic = _family(ch.fontname)
                size = round(ch.size * 2) / 2
                if size < 4 or size > 200:
                    size = body
                col = _color(ch.graphicstate) if hasattr(ch, "graphicstate") else None
                key = (fam, bold, italic, size, col.name() if col else None)
                if key != run_key:
                    cf = QTextCharFormat(w.base_cf)
                    cf.setFontFamilies([fam])
                    cf.setFontPointSize(size)
                    if bold:
                        cf.setFontWeight(700)
                    if italic:
                        cf.setFontItalic(True)
                    if col is not None:
                        cf.setForeground(col)
                else:
                    cf = run_cf
            if key != run_key:
                flush()
                run_key, run_cf = key, cf
            last_cf = cf
            run_text.append(t)
        if li < len(lines) - 1:
            # Satır sonu: "kelime-" + küçük harf -> tireyi kaldır, yoksa boşluk ekle
            joined = "".join(run_text)
            nxt = next((t for t, _c in lines[li + 1][1] if t.strip()), "")
            if joined.endswith("-") and len(joined) > 1 and joined[-2].isalpha() and nxt[:1].islower():
                run_text = [joined[:-1]]
            elif joined and not joined.endswith(" "):
                run_text.append(" ")
            elif not joined:
                # önceki run zaten yazıldı: boşluğu yeni run olarak ekle
                run_text.append(" ")
    flush()
