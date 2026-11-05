"""Temalar ve temaya duyarlı simgeler."""
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QColor, QFont, QIcon, QIconEngine, QPainter, QPalette, QPixmap

THEMES = {
    "Açık": {
        "window": "#F3F4F7", "panel": "#FFFFFF", "border": "#E1E4EA", "text": "#1F2937",
        "muted": "#5F6672", "hover": "#EDF1F8", "checked": "#DCE6F6", "input": "#FFFFFF",
        "input_border": "#B6BCC7", "view_bg": "#E6E8ED", "shadow": "#000000", "icon": "#2B3A55",
        "icon_disabled": "#B4BAC5", "ruler_bg": "#F3F4F7", "ruler_margin": "#D9DDE4",
        "ruler_text": "#FFFFFF", "menu": "#FFFFFF", "card": "#FFFFFF",
    },
    "Koyu": {
        "window": "#1B1D21", "panel": "#25282D", "border": "#3D424A", "text": "#E5E7EB",
        "muted": "#A3AAB6", "hover": "#363B43", "checked": "#3A4250", "input": "#1F2226",
        "input_border": "#5A606A", "view_bg": "#15171A", "shadow": "#000000", "icon": "#D7DCE4",
        "icon_disabled": "#5F6570", "ruler_bg": "#202327", "ruler_margin": "#2A2D33",
        "ruler_text": "#3A3F47", "menu": "#25282D", "card": "#2C3036",
    },
}

ACCENTS = {
    "Lacivert": "#2F5DA8", "Mor": "#6D4AB8", "Yeşil": "#1F7A5A", "Bordo": "#9B2C3B",
    "Turuncu": "#C2571A", "Grafit": "#3C4452",
}

CURRENT = {"theme": THEMES["Açık"], "accent": ACCENTS["Lacivert"]}
_ENGINES = []   # QIcon motorlarının Python tarafında silinmemesi için

MDL2 = "Segoe MDL2 Assets"


class GlyphEngine(QIconEngine):
    """Bir yazı tipi karakterini simge olarak çizer; renk verilmezse temanın simge rengini kullanır."""

    def __init__(self, spec):
        super().__init__()
        self.spec = spec

    def paint(self, painter, rect, mode, state):
        sp = self.spec
        if mode == QIcon.Mode.Disabled:
            color = CURRENT["theme"]["icon_disabled"]
        else:
            color = sp.get("color") or CURRENT["theme"]["icon"]
            if color == "accent":
                # simge kart/panel zeminine karışmasın (koyu temada vurgu açılır)
                t = CURRENT["theme"]
                color = ensure_contrast(CURRENT["accent"], [t["card"], t["panel"]], 3.0)
        size = min(rect.width(), rect.height())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(sp.get("font", MDL2))
        f.setPixelSize(max(4, int(size * sp.get("scale", 0.68))))
        f.setBold(sp.get("bold", False))
        f.setItalic(sp.get("italic", False))
        f.setUnderline(sp.get("underline", False))
        f.setStrikeOut(sp.get("strike", False))
        painter.setFont(f)
        painter.setPen(QColor(color))
        bar = sp.get("bar")
        r = QRect(rect.x(), rect.y(), size, size)
        tr = r.adjusted(0, 0, 0, -int(size * 0.18) if bar else 0)
        painter.drawText(tr, int(Qt.AlignmentFlag.AlignCenter), sp["ch"])
        if bar:
            painter.fillRect(int(r.x() + size * 0.15), int(r.y() + size * 0.8), int(size * 0.7),
                             max(2, int(size * 0.14)), QColor(bar))
        painter.restore()

    def pixmap(self, size, mode, state):
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        self.paint(p, QRect(QPoint(0, 0), size), mode, state)
        p.end()
        return pm

    def clone(self):
        e = GlyphEngine(dict(self.spec))
        _ENGINES.append(e)
        return e


def glyph(ch, font=MDL2, color=None, scale=0.68, **kw):
    e = GlyphEngine(dict(ch=ch, font=font, color=color, scale=scale, **kw))
    _ENGINES.append(e)
    return QIcon(e)


