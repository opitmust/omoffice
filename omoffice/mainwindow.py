"""Ana pencere: şerit arayüzü ve dosya işlemleri."""
import datetime
import json
import os
import re
import time
import traceback
import uuid
import zipfile

from PySide6.QtCore import Qt, QTimer, QSize, QSizeF, QMarginsF, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QAction, QActionGroup, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QPageSize,
    QPageLayout, QPdfWriter, QTextCharFormat, QTextCursor, QTextDocumentWriter, QTextFormat,
    QTextListFormat, QImage, QTextBlockFormat, QTextImageFormat, QDesktopServices, QPalette,
)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QFrame, QLabel,
    QToolButton, QComboBox, QFontComboBox, QMenu, QFileDialog, QMessageBox, QColorDialog,
    QDockWidget, QTreeWidget, QTreeWidgetItem, QInputDialog, QWidgetAction, QSizePolicy,
    QApplication, QSlider, QLineEdit, QDialog, QListWidget, QListWidgetItem, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QGraphicsOpacityEffect,
)

from .common import (
    APP_NAME, STYLES, PAPER_SIZES, MARGIN_PRESETS, DEFAULT_SIZE, PageSetup,
    app_data_dir, app_settings, pt2px, resource_dir, image_slot, IMAGE_SLOT_KINDS,
)
from . import __version__, theme, updates
from .theme import glyph, text_icon, THEMES, ACCENTS, CURRENT
from .templates import build as build_template
from .view import EditorView, Ruler
from .widgets import MiniBar, CommandPalette, CommentsPanel, ask_text
from .sidepanel import SidePanel, PanelPage
from .wizard import StartWizard
from .guidepanel import GuidePanel, CitationDialog, add_reference
from .templates import build_kind
from .odt_io import import_odt
from .pdf_io import PdfImportError, import_pdf
from .safety import sanitize_html, sanitize_markdown, UnsafeFileError
from .dialogs import (
    PageSetupDialog, ParagraphDialog, TableDialog, ImageSizeDialog, LinkDialog, SymbolDialog,
    FindReplaceDialog, HeaderFooterDialog,
)
from .docx_io import export_docx, import_docx, HIGHLIGHTS
from .editor import PageEdit, new_document, BULLET_STYLES, NUMBER_STYLES
from .spell import SpellChecker, LANGUAGES, WORD_RE

import logging
log = logging.getLogger("omoffice")

LH = QTextBlockFormat.LineHeightTypes

FONT_COLORS = ["#000000", "#404040", "#7F7F7F", "#FFFFFF", "#C00000", "#FF0000", "#FFC000",
               "#FFFF00", "#92D050", "#00B050", "#00B0F0", "#0070C0", "#002060", "#7030A0",
               "#2F5496", "#C55A11", "#BF8F00", "#538135"]
SHADE_COLORS = ["#F2F2F2", "#D9D9D9", "#FFF2CC", "#FCE4D6", "#E2EFDA", "#DDEBF7", "#EDE7F6",
                "#FDE9E7", "#E7F3F8", "#FFFDE7", "#1F2A44", "#2F5496"]
PAGE_COLORS = ["#FFFFFF", "#FFFBEA", "#FDF6EC", "#F4F9F4", "#EEF5FB", "#F6F1FB", "#FBEFF2",
               "#F2F2F2", "#FFF8DC", "#E8F1F2", "#2B2B2B", "#1E2A38"]
WATERMARKS = ["GİZLİ", "TASLAK", "ÖRNEK", "ACİL", "KOPYA", "KİŞİYE ÖZEL"]


