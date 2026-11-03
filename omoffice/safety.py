"""Dosya güvenliği: zip bombası, XXE, makro, zararlı bağlantı ve uzak kaynak korumaları.

OmOffice hiçbir zaman ağ bağlantısı kurmaz, belge içindeki kodu (makro vb.) çalıştırmaz
ve belgeden dosya sistemine bir şey çıkarmaz.
"""
import io
import os
import re
import zipfile

from lxml import etree

MAX_FILE_BYTES = 200 * 1024 * 1024          # 200 MB
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024  # 1 GB
MAX_RATIO = 150                              # tek girdi için sıkıştırma oranı sınırı
MAX_ENTRIES = 20000

SAFE_LINK_SCHEMES = ("http", "https", "mailto")

DOCX_MAIN = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
OTHER_MAINS = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",   # .dotx
    "application/vnd.ms-word.document.macroEnabled.main+xml",                             # .docm
    "application/vnd.ms-word.template.macroEnabledTemplate.main+xml",                     # .dotm
)

# DTD yüklemeyen, varlık (entity) çözmeyen, ağa çıkmayan ayrıştırıcı
SAFE_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                              huge_tree=False, remove_blank_text=False)


class UnsafeFileError(Exception):
    pass


def safe_fromstring(data):
    return etree.fromstring(data, SAFE_PARSER)


def check_zip(path):
    """Office/ODF zip paketini açmadan önce denetler. Uyarı listesi döndürür."""
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        raise UnsafeFileError(f"Dosya çok büyük ({size // (1024 * 1024)} MB). Sınır 200 MB.")
    if not zipfile.is_zipfile(path):
        raise UnsafeFileError("Bu dosya geçerli bir Word/OpenDocument paketi değil (bozuk ya da başka biçim).")
    warnings = []
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        if len(infos) > MAX_ENTRIES:
            raise UnsafeFileError("Paket olağan dışı sayıda dosya içeriyor.")
        total = 0
        for i in infos:
            total += i.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise UnsafeFileError("Paket açıldığında aşırı büyüyor (sıkıştırma bombası şüphesi).")
            if i.file_size > 10 * 1024 * 1024 and i.compress_size and i.file_size / i.compress_size > MAX_RATIO:
                raise UnsafeFileError("Olağan dışı sıkıştırma oranı (sıkıştırma bombası şüphesi).")
            name = i.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/") or re.match(r"^[A-Za-z]:", name):
                warnings.append("Paket şüpheli dosya yolları içeriyor (yok sayıldı).")
        if any("vbaproject" in i.filename.lower() or "activex" in i.filename.lower() for i in infos):
            warnings.append("Belgede makro/ActiveX bulundu. OmOffice makro çalıştırmaz; yalnızca metin açıldı.")
    return sorted(set(warnings))


def open_word_package(path):
    """.docx/.dotx/.docm/.dotm dosyasını python-docx'in açabileceği bir akışa çevirir."""
    warnings = check_zip(path)
    with open(path, "rb") as f:
        data = f.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        try:
            ct = z.read("[Content_Types].xml")
        except KeyError:
            raise UnsafeFileError("Word paketi eksik: [Content_Types].xml yok.")
        if DOCX_MAIN.encode() in ct and not any(m.encode() in ct for m in OTHER_MAINS):
            return io.BytesIO(data), warnings
        new_ct = ct
        for m in OTHER_MAINS:
            new_ct = new_ct.replace(m.encode(), DOCX_MAIN.encode())
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as o:
            for i in z.infolist():
                o.writestr(i, new_ct if i.filename == "[Content_Types].xml" else z.read(i.filename))
        out.seek(0)
        return out, warnings


def is_safe_link(url):
    m = re.match(r"^\s*([A-Za-z][A-Za-z0-9+.-]*):", url or "")
    return bool(m) and m.group(1).lower() in SAFE_LINK_SCHEMES


def sanitize_html(html):
    """İçe aktarılan HTML'den betik, dış kaynak ve yerel/ağ yolu taşıyan resimleri çıkarır."""
    from lxml import html as lhtml
    try:
        root = lhtml.fromstring(html)
    except (etree.ParserError, ValueError):
        return ""
    for bad in root.xpath("//script|//style[contains(., '@import')]|//link|//iframe|//object|//embed|"
                          "//meta|//base|//form|//input|//svg"):
        bad.getparent().remove(bad)
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in list(el.attrib):
            if attr.lower().startswith("on"):
                del el.attrib[attr]
        if el.tag.lower() == "img":
            src = el.get("src", "")
            if not src.lower().startswith("data:image/"):
                el.drop_tree() if el.getparent() is not None else None
        if el.tag.lower() == "a" and el.get("href") and not is_safe_link(el.get("href")):
            del el.attrib["href"]
    return lhtml.tostring(root, encoding="unicode")


def sanitize_markdown(md):
    """Markdown'daki yerel/ağ yollu resimleri metne çevirir (yalnızca data: resimleri kalır)."""
    return re.sub(r"!\[([^\]]*)\]\((?!data:image/)[^)]*\)", r"[resim: \1]", md)