def text_icon(ch, **kw):
    kw.setdefault("scale", 0.6)
    return glyph(ch, font="Segoe UI", **kw)


def _over(fg, bg, alpha):
    """Yarı saydam fg rengi bg üzerine bindirildiğinde görünen renk."""
    f, b = QColor(fg), QColor(bg)
    mix = [round(f.red() * alpha + b.red() * (1 - alpha)), round(f.green() * alpha + b.green() * (1 - alpha)),
           round(f.blue() * alpha + b.blue() * (1 - alpha))]
    return QColor(*mix).name()


def is_dark(t):
    return QColor(t["panel"]).lightness() < 128


def _lum(col):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    q = QColor(col)
    return 0.2126 * ch(q.red()) + 0.7152 * ch(q.green()) + 0.0722 * ch(q.blue())


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def ensure_contrast(color, backgrounds, ratio):
    """Rengin tonunu koruyarak, verilen tüm zeminlere karşı en az `ratio` kontrast sağlayana dek
    açar (koyu zeminde) ya da koyulaştırır (açık zeminde)."""
    if isinstance(backgrounds, str):
        backgrounds = [backgrounds]
    lighten = sum(_lum(b) for b in backgrounds) / len(backgrounds) < 0.18
    c = QColor(color)
    for _ in range(60):
        if min(contrast(c.name(), b) for b in backgrounds) >= ratio:
            break
        h, sat, li, _a = c.getHslF()
        h = max(h, 0.0)
        li = min(1.0, li + 0.02) if lighten else max(0.0, li - 0.02)
        if lighten and li > 0.6:
            sat = max(0.0, sat - 0.02)  # çok açılan renk pastelleşsin, göz yormasın
        c = QColor.fromHslF(h, sat, li)
    return c.name()


def tint(color, bg, alpha):
    """Vurgu renginin zemin üzerinde hafif tonu (seçim zeminleri için)."""
    return _over(color, bg, alpha)


def derived(t, a):
    """Stil sayfasının temadan ve vurgu renginden türettiği renkler (tests/theme_audit.py de kullanır).

    Vurgu rengi her yerde aynen kullanılmaz: beyaz yazının okunacağı çubuklarda gerekirse koyulaştırılır,
    koyu temada kenar ve işaretlerde zemine karışmasın diye açılır."""
    bar = ensure_contrast(a, "#FFFFFF", 4.6)
    file_ = QColor(bar).darker(122).name()
    alpha = 0.82
    while alpha < 1 and contrast(_over("#FFFFFF", bar, alpha), bar) < 4.5:
        alpha += 0.02
    dark = is_dark(t)
    accent_ui = ensure_contrast(a, [t["card"], t["panel"], t["window"], t["ruler_bg"]], 3.0)
    return {
        "bar": bar,                                 # üst çubuk, durum çubuğu, birincil düğme, seçim
        "file": file_,                              # Dosya düğmesi
        "primary": bar,
        "path_text": _over("#FFFFFF", bar, min(alpha, 1.0)),   # üst çubuktaki dosya yolu
        "rail_checked_text": t["text"] if dark else ensure_contrast(a, t["checked"], 4.6),
        "accent_ui": accent_ui,                     # kenarlar, onay kutusu, cetvel işareti
        "page_select": tint(a, "#FFFFFF", 0.28),    # sayfadaki metin seçimi (siyah yazı okunur kalır)
    }


def app_palette():
    """Stil sayfasının ulaşmadığı yerler (ipucu, iletişim kutuları, kaydırma alanları) de temaya uysun."""
    t = CURRENT["theme"]
    d = derived(t, CURRENT["accent"])
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    pal = QPalette()
    roles = {
        R.Window: t["window"], R.WindowText: t["text"], R.Base: t["input"], R.AlternateBase: t["hover"],
        R.Text: t["text"], R.Button: t["panel"], R.ButtonText: t["text"], R.BrightText: "#FFFFFF",
        R.ToolTipBase: t["menu"], R.ToolTipText: t["text"], R.PlaceholderText: t["muted"],
        R.Highlight: d["bar"], R.HighlightedText: "#FFFFFF", R.Link: d["accent_ui"],
        R.LinkVisited: d["accent_ui"], R.Light: t["hover"], R.Midlight: t["border"], R.Mid: t["input_border"],
        R.Dark: t["view_bg"], R.Shadow: "#000000",
    }
    for role, col in roles.items():
        pal.setColor(role, QColor(col))
    for role in (R.WindowText, R.Text, R.ButtonText):
        pal.setColor(G.Disabled, role, QColor(t["icon_disabled"]))
    return pal


