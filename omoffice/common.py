"""Ortak sabitler ve birim dönüşümleri."""
from dataclasses import dataclass, field
import copy
import os

from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextFormat

APP_NAME = "OmOffice"
APP_ORG = "OmOffice"

# Belge koordinatları 96 DPI piksel olarak tutulur (Qt'nin ekran varsayılanı).
DPI = 96.0

_UP = int(QTextFormat.Property.UserProperty.value) if hasattr(QTextFormat.Property.UserProperty, "value") else 0x100000

# Değişiklik izleme özellikleri (QTextCharFormat üzerinde)
TC_TYPE = _UP + 1      # "ins" | "del"
TC_AUTHOR = _UP + 2
TC_DATE = _UP + 3
COMMENT_PROP = _UP + 4   # virgülle ayrılmış açıklama kimlikleri
FOOTNOTE_PROP = _UP + 5  # dipnot kimliği (dipnot başvuru karakterinde)
PLACEHOLDER_PROP = _UP + 6  # şablondaki "[buraya yazın]" yer tutucu metni
# Paragraf stil adı (QTextBlockFormat üzerinde)
STYLE_PROP = _UP + 10
TOC_PROP = _UP + 11      # içindekiler paragrafı

DEFAULT_FONT = "Calibri"
DEFAULT_SIZE = 11.0


def pt2px(pt):
    return pt * DPI / 72.0


def px2pt(px):
    return px * 72.0 / DPI


def mm2px(mm):
    return mm * DPI / 25.4


def px2mm(px):
    return px * 25.4 / DPI


PAPER_SIZES = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A3": (297.0, 420.0),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
}

MARGIN_PRESETS = {
    "Normal": (25.0, 25.0, 25.0, 25.0),
    "Dar": (12.7, 12.7, 12.7, 12.7),
    "Orta": (25.4, 25.4, 19.1, 19.1),
    "Geniş": (25.4, 25.4, 50.8, 50.8),
}


@dataclass
class PageSetup:
    width_mm: float = 210.0
    height_mm: float = 297.0
    top_mm: float = 25.0
    bottom_mm: float = 25.0
    left_mm: float = 25.0
    right_mm: float = 25.0
    header_text: str = ""
    footer_text: str = ""
    header_align: str = "center"   # left | center | right
    footer_align: str = "center"
    different_first: bool = False
    page_color: str = ""        # "" = beyaz
    watermark: str = ""
    page_border: bool = False
    line_numbers: bool = False
    # Sayfaya özel üst/alt bilgi: {sayfa_no: {"header": metin, "header_align": .., "footer": .., "footer_align": ..}}
    # Anahtar yoksa varsayılan kullanılır; "" = o sayfada gösterme.
    hf_pages: dict = field(default_factory=dict)

    def copy(self):
        return copy.deepcopy(self)

    def hf_for(self, which, page_no):
        """Bir sayfada görünecek (metin, hizalama). which: "header" | "footer"; page_no 1'den başlar."""
        default_align = self.header_align if which == "header" else self.footer_align
        ov = self.hf_pages.get(page_no, {})
        if which in ov:
            return ov[which], ov.get(which + "_align") or default_align
        if self.different_first and page_no == 1:
            return "", default_align
        return (self.header_text if which == "header" else self.footer_text), default_align

    def has_page_overrides(self):
        return any(self.hf_pages.values())

    @property
    def landscape(self):
        return self.width_mm > self.height_mm


# Paragraf stilleri: ad -> (başlık düzeyi, punto, kalın, italik, renk, docx stil adı)
STYLES = {
    "Normal": (0, None, False, False, None, "Normal"),
    "Konu Başlığı": (0, 28.0, False, False, "#1F2A44", "Title"),
    "Başlık 1": (1, 16.0, True, False, "#2F5496", "Heading 1"),
    "Başlık 2": (2, 13.0, True, False, "#2F5496", "Heading 2"),
    "Başlık 3": (3, 12.0, True, False, "#1F3763", "Heading 3"),
    "Alıntı": (0, None, False, True, "#595959", "Quote"),
}
DOCX_TO_STYLE = {v[5].lower(): k for k, v in STYLES.items()}


def app_data_dir():
    # OMOFFICE_TEST_DATA: testler kullanıcının gerçek kurtarma dosyalarına dokunmasın
    base = os.environ.get("OMOFFICE_TEST_DATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def app_settings():
    test_dir = os.environ.get("OMOFFICE_TEST_DATA")
    if test_dir:  # testler kullanıcının ayarlarını ve son dosyalar listesini kirletmesin
        return QSettings(os.path.join(test_dir, "ayarlar.ini"), QSettings.Format.IniFormat)
    return QSettings(APP_ORG, APP_NAME)


def resource_dir():
    return os.path.dirname(os.path.abspath(__file__))


def turkish_upper(s):
    return s.replace("i", "İ").replace("ı", "I").upper()


def turkish_lower(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


_TR_ALPHABET = "aâbcçdefgğhıiîjklmnoöprsştuûüvyzqwx"


def turkish_sort_key(s):
    out = []
    for ch in turkish_lower(s.strip()):
        i = _TR_ALPHABET.find(ch)
        out.append((0, i) if i >= 0 else (1, ord(ch)))
    return out


def turkish_title(s):
    out, start = [], True
    for ch in s:
        if ch.isalpha():
            out.append(turkish_upper(ch) if start else turkish_lower(ch))
            start = False
        else:
            out.append(ch)
            start = ch.isspace() or ch in "-(\"'"
    return "".join(out)
