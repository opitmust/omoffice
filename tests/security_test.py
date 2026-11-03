"""OmOffice güvenlik testleri: python tests/security_test.py [çalışma_klasörü]

Kötü niyetli belgeler üretir ve OmOffice'in bunları güvenle işlediğini doğrular:
XXE (dış varlık), milyar kahkaha (entity bombası), zip bombası, bozuk paket, uzak resim,
UNC/yerel dosya resmi (HTML), zararlı bağlantılar, makrolu belge, yol geçişi (zip-slip),
dev boyutlu resim. Sonunda SECURITY PASS / FAIL yazar.
"""
import io
import os
import socket
import sys
import tempfile
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OMOFFICE_TEST_DATA"] = tempfile.mkdtemp(prefix="omoffice_data_")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImageReader, QTextDocument
from PySide6.QtWidgets import QApplication, QMessageBox

OUT = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="omoffice_sec_")
os.makedirs(OUT, exist_ok=True)
failures = []
SECRET = "OMOFFICE_GIZLI_ISARET_8f3a"


def check(cond, msg):
    print(("  ok  " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


# Ağ bağlantısı girişimlerini yakala (OmOffice hiç ağa çıkmamalı)
NET_ATTEMPTS = []
_orig_connect = socket.socket.connect


def _spy_connect(self, addr):
    NET_ATTEMPTS.append(addr)
    raise OSError("test: ağ engellendi")


socket.socket.connect = _spy_connect


def base_docx():
    from docx import Document
    d = Document()
    d.add_paragraph("Merhaba dünya")
    bio = io.BytesIO()
    d.save(bio)
    return bio.getvalue()


def rewrite(data, changes, extra=None):
    """zip içindeki dosyaları değiştirir: changes = {ad: fonksiyon(bytes)->bytes}."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            b = zin.read(it.filename)
            if it.filename in changes:
                b = changes[it.filename](b)
            zout.writestr(it.filename, b)
        for name, b in (extra or {}).items():
            zout.writestr(name, b)
    return out.getvalue()


def save(name, data):
    p = os.path.join(OUT, name)
    with open(p, "wb") as f:
        f.write(data)
    return p


def main():
    app = QApplication(sys.argv)
    QImageReader.setAllocationLimit(256)
    from omoffice.docx_io import import_docx
    from omoffice.odt_io import import_odt
    from omoffice.safety import UnsafeFileError, is_safe_link, sanitize_html, sanitize_markdown, check_zip
    from omoffice.editor import new_document
    from omoffice.mainwindow import MainWindow

    secret_file = save("gizli.txt", SECRET.encode())
    secret_url = "file:///" + secret_file.replace("\\", "/")

    # 1) XXE: dış varlık ile yerel dosya okuma denemesi (document.xml)
    def inject_xxe(b):
        s = b.decode("utf-8")
        s = s.replace("<?xml version='1.0' encoding='UTF-8' standalone='yes'?>", "", 1)
        s = s.replace('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', "", 1)
        dtd = f'<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE w:document [<!ENTITY xxe SYSTEM "{secret_url}">]>'
        return (dtd + s.replace("Merhaba dünya", "Merhaba &xxe; dünya")).encode("utf-8")

    p = save("xxe.docx", rewrite(base_docx(), {"word/document.xml": inject_xxe}))
    try:
        doc, _, _ = import_docx(p)
        text = doc.toPlainText()
        check(SECRET not in text, f"XXE (document.xml): yerel dosya içeriği sızmadı ({text[:40]!r})")
    except Exception as exc:
        check(SECRET not in str(exc), f"XXE (document.xml): reddedildi ({type(exc).__name__})")

    # 2) XXE: dipnotlar ve tema bölümü (OmOffice'in kendi ayrıştırdığı yerler)
    win = MainWindow()
    win.start_screen = False
    e = win.editor
    e.textCursor().insertText("Dipnotlu metin")
    e.insert_footnote("dipnot")
    fn_doc = save("fn_base.docx", b"")
    from omoffice.docx_io import export_docx
    export_docx(e, fn_doc)
    with open(fn_doc, "rb") as f:
        fn_data = f.read()

    def xxe_footnotes(b):
        s = b.decode("utf-8")
        s = s[s.index("<w:footnotes"):]
        dtd = f'<?xml version="1.0"?><!DOCTYPE w:footnotes [<!ENTITY xxe SYSTEM "{secret_url}">]>'
        return (dtd + s.replace(">dipnot<", ">&xxe;<")).encode()

    p = save("xxe_dipnot.docx", rewrite(fn_data, {"word/footnotes.xml": xxe_footnotes}))
    try:
        doc, _, meta = import_docx(p)
        check(all(SECRET not in t for t in meta["footnotes"].values()), "XXE (footnotes.xml): sızma yok")
    except Exception as exc:
        check(True, f"XXE (footnotes.xml): reddedildi ({type(exc).__name__})")

    # 3) Milyar kahkaha (entity genişletme bombası)
    def laughs(b):
        s = b.decode("utf-8")
        s = s[s.index("<w:document"):]
        ents = '<!ENTITY lol "lol">' + "".join(
            f'<!ENTITY lol{i} "{("&lol%s;" % (i - 1 if i > 1 else "")) * 10}">' for i in range(1, 10))
        dtd = f'<?xml version="1.0"?><!DOCTYPE w:document [{ents}]>'
        return (dtd + s.replace("Merhaba dünya", "&lol9;")).encode()

    p = save("bomba_entity.docx", rewrite(base_docx(), {"word/document.xml": laughs}))
    t0 = time.time()
    try:
        doc, _, _ = import_docx(p)
        n = doc.toPlainText().count("lol")
        check(n < 1000 and time.time() - t0 < 10, f"Milyar kahkaha: genişletilmedi ({n} 'lol', {time.time() - t0:.1f} sn)")
    except Exception as exc:
        check(time.time() - t0 < 10, f"Milyar kahkaha: reddedildi ({type(exc).__name__}, {time.time() - t0:.1f} sn)")

    # 4) Zip bombası (yüksek sıkıştırma oranlı dev girdi)
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
        with zipfile.ZipFile(io.BytesIO(base_docx())) as zin:
            for it in zin.infolist():
                z.writestr(it.filename, zin.read(it.filename))
        with z.open("word/media/bomba.bin", "w") as f:
            chunk = b"\0" * (1024 * 1024)
            for _ in range(150):
                f.write(chunk)
    p = save("zip_bombasi.docx", bomb.getvalue())
    check(os.path.getsize(p) < 2 * 1024 * 1024, f"zip bombası dosyası küçük ({os.path.getsize(p) // 1024} KB)")
    try:
        check_zip(p)
        check(False, "Zip bombası: tespit edilmedi")
    except UnsafeFileError as exc:
        check(True, f"Zip bombası: reddedildi — {exc}")

    # 5) Bozuk / sahte dosyalar arayüzü çökertmemeli
    orig_warn, orig_crit = QMessageBox.warning, QMessageBox.critical
    shown = []
    QMessageBox.warning = staticmethod(lambda *a, **k: shown.append(a[2] if len(a) > 2 else ""))
    QMessageBox.critical = staticmethod(lambda *a, **k: shown.append(a[2] if len(a) > 2 else ""))
    for name, data in (("sahte.docx", b"MZ\x90\x00 bu bir exe gibi"), ("yarim.docx", base_docx()[:300]),
                       ("bos.docx", b""), ("sahte.odt", b"PK\x03\x04bozuk")):
        p = save(name, data)
        ok = win.open_path(p)
        check(ok is False, f"Bozuk dosya ({name}): kibarca reddedildi, program çalışıyor")
    p = save("zip_bombasi2.docx", bomb.getvalue())
    check(win.open_path(p) is False, "Zip bombası arayüzden açılmadı")

    # 6) Uzak (bağlantılı) resim: ağa çıkılmamalı
    def link_rel(b):
        s = b.decode("utf-8")
        return s.replace("</Relationships>", '<Relationship Id="rIdX" Type="http://schemas.openxmlformats.org/'
                         'officeDocument/2006/relationships/image" Target="http://127.0.0.1:9/iz.png" '
                         'TargetMode="External"/></Relationships>').encode()

    def link_doc(b):
        s = b.decode("utf-8")
        pic = ('<w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
               '<wp:extent cx="952500" cy="952500"/><wp:docPr id="1" name="x"/>'
               '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData>'
               '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:blipFill>'
               '<a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:link="rIdX" r:embed="rIdX"/>'
               '</pic:blipFill></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
        return s.replace("<w:t>Merhaba dünya</w:t></w:r>", "<w:t>Merhaba dünya</w:t></w:r>" + pic).encode()

    p = save("uzak_resim.docx", rewrite(base_docx(), {"word/_rels/document.xml.rels": link_rel,
                                                     "word/document.xml": link_doc}))
    NET_ATTEMPTS.clear()
    try:
        doc, _, _ = import_docx(p)
        check(not NET_ATTEMPTS, "Uzak resim: ağ bağlantısı denenmedi")
    except Exception as exc:
        check(not NET_ATTEMPTS, f"Uzak resim: ağa çıkmadan reddedildi ({type(exc).__name__})")

    # 7) HTML/Markdown: yerel dosya, UNC ağ yolu, betik
    html = (f'<p>Merhaba</p><img src="{secret_url}"><img src="\\\\127.0.0.1\\paylasim\\a.png">'
            '<script>alert(1)</script><a href="javascript:alert(1)">tıkla</a>'
            '<link rel="stylesheet" href="file:///C:/x.css"><p onclick="kötü()">x</p>')
    clean = sanitize_html(html)
    check("<img" not in clean and "script" not in clean.lower() and "javascript:" not in clean
          and "onclick" not in clean and "<link" not in clean, "HTML temizleme: resim/betik/olay/bağlantı ayıklandı")
    md = clean_md = sanitize_markdown(f"![a]({secret_url}) ve ![b](\\\\\\\\sunucu\\\\x.png) ve ![c](data:image/png;base64,AA==)")
    check("file:" not in clean_md and "sunucu" not in clean_md and "data:image" in clean_md, "Markdown resim yolları ayıklandı")
    kd = new_document()
    res = kd.loadResource(QTextDocument.ResourceType.ImageResource, QUrl(secret_url))
    res2 = kd.loadResource(QTextDocument.ResourceType.ImageResource, QUrl.fromLocalFile("\\\\127.0.0.1\\x\\a.png"))
    check(res is None and res2 is None, "Belge yerel/UNC dosyalarını kaynak olarak yüklemiyor")
    hp = save("kotu.html", html.encode())
    check(win.open_path(hp) and not e.image_names(), "Kötü HTML açıldı, dış resim yüklenmedi")

    # 8) Zararlı bağlantılar
    for url in ("javascript:alert(1)", secret_url, "file://C:/Windows/System32/calc.exe", "\\\\sunucu\\pay",
                "ms-msdt:/id PCWDiagnostic", "vbscript:msgbox(1)", "C:\\Windows\\notepad.exe"):
        check(not is_safe_link(url), f"Güvensiz bağlantı engelleniyor: {url[:40]}")
    for url in ("https://example.com", "http://example.com/a?b=1", "mailto:a@b.com"):
        check(is_safe_link(url), f"Güvenli bağlantıya izin var: {url}")
    from PySide6.QtGui import QDesktopServices
    opened = []
    orig_open = QDesktopServices.openUrl
    QDesktopServices.openUrl = staticmethod(lambda u: opened.append(u))
    e.open_link("file:///C:/Windows/System32/calc.exe")
    e.open_link("https://example.com")
    QDesktopServices.openUrl = orig_open
    check(len(opened) == 1 and opened[0].toString().startswith("https"), "Ctrl+tık yalnızca güvenli adresi açtı")

    # 9) Makrolu belge (.docm): açılır, makro çalıştırılmaz, uyarı verilir
    def to_docm(b):
        return b.replace(b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                         b"application/vnd.ms-word.document.macroEnabled.main+xml")

    p = save("makrolu.docm", rewrite(base_docx(), {"[Content_Types].xml": to_docm},
                                     {"word/vbaProject.bin": b"\xd0\xcf\x11\xe0 sahte makro Shell(\"calc\")"}))
    doc, _, meta = import_docx(p)
    check("Merhaba" in doc.toPlainText() and any("makro" in w.lower() for w in meta["warnings"]),
          f"Makrolu belge: metin açıldı, makro yok sayıldı ({meta['warnings']})")

    # 10) Zip-slip: '../' içeren girdi adları hiçbir yere yazılmamalı
    evil_target = os.path.abspath(os.path.join(OUT, "..", "omoffice_ele_gecirildi.txt"))
    if os.path.exists(evil_target):
        os.remove(evil_target)
    p = save("zipslip.docx", rewrite(base_docx(), {}, {"../omoffice_ele_gecirildi.txt": b"pwned",
                                                        "../../omoffice_ele_gecirildi.txt": b"pwned"}))
    try:
        warnings = check_zip(p)
        import_docx(p)
    except Exception:
        warnings = ["reddedildi"]
    check(not os.path.exists(evil_target) and warnings, "Zip-slip: dosya dışarı yazılmadı, uyarı verildi")

    # 11) Dev boyutlu resim (bellek tüketme)
    import struct
    import zlib

    def png(w, h):
        def chunk(t, d):
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        raw = zlib.compress(b"\0" * 10)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
            chunk(b"IDAT", raw) + chunk(b"IEND", b"")

    from docx import Document
    d = Document()
    d.add_paragraph("resim:")
    ok_png = png(10, 10)
    d.add_picture(io.BytesIO(ok_png))
    bio = io.BytesIO()
    d.save(bio)
    data = bio.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        media = [n for n in z.namelist() if n.startswith("word/media/")][0]
    p = save("dev_resim.docx", rewrite(data, {media: lambda b: png(60000, 60000)}))
    t0 = time.time()
    try:
        doc, _, _ = import_docx(p)
        check(time.time() - t0 < 10, f"Dev resim (60000×60000): bellek tüketmeden geçildi ({time.time() - t0:.1f} sn)")
    except Exception as exc:
        check(True, f"Dev resim: reddedildi ({type(exc).__name__})")

    # 12) ODT içinde XXE
    odt = io.BytesIO()
    with zipfile.ZipFile(odt, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "{secret_url}">]>'
                   '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                   'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:text>'
                   '<text:p>a &xxe; b</text:p></office:text></office:body></office:document-content>')
    p = save("xxe.odt", odt.getvalue())
    try:
        doc, _, _ = import_odt(p)
        check(SECRET not in doc.toPlainText(), "XXE (ODT): sızma yok")
    except Exception as exc:
        check(True, f"XXE (ODT): reddedildi ({type(exc).__name__})")

    check(not NET_ATTEMPTS, f"Tüm testler boyunca hiç ağ bağlantısı denenmedi ({len(NET_ATTEMPTS)})")
    QMessageBox.warning, QMessageBox.critical = orig_warn, orig_crit
    e.document().setModified(False)
    win.close()
    print("\nSECURITY", "PASS" if not failures else f"FAIL ({len(failures)})")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