class MainWindow(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.settings = app_settings()
        self.path = None
        self.find_dialog = None
        self.font_color = "#C00000"
        self.highlight_color = "#FFFF00"
        self.spell = SpellChecker(self)
        self.editor = PageEdit(self.spell)
        self.editor.author = self.settings.value("author", self.editor.author)
        self.editor.autocorrect = self.settings.value("autocorrect", "1") == "1"
        self.view = EditorView(self.editor)
        self.ruler = Ruler(self.view)
        central = QWidget()
        self.central_layout = QHBoxLayout(central)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)
        left = QVBoxLayout()
        left.setSpacing(0)
        left.addWidget(self.ruler)
        left.addWidget(self.view, 1)
        self.central_layout.addLayout(left, 1)
        self.setCentralWidget(central)
        self.session = uuid.uuid4().hex[:12]
        self._crashing = False
        # Kurtarma kopyası: değişiklikten 15 sn sonra ve her dakika
        self.autosave = QTimer(self, interval=60_000, timeout=self._autosave)
        self.autosave_soon = QTimer(self, singleShot=True, interval=15_000, timeout=self._autosave)
        self.resize(1320, 880)
        self.actions = {}
        self.tts = None
        self.focus_mode = False
        self._build_actions()
        self._build_ribbon()
        self._build_status()
        self._build_nav()
        self._build_comments()
        self._build_guide()
        self._build_minibar()
        self._connect_editor()
        self.apply_theme(self.settings.value("theme", "Açık"), self.settings.value("accent", "Lacivert"))
        ruler_on = self.settings.value("ruler", "1") == "1"
        self.ruler.setVisible(ruler_on)
        self.actions["ruler"].setChecked(ruler_on)
        self.actions["autocorrect"].setChecked(self.editor.autocorrect)
        QTimer.singleShot(0, lambda: self.view.set_zoom(float(self.settings.value("zoom", 1.0))))
        self.spell.loaded.connect(lambda _: self.editor.highlighter.rehighlight())
        lang = self.settings.value("spell_lang", "tr_TR")
        self.set_spell_language(None if lang == "off" else lang)
        self.autosave.start()
        # Kurulum sırasındaki biçim ayarları kullanıcı değişikliği sayılmasın: boş belge "kaydedilsin mi?" diye sormasın
        self.editor.document().clearUndoRedoStacks()
        self.editor.document().setModified(False)
        self.update_title()
        self.update_format_state()
        self.start_screen = path is None
        if path:
            self.open_path(path)
        else:
            QTimer.singleShot(300, self._startup)

    # ================================================================ eylemler
    def act(self, key, text, slot=None, shortcut=None, icon=None, checkable=False, tip=None):
        a = QAction(text, self)
        if icon is not None:
            a.setIcon(icon)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        a.setCheckable(checkable)
        tt = tip or text
        if shortcut:
            tt += f" ({QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)})"
        a.setToolTip(tt)
        if slot is not None:
            a.triggered.connect(slot)
        self.addAction(a)
        self.actions[key] = a
        return a

    def _build_actions(self):
        e = self.editor
        A = self.act
        A("new", "Yeni", self.file_new, "Ctrl+N", glyph(""))
        A("open", "Aç", self.file_open, "Ctrl+O", glyph(""))
        A("save", "Kaydet", self.file_save, "Ctrl+S", glyph(""))
        A("saveas", "Farklı Kaydet", self.file_save_as, "Ctrl+Shift+S", glyph(""))
        A("pdf", "PDF Olarak Dışa Aktar", self.export_pdf, None, text_icon("PDF", scale=0.32, bold=True, color="#C62828"))
        A("print", "Yazdır", self.file_print, "Ctrl+P", glyph(""))
        A("preview", "Baskı Önizleme", self.print_preview, None, glyph(""))
        A("quit", "Çıkış", self.close, None)
        A("undo", "Geri Al", e.undo, "Ctrl+Z", glyph(""))
        A("redo", "Yinele", e.redo, "Ctrl+Y", glyph(""))
        A("cut", "Kes", e.cut, "Ctrl+X", glyph(""))
        A("copy", "Kopyala", e.copy, "Ctrl+C", glyph(""))
        A("paste", "Yapıştır", e.paste, "Ctrl+V", glyph(""))
        A("paste_plain", "Yalnızca metni yapıştır", self.paste_plain, "Ctrl+Shift+V")
        A("painter", "Biçim Boyacısı", self.format_painter, None, glyph(""), True)
        A("bold", "Kalın", lambda c: self.set_weight(c), "Ctrl+B", text_icon("K", bold=True), True)
        A("italic", "İtalik", lambda c: self.char(lambda f: f.setFontItalic(c)), "Ctrl+I",
          glyph("T", font="Georgia", italic=True, scale=0.6), True)
        A("underline", "Altı Çizili", lambda c: self.char(lambda f: f.setFontUnderline(c)), "Ctrl+U",
          text_icon("A", underline=True), True)
        A("strike", "Üstü Çizili", lambda c: self.char(lambda f: f.setFontStrikeOut(c)), None,
          text_icon("abc", strike=True, scale=0.4), True)
        A("sub", "Alt Simge", lambda c: self.set_valign(QTextCharFormat.VerticalAlignment.AlignSubScript if c else None),
          "Ctrl+=", text_icon("x₂", scale=0.45), True)
        A("sup", "Üst Simge", lambda c: self.set_valign(QTextCharFormat.VerticalAlignment.AlignSuperScript if c else None),
          "Ctrl+Shift+=", text_icon("x²", scale=0.45), True)
        A("grow", "Yazı Tipini Büyüt", lambda: self.step_font(1), "Ctrl+Shift+>", glyph(""))
        A("shrink", "Yazı Tipini Küçült", lambda: self.step_font(-1), "Ctrl+Shift+<", glyph(""))
        A("clear", "Tüm Biçimlendirmeyi Temizle", e.clear_formatting, "Ctrl+Space",
          text_icon("A✕", scale=0.4, color="#B23B3B"))
        A("color", "Yazı Tipi Rengi", lambda: self.apply_font_color(self.font_color), None,
          text_icon("A", bar=self.font_color, scale=0.55))
        A("highlight", "Metin Vurgu Rengi", lambda: self.apply_highlight(self.highlight_color), None,
          glyph("", bar=self.highlight_color, scale=0.45))
        self.align_group = QActionGroup(self)
        for key, text, sc, ch, flag in (
                ("left", "Sola Hizala", "Ctrl+L", "", Qt.AlignmentFlag.AlignLeft),
                ("center", "Ortala", "Ctrl+E", "", Qt.AlignmentFlag.AlignHCenter),
                ("right", "Sağa Hizala", "Ctrl+R", "", Qt.AlignmentFlag.AlignRight),
                ("justify", "İki Yana Yasla", "Ctrl+J", None, Qt.AlignmentFlag.AlignJustify)):
            icon = glyph(ch) if ch else text_icon("☰", scale=0.55)
            a = A(key, text, lambda _=False, f=flag: self.set_alignment(f), sc, icon, True)
            self.align_group.addAction(a)
        A("bullets", "Madde İşaretleri", lambda: e.toggle_list(QTextListFormat.Style.ListDisc), None,
          glyph(""))
        A("numbers", "Numaralandırma", lambda: e.toggle_list(QTextListFormat.Style.ListDecimal), None,
          text_icon("1.\n2.", scale=0.3, bold=True))
        A("indent", "Girintiyi Artır", lambda: e.change_list_level(1), None, text_icon("⇥", scale=0.6))
        A("outdent", "Girintiyi Azalt", lambda: e.change_list_level(-1), None, text_icon("⇤", scale=0.6))
        A("paragraph", "Paragraf Ayarları…", self.paragraph_dialog, None, text_icon("¶", scale=0.6))
        A("marks", "Biçimlendirme İşaretlerini Göster", lambda c: e.set_show_marks(c), "Ctrl+*",
          text_icon("¶", scale=0.6, color="accent", bold=True), True)
        A("find", "Bul", self.show_find, "Ctrl+F", glyph(""))
        A("replace", "Değiştir", self.show_find, "Ctrl+H", glyph(""))
        A("selectall", "Tümünü Seç", e.selectAll, "Ctrl+A", glyph(""))
        # Ekle
        A("pagebreak", "Sayfa Sonu", e.insert_page_break, "Ctrl+Return", glyph(""))
        A("table", "Tablo", self.insert_table, None, glyph(""))
        A("image", "Resim", self.insert_image, None, glyph(""))
        A("link", "Bağlantı", self.insert_link, "Ctrl+K", glyph(""))
        A("hr", "Yatay Çizgi", e.insert_horizontal_rule, None, text_icon("―", scale=0.6))
        A("symbol", "Simge", self.insert_symbol, None, text_icon("Ω", scale=0.6))
        A("date", "Tarih ve Saat", self.insert_date, None, glyph(""))
        A("toc", "İçindekiler", self.insert_toc, None, glyph("", color="accent"))
        self.shade_color = "#DDEBF7"
        A("header", "Üst / Alt Bilgi", lambda: self.page_setup(2), None, glyph(""))
        A("pagenum", "Sayfa Numarası", self.add_page_numbers, None, text_icon("#", scale=0.6, bold=True))
        # Düzen
        A("pagesetup", "Sayfa Yapısı…", lambda: self.page_setup(0), None, glyph(""))
        A("portrait", "Dikey", lambda: self.set_orientation(False), None, text_icon("▯", scale=0.7), True)
        A("landscape", "Yatay", lambda: self.set_orientation(True), None, text_icon("▭", scale=0.7), True)
        for key, text, op in (("row_above", "Üste Satır", "row_above"), ("row_below", "Alta Satır", "row_below"),
                              ("col_left", "Sola Sütun", "col_left"), ("col_right", "Sağa Sütun", "col_right"),
                              ("del_row", "Satırı Sil", "del_row"), ("del_col", "Sütunu Sil", "del_col"),
                              ("merge", "Hücreleri Birleştir", "merge"), ("split", "Hücreyi Böl", "split"),
                              ("del_table", "Tabloyu Sil", "delete")):
            A(key, text, lambda _=False, op=op: self.editor.table_op(op))
        A("cellcolor", "Hücre Rengi…", self.cell_color)
        # Gözden geçir
        A("spellnext", "Sonraki Yazım Hatası", self.next_spelling_error, "F7", text_icon("abc✓", scale=0.3, bold=True))
        A("wordcount", "Sözcük Sayısı", self.word_count, None, text_icon("123", scale=0.35, bold=True))
        A("track", "Değişiklikleri İzle", self.toggle_track, "Ctrl+Shift+E", glyph(""), True)
        A("accept", "Kabul Et", lambda: self._tc(lambda: e.tc_resolve_current(True)), None,
          glyph("", color="#2E7D32"))
        A("reject", "Reddet", lambda: self._tc(lambda: e.tc_resolve_current(False)), None,
          glyph("", color="#C62828"))
        A("accept_all", "Tüm Değişiklikleri Kabul Et", lambda: self._tc(lambda: e.tc_resolve(True)))
        A("reject_all", "Tüm Değişiklikleri Reddet", lambda: self._tc(lambda: e.tc_resolve(False)))
        A("prev_change", "Önceki", lambda: e.tc_goto(False) or self.statusBar().showMessage("Önceki değişiklik yok", 2500),
          None, glyph(""))
        A("next_change", "Sonraki", lambda: e.tc_goto(True) or self.statusBar().showMessage("Sonraki değişiklik yok", 2500),
          None, glyph(""))
        A("author", "Kullanıcı Adı…", self.set_author, None, glyph(""))
        # Görünüm
        A("nav", "Gezinti Bölmesi", self.toggle_nav, None, glyph(""), True)
        A("fullscreen", "Tam Ekran", self.toggle_fullscreen, "F11", glyph(""), True)
        A("ruler", "Cetvel", self.toggle_ruler, None, text_icon("📏", scale=0.55), True)
        A("focus", "Odak Modu", self.toggle_focus, "Ctrl+Shift+F", glyph("\uE7B3"), True)
        A("zoom_in", "Yakınlaştır", lambda: self.view.set_zoom(self.view.zoom * 1.1), "Ctrl++", glyph("\uE8A3"))
        A("zoom_out", "Uzaklaştır", lambda: self.view.set_zoom(self.view.zoom / 1.1), "Ctrl+-", glyph("\uE71F"))
        A("zoom_100", "%100", lambda: self.view.set_zoom(1.0), "Ctrl+0", text_icon("1:1", scale=0.42, bold=True))
        A("fit_width", "Sayfa Genişliği", self.view.fit_width, None, glyph("\uE9A6"))
        A("fit_page", "Tüm Sayfa", self.view.fit_page, None, glyph("\uE7C3"))
        A("palette", "Komut Ara…", self.show_palette, "Ctrl+Shift+P", glyph("\uE721"))
        self.actions["palette"].setShortcuts([QKeySequence("Ctrl+Shift+P"), QKeySequence("Alt+Q")])
        A("ribbon_toggle", "Şeridi Daralt / Genişlet", self.toggle_ribbon, "Ctrl+F1", glyph("\uE70E"))
        A("start", "Başlangıç Ekranı", self.show_start, None, glyph("\uE80F"))
        A("catalog", "Şablon Kataloğu…", lambda: self.show_start(catalog=True), "Ctrl+Shift+N", glyph("\uE8F1"))
        A("recover", "Kaydedilmemiş Belgeleri Kurtar…", self.show_recovery, None, glyph("\uE777"))
        A("check_updates", "Güncellemeleri Denetle…", lambda: self.check_updates(manual=True), None, glyph(""))
        A("auto_update", "Açılışta Güncellemeleri Denetle", self.set_auto_update, None, None, True,
          "Açıksa OmOffice günde en fazla bir kez GitHub'dan yalnızca en son sürüm numarasını sorar")
        A("shortcuts", "Klavye Kısayolları", self.show_shortcuts, "F1", glyph("\uE765"))
        A("open_folder", "Dosya Konumunu Aç", self.open_folder, None, glyph("\uE838"))
        A("copy_path", "Dosya Yolunu Kopyala", self.copy_path, None, glyph("\uE8C8"))
        A("fix_caps", "Büyük Harf Hatalarını Düzelt", self.fix_caps, None, text_icon("Aa✓", scale=0.34, bold=True))
        A("cite", "Kaynak Ekle…", self.add_citation, "Ctrl+Alt+C", glyph("\uE8F1"))
        A("guide", "Rehber", lambda: self.guide_page.show(), "Ctrl+Shift+G", glyph("\uE82F"))
        # Tasarım
        A("wm_custom", "Özel filigran…", self.custom_watermark)
        A("wm_remove", "Filigranı kaldır", lambda: self._set_setup(watermark=""))
        A("border", "Sayfa Kenarlığı", lambda c: self._set_setup(page_border=c), None, glyph("\uE739"), True)
        A("linenum", "Satır Numaraları", lambda c: self._set_setup(line_numbers=c), None,
          text_icon("1\n2\n3", scale=0.24, bold=True), True)
        # Başvurular
        A("toc_update", "Tabloyu Güncelleştir", self.update_toc, None, glyph("\uE72C"))
        A("footnote", "Dipnot Ekle", self.insert_footnote, "Ctrl+Alt+F", text_icon("ab¹", scale=0.4, bold=True))
        A("footnote_list", "Dipnotları Göster", self.list_footnotes, None, glyph("\uE8FD"))
        # Açıklamalar, okuma, düzeltme
        A("comment", "Yeni Açıklama", self.new_comment, "Ctrl+Alt+M", glyph("\uE90A"))
        A("comments_pane", "Açıklamalar Bölmesi", self.toggle_comments, None, glyph("\uE8BD"), True)
        A("comment_del_all", "Tüm açıklamaları sil", self.delete_all_comments)
        A("speak", "Sesli Oku", self.toggle_speak, "Ctrl+Alt+Space", glyph("\uE767"), True)
        A("autocorrect", "Otomatik Düzelt", self.toggle_autocorrect, None, text_icon("a→A", scale=0.34, bold=True), True)
        A("sort", "Sırala (A→Z)", lambda: self._sort(False), None, text_icon("A↓Z", scale=0.34, bold=True))
        A("sort_desc", "Sırala (Z→A)", lambda: self._sort(True))
        A("shading", "Paragraf Gölgelendirme", lambda: self.editor.set_paragraph_shading(self.shade_color), None,
          glyph("\uE790", bar="#DDEBF7", scale=0.5))

    # ================================================================== şerit
    def _group(self, title, rows):
        """Yan paneldeki kart biçimli araç grubu."""
        frame = QFrame()
        frame.setObjectName("group")
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(3)
        t = QLabel(title.upper())
        t.setObjectName("groupTitle")
        v.addWidget(t)
        if len(rows) == 1:
            for item in rows[0]:
                if isinstance(item, tuple):
                    item = item[0]
                v.addWidget(self._widget(item, big=True), 0, Qt.AlignmentFlag.AlignLeft)
            return frame
        grid = QGridLayout()
        grid.setSpacing(2)
        r = 0
        for row in rows:
            col = 0
            for item in row:
                span = 1
                if isinstance(item, tuple):
                    item, span = item
                if col + span > 8:
                    r += 1
                    col = 0
                grid.addWidget(self._widget(item), r, col, 1, span)
                col += span
            r += 1
        grid.setColumnStretch(8, 1)
        v.addLayout(grid)
        return frame

    @staticmethod
    def _wide(b):
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setIconSize(QSize(20, 20))
        b.setMinimumHeight(32)
        b.setText(b.text().replace("\n", " "))
        b.setObjectName("wideButton")
        return b

    def _widget(self, item, big=False):
        if isinstance(item, QWidget):
            if big and isinstance(item, QToolButton):
                self._wide(item)
            return item
        b = QToolButton()
        b.setDefaultAction(self.actions[item])
        if big:
            return self._wide(b)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setIconSize(QSize(20, 20))
        return b

    def _big(self, key, menu=None):
        b = QToolButton()
        b.setDefaultAction(self.actions[key])
        self._wide(b)
        if menu is not None:
            b.setMenu(menu)
            b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        return b

    def _small(self, key, menu=None, text=False):
        b = QToolButton()
        b.setDefaultAction(self.actions[key])
        b.setIconSize(QSize(20, 20))
        if text:
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        if menu is not None:
            b.setMenu(menu)
            b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        return b

    def _menu_button(self, text, menu, icon=None, big=False):
        b = QToolButton()
        b.setText(text.replace("\n", " "))
        if icon:
            b.setIcon(icon)
        b.setMenu(menu)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        if big:
            self._wide(b)
        else:
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setIconSize(QSize(20, 20))
        return b

    def _build_topbar(self):
        bar = theme.GlassFrame("bar")
        bar.setObjectName("topBar")
        bar.setFixedHeight(48)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 8, 0)
        h.setSpacing(6)
        file_btn = QToolButton()
        file_btn.setObjectName("fileButton")
        file_btn.setText("Dosya")
        file_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        file_btn.setFixedHeight(48)
        self.file_menu = QMenu(self)
        file_btn.setMenu(self.file_menu)
        self.file_menu.aboutToShow.connect(self._fill_file_menu)
        h.addWidget(file_btn)
        emblem = QLabel()
        emblem.setObjectName("appEmblem")
        pm = QPixmap(os.path.join(resource_dir(), "omoffice.png"))
        if not pm.isNull():
            dpr = self.devicePixelRatioF()
            pm = pm.scaled(round(24 * dpr), round(24 * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            emblem.setPixmap(pm)
            h.addWidget(emblem)
        logo = QLabel("OmOffice")
        logo.setObjectName("appName")
        h.addWidget(logo)
        h.addSpacing(16)
        tv = QVBoxLayout()
        tv.setSpacing(0)
        tv.setContentsMargins(0, 4, 0, 4)
        self.title_label = QLabel()
        self.title_label.setObjectName("docTitle")
        self.path_btn = QToolButton()
        self.path_btn.setObjectName("docPath")
        self.path_btn.clicked.connect(self.open_folder)
        tv.addWidget(self.title_label)
        tv.addWidget(self.path_btn)
        h.addLayout(tv)
        h.addStretch(1)
        self.search_box = QLineEdit()
        self.search_box.setObjectName("ribbonSearch")
        self.search_box.setPlaceholderText("🔍  Ne yapmak istiyorsunuz? (Alt+Q)")
        self.search_box.setReadOnly(True)
        self.search_box.mousePressEvent = lambda _e: self.show_palette()
        h.addWidget(self.search_box)
        h.addSpacing(8)
        for k, ch in (("save", "\uE74E"), ("undo", "\uE7A7"), ("redo", "\uE7A6"), ("print", "\uE749"),
                      ("shortcuts", "\uE765"), ("ribbon_toggle", "\uE89F")):
            b = QToolButton()
            b.setDefaultAction(self.actions[k])
            b.setIcon(glyph(ch, color="#FFFFFF"))
            b.setObjectName("quickButton")
            b.setIconSize(QSize(17, 17))
            h.addWidget(b)
        self.topbar = bar

    def _color_menu(self, colors, on_pick, none_label=None, columns=6):
        menu = QMenu(self)
        w = QWidget()
        g = QGridLayout(w)
        g.setSpacing(3)
        g.setContentsMargins(6, 6, 6, 6)
        for i, c in enumerate(colors):
            b = QToolButton()
            b.setFixedSize(22, 22)
            b.setStyleSheet(f"QToolButton {{ background: {c}; border: 1px solid #999; border-radius: 2px; }}"
                            f"QToolButton:hover {{ border: 2px solid #333; }}")
            b.setToolTip(c)
            b.clicked.connect(lambda _=False, c=c: (menu.close(), on_pick(c)))
            g.addWidget(b, i // columns, i % columns)
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(w)
        menu.addAction(wa)
        if none_label:
            menu.addAction(none_label, lambda: on_pick(None))
        menu.addAction("Diğer renkler…", lambda: self._pick_color(on_pick))
        return menu

    def _pick_color(self, on_pick):
        c = QColorDialog.getColor(parent=self)
        if c.isValid():
            on_pick(c.name())

    def _build_ribbon(self):
        rib = SidePanel()
        self._build_topbar()

        def page(*groups):
            w = QWidget()
            w.setObjectName("ribbonPage")
            v = QVBoxLayout(w)
            v.setContentsMargins(8, 8, 8, 8)
            v.setSpacing(8)
            for g in groups:
                v.addWidget(g)
            v.addStretch(1)
            return w

        # ---- Giriş
        paste_menu = QMenu(self)
        paste_menu.addAction(self.actions["paste"])
        paste_menu.addAction(self.actions["paste_plain"])
        self.font_box = QFontComboBox()
        self.font_box.setMaximumWidth(170)
        self.font_box.textActivated.connect(lambda fam: (self.char(lambda f: f.setFontFamilies([fam])),
                                                         self.view.focus_editor()))
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.addItems([str(s) for s in (8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72)])
        self.size_box.setFixedWidth(60)
        self.size_box.textActivated.connect(self._size_chosen)
        self.size_box.lineEdit().returnPressed.connect(lambda: self._size_chosen(self.size_box.currentText()))
        case_menu = QMenu(self)
        for label, mode in (("Cümle düzeni.", "sentence"), ("küçük harf", "lower"), ("BÜYÜK HARF", "upper"),
                            ("Her Sözcüğün İlk Harfi Büyük", "title")):
            case_menu.addAction(label, lambda m=mode: self.editor.change_case(m))
        case_btn = self._menu_button("", case_menu, text_icon("Aa", scale=0.45))
        case_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        case_btn.setToolTip("Büyük/Küçük Harf Değiştir")
        self.color_btn = self._small("color", self._color_menu(FONT_COLORS, self._font_color_picked, "Otomatik"))
        self.hl_btn = self._small("highlight", self._color_menu(list(HIGHLIGHTS.values())[:15],
                                                                 self._highlight_picked, "Renk yok", 5))
        bullet_menu = QMenu(self)
        for label, st in (("● Dolu daire", BULLET_STYLES[0]), ("○ Boş daire", BULLET_STYLES[1]),
                          ("■ Kare", BULLET_STYLES[2])):
            bullet_menu.addAction(label, lambda st=st: self.editor.toggle_list(st))
        number_menu = QMenu(self)
        for label, st in (("1. 2. 3.", QTextListFormat.Style.ListDecimal),
                          ("a. b. c.", QTextListFormat.Style.ListLowerAlpha),
                          ("A. B. C.", QTextListFormat.Style.ListUpperAlpha),
                          ("i. ii. iii.", QTextListFormat.Style.ListLowerRoman),
                          ("I. II. III.", QTextListFormat.Style.ListUpperRoman)):
            number_menu.addAction(label, lambda st=st: self.editor.toggle_list(st))
        spacing_menu = QMenu(self)
        for v in (100, 115, 150, 200, 250, 300):
            spacing_menu.addAction(f"{v / 100:.2f}".rstrip("0").rstrip(".").replace(".", ","),
                                   lambda v=v: self.set_line_spacing(v))
        spacing_menu.addSeparator()
        spacing_menu.addAction("Paragraftan önce boşluk ekle/kaldır", lambda: self.toggle_space("top"))
        spacing_menu.addAction("Paragraftan sonra boşluk ekle/kaldır", lambda: self.toggle_space("bottom"))
        spacing_menu.addAction("Satır aralığı seçenekleri…", self.paragraph_dialog)
        spacing_btn = self._menu_button("", spacing_menu, text_icon("↕≡", scale=0.38))
        spacing_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        spacing_btn.setToolTip("Satır ve Paragraf Aralığı")
        self.style_box = QComboBox()
        self.style_box.addItems(list(STYLES))
        self.style_box.setMinimumWidth(130)
        self.style_box.textActivated.connect(lambda n: (self.editor.apply_style(n), self.view.focus_editor()))
        style_btns = QWidget()
        sl = QGridLayout(style_btns)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(3)
        for si, name in enumerate(("Normal", "Başlık 1", "Başlık 2", "Konu Başlığı")):
            lvl, size, bold, italic, color, _ = STYLES[name]
            b = QToolButton()
            b.setText(name)
            b.setFixedHeight(44)
            f = QFont(b.font())
            f.setPointSizeF(min(13, max(9, (size or 11) * 0.7)))
            f.setBold(bold)
            b.setFont(f)
            b.setProperty("style_color", color or "")
            self.style_chips = getattr(self, "style_chips", []) + [b]
            b.clicked.connect(lambda _=False, n=name: (self.editor.apply_style(n), self.view.focus_editor()))
            sl.addWidget(b, si // 2, si % 2)
        home = page(
            self._group("Pano", [[self._big("paste", paste_menu), self._col("cut", "copy", "painter")]]),
            self._group("Yazı Tipi", [
                [(self.font_box, 6), (self.size_box, 2)],
                ["bold", "italic", "underline", "strike", "sub", "sup", "grow", "shrink"],
                [self.color_btn, self.hl_btn, case_btn, "clear"],
            ]),
            self._group("Paragraf", [
                [self._small("bullets", bullet_menu), self._small("numbers", number_menu), "outdent", "indent",
                 "marks"],
                ["left", "center", "right", "justify", spacing_btn,
                 self._small("shading", self._color_menu(SHADE_COLORS, self._shade_picked, "Gölgelendirme yok")),
                 self._small("sort", self._mk_menu("sort", "sort_desc")), "paragraph"],
            ]),
            self._group("Stiller", [[style_btns], [self.style_box]]),
            self._group("Düzenleme", [[self._col("find", "replace", "selectall")]]),
        )
        rib.add_page("Giriş", glyph("\uE80F"), home)

        # ---- Ekle
        hf_menu = QMenu(self)
        hf_menu.addAction("Üst / alt bilgiyi düzenle…", lambda: self.page_setup(2))
        hf_menu.addAction("Üst / alt bilgiyi kaldır", self.remove_header_footer)
        insert = page(
            self._group("Sayfalar", [[self._big("pagebreak")]]),
            self._group("Tablolar", [[self._big("table", self._table_grid_menu())]]),
            self._group("Çizimler", [[self._big("image"), self._big("hr")]]),
            self._group("Bağlantılar", [[self._big("link")]]),
            self._group("Üst ve Alt Bilgi", [[self._big("header", hf_menu), self._big("pagenum")]]),
            self._group("Açıklamalar", [[self._big("comment")]]),
            self._group("Metin", [[self._big("date"), self._big("footnote")]]),
            self._group("Simgeler", [[self._big("symbol")]]),
        )
        rib.add_page("Ekle", glyph("\uE710"), insert)

        # ---- Tasarım
        wm_menu = QMenu(self)
        for w in WATERMARKS:
            wm_menu.addAction(w, lambda w=w: self._set_setup(watermark=w))
        wm_menu.addSeparator()
        wm_menu.addAction(self.actions["wm_custom"])
        wm_menu.addAction(self.actions["wm_remove"])
        theme_menu = QMenu(self)
        for name in THEMES:
            theme_menu.addAction(f"{name} tema", lambda n=name: self.apply_theme(n, None, animate=True))
        theme_menu.addSeparator()
        for name in ACCENTS:
            theme_menu.addAction(text_icon("●", color=ACCENTS[name], scale=0.8), f"Vurgu: {name}",
                                 lambda n=name: self.apply_theme(None, n, animate=True))
        design = page(
            self._group("Sayfa Arka Planı", [[
                self._menu_button("Filigran", wm_menu, text_icon("Ⓦ", scale=0.6), True),
                self._menu_button("Sayfa\nRengi", self._color_menu(PAGE_COLORS, self._page_color_picked,
                                                                    "Renk yok", 6), glyph("\uE790"), True),
                self._big("border")]]),
            self._group("Uygulama Görünümü", [[self._menu_button("Tema ve\nRenk", theme_menu, glyph("\uE771"), True)]]),
        )
        rib.add_page("Tasarım", glyph("\uE771"), design)

        # ---- Düzen
        margin_menu = QMenu(self)
        for name, (t, b, l, r) in MARGIN_PRESETS.items():
            margin_menu.addAction(f"{name}  (Üst {t:g} · Alt {b:g} · Sol {l:g} · Sağ {r:g} mm)",
                                  lambda m=(t, b, l, r): self.set_margins(*m))
        margin_menu.addSeparator()
        margin_menu.addAction("Özel kenar boşlukları…", lambda: self.page_setup(1))
        size_menu = QMenu(self)
        for name, (w, h) in PAPER_SIZES.items():
            size_menu.addAction(f"{name}  ({w:g} × {h:g} mm)", lambda wh=(w, h): self.set_paper(*wh))
        size_menu.addSeparator()
        size_menu.addAction("Diğer kağıt boyutları…", lambda: self.page_setup(0))
        self.orient_group = QActionGroup(self)
        self.orient_group.addAction(self.actions["portrait"])
        self.orient_group.addAction(self.actions["landscape"])
        layout = page(
            self._group("Sayfa Yapısı", [[
                self._menu_button("Kenar\nBoşlukları", margin_menu, glyph(""), True),
                self._big("portrait"), self._big("landscape"),
                self._menu_button("Boyut", size_menu, glyph(""), True),
                self._big("pagesetup"), self._big("linenum")]]),
            self._group("Paragraf", [[self._col("indent", "outdent", "paragraph")]]),
            self._group("Tablo — Satır ve Sütun", [
                [self._txt("row_above"), self._txt("col_left"), self._txt("del_row")],
                [self._txt("row_below"), self._txt("col_right"), self._txt("del_col")],
            ]),
            self._group("Tablo — Hücreler", [
                [self._txt("merge"), self._txt("cellcolor")],
                [self._txt("split"), self._txt("del_table")],
            ]),
        )
        rib.add_page("Düzen", glyph("\uE7C3"), layout)

        toc_menu = QMenu(self)
        toc_menu.addAction(self.actions["toc"])
        toc_menu.addAction(self.actions["toc_update"])
        refs = page(
            self._group("İçindekiler", [[self._big("toc", toc_menu), self._big("toc_update")]]),
            self._group("Dipnotlar", [[self._big("footnote"), self._big("footnote_list")]]),
            self._group("Kaynakça", [[self._big("cite")]]),
        )
        rib.add_page("Başvurular", glyph("\uE8F1"), refs)

        # ---- Gözden Geçir
        lang_menu = QMenu(self)
        self.lang_group = QActionGroup(self)
        for code, label in list(LANGUAGES.items()) + [("off", "Denetim kapalı")]:
            a = lang_menu.addAction(label)
            a.setCheckable(True)
            a.setData(code)
            self.lang_group.addAction(a)
            a.triggered.connect(lambda _=False, c=code: self.set_spell_language(None if c == "off" else c))
        self.lang_btn = self._menu_button("Dil", lang_menu, glyph(""), True)
        review = page(
            self._group("Yazım Denetimi", [[self._big("spellnext"), self.lang_btn, self._big("autocorrect"), self._big("fix_caps")]]),
            self._group("Sayım ve Ses", [[self._big("wordcount"), self._big("speak")]]),
            self._group("Açıklamalar", [[self._big("comment"), self._big("comments_pane", self._mk_menu(
                "comments_pane", "comment_del_all"))]]),
            self._group("İzleme", [[self._big("track"), self._big("author")]]),
            self._group("Değişiklikler", [[
                self._big("accept", self._mk_menu("accept", "accept_all")),
                self._big("reject", self._mk_menu("reject", "reject_all")),
                self._col("prev_change", "next_change")]]),
        )
        rib.add_page("Gözden Geçir", glyph("\uE8FB"), review)

        # ---- Görünüm
        view = page(
            self._group("Göster", [[self._big("nav"), self._big("ruler"), self._big("marks"),
                                    self._big("comments_pane")]]),
            self._group("Yakınlaştır", [[self._big("zoom_100"), self._big("fit_width"), self._big("fit_page"),
                                         self._col("zoom_in", "zoom_out")]]),
            self._group("Odak", [[self._big("focus"), self._big("fullscreen")]]),
            self._group("Tema", [[self._menu_button("Tema ve\nRenk", theme_menu, glyph("\uE771"), True)]]),
        )
        rib.add_page("Görünüm", glyph("\uE7B3"), view)

        rib.add_rail_action(self.actions["ribbon_toggle"], glyph("\uE89F"))
        self.ribbon = rib
        self.setMenuWidget(self.topbar)
        self.central_layout.addWidget(rib)

    def _mk_menu(self, *keys):
        m = QMenu(self)
        for k in keys:
            m.addAction(self.actions[k])
        return m

    def _txt(self, key):
        b = QToolButton()
        b.setDefaultAction(self.actions[key])
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        return b

    def _col(self, *keys):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(1)
        for k in keys:
            v.addWidget(self._small(k, text=True))
        return w

    def _table_grid_menu(self):
        menu = QMenu(self)
        w = QWidget()
        g = QGridLayout(w)
        g.setSpacing(2)
        g.setContentsMargins(6, 6, 6, 6)
        label = QLabel("Tablo ekle")
        cells = {}

        t = CURRENT["theme"]
        on = theme.tint(theme.derived(t, CURRENT["accent"])["accent_ui"], t["input"], 0.45)
        cell_off = f"background: {t['input']}; border: 1px solid {t['input_border']};"
        cell_on = f"background: {on}; border: 1px solid {theme.derived(t, CURRENT['accent'])['accent_ui']};"

        def hover(r, c):
            label.setText(f"{c + 1} × {r + 1} Tablo")
            for (rr, cc), b in cells.items():
                b.setStyleSheet(cell_on if rr <= r and cc <= c else cell_off)

        for r in range(8):
            for c in range(10):
                b = QToolButton()
                b.setFixedSize(16, 16)
                b.setStyleSheet(cell_off)
                b.setMouseTracking(True)
                b.enterEvent = lambda _e, r=r, c=c: hover(r, c)
                b.clicked.connect(lambda _=False, r=r, c=c: (menu.close(), self.editor.insert_table(r + 1, c + 1)))
                cells[(r, c)] = b
                g.addWidget(b, r + 1, c)
        g.addWidget(label, 0, 0, 1, 10)
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(w)
        menu.addAction(wa)
        menu.addAction("Tablo ekle…", self.insert_table)
        return menu

    def _fill_file_menu(self):
        m = self.file_menu
        m.clear()
        for k in ("new", "catalog", "open", "save", "saveas"):
            m.addAction(self.actions[k])
        recent = m.addMenu("Son Kullanılanlar")
        files = self.settings.value("recent", []) or []
        if isinstance(files, str):
            files = [files]
        files = [f for f in files if os.path.exists(f)]
        for f in files[:10]:
            a = recent.addAction(f"{os.path.basename(f)}    —    {os.path.dirname(f)}",
                                 lambda f=f: self.open_path(f) if self.maybe_save() else None)
            a.setToolTip(f)
        if not files:
            recent.addAction("(boş)").setEnabled(False)
        imp = m.addMenu("İçe Aktar")
        for label, kind in (("Word belgesi / şablonu (.docx, .dotx, .docm)…", "word"),
                            ("OpenDocument metni (.odt)…", "odt"), ("PDF belgesi (.pdf)…", "pdf"),
                            ("Web sayfası (.html)…", "html"),
                            ("Markdown (.md)…", "md"), ("Düz metin (.txt)…", "txt")):
            imp.addAction(label, lambda k=kind: self.file_open(k))
        exp = m.addMenu("Dışa Aktar")
        exp.addAction(self.actions["pdf"])
        for label, ext in (("Word kopyası (.docx)…", ".docx"), ("OpenDocument (.odt)…", ".odt"),
                           ("Web sayfası (.html)…", ".html"), ("Markdown (.md)…", ".md"),
                           ("Düz metin (.txt)…", ".txt")):
            exp.addAction(label, lambda e=ext: self.export_as(e))
        m.addSeparator()
        for k in ("print", "preview"):
            m.addAction(self.actions[k])
        m.addSeparator()
        for k in ("open_folder", "copy_path"):
            self.actions[k].setEnabled(bool(self.path))
            m.addAction(self.actions[k])
        m.addAction(self.actions["recover"])
        m.addSeparator()
        m.addAction("Sayfa Yapısı…", lambda: self.page_setup(0))
        for k in ("start", "palette", "shortcuts"):
            m.addAction(self.actions[k])
        m.addAction("Hakkında", self.about)
        m.addAction(self.actions["check_updates"])
        self.actions["auto_update"].setChecked(self.settings.value("update_check") == "1")
        m.addAction(self.actions["auto_update"])
        m.addSeparator()
        m.addAction(self.actions["quit"])

    # ============================================================= durum çubuğu
    def _build_status(self):
        sb = self.statusBar()
        self.page_label = QLabel()
        self.words_label = QLabel()
        self.lang_label = QLabel()
        self.track_label = QLabel()
        for w in (self.page_label, self.words_label, self.lang_label):
            sb.addWidget(w)
        sb.addPermanentWidget(self.track_label)
        for k in ("comments_pane", "focus", "fit_width"):
            b = QToolButton()
            b.setDefaultAction(self.actions[k])
            b.setIcon(glyph({"comments_pane": "\uE8BD", "focus": "\uE7B3", "fit_width": "\uE9A6"}[k], color="#FFFFFF"))
            b.setIconSize(QSize(14, 14))
            sb.addPermanentWidget(b)
        zo = QToolButton()
        zo.setText("−")
        zo.clicked.connect(self.actions["zoom_out"].trigger)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(20, 400)
        self.zoom_slider.setFixedWidth(130)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(lambda v: abs(v - self.view.zoom * 100) > 0.6 and self.view.set_zoom(v / 100))
        zi = QToolButton()
        zi.setText("+")
        zi.clicked.connect(self.actions["zoom_in"].trigger)
        self.zoom_label = QToolButton()
        self.zoom_label.setText("%100")
        self.zoom_label.setToolTip("Yakınlaştırma — tıklayın: %100")
        self.zoom_label.clicked.connect(lambda: self.view.set_zoom(1.0))
        for w in (zo, self.zoom_slider, zi, self.zoom_label):
            sb.addPermanentWidget(w)
        self.view.zoomChanged.connect(self._zoom_changed)
        self.stats_timer = QTimer(self, singleShot=True, interval=350, timeout=self.update_stats)
        # Yeni sürüm bildirimi: yalnızca denetim yeni bir sürüm bulursa görünür
        self.update_button = QToolButton()
        self.update_button.setObjectName("updateButton")
        self.update_button.setVisible(False)
        self.update_button.clicked.connect(self.open_releases)
        sb.insertPermanentWidget(0, self.update_button)

    def _build_nav(self):
        self.nav_tree = QTreeWidget()
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.itemClicked.connect(self._nav_go)
        self.nav_dock = QDockWidget("Gezinti", self)
        self.nav_dock.setWidget(self.nav_tree)
        self.nav_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.nav_dock)
        self.nav_dock.hide()
        self.nav_dock.visibilityChanged.connect(lambda v: self.actions["nav"].setChecked(v))
        self.nav_timer = QTimer(self, singleShot=True, interval=600, timeout=self.refresh_nav)

    def _connect_editor(self):
        e = self.editor
        e.currentCharFormatChanged.connect(lambda _: self.update_format_state())
        e.cursorPositionChanged.connect(self.update_format_state)
        e.pageInfoChanged.connect(self.stats_timer.start)
        e.headerFooterRequested.connect(lambda: self.page_setup(2))
        e.hfEditRequested.connect(self.edit_page_hf)
        e.imageReplaceRequested.connect(self.replace_image)
        e.hfChanged.connect(self.update_title)
        e.imageEditRequested.connect(self.edit_image)
        e.formatPainterDone.connect(lambda: self.actions["painter"].setChecked(False))
        e.footnoteEditRequested.connect(self.edit_footnote)
        e.newCommentRequested.connect(self.new_comment)
        e.selectionFinished.connect(self._show_minibar)
        e.cursorPositionChanged.connect(self._maybe_hide_minibar)
        e.commentsChanged.connect(self._comments_changed)
        self._connect_document()

    def _connect_document(self):
        doc = self.editor.document()
        doc.modificationChanged.connect(lambda _: self.update_title())
        doc.contentsChanged.connect(self.nav_timer.start)
        doc.contentsChanged.connect(self.autosave_soon.start)
        doc.undoAvailable.connect(self.actions["undo"].setEnabled)
        doc.redoAvailable.connect(self.actions["redo"].setEnabled)
        self.actions["undo"].setEnabled(doc.isUndoAvailable())
        self.actions["redo"].setEnabled(doc.isRedoAvailable())

    # ================================================================== durum
    def update_title(self):
        name = os.path.basename(self.path) if self.path else getattr(self, "_import_name", None) or "Belge1"
        modified = self.editor.document().isModified()
        mod = "● " if modified else ""
        self.setWindowTitle(f"{mod}{name} — {APP_NAME}")
        self.setWindowModified(modified)
        if hasattr(self, "title_label"):
            self.title_label.setText(f"{mod}{name}")
            if self.path:
                fm = self.path_btn.fontMetrics()
                self.path_btn.setText(fm.elidedText(self.path, Qt.TextElideMode.ElideMiddle, 520))
                self.path_btn.setToolTip(f"{self.path}\nKlasörü açmak için tıklayın")
            else:
                self.path_btn.setText("Henüz kaydedilmedi — kaydetmek için Ctrl+S")
                self.path_btn.setToolTip("")

    def update_format_state(self):
        e = self.editor
        cf = e.currentCharFormat()
        fams = cf.fontFamilies() if cf.hasProperty(QTextFormat.Property.FontFamilies) else None
        fam = fams[0] if fams else e.document().defaultFont().family()
        self.font_box.blockSignals(True)
        self.font_box.setCurrentFont(QFont(fam))
        if self.font_box.currentFont().family() != fam:
            # Sistemde kurulu olmayan yazı tipinin (ör. bulut yazı tipi Aptos) adını yine de göster
            self.font_box.setEditText(fam)
        self.font_box.blockSignals(False)
        size = cf.fontPointSize() or e.document().defaultFont().pointSizeF()
        self.size_box.setEditText(f"{size:g}")
        self.actions["bold"].setChecked(cf.fontWeight() >= 600)
        self.actions["italic"].setChecked(cf.fontItalic())
        self.actions["underline"].setChecked(cf.fontUnderline())
        self.actions["strike"].setChecked(cf.fontStrikeOut())
        va = cf.verticalAlignment()
        self.actions["sub"].setChecked(va == QTextCharFormat.VerticalAlignment.AlignSubScript)
        self.actions["sup"].setChecked(va == QTextCharFormat.VerticalAlignment.AlignSuperScript)
        al = e.textCursor().blockFormat().alignment()
        key = ("center" if al & Qt.AlignmentFlag.AlignHCenter else "justify" if al & Qt.AlignmentFlag.AlignJustify
               else "right" if al & Qt.AlignmentFlag.AlignRight else "left")
        self.actions[key].setChecked(True)
        self.style_box.blockSignals(True)
        self.style_box.setCurrentText(e.current_style_name())
        self.style_box.blockSignals(False)
        landscape = e.setup.landscape
        self.actions["landscape" if landscape else "portrait"].setChecked(True)
        in_table = e.textCursor().currentTable() is not None
        for k in ("row_above", "row_below", "col_left", "col_right", "del_row", "del_col", "merge", "split",
                  "del_table", "cellcolor"):
            self.actions[k].setEnabled(in_table)
        self.stats_timer.start()

    def update_stats(self):
        e = self.editor
        text = e.document().toPlainText()
        words = len(WORD_RE.findall(text)) + len(re.findall(r"\b\d+\b", text))
        self.page_label.setText(f"Sayfa {e.current_page()} / {e.page_count()}")
        self.words_label.setText(f"{words:,} sözcük".replace(",", "."))
        lang = self.spell.language
        if lang is None:
            self.lang_label.setText("Yazım denetimi kapalı")
        elif self.spell.ready:
            self.lang_label.setText(LANGUAGES.get(lang, lang))
        else:
            self.lang_label.setText(f"{LANGUAGES.get(lang, lang)} (sözlük yükleniyor…)")
            QTimer.singleShot(1500, self.stats_timer.start)
        self.track_label.setText("● Değişiklikler izleniyor" if e.track_changes else "")

    # ============================================================== biçimler
    def char(self, fn):
        f = QTextCharFormat()
        fn(f)
        self.editor.merge_format(f)

    def set_weight(self, checked):
        self.char(lambda f: f.setFontWeight(QFont.Weight.Bold if checked else QFont.Weight.Normal))

    def set_valign(self, va):
        self.char(lambda f: f.setVerticalAlignment(va or QTextCharFormat.VerticalAlignment.AlignNormal))
        self.update_format_state()

    def _size_chosen(self, text):
        try:
            size = float(text.replace(",", "."))
        except ValueError:
            return
        if 1 <= size <= 1638:
            self.char(lambda f: f.setFontPointSize(size))
            self.view.focus_editor()

    def step_font(self, d):
        steps = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]
        cur = self.editor.currentCharFormat().fontPointSize() or DEFAULT_SIZE
        if d > 0:
            nxt = next((s for s in steps if s > cur), cur + 10)
        else:
            nxt = next((s for s in reversed(steps) if s < cur), max(1, cur - 1))
        self.char(lambda f: f.setFontPointSize(nxt))

    def _font_color_picked(self, color):
        if color is None:
            color = "#000000"
        self.font_color = color
        self.actions["color"].setIcon(text_icon("A", bar=color, scale=0.55))
        self.apply_font_color(color)

    def apply_font_color(self, color):
        self.char(lambda f: f.setForeground(QColor(color)))

    def _highlight_picked(self, color):
        if color is not None:
            self.highlight_color = color
            self.actions["highlight"].setIcon(glyph("", bar=color, scale=0.45))
        self.apply_highlight(color)

    def apply_highlight(self, color):
        c = self.editor.textCursor()
        if color is None:
            if c.hasSelection():
                for a, b, kind, cf in reversed(self.editor.tc_segments(c.selectionStart(), c.selectionEnd())):
                    m = QTextCursor(self.editor.document())
                    m.setPosition(a)
                    m.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
                    f = QTextCharFormat(cf)
                    f.clearBackground()
                    m.setCharFormat(f)
            return
        self.char(lambda f: f.setBackground(QColor(color)))

    def set_alignment(self, flag):
        self.editor.setAlignment(flag | Qt.AlignmentFlag.AlignAbsolute if flag == Qt.AlignmentFlag.AlignLeft else flag)

    def set_line_spacing(self, value):
        c = self.editor.textCursor()
        bf = QTextBlockFormat()
        bf.setLineHeight(value, LH.ProportionalHeight.value)
        c.mergeBlockFormat(bf)

    def toggle_space(self, which):
        c = self.editor.textCursor()
        bf = c.blockFormat()
        cur = bf.topMargin() if which == "top" else bf.bottomMargin()
        new = 0 if cur > 0 else pt2px(12 if which == "top" else 8)
        f = QTextBlockFormat()
        (f.setTopMargin if which == "top" else f.setBottomMargin)(new)
        c.mergeBlockFormat(f)

    def paragraph_dialog(self):
        c = self.editor.textCursor()
        dlg = ParagraphDialog(c.blockFormat(), self)
        if dlg.exec():
            bf = dlg.result_format()
            c.mergeBlockFormat(bf)

    def format_painter(self, checked):
        if checked:
            self.editor.start_format_painter()
            self.statusBar().showMessage("Biçim boyacısı: biçimi uygulamak için metin seçin", 4000)
        else:
            self.editor.painter_format = None
            self.editor.viewport().unsetCursor()

    def paste_plain(self):
        text = QApplication.clipboard().text()
        if text:
            self.editor.type_text(text)

    # ================================================================== ekle
    def insert_table(self):
        dlg = TableDialog(self)
        if dlg.exec():
            self.editor.insert_table(dlg.rows.value(), dlg.cols.value())

    def insert_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Resim Ekle", self._dir(),
                                              "Resimler (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.svg)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, APP_NAME, "Resim açılamadı.")
            return
        self.editor.insert_image(img)
        # eklenen resim seçili gelsin: köşelerinden hemen boyutlandırılabilir
        self.editor._select_image(self.editor.textCursor().position() - 1)
        self.statusBar().showMessage("Resim eklendi. Köşelerinden sürükleyerek boyutlandırabilirsiniz.", 5000)

    def edit_image(self, pos):
        e = self.editor
        fmt = e._image_at(pos)
        if fmt is None:
            return
        _, img = e.image_bytes(fmt.name())
        natural = (img.width(), img.height()) if img is not None else (fmt.width(), fmt.height())
        dlg = ImageSizeDialog(fmt.width() or natural[0], fmt.height() or natural[1], natural, self)
        if dlg.exec():
            w, h = dlg.size_px()
            c = QTextCursor(e.document())
            c.setPosition(pos)
            c.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
            nf = QTextImageFormat(fmt)
            nf.setWidth(w)
            nf.setHeight(h)
            c.setCharFormat(nf)

    def insert_link(self):
        c = self.editor.textCursor()
        cf = c.charFormat()
        dlg = LinkDialog(c.selectedText(), cf.anchorHref() if cf.isAnchor() else "", self)
        if dlg.exec() and dlg.url.text().strip():
            url = dlg.url.text().strip()
            if "://" not in url and not url.startswith(("mailto:", "#")):
                url = "https://" + url
            self.editor.insert_link(dlg.text.text(), url)

    def insert_symbol(self):
        dlg = SymbolDialog(self)
        if dlg.exec() and dlg.choice:
            self.editor.type_text(dlg.choice)

    def insert_date(self):
        now = datetime.datetime.now()
        months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül",
                  "Ekim", "Kasım", "Aralık"]
        days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        options = [now.strftime("%d.%m.%Y"), f"{now.day} {months[now.month - 1]} {now.year}",
                   f"{now.day} {months[now.month - 1]} {now.year} {days[now.weekday()]}",
                   now.strftime("%d.%m.%Y %H:%M"), now.strftime("%H:%M"), now.strftime("%Y-%m-%d")]
        choice, ok = QInputDialog.getItem(self, "Tarih ve Saat", "Biçim:", options, 1, False)
        if ok:
            self.editor.type_text(choice)

    def insert_toc(self):
        if not self.editor.insert_toc():
            QMessageBox.information(self, APP_NAME, "İçindekiler için belgede başlık bulunamadı.\n"
                                                    "Önce Giriş > Stiller'den 'Başlık 1/2/3' uygulayın.")

    def add_page_numbers(self):
        s = self.editor.setup.copy()
        s.footer_text = "Sayfa {SAYFA} / {TOPLAM}"
        s.footer_align = "center"
        self._apply_setup(s)

    def remove_header_footer(self):
        s = self.editor.setup.copy()
        s.header_text = s.footer_text = ""
        self._apply_setup(s)

    # ================================================================= düzen
    def _apply_setup(self, s):
        self.editor.setup = s
        self.editor.apply_page_setup()
        self.editor.document().setModified(True)
        self.update_format_state()

    def page_setup(self, tab=0):
        dlg = PageSetupDialog(self.editor.setup, self, tab)
        if dlg.exec():
            self._apply_setup(dlg.result_setup())

    def set_margins(self, t, b, l, r):
        s = self.editor.setup.copy()
        s.top_mm, s.bottom_mm, s.left_mm, s.right_mm = t, b, l, r
        self._apply_setup(s)

    def set_paper(self, w, h):
        s = self.editor.setup.copy()
        if s.landscape:
            w, h = h, w
        s.width_mm, s.height_mm = w, h
        self._apply_setup(s)

    def set_orientation(self, landscape):
        s = self.editor.setup.copy()
        if s.landscape != landscape:
            s.width_mm, s.height_mm = s.height_mm, s.width_mm
            self._apply_setup(s)

    def cell_color(self):
        c = QColorDialog.getColor(QColor("#DDEBF7"), self, "Hücre Rengi")
        if c.isValid():
            self.editor.set_cell_background(c.name())

    # ========================================================= gözden geçir
    def set_spell_language(self, code):
        self.spell.set_language(code)
        self.settings.setValue("spell_lang", code or "off")
        for a in self.lang_group.actions():
            a.setChecked(a.data() == (code or "off"))
        self.editor.highlighter.rehighlight()
        self.update_stats()

    def next_spelling_error(self):
        if not self.spell.ready:
            self.statusBar().showMessage("Sözlük henüz hazır değil.", 3000)
            return
        e = self.editor
        start = e.textCursor().selectionEnd()
        block = e.document().findBlock(start)
        wrapped = False
        while True:
            while block.isValid():
                for m in WORD_RE.finditer(block.text()):
                    pos = block.position() + m.start()
                    if pos < start and not wrapped:
                        continue
                    if not self.spell.check(m.group()):
                        c = e.textCursor()
                        c.setPosition(pos)
                        c.setPosition(pos + len(m.group()), QTextCursor.MoveMode.KeepAnchor)
                        e.setTextCursor(c)
                        e.ensureCursorVisible()
                        self.statusBar().showMessage(
                            "Öneriler için sağ tıklayın: " + ", ".join(self.spell.suggest(m.group(), 4)), 6000)
                        return
                block = block.next()
            if wrapped:
                break
            wrapped = True
            block = e.document().begin()
        QMessageBox.information(self, APP_NAME, "Yazım denetimi tamamlandı. Hata bulunamadı.")

    def word_count(self):
        e = self.editor
        c = e.textCursor()
        text = c.selection().toPlainText() if c.hasSelection() else e.document().toPlainText()
        words = len(WORD_RE.findall(text)) + len(re.findall(r"\b\d+\b", text))
        chars = len(text.replace("\n", "").replace(" ", ""))
        nospace = len(re.sub(r"\s", "", text))
        paras = len([p for p in text.split("\n") if p.strip()])
        scope = "Seçim" if c.hasSelection() else "Belge"
        QMessageBox.information(self, "Sözcük Sayısı",
                                f"<b>{scope}</b><br><br>Sayfa: {e.page_count()}<br>Sözcük: {words}<br>"
                                f"Karakter (boşluksuz): {nospace}<br>Karakter (boşluklu): {chars}<br>"
                                f"Paragraf: {paras}")

    def toggle_track(self, on):
        self.editor.track_changes = on
        self.update_stats()
        self.statusBar().showMessage("Değişiklik izleme " + ("açık" if on else "kapalı"), 2500)

    def _tc(self, fn):
        n = fn()
        if not n:
            self.statusBar().showMessage("İşlenecek değişiklik yok", 2500)

    def set_author(self):
        name, ok = QInputDialog.getText(self, "Kullanıcı Adı", "Değişikliklerde görünecek ad:",
                                        text=self.editor.author)
        if ok and name.strip():
            self.editor.author = name.strip()
            self.settings.setValue("author", self.editor.author)

    # =============================================================== görünüm
    def toggle_nav(self, on):
        self.nav_dock.setVisible(on)
        if on:
            self.refresh_nav()

    def refresh_nav(self):
        if not self.nav_dock.isVisible():
            return
        t = self.nav_tree
        t.clear()
        stack = []
        for lvl, text, pos in self.editor.headings():
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.ItemDataRole.UserRole, pos)
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            (stack[-1][1].addChild(item) if stack else t.addTopLevelItem(item))
            stack.append((lvl, item))
        t.expandAll()
        if not t.topLevelItemCount():
            t.addTopLevelItem(QTreeWidgetItem(["(Başlık yok — Başlık stillerini kullanın)"]))

    def _nav_go(self, item):
        pos = item.data(0, Qt.ItemDataRole.UserRole)
        if pos is None:
            return
        c = self.editor.textCursor()
        c.setPosition(min(pos, self.editor.document().characterCount() - 1))
        self.editor.setTextCursor(c)
        self.editor.ensureCursorVisible()
        self.view.focus_editor()

    def toggle_fullscreen(self, on):
        self.showFullScreen() if on else self.showNormal()

    def show_find(self):
        if self.find_dialog is None:
            self.find_dialog = FindReplaceDialog(self.editor, self)
        sel = self.editor.textCursor().selectedText()
        if sel and " " not in sel:
            self.find_dialog.find.setText(sel)
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.find.setFocus()
        self.find_dialog.find.selectAll()

    # ================================================================= dosya
    def _dir(self):
        return self.settings.value("last_dir", os.path.join(os.path.expanduser("~"), "Documents"))

    def _remember(self, path):
        self.settings.setValue("last_dir", os.path.dirname(path))
        files = self.settings.value("recent", []) or []
        if isinstance(files, str):
            files = [files]
        files = [path] + [f for f in files if os.path.normcase(f) != os.path.normcase(path)]
        self.settings.setValue("recent", files[:10])

    def maybe_save(self):
        if not self.editor.document().isModified():
            return True
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Belgedeki değişiklikler kaydedilsin mi?")
        box.setInformativeText("Kaydetmezseniz de bir kopya 7 gün boyunca Dosya › Kaydedilmemiş Belgeleri "
                               "Kurtar altında saklanır.")
        save = box.addButton("Kaydet", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Kaydetme", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("İptal", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return self.file_save()
        if box.clickedButton() is discard:
            self._keep_unsaved_copy()
            return True
        return False

    def _set_doc(self, doc, setup, path, meta=None):
        if path is not None:
            self._import_name = None
        self.editor.set_document(doc, setup, meta)
        self._connect_document()
        self.path = path
        self.editor.document().setModified(False)
        self.update_title()
        self.update_format_state()
        self.refresh_nav()

    def file_new(self):
        if self.maybe_save():
            self._import_name = None
            self._set_doc(new_document(), PageSetup(), None)

    OPEN_FILTERS = {
        None: "Desteklenen belgeler (*.docx *.dotx *.docm *.dotm *.odt *.pdf *.html *.htm *.txt *.md);;"
              "Word belgesi (*.docx *.dotx *.docm *.dotm);;OpenDocument metni (*.odt);;PDF belgesi (*.pdf);;"
              "Web sayfası (*.html *.htm);;Düz metin (*.txt);;Markdown (*.md);;Tüm dosyalar (*)",
        "word": "Word belgesi / şablonu (*.docx *.dotx *.docm *.dotm)",
        "odt": "OpenDocument metni (*.odt)",
        "pdf": "PDF belgesi (*.pdf)",
        "html": "Web sayfası (*.html *.htm)",
        "md": "Markdown (*.md)",
        "txt": "Düz metin (*.txt)",
    }

    def file_open(self, kind=None):
        if not self.maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Aç" if kind is None else "İçe Aktar", self._dir(),
                                              self.OPEN_FILTERS.get(kind if isinstance(kind, str) else None))
        if path:
            self.open_path(path)

    def open_path(self, path):
        ext = os.path.splitext(path)[1].lower()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        meta = {}
        try:
            head = b""
            if ext not in (".docx", ".dotx", ".docm", ".dotm", ".odt"):
                with open(path, "rb") as f:
                    head = f.read(8192)
            if ext == ".pdf" or head.startswith(b"%PDF"):
                ext = ".pdf"
                doc, setup, meta = import_pdf(path)
            elif ext in (".docx", ".dotx", ".docm", ".dotm"):
                doc, setup, meta = import_docx(path)
            elif ext == ".odt":
                doc, setup, meta = import_odt(path)
            elif ext in (".doc", ".rtf", ".wps", ".pages"):
                raise UnsafeFileError(
                    f"Eski/başka biçimdeki ({ext}) dosyalar doğrudan açılamıyor.\n"
                    "Ücretsiz LibreOffice ya da Word ile .docx olarak kaydedip yeniden deneyin.")
            else:
                if b"\x00" in head or head[:4] in (b"PK\x03\x04", b"\xd0\xcf\x11\xe0"):
                    raise UnsafeFileError("Bu dosya düz metin değil (ikili ya da desteklenmeyen biçim); "
                                          "açılırsa okunamayan karakterler görünür.")
                if os.path.getsize(path) > 50 * 1024 * 1024:
                    raise UnsafeFileError("Metin dosyası çok büyük (50 MB üstü).")
                doc, setup = new_document(), PageSetup()
                with open(path, encoding="utf-8", errors="replace") as f:
                    data = f.read()
                if ext in (".html", ".htm"):
                    doc.setHtml(sanitize_html(data))
                elif ext == ".md":
                    doc.setMarkdown(sanitize_markdown(data))
                else:
                    QTextCursor(doc).insertText(data)
                doc.setModified(False)
        except (UnsafeFileError, PdfImportError) as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, APP_NAME, f"Dosya açılamadı:\n{path}\n\n{exc}")
            return False
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME, f"Dosya açılamadı (bozuk ya da desteklenmeyen içerik):\n{path}\n\n{exc}")
            return False
        QApplication.restoreOverrideCursor()
        native = ext == ".docx"
        self._import_name = None if native else os.path.splitext(os.path.basename(path))[0] + " (içe aktarıldı)"
        self._set_doc(doc, setup, path if native else None, meta)
        self._remember(path)
        if self.editor.comments:
            self.comments_dock.show()
        if self.editor.has_changes():
            self.statusBar().showMessage("Bu belgede izlenen değişiklikler var — Gözden Geçir panelinden bakın.", 6000)
        if meta.get("warnings"):
            QMessageBox.information(self, APP_NAME, "\n".join(meta["warnings"]))
        if not native:
            self.statusBar().showMessage(
                meta.get("notice") or "İçe aktarıldı. Kaydederken Word (.docx) olarak kaydedilecek.", 9000)
        return True

    def file_save(self):
        if not self.path:
            return self.file_save_as()
        return self.save_to(self.path)

    def file_save_as(self):
        base = getattr(self, "_import_name", None)
        base = base.replace(" (içe aktarıldı)", "") if base else "Belge1"
        start = self.path or os.path.join(self._dir(), base + ".docx")
        path, flt = QFileDialog.getSaveFileName(
            self, "Farklı Kaydet", start,
            "Word belgesi (*.docx);;OpenDocument metni (*.odt);;Web sayfası (*.html);;"
            "Düz metin (*.txt);;Markdown (*.md);;PDF (*.pdf)")
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            m = re.search(r"\*(\.\w+)", flt)
            path += m.group(1) if m else ".docx"
        if path.lower().endswith(".pdf"):
            return self.export_pdf(path)
        ok = self.save_to(path)
        if ok and not path.lower().endswith(".docx"):
            self.statusBar().showMessage("Not: tam biçim desteği için .docx kullanın.", 5000)
        return ok

    def export_as(self, ext):
        base = os.path.splitext(self.path)[0] if self.path else os.path.join(self._dir(), "Belge1")
        flt = {".docx": "Word belgesi (*.docx)", ".odt": "OpenDocument metni (*.odt)", ".html": "Web sayfası (*.html)",
               ".md": "Markdown (*.md)", ".txt": "Düz metin (*.txt)"}[ext]
        path, _ = QFileDialog.getSaveFileName(self, "Dışa Aktar", base + ext, flt)
        if path:
            if not path.lower().endswith(ext):
                path += ext
            self.save_to(path, copy=True)

    @staticmethod
    def _replace_file(tmp, target):
        """Virüs tarayıcı/OneDrive dosyayı kısa süre kilitleyebilir; hemen hata vermeden birkaç kez dener."""
        for attempt in range(4):
            try:
                os.replace(tmp, target)
                return
            except PermissionError:
                if attempt == 3:
                    raise
                time.sleep(0.25)

    def save_to(self, path, copy=False):
        """Önce geçici dosyaya yazar ve doğrular; asıl dosya yalnızca kayıt tamamlanınca değişir.
        Böylece disk dolması, hata veya elektrik kesintisi eski belgeyi bozamaz."""
        ext = os.path.splitext(path)[1].lower()
        doc = self.editor.document()
        target = os.path.realpath(path)
        folder, name = os.path.split(target)
        tmp = os.path.join(folder, f".~{os.getpid()}-{name}.tmp")
        try:
            if ext == ".docx":
                export_docx(self.editor, tmp)
                with zipfile.ZipFile(tmp) as z:
                    if z.testzip() is not None or "word/document.xml" not in z.namelist():
                        raise IOError("Yazılan dosya doğrulanamadı")
            elif ext == ".odt":
                w = QTextDocumentWriter(tmp, b"odf")
                if not w.write(doc):
                    raise IOError("ODT yazılamadı")
            elif ext in (".html", ".htm"):
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(doc.toHtml())
            elif ext == ".md":
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(doc.toMarkdown())
            else:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(doc.toPlainText())
            self._replace_file(tmp, target)
        except PermissionError:
            log.warning("Kaydedilemedi (izin): %s", path, exc_info=True)
            QMessageBox.critical(self, APP_NAME, f"Kaydedilemedi — dosya başka bir programda açık olabilir:\n{path}")
            return False
        except Exception as exc:
            log.warning("Kaydedilemedi: %s", path, exc_info=True)
            QMessageBox.critical(self, APP_NAME, f"Kaydedilemedi:\n{exc}")
            return False
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError as exc:
                    log.debug("geçici dosya silinemedi: %s", exc)
        if ext == ".docx" and not copy:
            self.path = path
            self._import_name = None
            doc.setModified(False)
            self._clear_recovery()
        self._remember(path)
        self.update_title()
        self.statusBar().showMessage(f"Kaydedildi: {path}", 3000)
        return True

    def _page_layout(self):
        s = self.editor.setup
        w, h = sorted((s.width_mm, s.height_mm))
        return QPageLayout(QPageSize(QSizeF(w, h), QPageSize.Unit.Millimeter, "OmOffice"),
                           QPageLayout.Orientation.Landscape if s.landscape else QPageLayout.Orientation.Portrait,
                           QMarginsF(0, 0, 0, 0))

    def export_pdf(self, path=None):
        if not path:
            base = os.path.splitext(self.path)[0] + ".pdf" if self.path else os.path.join(self._dir(), "Belge1.pdf")
            path, _ = QFileDialog.getSaveFileName(self, "PDF Olarak Dışa Aktar", base, "PDF (*.pdf)")
            if not path:
                return False
        w = QPdfWriter(path)
        w.setResolution(300)
        w.setPageLayout(self._page_layout())
        w.setTitle(os.path.splitext(os.path.basename(path))[0])
        w.setCreator(APP_NAME)
        n = self.editor.render_pages(w)
        del w
        self.statusBar().showMessage(f"PDF oluşturuldu ({n} sayfa): {path}", 5000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return True

    def _printer(self):
        p = QPrinter(QPrinter.PrinterMode.HighResolution)
        p.setPageLayout(self._page_layout())
        p.setFullPage(True)
        return p

    def file_print(self):
        p = self._printer()
        dlg = QPrintDialog(p, self)
        dlg.setWindowTitle("Yazdır")
        if dlg.exec():
            self.editor.render_pages(p)

    def print_preview(self):
        p = self._printer()
        dlg = QPrintPreviewDialog(p, self)
        dlg.setWindowTitle("Baskı Önizleme")
        dlg.paintRequested.connect(self.editor.render_pages)
        dlg.resize(1000, 800)
        dlg.exec()

    # ============================================================ kurtarma
    @staticmethod
    def _rec_dir():
        d = os.path.join(app_data_dir(), "kurtarma")
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def _unsaved_dir():
        d = os.path.join(app_data_dir(), "kaydedilmemis")
        os.makedirs(d, exist_ok=True)
        return d

    def _rec_base(self):
        return os.path.join(self._rec_dir(), self.session)

    def _autosave(self, force=False):
        doc = self.editor.document()
        if not (force or doc.isModified()) or doc.isEmpty() and not self.path:
            return True
        base = self._rec_base()
        try:
            export_docx(self.editor, base + ".tmp.docx")
            os.replace(base + ".tmp.docx", base + ".docx")
            with open(base + ".tmp.json", "w", encoding="utf-8") as f:
                json.dump({"path": self.path, "title": self.title_label.text().lstrip("● ") if hasattr(self, "title_label")
                           else "", "time": time.time(), "pid": os.getpid()}, f, ensure_ascii=False)
            os.replace(base + ".tmp.json", base + ".json")
            return True
        except Exception:  # kurtarma kopyası hiçbir zaman kullanıcıyı engellememeli
            log.warning("Otomatik kurtarma kopyası alınamadı", exc_info=True)
            return False

    def _clear_recovery(self):
        for ext in (".docx", ".json", ".tmp.docx", ".tmp.json"):
            try:
                os.remove(self._rec_base() + ext)
            except OSError:
                pass

    def _keep_unsaved_copy(self):
        """'Kaydetme' denilen belgenin bir kopyasını 7 gün saklar (Word'deki gibi)."""
        try:
            name = re.sub(r"[^\w\- ]", "_", os.path.splitext(os.path.basename(self.path or "Belge1"))[0])[:40]
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            export_docx(self.editor, os.path.join(self._unsaved_dir(), f"{stamp}_{name}.docx"))
        except Exception:
            log.warning("Kaydedilmemiş kopya alınamadı", exc_info=True)

    @staticmethod
    def _pid_alive(pid):
        if not pid:
            return False
        if pid == os.getpid():
            return True
        try:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
        except Exception as exc:  # bozuk/eksik bölüm işlemi durdurmasın
            log.debug("yok sayılan hata: %s", exc)
        return False

    def recovery_entries(self):
        """[(etiket, docx yolu, json yolu|None, kaynak)] — çöken oturumlar ve kaydedilmeden kapatılanlar."""
        out = []
        rd = self._rec_dir()
        for fn in sorted(os.listdir(rd)):
            if not fn.endswith(".json") or fn.startswith(self.session):
                continue
            jp = os.path.join(rd, fn)
            dp = jp[:-5] + ".docx"
            try:
                with open(jp, encoding="utf-8") as f:
                    info = json.load(f)
            except (OSError, ValueError):
                continue
            if not os.path.exists(dp) or self._pid_alive(info.get("pid")):
                continue
            when = datetime.datetime.fromtimestamp(info.get("time", 0)).strftime("%d.%m.%Y %H:%M")
            out.append((f"{info.get('title') or 'Belge'}  ·  {when}  ·  beklenmedik kapanış", dp, jp, info.get("path")))
        ud = self._unsaved_dir()
        cutoff = time.time() - 7 * 86400
        for fn in sorted(os.listdir(ud), reverse=True):
            fp = os.path.join(ud, fn)
            if os.path.getmtime(fp) < cutoff:
                try:
                    os.remove(fp)
                except OSError:
                    pass
                continue
            when = datetime.datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%d.%m.%Y %H:%M")
            out.append((f"{fn[16:-5] or 'Belge'}  ·  {when}  ·  kaydedilmeden kapatıldı", fp, None, None))
        return out

    def _offer_recovery(self):
        if any(e[2] for e in self.recovery_entries()):
            self.start_screen = False
            self.show_recovery(crashed_only=True)

    def show_recovery(self, crashed_only=False):
        entries = [e for e in self.recovery_entries() if e[2] or not crashed_only]
        dlg = QDialog(self)
        dlg.setWindowTitle("Belge Kurtarma")
        dlg.resize(620, 380)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(f"<b>Kurtarılabilen belgeler</b><br><span style='color:{CURRENT['theme']['muted']}'>OmOffice değişiklikleri 15 saniyede "
                           "bir kurtarma kopyasına yazar; 'Kaydetme' dediğiniz belgeler de 7 gün saklanır.</span>"))
        lst = QListWidget()
        for label, dp, jp, orig in entries:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, (dp, jp, orig))
            it.setToolTip(dp)
            lst.addItem(it)
        if not entries:
            lst.addItem("(kurtarılacak belge yok)")
        else:
            lst.setCurrentRow(0)
        v.addWidget(lst, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        b_del = QPushButton("Sil")
        b_open = QPushButton("Aç")
        b_open.setObjectName("primary")
        b_close = QPushButton("Kapat")
        for b in (b_del, b_close, b_open):
            row.addWidget(b)
        v.addLayout(row)

        def current():
            it = lst.currentItem()
            return it.data(Qt.ItemDataRole.UserRole) if it is not None else None

        def do_delete():
            d = current()
            if not d:
                return
            for p_ in (d[0], d[1]):
                if p_:
                    try:
                        os.remove(p_)
                    except OSError:
                        pass
            lst.takeItem(lst.currentRow())

        def do_open():
            d = current()
            if not d or not self.maybe_save():
                return
            doc, setup, meta = import_docx(d[0])
            self._import_name = (os.path.splitext(os.path.basename(d[2]))[0] if d[2] else "Belge") + " (kurtarıldı)"
            self._set_doc(doc, setup, None, meta)
            self.editor.document().setModified(True)
            self.update_title()
            if d[1]:  # çöken oturum dosyalarını bu oturuma devret
                for p_ in (d[0], d[1]):
                    try:
                        os.remove(p_)
                    except OSError:
                        pass
                self._autosave(force=True)
            dlg.accept()
            self.statusBar().showMessage("Belge kurtarıldı. Ctrl+S ile kalıcı olarak kaydedin.", 8000)

        b_del.clicked.connect(do_delete)
        b_open.clicked.connect(do_open)
        lst.itemDoubleClicked.connect(lambda _: do_open())
        b_close.clicked.connect(dlg.reject)
        dlg.exec()

    def on_crash(self, etype, value, tb):
        """Yakalanmamış hata: belgeyi kurtarma kopyasına yaz, programı kapatma."""
        log.error("Yakalanmamış hata", exc_info=(etype, value, tb))
        traceback.print_exception(etype, value, tb)
        if self._crashing:
            return
        self._crashing = True
        try:
            if self._autosave(force=True):
                state = "Beklenmeyen bir hata oluştu, ama belgeniz güvende:\nbir kurtarma kopyası alındı."
            else:
                state = ("Beklenmeyen bir hata oluştu ve kurtarma kopyası ALINAMADI.\n"
                         "Lütfen belgeyi hemen Farklı Kaydet ile kaydedin.")
            QMessageBox.warning(self, APP_NAME, f"{state}\n\nAyrıntı: {etype.__name__}: {value}")
        finally:
            self._crashing = False

    def about(self):
        QMessageBox.about(self, APP_NAME, f"<h3>{APP_NAME} {__version__}</h3><p>Python + PySide6 ile yazılmış belge düzenleyici."
                                          "</p><p>.docx açar ve kaydeder; PDF'e aktarır.</p>"
                                          "<p>Copyright © 2026 Ömer Faruk<br>GNU GPL sürüm 3 veya sonrası ile lisanslıdır; "
                                          "hiçbir garanti verilmez. Ayrıntılar program klasöründeki LICENSE.txt ve "
                                          "THIRD_PARTY_NOTICES.md dosyalarındadır.</p>")

    def closeEvent(self, e):
        if self.maybe_save():
            self._clear_recovery()
            self.settings.setValue("zoom", self.view.zoom)
            self.settings.setValue("ruler", "1" if self.actions["ruler"].isChecked() else "0")
            if self.tts is not None:
                self.tts.stop()
            self.minibar.hide()
            e.accept()
        else:
            e.ignore()

    # ======================================================== yeni özellikler
    def _startup(self):
        if os.environ.get("OMOFFICE_TEST_DATA"):  # otomatik testler için
            return
        self._offer_recovery()
        if self.start_screen and self.settings.value("show_start", "1") == "1":
            self.show_start()
        QTimer.singleShot(1500, self._startup_update_check)

    # ---- güncelleme denetimi
    def _startup_update_check(self):
        """İlk açılışta bir kez izin ister; izin varsa günde en fazla bir kez arka planda denetler."""
        choice = self.settings.value("update_check")
        if choice is None:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("Yeni sürüm bildirimi")
            box.setText("Yeni bir OmOffice sürümü çıktığında size haber verilsin mi?")
            box.setInformativeText(
                "Bunun için OmOffice açılışta, günde en fazla bir kez GitHub'dan yalnızca en son sürümün "
                "numarasını sorar. Belgeleriniz veya kişisel bilgileriniz gönderilmez; hiçbir şey kendiliğinden "
                "indirilmez ya da kurulmaz.\n\nBu ayarı daha sonra Dosya menüsünden değiştirebilirsiniz.")
            yes = box.addButton("Evet, haber ver", QMessageBox.ButtonRole.YesRole)
            box.addButton("Hayır", QMessageBox.ButtonRole.NoRole)
            box.setDefaultButton(yes)
            box.exec()
            choice = "1" if box.clickedButton() is yes else "0"
            self.settings.setValue("update_check", choice)
            self.actions["auto_update"].setChecked(choice == "1")
        if choice != "1":
            return
        last = float(self.settings.value("update_last_check", 0) or 0)
        if time.time() - last >= updates.CHECK_INTERVAL:
            self.check_updates(manual=False)
        elif self.settings.value("update_latest"):
            self._show_update(self.settings.value("update_latest"))   # daha önce bulunan, henüz kurulmamış sürüm

    def set_auto_update(self, on):
        self.settings.setValue("update_check", "1" if on else "0")
        if on:
            self.check_updates(manual=False)
        else:
            self.update_button.setVisible(False)

    def check_updates(self, manual=False):
        if getattr(self, "_update_job", None) is not None:
            return
        if manual:
            self.statusBar().showMessage("Güncellemeler denetleniyor…", 3000)
        job = updates.UpdateCheck(self)
        job.done.connect(lambda latest, err: self._update_result(latest, err, manual))
        job.finished.connect(job.deleteLater)
        self._update_job = job
        job.start()

    def _update_result(self, latest, err, manual):
        self._update_job = None
        if latest is None:
            if manual:
                QMessageBox.warning(self, "Güncelleme denetimi",
                                    "Güncellemeler denetlenemedi. İnternet bağlantınızı kontrol edip yeniden deneyin."
                                    f"\n\nAyrıntı: {err}")
            return
        self.settings.setValue("update_last_check", time.time())
        if updates.is_newer(latest):
            self.settings.setValue("update_latest", latest)
            self._show_update(latest)
            if manual:
                r = QMessageBox.question(self, "Yeni sürüm var",
                                         f"OmOffice {latest} yayımlandı (kullandığınız: {__version__}).\n\n"
                                         "İndirme sayfası tarayıcıda açılsın mı?")
                if r == QMessageBox.StandardButton.Yes:
                    self.open_releases()
        else:
            self.settings.remove("update_latest")
            self.update_button.setVisible(False)
            if manual:
                QMessageBox.information(self, "Güncelleme denetimi",
                                        f"OmOffice güncel. Kullandığınız sürüm: {__version__}")

    def _show_update(self, latest):
        if not updates.is_newer(latest):
            return
        self.update_button.setText(f"⬆ Yeni sürüm: {latest}")
        self.update_button.setToolTip("İndirme sayfasını tarayıcıda açar. Yeni sürümü kurmak için eskisini "
                                      "kaldırmanız gerekmez.")
        self.update_button.setVisible(True)

    def open_releases(self):
        QDesktopServices.openUrl(QUrl(updates.RELEASES_URL))

    def show_start(self, catalog=False):
        files = self.settings.value("recent", []) or []
        if isinstance(files, str):
            files = [files]
        files = [f for f in files if os.path.exists(f)][:8]
        dlg = StartWizard(files, lambda ch: glyph(ch, color="accent"), self.editor.author, self, catalog)
        if not dlg.exec() or dlg.choice is None:
            return
        choice = dlg.choice
        if choice[0] == "open" and self.maybe_save():
            self.open_path(choice[1])
        elif choice[0] == "browse":
            self.file_open()
        elif choice[0] == "recover":
            self.show_recovery()
        elif choice[0] == "kind" and self.maybe_save():
            _, key, answers, opts = choice
            self._import_name = None
            self._set_doc(new_document(), PageSetup(), None)
            if key != "bos":
                build_kind(self.editor, key, answers, opts)
            else:
                self.editor.doc_info = {"kind": "bos"}
            self.update_format_state()
            self.refresh_nav()
            self.view.verticalScrollBar().setValue(0)
            if opts.get("guide"):
                self.guide_page.show()
                self.guide_panel.refresh()
        self.view.focus_editor()

    # ---- tema
    def apply_theme(self, name=None, accent=None, animate=False):
        name = name or self.settings.value("theme", "Açık")
        accent = accent or self.settings.value("accent", "Lacivert")
        if name not in THEMES:
            name = "Açık"
        if accent not in ACCENTS:
            accent = "Lacivert"
        fade = self._theme_fade_start() if animate else None
        CURRENT["theme"] = THEMES[name]
        CURRENT["accent"] = ACCENTS[accent]
        self.settings.setValue("theme", name)
        self.settings.setValue("accent", accent)
        t = THEMES[name]
        d = theme.derived(t, ACCENTS[accent])
        QApplication.setPalette(theme.app_palette())
        self.setStyleSheet(theme.style_sheet())
        # Windows 11 stili pencere stilindeki üst çubuk yazı rengini uygulamıyor; cam çubuğa doğrudan verilir
        self.topbar.setStyleSheet(
            "QLabel { color: white; background: transparent; }"
            f"QToolButton#docPath {{ color: {d['path_text']}; font-size: 8pt; padding: 0; border: none; }}"
            "QToolButton#docPath:hover { color: white; text-decoration: underline; background: transparent; }")
        self.view.set_colors(t["view_bg"], "#000000")
        self.ruler.set_colors({"bg": t["ruler_bg"], "margin": t["ruler_margin"], "text": t["ruler_text"],
                               "tick": t["muted"], "marker": d["accent_ui"]})
        # sayfadaki seçim: vurgunun açık tonu, yazı siyah kalır (sayfa her temada beyaz)
        pal = self.editor.palette()
        pal.setColor(QPalette.ColorRole.Highlight, QColor(d["page_select"]))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#000000"))
        self.editor.setPalette(pal)
        for b in getattr(self, "style_chips", []):
            c = b.property("style_color") or t["text"]
            c = theme.ensure_contrast(c, t["card"], 4.5)
            b.setStyleSheet(f"QToolButton {{ color: {c}; border: 1px solid {t['border']}; "
                            f"padding: 2px 8px; }}")
        for w in self.findChildren(QWidget):
            w.update()
        if fade is not None:
            fade()

    def _theme_fade_start(self):
        """Tema değişirken eski görünümü üstte tutup yavaşça soldurur (çapraz geçiş)."""
        if not self.isVisible():
            return None
        shot = QLabel(self)
        shot.setPixmap(self.grab())
        shot.setGeometry(self.rect())
        shot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shot.show()
        shot.raise_()
        QApplication.processEvents()

        def run():
            # yeni temanın ilk (ağır) yeniden çizimi katmanın altında bitsin; yoksa geçişin ilk yarısını yutar
            QApplication.processEvents()
            eff = QGraphicsOpacityEffect(shot)
            shot.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", shot)
            anim.setDuration(260)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
            anim.finished.connect(shot.hide)
            anim.finished.connect(shot.deleteLater)
            anim.start()
        return run

    def toggle_ruler(self, on):
        self.ruler.setVisible(on)

    def toggle_ribbon(self):
        self.ribbon.set_collapsed(not self.ribbon.is_collapsed())

    def toggle_focus(self, on):
        self.focus_mode = on
        self.menuWidget().setVisible(not on)
        self.ribbon.setVisible(not on)
        self.statusBar().setVisible(not on)
        self.ruler.setVisible(not on and self.actions["ruler"].isChecked())
        for d in (self.nav_dock, self.comments_dock):
            if on:
                d.setProperty("was_visible", d.isVisible())
                d.hide()
            elif d.property("was_visible"):
                d.show()
        if on:
            self.showFullScreen()
            self.view.fit_width() if self.view.zoom < 1.0 else None
            self.statusBar().showMessage("")
            self._focus_hint = QLabel("Odak modu — çıkmak için Esc", self)
            self._focus_hint.setStyleSheet("background: rgba(0,0,0,0.6); color: white; padding: 6px 12px; "
                                           "border-radius: 6px;")
            self._focus_hint.adjustSize()
            self._focus_hint.move((self.width() - self._focus_hint.width()) // 2, 16)
            self._focus_hint.show()
            QTimer.singleShot(2500, self._focus_hint.deleteLater)
        else:
            self.showNormal() if not self.actions["fullscreen"].isChecked() else None
        self.view.focus_editor()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.focus_mode:
            self.actions["focus"].setChecked(False)
            self.toggle_focus(False)
            return
        super().keyPressEvent(e)

    def _zoom_changed(self, z):
        self.zoom_label.setText(f"%{round(z * 100)}")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(round(z * 100))
        self.zoom_slider.blockSignals(False)

    # ---- komut paleti
    def show_palette(self):
        cats = {}
        for i in range(self.ribbon.count()):
            page = self.ribbon.widget(i)
            for b in page.findChildren(QToolButton):
                a = b.defaultAction()
                if a is not None:
                    cats.setdefault(a, self.ribbon.tabText(i))
        entries = []
        seen = set()
        for key, a in self.actions.items():
            if a in seen or not a.text():
                continue
            seen.add(a)
            entries.append((a.text().replace("&", ""), cats.get(a, "Dosya"), a))
        for name in THEMES:
            a = QAction(f"{name} temaya geç", self)
            a.triggered.connect(lambda _=False, n=name: self.apply_theme(n, None, animate=True))
            entries.append((a.text(), "Tasarım", a))
        for name in STYLES:
            a = QAction(f"Stil uygula: {name}", self)
            a.triggered.connect(lambda _=False, n=name: self.editor.apply_style(n))
            entries.append((a.text(), "Giriş", a))
        for wm in WATERMARKS:
            a = QAction(f"Filigran ekle: {wm}", self)
            a.triggered.connect(lambda _=False, w=wm: self._set_setup(watermark=w))
            entries.append((a.text(), "Tasarım", a))
        for name in PAPER_SIZES:
            a = QAction(f"Kağıt boyutu: {name}", self)
            a.triggered.connect(lambda _=False, n=name: self.set_paper(*PAPER_SIZES[n]))
            entries.append((a.text(), "Düzen", a))
        entries.sort(key=lambda t: t[0])
        self._palette = CommandPalette(entries, self)
        self._palette.open_centered(self)

    # ---- mini araç çubuğu
    def _build_minibar(self):
        self.mini_style = QComboBox()
        self.mini_style.addItems(list(STYLES))
        self.mini_style.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mini_style.textActivated.connect(lambda n: (self.editor.apply_style(n), self.view.focus_editor()))
        self.minibar = MiniBar([self.actions[k] for k in ("bold", "italic", "underline")] + [None] +
                               [self.actions[k] for k in ("color", "highlight")] + [None] +
                               [self.actions[k] for k in ("bullets", "link", "comment", "clear")],
                               [self.mini_style], self)

    def _show_minibar(self):
        if self.focus_mode and False:
            return
        self.mini_style.blockSignals(True)
        self.mini_style.setCurrentText(self.editor.current_style_name())
        self.mini_style.blockSignals(False)
        self.minibar.show_at(self.view.selection_anchor_global())

    def _maybe_hide_minibar(self):
        if not self.editor.textCursor().hasSelection() and self.minibar.isVisible():
            self.minibar.hide()

    def moveEvent(self, e):
        super().moveEvent(e)
        if hasattr(self, "minibar"):
            self.minibar.hide()

    # ---- açıklamalar
    def _build_comments(self):
        self.comments_panel = CommentsPanel(self.editor)
        idx = self.ribbon.add_page("Açıklamalar", glyph("\uE90A"), self.comments_panel, scroll=False)
        self.comments_dock = PanelPage(self.ribbon, idx)
        self.comments_dock.visibilityChanged.connect(lambda v: self.actions["comments_pane"].setChecked(v))

    def _build_guide(self):
        self.guide_panel = GuidePanel(self.editor)
        idx = self.ribbon.add_page("Rehber", glyph("\uE82F"), self.guide_panel,
                                   tooltip="Rehber: bölüme göre ipuçları, örnek cümleler, kontrol listesi")
        self.guide_page = PanelPage(self.ribbon, idx)
        self.guide_panel.citationRequested.connect(self.add_citation)
        self.guide_panel.fixCapsRequested.connect(self.fix_caps)
        self.guide_panel.tocRequested.connect(self.update_toc)
        self.ribbon.select(0)

    def add_citation(self):
        info = dict(self.editor.doc_info or {})
        dlg = CitationDialog(info.get("citation") or "APA 7", self)
        if not dlg.exec():
            return
        r = dlg.ref()
        if not (r.get("title") or r.get("authors")):
            self.statusBar().showMessage("Kaynak eklemek için en azından yazar ya da başlık girin.", 4000)
            return
        here = QTextCursor(self.editor.textCursor())
        style = dlg.style.currentText()
        cite = add_reference(self.editor, style, r)
        here.clearSelection()
        self.editor.setTextCursor(here)
        self.editor.type_text(cite)
        info["citation"] = style
        self.editor.doc_info = info
        self.statusBar().showMessage(f"Kaynak eklendi: {cite}  (Kaynakça bölümüne {style} stilinde yazıldı)", 6000)

    def replace_image(self, pos):
        """Şablondaki logo/fotoğraf yer tutucusunu ya da herhangi bir resmi yenisiyle değiştirir."""
        fmt = self.editor._image_at(pos)
        slot = image_slot(fmt.name()) if fmt is not None else None
        title = IMAGE_SLOT_KINDS[slot].replace(" ekle", " Seç").title() if slot else "Resmi Değiştir"
        path, _ = QFileDialog.getOpenFileName(self, title, self._dir(),
                                              "Resimler (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull() or not self.editor.replace_image(pos, img):
            QMessageBox.warning(self, APP_NAME, "Resim açılamadı ya da değiştirilemedi.")
            return
        self.statusBar().showMessage("Resim yerleştirildi. Köşelerinden sürükleyerek boyutlandırabilirsiniz.", 5000)

    def edit_page_hf(self, page_no, which):
        """Sayfadaki üst/alt bilgiye tıklanınca: o sayfaya özel düzenleme (eksi sayfa = tüm sayfalar)."""
        scope = "all" if page_no < 0 else "page"
        page_no = abs(page_no)
        e = self.editor
        text, align = e.setup.hf_for(which, page_no)
        if not text and scope == "page":
            # boş sayfaya eklerken varsayılan metni öner
            text = e.setup.header_text if which == "header" else e.setup.footer_text
        dlg = HeaderFooterDialog(which, page_no, e.page_count(), text, align, scope, self)
        if not dlg.exec():
            return
        if dlg.removed:
            e.hf_set(page_no, which, "", scope="page")
        else:
            e.hf_set(page_no, which, dlg.text.toPlainText(), dlg.align.currentData(), dlg.scope())
        where = {"page": f"yalnızca {page_no}. sayfada", "from": f"{page_no}. sayfadan itibaren",
                 "all": "tüm sayfalarda"}[dlg.scope() if not dlg.removed else "page"]
        self.statusBar().showMessage(("Üst" if which == "header" else "Alt") + f" bilgi {where} güncellendi.", 4000)

    def fix_caps(self):
        fixes = self.editor.fix_capitalization(apply=True)
        if not fixes:
            QMessageBox.information(self, APP_NAME, "Büyük harf hatası bulunamadı.")
            return
        sample = "\n".join(f"• {w}  →  {f}" for _, w, f in fixes[:12])
        more = f"\n… ve {len(fixes) - 12} tane daha" if len(fixes) > 12 else ""
        QMessageBox.information(self, APP_NAME, f"{len(fixes)} düzeltme yapıldı (Ctrl+Z ile geri alınabilir):\n\n"
                                                f"{sample}{more}")

    def open_folder(self):
        if self.path and os.path.exists(os.path.dirname(self.path)):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.path)))
        else:
            self.statusBar().showMessage("Belge henüz kaydedilmedi; önce Ctrl+S ile kaydedin.", 4000)

    def copy_path(self):
        if self.path:
            QApplication.clipboard().setText(self.path)
            self.statusBar().showMessage(f"Kopyalandı: {self.path}", 3000)

    BUILTIN_SHORTCUTS = [
        ("Kopyala", "Ctrl+C"), ("Kes", "Ctrl+X"), ("Yapıştır", "Ctrl+V"), ("Yalnızca metni yapıştır", "Ctrl+Shift+V"),
        ("Tümünü seç", "Ctrl+A"), ("Geri al", "Ctrl+Z"), ("Yinele", "Ctrl+Y"), ("Sözcük sil (geri)", "Ctrl+Backspace"),
        ("Satır sonu (aynı paragrafta)", "Shift+Enter"), ("Liste düzeyini artır / azalt", "Tab / Shift+Tab"),
        ("Bir sözcük sola / sağa", "Ctrl+← / Ctrl+→"), ("Belge başı / sonu", "Ctrl+Home / Ctrl+End"),
        ("Bağlantıyı aç", "Ctrl+Tık"), ("Yakınlaştır", "Ctrl+Tekerlek"), ("Odak modundan çık", "Esc"),
    ]

    def show_shortcuts(self):
        rows = {}
        for a in self.actions.values():
            sc = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
            if sc and a.text():
                rows[a.text().replace("&", "")] = sc
        for name, sc in self.BUILTIN_SHORTCUTS:
            rows.setdefault(name, sc)
        dlg = QDialog(self)
        dlg.setWindowTitle("Klavye Kısayolları")
        dlg.resize(520, 560)
        v = QVBoxLayout(dlg)
        flt = QLineEdit()
        flt.setPlaceholderText("Ara…")
        v.addWidget(flt)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Komut", "Kısayol"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        items = sorted(rows.items())
        table.setRowCount(len(items))
        for i, (n, sc) in enumerate(items):
            table.setItem(i, 0, QTableWidgetItem(n))
            table.setItem(i, 1, QTableWidgetItem(sc))
        flt.textChanged.connect(lambda t: [table.setRowHidden(i, t.lower() not in (items[i][0] + items[i][1]).lower())
                                           for i in range(len(items))])
        v.addWidget(table)
        dlg.exec()

    def toggle_comments(self, on):
        self.comments_dock.setVisible(on)

    def new_comment(self):
        c = self.editor.textCursor()
        if not c.hasSelection():
            c.select(QTextCursor.SelectionType.WordUnderCursor)
            if not c.hasSelection():
                self.statusBar().showMessage("Açıklama eklemek için önce metin seçin.", 3000)
                return
            self.editor.setTextCursor(c)
        self.minibar.hide()
        text = ask_text(self, "Yeni Açıklama", "", f"“{c.selectedText()[:60]}” için açıklama:")
        if text:
            self.editor.add_comment(text)
            self.editor.highlighter.rehighlight()
            self.comments_dock.show()

    def _comments_changed(self):
        self.editor.highlighter.rehighlight()

    def delete_all_comments(self):
        if not self.editor.comments:
            return
        if QMessageBox.question(self, APP_NAME, "Belgedeki tüm açıklamalar silinsin mi?") == \
                QMessageBox.StandardButton.Yes:
            for cid in list(self.editor.comments):
                self.editor.delete_comment(cid)

    # ---- dipnotlar
    def insert_footnote(self):
        text = ask_text(self, "Dipnot Ekle", "", "Dipnot metni:")
        if text:
            self.editor.insert_footnote(text)
            self.editor.viewport().update()

    def edit_footnote(self, fid):
        text = ask_text(self, "Dipnotu Düzenle", self.editor.footnotes.get(fid, ""))
        if text is not None:
            self.editor.footnotes[fid] = text
            self.editor._invalidate()
            self.editor.document().setModified(True)
            self.editor.viewport().update()

    def list_footnotes(self):
        refs = self.editor.footnote_refs()
        if not refs:
            QMessageBox.information(self, "Dipnotlar", "Belgede dipnot yok.")
            return
        items = [f"{n}. {self.editor.footnotes.get(fid, '')}" for n, (_, _, fid) in enumerate(refs, 1)]
        choice, ok = QInputDialog.getItem(self, "Dipnotlar", "Gitmek için seçin:", items, 0, False)
        if ok:
            a = refs[items.index(choice)][0]
            c = self.editor.textCursor()
            c.setPosition(a)
            self.editor.setTextCursor(c)
            self.editor.ensureCursorVisible()

    def update_toc(self):
        if not self.editor.update_toc():
            self.insert_toc()
        else:
            self.statusBar().showMessage("İçindekiler güncellendi.", 2500)

    # ---- tasarım
    def _set_setup(self, **kw):
        st = self.editor.setup.copy()
        for k, v in kw.items():
            setattr(st, k, v)
        self._apply_setup(st)

    def custom_watermark(self):
        text, ok = QInputDialog.getText(self, "Özel Filigran", "Filigran metni:", text=self.editor.setup.watermark)
        if ok:
            self._set_setup(watermark=text.strip())

    def _page_color_picked(self, color):
        self._set_setup(page_color="" if color in (None, "#FFFFFF") else color)

    def _shade_picked(self, color):
        if color:
            self.shade_color = color
            self.actions["shading"].setIcon(glyph("\uE790", bar=color, scale=0.5))
        self.editor.set_paragraph_shading(color)

    def _sort(self, desc):
        if not self.editor.sort_paragraphs(desc):
            self.statusBar().showMessage("Sıralamak için tablo dışında birden çok paragraf seçin.", 3500)

    def toggle_autocorrect(self, on):
        self.editor.autocorrect = on
        self.settings.setValue("autocorrect", "1" if on else "0")

    # ---- sesli okuma
    def toggle_speak(self, on):
        if not on:
            if self.tts is not None:
                self.tts.stop()
            self.editor.setExtraSelections([])
            return
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
        except ImportError:
            QMessageBox.warning(self, APP_NAME, "Bu sistemde metin okuma desteği yok.")
            self.actions["speak"].setChecked(False)
            return
        if self.tts is None:
            self.tts = QTextToSpeech(self)
            lang = (self.spell.language or "tr_TR")[:2]
            for v in self.tts.availableVoices():
                if v.locale().name().startswith(lang):
                    self.tts.setVoice(v)
                    break
            self.tts.stateChanged.connect(self._tts_state)
            if hasattr(self.tts, "sayingWord"):
                self.tts.sayingWord.connect(self._tts_word)
        c = self.editor.textCursor()
        if c.hasSelection():
            start, end = c.selectionStart(), c.selectionEnd()
        else:
            start = c.block().position()
            end = self.editor.document().characterCount() - 1
        r = QTextCursor(self.editor.document())
        r.setPosition(start)
        r.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        text = r.selectedText().replace("\u2029", "\n").replace("\ufffc", " ")
        if not text.strip():
            self.actions["speak"].setChecked(False)
            return
        self._tts_base = start
        self.tts.say(text)

    def _tts_word(self, word, _id, start, length):
        from PySide6.QtWidgets import QTextEdit
        c = QTextCursor(self.editor.document())
        c.setPosition(self._tts_base + start)
        c.setPosition(self._tts_base + start + length, QTextCursor.MoveMode.KeepAnchor)
        sel = QTextEdit.ExtraSelection()
        sel.cursor = c
        f = QTextCharFormat()
        f.setBackground(QColor("#BFE3FF"))
        sel.format = f
        self.editor.setExtraSelections([sel])
        rc = self.editor.cursorRect(c)
        self.view.ensureVisible(self.view.proxy.mapRectToScene(rc), 40, 120)

    def _tts_state(self, state):
        from PySide6.QtTextToSpeech import QTextToSpeech
        if state in (QTextToSpeech.State.Ready, QTextToSpeech.State.Error):
            self.actions["speak"].setChecked(False)
            self.editor.setExtraSelections([])
