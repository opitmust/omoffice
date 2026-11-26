"""Yakınlaştırılabilir sayfa görünümü ve cetvel."""
from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QPolygonF, QTransform, QFont, QPen, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QAbstractScrollArea, QGraphicsView, QGraphicsScene, QFrame, QWidget

from .common import mm2px, px2mm

SCENE_MARGIN = 28


class EditorView(QGraphicsView):
    """PageEdit'i bir grafik sahnesine koyar; kaydırma ve yakınlaştırmayı burası yapar."""

    zoomChanged = Signal(float)
    viewChanged = Signal()

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.zoom = 1.0
        self.fit_mode = None   # None | "width" | "page"
        scene = QGraphicsScene(self)
        self.setScene(scene)
        self.proxy = scene.addWidget(editor)
        self.proxy.setPos(0, 0)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.bg = QColor("#E4E7EC")
        self.shadow = QColor(0, 0, 0, 40)
        self._sizing = False
        editor.page_step = lambda: self.viewport().height() / self.zoom * 0.9
        editor.cursorVisibilityRequested.connect(self.ensure_cursor)
        editor.cursorPositionChanged.connect(self.ensure_cursor)
        editor.documentReplaced.connect(self._hook_document)
        editor.pageInfoChanged.connect(self.update_size)
        self.verticalScrollBar().valueChanged.connect(self.viewChanged)
        self.horizontalScrollBar().valueChanged.connect(self.viewChanged)
        self._hook_document()

    def _hook_document(self):
        self.editor.document().documentLayout().documentSizeChanged.connect(lambda _: self.update_size())
        self.update_size()

    def set_colors(self, bg, shadow):
        self.bg = QColor(bg)
        self.shadow = QColor(shadow)
        self.editor.bg_color = self.bg
        self.resetCachedContent()
        self.viewport().update()
        self.editor.viewport().update()

    def update_size(self):
        if self._sizing:
            return
        self._sizing = True
        try:
            pw, ph = self.editor.page_px()
            n = self.editor.page_count()
            w, h = int(round(pw)), int(round(n * ph))
            if self.editor.width() != w or self.editor.height() != h:
                self.editor.setFixedSize(w, h)
            self.scene().setSceneRect(-SCENE_MARGIN, -SCENE_MARGIN, w + 2 * SCENE_MARGIN, h + 2 * SCENE_MARGIN)
        finally:
            self._sizing = False

    def drawBackground(self, painter, rect):
        painter.fillRect(rect, self.bg)
        pw, ph = self.editor.page_px()
        n = self.editor.page_count()
        g = 9
        first = max(0, int(rect.top() // ph))
        last = min(n - 1, int(rect.bottom() // ph) + 1)
        for i in range(first, last + 1):
            r = QRectF(0, i * ph + g, pw, ph - 2 * g)
            for k, a in ((7, 0.07), (4, 0.12), (2, 0.2), (1, 0.3)):
                c = QColor(self.shadow)
                c.setAlphaF(c.alphaF() * a)
                painter.fillRect(r.adjusted(-k, -k + 2, k, k + 2), c)

    # ---- yakınlaştırma
    def set_zoom(self, z, fit=None):
        z = max(0.2, min(5.0, z))
        self.fit_mode = fit
        self.zoom = z
        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setTransform(QTransform.fromScale(z, z))
        self.setTransformationAnchor(anchor)
        self.zoomChanged.emit(z)
        self.viewChanged.emit()

    def fit_width(self):
        pw, _ = self.editor.page_px()
        self.set_zoom((self.viewport().width() - 2 * SCENE_MARGIN) / pw, "width")

    def fit_page(self):
        pw, ph = self.editor.page_px()
        z = min((self.viewport().width() - 2 * SCENE_MARGIN) / pw, (self.viewport().height() - 20) / ph)
        self.set_zoom(z, "page")
        top = self.editor.current_page() - 1
        self.centerOn(pw / 2, top * ph + ph / 2)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fit_mode == "width":
            QTimer.singleShot(0, self.fit_width)
        self.viewChanged.emit()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = e.angleDelta().y() / 120.0
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            z = max(0.2, min(5.0, self.zoom * (1.1 ** steps)))
            self.setTransform(QTransform.fromScale(z, z))
            self.zoom = z
            self.fit_mode = None
            self.zoomChanged.emit(z)
            self.viewChanged.emit()
            e.accept()
            return
        # Tekerlek olayını sahneye (sayfaya) göndermeden doğrudan kaydır: sahnedeki editör olayı
        # yok saysa da Qt onu kabul edilmiş sayıyor ve sayfanın üstündeyken kaydırma hiç olmuyordu.
        QAbstractScrollArea.wheelEvent(self, e)

    def ensure_cursor(self):
        r = QRectF(self.editor.cursorRect())
        sr = self.proxy.mapRectToScene(r)
        self.ensureVisible(sr, 30, 60)

    def focus_editor(self):
        self.setFocus()
        self.scene().setFocusItem(self.proxy)
        self.editor.setFocus()

    def doc_to_viewport(self, pt):
        return self.mapFromScene(self.proxy.mapToScene(pt))

    def selection_anchor_global(self):
        """Seçimin üst kenarının ekran konumu (mini araç çubuğu için)."""
        c = self.editor.textCursor()
        a = QTextCursor(c)
        a.setPosition(c.selectionStart())
        r1 = self.editor.cursorRect(a)
        r2 = self.editor.cursorRect()
        top = min(r1.top(), r2.top())
        vp = self.doc_to_viewport(QPointF(r2.left(), top))
        return self.viewport().mapToGlobal(vp)


class Ruler(QWidget):
    """Yatay cetvel: kenar boşlukları ve paragraf girintileri (sürüklenebilir)."""

    HEIGHT = 24

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.editor = view.editor
        self.setFixedHeight(self.HEIGHT)
        self.colors = {"bg": "#F3F4F7", "margin": "#D9DDE4", "text": "#FFFFFF", "tick": "#6B7280",
                       "marker": "#2F5DA8"}
        self.drag = None
        self.setMouseTracking(True)
        view.viewChanged.connect(self.update)
        self.editor.cursorPositionChanged.connect(self.update)

    def set_colors(self, colors):
        self.colors.update(colors)
        self.update()

    def _x(self, doc_x):
        return self.view.doc_to_viewport(QPointF(doc_x, 0)).x() + self.view.viewport().x()

    def _doc_x(self, x):
        return self.view.mapToScene(int(x - self.view.viewport().x()), 0).x()

    def _markers(self):
        s = self.editor.setup
        lm = mm2px(s.left_mm)
        rm = mm2px(s.width_mm - s.right_mm)
        bf = self.editor.textCursor().blockFormat()
        lst = self.editor.textCursor().block().textList()
        indent = (lst.format().indent() if lst else bf.indent()) * self.editor.document().indentWidth()
        left = lm + bf.leftMargin() + indent
        first = left + bf.textIndent()
        right = rm - bf.rightMargin()
        return {"first": first, "left": left, "right": right}

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        C = {k: QColor(v) for k, v in self.colors.items()}
        p.fillRect(self.rect(), C["bg"])
        s = self.editor.setup
        x0, x1 = self._x(0), self._x(mm2px(s.width_mm))
        lm, rm = self._x(mm2px(s.left_mm)), self._x(mm2px(s.width_mm - s.right_mm))
        top, h = 4, self.HEIGHT - 8
        p.fillRect(QRectF(x0, top, x1 - x0, h), C["margin"])
        p.fillRect(QRectF(lm, top, rm - lm, h), C["text"])
        f = QFont(self.font())
        f.setPixelSize(9)
        p.setFont(f)
        p.setPen(C["tick"])
        mm = -int(s.left_mm // 2.5) * 2.5
        while mm <= s.width_mm - s.left_mm + 0.01:
            x = self._x(mm2px(s.left_mm + mm))
            if x0 <= x <= x1:
                k = round(mm / 2.5)
                if k % 4 == 0 and k != 0:
                    p.drawText(QRectF(x - 10, top, 20, h), int(Qt.AlignmentFlag.AlignCenter), str(abs(k // 4)))
                elif k % 2 == 0:
                    p.drawLine(QPointF(x, top + h / 2 - 3), QPointF(x, top + h / 2 + 3))
                else:
                    p.drawLine(QPointF(x, top + h / 2 - 1), QPointF(x, top + h / 2 + 1))
            mm += 2.5
        m = self._markers()
        p.setPen(QPen(C["marker"].darker(130), 1))
        p.setBrush(C["marker"])
        fx = self._x(m["first"])
        p.drawPolygon(QPolygonF([QPointF(fx - 5, 0), QPointF(fx + 5, 0), QPointF(fx, 7)]))
        lx = self._x(m["left"])
        p.drawPolygon(QPolygonF([QPointF(lx - 5, self.HEIGHT - 1), QPointF(lx + 5, self.HEIGHT - 1),
                                 QPointF(lx, self.HEIGHT - 8)]))
        rx = self._x(m["right"])
        p.drawPolygon(QPolygonF([QPointF(rx - 5, self.HEIGHT - 1), QPointF(rx + 5, self.HEIGHT - 1),
                                 QPointF(rx, self.HEIGHT - 8)]))
        if self.drag:
            p.setPen(QPen(C["marker"], 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(self._x(self.drag[1]), 0), QPointF(self._x(self.drag[1]), self.HEIGHT))
        p.end()

    def _hit(self, pos):
        m = self._markers()
        cands = []
        for k, v in m.items():
            x = self._x(v)
            if abs(pos.x() - x) <= 6:
                if k == "first" and pos.y() <= self.HEIGHT / 2:
                    cands.append((0, k))
                elif k in ("left", "right") and pos.y() > self.HEIGHT / 2:
                    cands.append((0, k))
                else:
                    cands.append((1, k))
        return min(cands)[1] if cands else None

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.drag:
            step = mm2px(2.5)
            s = self.editor.setup
            lm = mm2px(s.left_mm)
            x = self._doc_x(pos.x())
            x = lm + round((x - lm) / step) * step
            self.drag = (self.drag[0], x)
            self.update()
            return
        self.setCursor(Qt.CursorShape.SizeHorCursor if self._hit(pos) else Qt.CursorShape.ArrowCursor)
        names = {"first": "İlk satır girintisi", "left": "Sol girinti", "right": "Sağ girinti"}
        h = self._hit(pos)
        self.setToolTip(names.get(h, ""))

    def mousePressEvent(self, e):
        h = self._hit(e.position())
        if h:
            self.drag = (h, self._markers()[h])

    def mouseReleaseEvent(self, e):
        if not self.drag:
            return
        kind, x = self.drag
        self.drag = None
        s = self.editor.setup
        lm = mm2px(s.left_mm)
        rm = mm2px(s.width_mm - s.right_mm)
        m = self._markers()
        c = self.editor.textCursor()
        lst = c.block().textList()
        indent = (lst.format().indent() if lst else c.blockFormat().indent()) * self.editor.document().indentWidth()
        bf = QTextBlockFormat()
        if kind == "first":
            bf.setTextIndent(x - m["left"])
        elif kind == "left":
            bf.setLeftMargin(max(0.0, x - lm - indent))
            bf.setTextIndent(m["first"] - m["left"])
        else:
            bf.setRightMargin(max(0.0, rm - x))
        c.mergeBlockFormat(bf)
        self.update()
