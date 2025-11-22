import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView,
    QGraphicsRectItem, QPushButton, QWidget, QVBoxLayout
)
from PyQt6.QtGui import QBrush, QPen, QColor
from PyQt6.QtCore import Qt, QRectF


# ------------------------------------------------------------
# Item gráfico básico (um bloco arrastável)
# ------------------------------------------------------------
class ComponentItem(QGraphicsRectItem):
    def __init__(self, x=0, y=0, w=80, h=40):
        super().__init__(QRectF(0, 0, w, h))
        self.setBrush(QBrush(QColor("#ADD8E6")))
        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(x, y)


# ------------------------------------------------------------
# View personalizada (zoom + pan)
# ------------------------------------------------------------
class GraphicsView(QGraphicsView):
    def __init__(self, *args):
        super().__init__(*args)
        self._panning = False
        self._pan_start = None
        self.setRenderHints(self.renderHints())

        # Suavização visual
        self.setRenderHints(self.renderHints())

        # Melhor qualidade de arraste
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

    def wheelEvent(self, event):
        """Zoom com a roda do mouse."""
        zoom_in_factor = 1.25
        zoom_out_factor = 1 / zoom_in_factor

        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor

        self.scale(zoom_factor, zoom_factor)

    def mousePressEvent(self, event):
        """Pan com botão direito."""
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)


# ------------------------------------------------------------
# Janela principal
# ------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Simulador – Editor Gráfico (Template)")

        # Cena e view gráfica
        self.scene = QGraphicsScene()
        self.view = GraphicsView(self.scene)

        # Botão para adicionar componentes
        self.btn_add = QPushButton("Adicionar Componente")
        self.btn_add.clicked.connect(self.add_component)

        # Layout base
        layout = QVBoxLayout()
        layout.addWidget(self.btn_add)
        layout.addWidget(self.view)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def add_component(self):
        """Adiciona um componente padrão na cena."""
        item = ComponentItem(0, 0, 80, 40)
        self.scene.addItem(item)


# ------------------------------------------------------------
# Execução
# ------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(800, 600)
    w.show()
    sys.exit(app.exec())
