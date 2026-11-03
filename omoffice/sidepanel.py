"""Sağ kenardaki dikey araç çubuğu: simge rayı + açılır araç paneli."""
from PySide6.QtCore import Qt, Signal, QObject, QSize
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QToolButton, QStackedWidget, QLabel, QScrollArea,
    QButtonGroup,
)

PANEL_WIDTH = 318


class SidePanel(QWidget):
    currentChanged = Signal(int)
    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.panel = QFrame()
        self.panel.setObjectName("sidePanel")
        self.panel.setFixedWidth(PANEL_WIDTH)
        pv = QVBoxLayout(self.panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)
        self.header = QLabel()
        self.header.setObjectName("panelTitle")
        pv.addWidget(self.header)
        self.stack = QStackedWidget()
        pv.addWidget(self.stack, 1)
        self.rail = QFrame()
        self.rail.setObjectName("rail")
        self.rail.setFixedWidth(68)
        self.rail_layout = QVBoxLayout(self.rail)
        self.rail_layout.setContentsMargins(4, 8, 4, 8)
        self.rail_layout.setSpacing(4)
        self.rail_layout.addStretch(1)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        h.addWidget(self.panel)
        h.addWidget(self.rail)
        self.pages, self.titles, self.buttons = [], [], []
        self._current = -1

    def add_page(self, title, icon, widget, scroll=True, tooltip=None):
        i = len(self.pages)
        if scroll:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            widget.setMaximumWidth(PANEL_WIDTH - 14)  # uzun metinler kaydırma yerine satır kaydırsın
            area.setWidget(widget)
            self.stack.addWidget(area)
        else:
            self.stack.addWidget(widget)
        b = QToolButton()
        b.setObjectName("railButton")
        b.setCheckable(True)
        b.setIcon(icon)
        b.setIconSize(QSize(22, 22))
        b.setText({"Açıklamalar": "Yorumlar", "Gözden Geçir": "İnceleme", "Başvurular": "Kaynaklar"}
                  .get(title, title))
        b.setToolTip(tooltip or title)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setFixedSize(60, 54)
        b.clicked.connect(lambda _=False, i=i: self.select(i, toggle=True))
        self.group.addButton(b, i)
        self.rail_layout.insertWidget(len(self.buttons), b)
        self.pages.append(widget)
        self.titles.append(title)
        self.buttons.append(b)
        if self._current < 0:
            self.select(0)
        return i

    def add_rail_action(self, action, icon=None):
        """Rayın en altına tek tıklık düğme (ör. paneli daralt)."""
        b = QToolButton()
        b.setObjectName("railButton")
        b.setDefaultAction(action)
        if icon is not None:
            b.setIcon(icon)
        b.setIconSize(QSize(20, 20))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        b.setFixedSize(60, 40)
        self.rail_layout.addWidget(b)
        return b

    def select(self, i, toggle=False):
        if toggle and i == self._current and self.panel.isVisibleTo(self):
            self.set_collapsed(True)
            return
        self._current = i
        self.stack.setCurrentIndex(i)
        self.header.setText(self.titles[i])
        self.buttons[i].setChecked(True)
        self.set_collapsed(False)
        self.currentChanged.emit(i)

    def set_collapsed(self, collapsed):
        self.panel.setVisible(not collapsed)
        if collapsed:
            self.group.setExclusive(False)
            for b in self.buttons:
                b.setChecked(False)
            self.group.setExclusive(True)
        elif 0 <= self._current < len(self.buttons):
            self.buttons[self._current].setChecked(True)
        self.collapsedChanged.emit(collapsed)

    def is_collapsed(self):
        return not self.panel.isVisibleTo(self)

    # QTabWidget benzeri arayüz (komut paleti ve testler için)
    def count(self):
        return len(self.pages)

    def widget(self, i):
        return self.pages[i]

    def tabText(self, i):
        return self.titles[i]

    def currentIndex(self):
        return self._current

    def setCurrentIndex(self, i):
        self.select(i)

    def index_of(self, title):
        return self.titles.index(title)


class PanelPage(QObject):
    """Yan paneldeki bir sayfayı yuvalanabilir pencere gibi kullanmak için (show/hide/isVisible)."""

    visibilityChanged = Signal(bool)

    def __init__(self, side, index):
        super().__init__(side)
        self.side = side
        self.index = index
        self._last = False
        side.currentChanged.connect(self._emit)
        side.collapsedChanged.connect(self._emit)

    def _emit(self, *_):
        v = self.isVisible()
        if v != self._last:
            self._last = v
            self.visibilityChanged.emit(v)

    def isVisible(self):
        return not self.side.is_collapsed() and self.side.currentIndex() == self.index

    def show(self):
        self.side.select(self.index)

    def hide(self):
        if self.isVisible():
            self.side.set_collapsed(True)

    def setVisible(self, v):
        self.show() if v else self.hide()
