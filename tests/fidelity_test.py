"""Word sadakat testi: python tests/fidelity_test.py <klasör> [tür ...]

Her şablonu OmOffice'te oluşturur, .docx'e kaydeder, Microsoft Word ile PDF'e çevirir ve
sayfa sayfa karşılaştırır: sayfa sayısı, her sayfanın son satırının Word'de aynı sayfada
olup olmadığı, metin benzerliği. Yan yana görseller <klasör>/karsilastir_<tür>_<n>.png.
"""
import difflib
import os
import re
import subprocess  # nosec B404 - yalnızca test: Word'ü PowerShell COM ile çağırmak için
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["OMOFFICE_TEST_DATA"] = tempfile.mkdtemp(prefix="omoffice_data_")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QTextCursor
from PySide6.QtWidgets import QApplication

ANSWERS = {"title": "Yapay Zekâ Destekli Öğrenmenin Akademik Başarıya Etkisi", "author": "Ayşe Yılmaz",
           "institution": "Örnek Üniversitesi", "department": "Eğitim Bilimleri",
           "course": "Araştırma Yöntemleri", "keywords": "yapay zekâ, öğrenme analitiği, başarı",
           "advisor": "Prof. Dr. Mehmet Demir", "degree": "Yüksek Lisans Tezi", "student_no": "20231234",
           "instructor": "Doç. Dr. Selin Kaya", "recipient": "Mühendislik Fakültesi Dekanlığına",
           "subject": "Ders kaydı hakkında"}
OPTS = {"cover": True, "toc": True, "placeholders": True, "citation": "APA 7"}
MAX_DRIFT = 6.0   # pt; bir paragrafın Word'de OmOffice'e göre en fazla bu kadar kaymasına izin verilir


def norm(t):
    return re.sub(r"\s+", " ", t.replace("­", "")).strip()


