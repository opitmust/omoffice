"""Yazım denetimi (Hunspell sözlükleri, spylls ile) ve belge vurgulayıcısı."""
import os
import re
import threading
import time

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor

from .common import TC_TYPE, TC_AUTHOR, COMMENT_PROP, resource_dir, app_data_dir

import logging
log = logging.getLogger("omoffice")

WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")

LANGUAGES = {"tr_TR": "Türkçe", "en_US": "İngilizce"}


class SpellChecker(QObject):
    """Sözlüğü arka planda yükler; ana iş parçacığından sorgulanır."""

    loaded = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.language = None
        self._dicts = {}
        self._loading = set()
        self._cache = {}
        self._ignored = set()
        self._user_path = os.path.join(app_data_dir(), "kullanici_sozlugu.txt")
        self._user = set()
        try:
            with open(self._user_path, encoding="utf-8") as f:
                self._user = {w.strip() for w in f if w.strip()}
        except OSError:
            pass

    @property
    def ready(self):
        return self.language is not None and self.language in self._dicts

    def set_language(self, code):
        self.language = code
        self._cache = {}
        if code is None or code in self._dicts or code in self._loading:
            if code in self._dicts:
                self.loaded.emit(code)
            return
        self._loading.add(code)
        threading.Thread(target=self._load, args=(code,), daemon=True).start()

    def _load(self, code):
        try:
            from spylls.hunspell import Dictionary
            d = Dictionary.from_files(os.path.join(resource_dir(), "dicts", code))
        except Exception as exc:  # sözlük yoksa denetim kapalı kalır
            print("Sözlük yüklenemedi:", code, exc)
            d = None
        self._loading.discard(code)
        if d is not None:
            self._dicts[code] = d
            try:
                self.loaded.emit(code)
            except RuntimeError:  # pencere sözlük yüklenirken kapatıldıysa
                return

    def check(self, word):
        if not self.ready or len(word) < 2:
            return True
        if word in self._user or word in self._ignored:
            return True
        hit = self._cache.get(word)
        if hit is None:
            try:
                hit = self._dicts[self.language].lookup(word)
            except Exception:
                hit = True
            self._cache[word] = hit
        return hit

    def suggest(self, word, limit=6, seconds=1.5):
        if not self.ready:
            return []
        out, t0 = [], time.time()
        try:
            for s in self._dicts[self.language].suggest(word):
                out.append(s)
                if len(out) >= limit or time.time() - t0 > seconds:
                    break
        except Exception as exc:  # bozuk/eksik bölüm işlemi durdurmasın
            log.debug("yok sayılan hata: %s", exc)
        return out

    def ignore(self, word):
        self._ignored.add(word)

    def add_to_dictionary(self, word):
        self._user.add(word)
        try:
            with open(self._user_path, "a", encoding="utf-8") as f:
                f.write(word + "\n")
        except OSError:
            pass


_AUTHOR_COLORS = ["#1565C0", "#2E7D32", "#6A1B9A", "#EF6C00", "#00838F", "#AD1457"]


def author_color(author):
    return QColor(_AUTHOR_COLORS[sum(map(ord, author or "")) % len(_AUTHOR_COLORS)])


class DocHighlighter(QSyntaxHighlighter):
    """Değişiklik izleme işaretlerini ve yazım hatalarını görsel olarak gösterir.

    Belgenin kendi biçimini değiştirmez; yalnızca yerleşim katmanında çizer.
    """

    def __init__(self, doc, spell=None, show_changes=True, comment_state=None):
        super().__init__(doc)
        self.spell = spell
        self.show_changes = show_changes
        # comment_state(id) -> "active" | "open" | None (çözülmüş/silinmiş)
        self.comment_state = comment_state

    def highlightBlock(self, text):
        block = self.currentBlock()
        bpos = block.position()
        if self.show_changes or self.comment_state:
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                cf = frag.charFormat()
                kind = cf.property(TC_TYPE) if self.show_changes else None
                ids = cf.property(COMMENT_PROP) if self.comment_state else None
                if ids:
                    states = [self.comment_state(i) for i in str(ids).split(",") if i]
                    if "active" in states or "open" in states:
                        f = QTextCharFormat()
                        f.setBackground(QColor("#FFD666" if "active" in states else "#FFF0B8"))
                        self.setFormat(frag.position() - bpos, frag.length(), f)
                if kind:
                    f = self.format(frag.position() - bpos)
                    if kind == "ins":
                        f.setForeground(author_color(cf.property(TC_AUTHOR)))
                        f.setFontUnderline(True)
                    else:
                        f.setForeground(QColor("#C62828"))
                        f.setFontStrikeOut(True)
                    self.setFormat(frag.position() - bpos, frag.length(), f)
                it += 1
        if self.spell is not None and self.spell.ready:
            for m in WORD_RE.finditer(text):
                if not self.spell.check(m.group()):
                    for i in range(m.start(), m.end()):
                        f = self.format(i)
                        f.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
                        f.setUnderlineColor(QColor("#E53935"))
                        self.setFormat(i, 1, f)
