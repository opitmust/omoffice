"""Yeni sürüm denetimi.

Kullanıcı izin verdiyse GitHub'dan yalnızca en son sürümün numarası sorulur: istekte belge, ad, sürüm ya da
başka bir kişisel bilgi gönderilmez. Yeni sürüm indirilmez veya kurulmaz; kullanıcıya bildirilir ve isterse
indirme sayfası tarayıcıda açılır. İndirme sayfasının adresi sabittir, yanıttaki bağlantılara güvenilmez.
"""
import json
import logging
import re

from PySide6.QtCore import QThread, Signal

from . import __version__

REPO = "opitmust/omoffice"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
TIMEOUT = 10            # saniye
MAX_BYTES = 512 * 1024  # yanıt bundan büyükse okunmaz
CHECK_INTERVAL = 24 * 3600

log = logging.getLogger("omoffice.updates")


def parse_version(text):
    """'v1.2.3' / '1.2' → (1, 2, 3) / (1, 2, 0); tanınmazsa None."""
    m = re.fullmatch(r"\s*v?(\d{1,4})\.(\d{1,4})(?:\.(\d{1,6}))?\s*", text or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def is_newer(latest, current=__version__):
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def fetch_latest(timeout=TIMEOUT):
    """GitHub'daki en son (ön sürüm olmayan) sürümün numarasını döndürür. Hata olursa istisna fırlatır."""
    import ssl
    import urllib.request
    req = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "OmOffice-update-check",   # GitHub User-Agent ister; sürüm ya da kimlik gönderilmez
    })
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:  # nosec B310 - sabit https adresi
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("yanıt çok büyük")
    info = json.loads(data.decode("utf-8"))
    if not isinstance(info, dict):
        raise ValueError("beklenmeyen yanıt")
    tag = info.get("tag_name")
    if info.get("draft") or info.get("prerelease") or not isinstance(tag, str) or parse_version(tag) is None:
        raise ValueError(f"tanınmayan sürüm bilgisi: {tag!r}")
    v = parse_version(tag)
    return f"{v[0]}.{v[1]}.{v[2]}"


class UpdateCheck(QThread):
    """Denetimi arka planda yapar; arayüz beklemez. done(sürüm ya da None, hata metni)."""

    done = Signal(object, str)

    def run(self):
        try:
            self.done.emit(fetch_latest(), "")
        except Exception as ex:  # ağ yok, GitHub erişilemez, yanıt bozuk… program etkilenmemeli
            log.info("Güncelleme denetimi yapılamadı: %s", ex)
            self.done.emit(None, str(ex) or type(ex).__name__)
