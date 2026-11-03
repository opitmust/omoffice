"""Temalar ve temaya duyarlı simgeler."""
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QColor, QFont, QIcon, QIconEngine, QPainter, QPixmap

THEMES = {
    "Açık": {
        "window": "#F3F4F7", "panel": "#FFFFFF", "border": "#E1E4EA", "text": "#1F2937",
        "muted": "#6B7280", "hover": "#EDF1F8", "checked": "#DCE6F6", "input": "#FFFFFF",
        "input_border": "#CDD2DA", "view_bg": "#E6E8ED", "shadow": "#000000", "icon": "#2B3A55",
        "icon_disabled": "#B4BAC5", "ruler_bg": "#F3F4F7", "ruler_margin": "#D9DDE4",
        "ruler_text": "#FFFFFF", "menu": "#FFFFFF", "card": "#FFFFFF",
    },
    "Koyu": {
        "window": "#1B1D21", "panel": "#25282D", "border": "#34383F", "text": "#E5E7EB",
        "muted": "#9CA3AF", "hover": "#30343B", "checked": "#3A4250", "input": "#1F2226",
        "input_border": "#40454D", "view_bg": "#15171A", "shadow": "#000000", "icon": "#D7DCE4",
        "icon_disabled": "#5A606A", "ruler_bg": "#202327", "ruler_margin": "#3A3E45",
        "ruler_text": "#D9DCE1", "menu": "#25282D", "card": "#2C3036",
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
                color = CURRENT["accent"]
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


def style_sheet():
    t = CURRENT["theme"]
    a = CURRENT["accent"]
    ac = QColor(a)
    tab_text = "#EEF2FA"
    return f"""
QMainWindow, QDialog {{ background: {t['window']}; color: {t['text']}; }}
QWidget {{ color: {t['text']}; }}
QTabWidget#ribbon {{ background: {a}; }}
QTabWidget#ribbon::pane {{ border: none; border-bottom: 1px solid {t['border']}; background: {t['panel']}; top: -1px; }}
QTabWidget#ribbon > QTabBar::tab {{ background: transparent; color: {tab_text}; padding: 7px 16px;
    border: none; font-size: 10pt; margin-top: 4px; }}
QTabWidget#ribbon > QTabBar::tab:selected {{ background: {t['panel']}; color: {a if t['panel'] == '#FFFFFF' else t['text']};
    border-top-left-radius: 7px; border-top-right-radius: 7px; font-weight: 600; }}
QTabWidget#ribbon > QTabBar::tab:hover:!selected {{ background: rgba(255,255,255,0.16); }}
QWidget#ribbonPage {{ background: {t['panel']}; }}
QFrame#group {{ border: none; border-right: 1px solid {t['border']}; background: transparent; }}
QLabel#groupTitle {{ color: {t['muted']}; font-size: 8pt; background: transparent; }}
QToolButton {{ border: 1px solid transparent; border-radius: 5px; padding: 2px; background: transparent; color: {t['text']}; }}
QToolButton:hover {{ background: {t['hover']}; border-color: {t['border']}; }}
QToolButton:checked {{ background: {t['checked']}; border-color: {ac.lighter(130).name()}; }}
QToolButton:disabled {{ color: {t['icon_disabled']}; }}
QToolButton#fileButton {{ background: {ac.darker(115).name()}; color: white; font-weight: 600; padding: 4px 16px;
    border-radius: 0; }}
QToolButton#quickButton:hover {{ background: rgba(255,255,255,0.18); border-color: transparent; }}
QLineEdit#ribbonSearch {{ background: rgba(255,255,255,0.18); border: 1px solid rgba(255,255,255,0.25);
    border-radius: 12px; color: white; padding: 3px 10px; min-width: 210px; }}
QLineEdit#ribbonSearch:focus {{ background: white; color: #222; }}
QComboBox, QFontComboBox, QLineEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit#plain {{
    border: 1px solid {t['input_border']}; border-radius: 4px; padding: 2px 5px;
    background: {t['input']}; color: {t['text']}; min-height: 20px; }}
QComboBox QAbstractItemView {{ background: {t['menu']}; color: {t['text']}; selection-background-color: {a}; }}
QMenu {{ background: {t['menu']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['hover']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 8px; }}
QStatusBar {{ background: {a}; color: white; }}
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
QPushButton#primary {{ background: {a}; color: white; border-color: {a}; }}
QCheckBox, QRadioButton, QLabel {{ background: transparent; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1.5px solid {t['input_border']}; border-radius: 4px;
    background: {t['input']}; }}
QCheckBox::indicator:hover {{ border-color: {a}; }}
QCheckBox::indicator:checked {{ background: {a}; border-color: {a}; }}
QTabWidget::pane {{ border: 1px solid {t['border']}; }}
QTabBar::tab {{ background: {t['window']}; color: {t['text']}; padding: 6px 12px; }}
QTabBar::tab:selected {{ background: {t['panel']}; }}
QWidget#topBar {{ background: {a}; }}
QWidget#topBar QLabel {{ color: white; }}
QLabel#appName {{ font-size: 12pt; font-weight: 700; padding-left: 4px; }}
QLabel#docTitle {{ font-size: 10pt; font-weight: 600; }}
QToolButton#docPath {{ color: rgba(255,255,255,0.78); font-size: 8pt; padding: 0; border: none; }}
QToolButton#docPath:hover {{ color: white; text-decoration: underline; background: transparent; }}
QToolButton#fileButton {{ min-width: 64px; }}
QFrame#rail {{ background: {t['panel']}; border-left: 1px solid {t['border']}; }}
QToolButton#railButton {{ font-size: 8pt; color: {t['muted']}; border-radius: 8px; }}
QToolButton#railButton:checked {{ background: {t['checked']}; color: {a if t['panel'] == '#FFFFFF' else t['text']};
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
QScrollBar:vertical {{ background: transparent; width: 12px; }}
QScrollBar::handle:vertical {{ background: rgba(128,128,128,0.45); border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; }}
QScrollBar::handle:horizontal {{ background: rgba(128,128,128,0.45); border-radius: 4px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