def omoffice_pages(e):
    """OmOffice'in yerleşimine göre her sayfadaki satırlar."""
    e.page_count()
    doc = e.document()
    lay = doc.documentLayout()
    _, ph = e.page_px()
    pages = {}
    block = doc.begin()
    while block.isValid():
        bl = block.layout()
        top = lay.blockBoundingRect(block).top()
        text = block.text()
        for i in range(bl.lineCount() if bl else 0):
            ln = bl.lineAt(i)
            pg = int((top + ln.y() + ln.height() / 2) // ph)
            s = norm(text[ln.textStart():ln.textStart() + ln.textLength()].replace("￼", ""))
            if s:
                pages.setdefault(pg, []).append(s)
        block = block.next()
    return [pages.get(i, []) for i in range(e.page_count())]


def omoffice_positions(e):
    """Tablo dışındaki dolu paragrafların (sayfa, y pt, metin başı) listesi."""
    doc = e.document()
    lay = doc.documentLayout()
    _, ph = e.page_px()
    out = []
    b = doc.begin()
    while b.isValid():
        text = norm(b.text().replace("￼", ""))
        if text and QTextCursor(b).currentTable() is None and b.layout().lineCount():
            y = lay.blockBoundingRect(b).top() + b.layout().lineAt(0).y()
            out.append((int(y // ph) + 1, (y % ph) * 72 / 96, text[:12]))
        b = b.next()
    return out


def word_positions(path):
    out = []
    with open(path, encoding="utf-8-sig") as f:
        for ln in f:
            pg, y, text = ln.rstrip("\n").split("|", 2)
            text = norm(text.replace("\r", "").replace("\x07", "").replace("\x0c", ""))
            if text:
                out.append((int(pg), float(y.replace(",", ".")), text[:12]))
    return out


def drift(kpos, wpos):
    """Aynı metinle başlayan paragrafların dikey konum farkı (pt); en büyüğü ve yeri."""
    worst, where, j = 0.0, "", 0
    for kp, ky, kt in kpos:
        for jj in range(j, min(j + 8, len(wpos))):
            wp, wy, wt = wpos[jj]
            if wt.casefold() == kt.casefold():  # Word büyük harf dönüşümünü metne uygulamış olabilir
                j = jj + 1
                d = abs(wy - ky) if wp == kp else 999.0
                if d > worst:
                    worst, where = d, f"s{kp} '{kt}'"
                break
    return worst, where


def word_convert(jobs):
    """[(docx, pdf)] → Word ile tek oturumda PDF'e çevirir; paragraf konumlarını <pdf>.pos'a yazar."""
    lines = ["$w=New-Object -ComObject Word.Application", "$w.Visible=$false"]
    for docx, pdf in jobs:
        lines.append(f"$d=$w.Documents.Open('{docx}', $false, $true); $d.ExportAsFixedFormat('{pdf}', 17); "
                     f"$o=foreach($p in $d.Paragraphs){{ if(-not $p.Range.Information(12)){{ $r=$p.Range; "
                     f"$t=$r.Text.Substring(0,[Math]::Min(20,$r.Text.Length)) -replace '[\\r\\n\\x07\\x0b\\x0c|]',' '; "
                     f"$r.Collapse(1); "
                     f"'{{0}}|{{1}}|{{2}}' -f $r.Information(3), $r.Information(6), $t }} }}; "
                     f"[IO.File]::WriteAllLines('{pdf}.pos', [string[]]$o, [Text.Encoding]::UTF8); "
                     f"$d.Close($false)")
    lines.append("$w.Quit()")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(lines)],  # nosec
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(r.stderr)


def main():
    out = os.path.abspath(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    app = QApplication(sys.argv)
    from PySide6.QtPdf import QPdfDocument
    from omoffice.common import PageSetup
    from omoffice.docx_io import export_docx, import_docx
    from omoffice.editor import PageEdit, new_document
    from omoffice.guide import KINDS
    from omoffice.templates import build_kind
    kinds = sys.argv[2:] or list(KINDS)
    e = PageEdit(None)
    e.resize(900, 1200)
    e2 = PageEdit(None)
    built, roundtrip = {}, {}
    for key in kinds:
        e.set_document(new_document(), PageSetup())
        build_kind(e, key, ANSWERS, OPTS)
        path = os.path.join(out, f"{key}.docx")
        export_docx(e, path)
        built[key] = (omoffice_pages(e), [e.render_page_image(i, 595) for i in range(e.page_count())],
                      omoffice_positions(e))
        # Kaydet-aç: OmOffice'te de yerleşim aynı kalmalı
        doc, setup, meta = import_docx(path)
        e2.set_document(doc, setup, meta)
        rt, rt_where = drift(built[key][2], omoffice_positions(e2))
        roundtrip[key] = (rt, rt_where, e2.page_count())
    word_convert([(os.path.join(out, f"{k}.docx"), os.path.join(out, f"{k}.pdf")) for k in kinds])

    total_bad = 0
    for key in kinds:
        kp, kimgs, kpos = built[key]
        pd = QPdfDocument()
        pd.load(os.path.join(out, f"{key}.pdf"))
        worst, where = drift(kpos, word_positions(os.path.join(out, f"{key}.pdf.pos")))
        wn = pd.pageCount()
        wtext = [norm(pd.getAllText(i).text()) for i in range(wn)]
        bad = []
        if wn != len(kp):
            bad.append(f"sayfa sayısı OmOffice {len(kp)} / Word {wn}")
        sims = []
        for i, lines in enumerate(kp):
            if not lines:
                continue
            last = lines[-1][-40:]
            where = [j + 1 for j, t in enumerate(wtext) if last in t]
            if i < wn:
                body = " ".join(lines)
                sims.append(difflib.SequenceMatcher(None, body, wtext[i]).ratio())
            if where and (i + 1) not in where:
                bad.append(f"s{i + 1} son satırı Word'de s{where[0]}: «{last}»")
        sim = sum(sims) / len(sims) if sims else 0
        if worst > MAX_DRIFT:
            bad.append(f"paragraf konumu {worst:.1f} pt kaymış: {where}")
        rt, rt_where, rt_pages = roundtrip[key]
        if rt > MAX_DRIFT or rt_pages != len(kp):
            bad.append(f"OmOffice'te kaydet-aç sonrası {rt:.1f} pt kayma, {rt_pages} sayfa: {rt_where}")
        status = "OK " if not bad else "KAY"
        print(f"{status} {key:12s} OmOffice {len(kp)} s / Word {wn} s, benzerlik %{sim * 100:.0f}, "
              f"en büyük kayma {worst:.1f} pt ({where})")
        for b in bad[:6]:
            print("      -", b)
        total_bad += bool(bad)
        for i in range(max(len(kimgs), wn)):
            wi = pd.render(i, pd.pagePointSize(i).toSize()) if i < wn else None
            ki = kimgs[i] if i < len(kimgs) else None
            h = max(x.height() for x in (wi, ki) if x is not None)
            sheet = QImage(595 * 2 + 30, h + 30, QImage.Format.Format_RGB32)
            sheet.fill(QColor("#888888"))
            p = QPainter(sheet)
            p.setPen(Qt.GlobalColor.white)
            p.drawText(10, 18, f"OMOFFICE — {key} s{i + 1}")
            p.drawText(615, 18, "WORD")
            if ki is not None:
                p.drawImage(10, 25, ki)
            if wi is not None:
                p.drawImage(615, 25, wi.scaledToWidth(595, Qt.TransformationMode.SmoothTransformation))
            p.end()
            sheet.save(os.path.join(out, f"karsilastir_{key}_{i + 1}.png"))
    print("\nFIDELITY", "PASS" if not total_bad else f"FAIL ({total_bad}/{len(kinds)} türde kayma)")
    return 0 if not total_bad else 1


if __name__ == "__main__":
    sys.exit(main())