def style_sheet():
    t = CURRENT["theme"]
    d = derived(t, CURRENT["accent"])
    a = d["accent_ui"]          # kenar, işaret ve seçili öğe vurgusu
    bar = d["bar"]              # üzerinde beyaz yazı olan vurgu zeminleri
    sel_text = d["rail_checked_text"]
    tab_text = "#EEF2FA"
    return f"""
QMainWindow, QDialog {{ background: {t['window']}; color: {t['text']}; }}
QWidget {{ color: {t['text']}; }}
QTabWidget#ribbon {{ background: {bar}; }}
QTabWidget#ribbon::pane {{ border: none; border-bottom: 1px solid {t['border']}; background: {t['panel']}; top: -1px; }}
QTabWidget#ribbon > QTabBar::tab {{ background: transparent; color: {tab_text}; padding: 7px 16px;
    border: none; font-size: 10pt; margin-top: 4px; }}
QTabWidget#ribbon > QTabBar::tab:selected {{ background: {t['panel']}; color: {sel_text};
    border-top-left-radius: 7px; border-top-right-radius: 7px; font-weight: 600; }}
QTabWidget#ribbon > QTabBar::tab:hover:!selected {{ background: rgba(255,255,255,0.16); }}
QWidget#ribbonPage {{ background: {t['panel']}; }}
QFrame#group {{ border: none; border-right: 1px solid {t['border']}; background: transparent; }}
QLabel#groupTitle {{ color: {t['muted']}; font-size: 8pt; background: transparent; }}
QToolButton {{ border: 1px solid transparent; border-radius: 5px; padding: 2px; background: transparent; color: {t['text']}; }}
QToolButton:hover {{ background: {t['hover']}; border-color: {t['border']}; }}
QToolButton:checked {{ background: {t['checked']}; border-color: {a}; }}
QToolButton:disabled {{ color: {t['icon_disabled']}; }}
QToolButton#fileButton {{ background: {d['file']}; color: white; font-weight: 600; padding: 4px 16px;
    border-radius: 0; }}
QToolButton#quickButton:hover {{ background: rgba(255,255,255,0.18); border-color: transparent; }}
QLineEdit#ribbonSearch {{ background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.25);
    border-radius: 12px; color: white; padding: 3px 10px; min-width: 210px; }}
QLineEdit#ribbonSearch:focus {{ background: white; color: #222; }}
QComboBox, QFontComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit#plain {{
    border: 1px solid {t['input_border']}; border-radius: 4px; padding: 2px 5px;
    background: {t['input']}; color: {t['text']}; min-height: 20px; }}
QComboBox QAbstractItemView {{ background: {t['menu']}; color: {t['text']}; selection-background-color: {bar}; selection-color: white; }}
QMenu {{ background: {t['menu']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['hover']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
QStatusBar {{ background: {bar}; color: white; }}
QStatusBar QLabel {{ color: white; padding: 0 8px; background: transparent; }}
QStatusBar QToolButton {{ color: white; }}
QStatusBar QToolButton:hover {{ background: rgba(255,255,255,0.18); border-color: transparent; }}
QSlider::groove:horizontal {{ height: 3px; background: rgba(255,255,255,0.45); border-radius: 1px; }}
QSlider::handle:horizontal {{ background: white; width: 10px; margin: -5px 0; border-radius: 5px; }}
QDockWidget {{ color: {t['text']}; }}
QDockWidget::title {{ background: {t['panel']}; padding: 7px; border-bottom: 1px solid {t['border']}; }}
QTreeWidget, QListWidget {{ background: {t['panel']}; color: {t['text']}; border: none; }}
QFrame#palette QListWidget::item {{ padding: 6px 4px; border-radius: 5px; }}
QTreeWidget::item:selected, QListWidget::item:selected {{ background: {t['checked']}; color: {t['text']}; }}
QScrollArea {{ background: {t['panel']}; border: none; }}
QWidget#cardHost {{ background: {t['panel']}; }}
QFrame#card {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame#card[active="true"] {{ border: 2px solid {a}; }}
QFrame#miniBar {{ background: {t['menu']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame#palette {{ background: {t['menu']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QPushButton {{ background: {t['input']}; border: 1px solid {t['input_border']}; border-radius: 5px; padding: 5px 14px; color: {t['text']}; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton#primary {{ background: {bar}; color: white; border-color: {bar}; }}
QPushButton#primary:hover {{ background: {d['file']}; }}
QCheckBox, QRadioButton, QLabel {{ background: transparent; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1.5px solid {t['input_border']}; border-radius: 4px;
    background: {t['input']}; }}
QCheckBox::indicator:hover {{ border-color: {a}; }}
QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}
QTabWidget::pane {{ border: 1px solid {t['border']}; }}
QTabBar::tab {{ background: {t['window']}; color: {t['text']}; padding: 6px 12px; }}
QTabBar::tab:selected {{ background: {t['panel']}; }}
QWidget#topBar {{ background: {bar}; }}
QWidget#topBar QLabel {{ color: white; }}
QLabel#appName {{ font-size: 12pt; font-weight: 700; padding-left: 4px; }}
QLabel#docTitle {{ font-size: 10pt; font-weight: 600; }}
QToolButton#docPath {{ color: {d['path_text']}; font-size: 8pt; padding: 0; border: none; }}
QToolButton#docPath:hover {{ color: white; text-decoration: underline; background: transparent; }}
QToolButton#fileButton {{ min-width: 64px; }}
QFrame#rail {{ background: {t['panel']}; border-left: 1px solid {t['border']}; }}
QToolButton#railButton {{ font-size: 8pt; color: {t['muted']}; border-radius: 8px; }}
QToolButton#railButton:checked {{ background: {t['checked']}; color: {sel_text};
    border: none; border-right: 3px solid {a}; font-weight: 600; }}
QFrame#sidePanel {{ background: {t['window']}; border-left: 1px solid {t['border']}; }}
QFrame#sidePanel QScrollArea, QFrame#sidePanel QStackedWidget > QWidget {{ background: {t['window']}; }}
QWidget#ribbonPage {{ background: {t['window']}; }}
QLabel#panelTitle {{ font-size: 13pt; font-weight: 600; padding: 12px 14px 6px 14px; background: {t['window']}; }}
QFrame#group {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QLabel#groupTitle {{ color: {t['muted']}; font-size: 7.5pt; font-weight: 600; letter-spacing: 1px; }}
QToolButton#wideButton {{ padding: 3px 8px; }}
QToolButton#kindCard {{ border: 1px solid {t['border']}; border-radius: 12px; background: {t['card']}; padding: 8px; }}
QToolButton#kindCard:hover {{ border: 1px solid {a}; }}
QToolButton#kindCard:checked {{ border: 2px solid {a}; background: {t['checked']}; }}
QLabel#descBox {{ background: {t['card']}; border: 1px solid {t['border']}; border-radius: 10px; padding: 12px; }}
*[hint="true"] {{ color: {t['muted']}; }}
QLabel#previewBox {{ background: {t['view_bg']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QToolTip {{ background: {t['menu']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px 6px; }}
QPushButton:focus, QToolButton:focus {{ outline: none; }}
QScrollBar:vertical {{ background: transparent; width: 12px; }}
QScrollBar::handle:vertical {{ background: rgba(128,128,128,0.45); border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; }}
QScrollBar::handle:horizontal {{ background: rgba(128,128,128,0.45); border-radius: 4px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
