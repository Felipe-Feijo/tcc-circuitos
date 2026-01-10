import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView,
    QGraphicsRectItem, QPushButton, QWidget, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtGui import QBrush, QPen, QColor
from PyQt6.QtCore import Qt, QRectF


# ------------------------------------------------------------
# Item gráfico básico (um bloco arrastável)
# ------------------------------------------------------------
class ComponentItem(QGraphicsRectItem):
    def __init__(self, x=0, y=0, w=80, h=40):
        super().__init__(QRectF(0, 0, w, h))
        self.editor = None

        self.setBrush(QBrush(QColor("#ADD8E6")))
        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPos(x, y)

    def mousePressEvent(self, event):
        if self.editor and self.editor.delete_mode:   # se modo delete estiver ativo
            self.scene().removeItem(self)            # apaga o item
            return                                   # evita clique normal
        super().mousePressEvent(event)

# ------------------------------------------------------------
# View personalizada (zoom + pan)
# ------------------------------------------------------------
class GraphicsView(QGraphicsView):
    def __init__(self, editor, *args):
        super().__init__(*args)
        self.editor = editor

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
        # Clique esquerdo no modo adicionar → criar item na posição clicada
        if event.button() == Qt.MouseButton.LeftButton and self.editor.add_mode:
            scene_pos = self.mapToScene(event.pos())
            self.editor.add_component_at(scene_pos.x(), scene_pos.y())
            return  # evita clicar/selecionar outros itens

        # Pan com botão direito
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
        self.scene = QGraphicsScene()
        self.view = GraphicsView(self, self.scene)

        # Estado do modo mover
        self.move_mode = False

        self.delete_mode = False

        self.add_mode = False

        # -----------------------------
        # Botão "Mover"
        # -----------------------------
        self.btn_move = QPushButton("Mover")
        self.btn_move.setCheckable(True)
        self.btn_move.clicked.connect(lambda checked: self.activate_mode("move") if checked else self.activate_mode(None))



        self.btn_move.setFixedSize(120, 32)  # tamanho fixo

        self.btn_move.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border-radius: 6px;
                padding: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1E88E5;
            }
            QPushButton:checked {
                background-color: #0D47A1;
            }
        """)

        # -----------------------------
        # Botão "Adicionar Componente"
        # -----------------------------
        self.btn_add = QPushButton("Adicionar")
        self.btn_add.setCheckable(True)
        self.btn_add.clicked.connect(lambda checked: self.activate_mode("add") if checked else self.activate_mode(None))
        self.btn_add.setFixedSize(150, 32)

        self.btn_move.setStyleSheet("""
            QPushButton {
                background-color: #b0b0b0;      /* CINZA (OFF) */
                color: black;
                border-radius: 6px;
                padding: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c8c8c8;
            }
            QPushButton:checked {
                background-color: #1976D2;     /* AZUL (ON) */
                color: white;
            }
            QPushButton:checked:hover {
                background-color: #1E88E5;
            }
        """)

        # -----------------------------
        # Botão "Deletar"
        # -----------------------------
        self.btn_delete = QPushButton("Deletar")
        self.btn_delete.setCheckable(True)
        self.btn_delete.clicked.connect(lambda checked: self.activate_mode("delete") if checked else self.activate_mode(None))


        self.btn_delete.setFixedSize(120, 32)

        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #b0b0b0;      /* cinza (OFF) */
                color: black;
                border-radius: 6px;
                padding: 6px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #c8c8c8;
            }
            QPushButton:checked {
                background-color: #D32F2F;      /* vermelho (ON) */
                color: white;
            }
            QPushButton:checked:hover {
                background-color: #E53935;
            }
        """)


        # -----------------------------
        # BARRA SUPERIOR (TOOLBAR)
        # -----------------------------
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)       # espaço entre os botões
        toolbar.setContentsMargins(10, 10, 10, 10)

        toolbar.addWidget(self.btn_move)
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_delete)
        toolbar.addStretch()         # empurra tudo para a esquerda

        # -----------------------------
        # Layout principal (toolbar + view)
        # -----------------------------
        main_layout = QVBoxLayout()
        main_layout.addLayout(toolbar)
        main_layout.addWidget(self.view)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def activate_mode(self, mode):
        # Resetar estados
        self.move_mode = False
        self.delete_mode = False
        self.add_mode = False

        # Desmarcar todos botões
        self.btn_move.setChecked(False)
        self.btn_add.setChecked(False)
        self.btn_delete.setChecked(False)

        # Ativar o modo correto
        if mode == "move":
            self.move_mode = True
            self.btn_move.setChecked(True)

            # permitir mover os itens
            for item in self.scene.items():
                if isinstance(item, ComponentItem):
                    item.setFlag(
                        QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True
                    )

        elif mode == "add":
            self.add_mode = True
            self.btn_add.setChecked(True)

            # mover deve ficar OFF
            for item in self.scene.items():
                if isinstance(item, ComponentItem):
                    item.setFlag(
                        QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False
                    )

        elif mode == "delete":
            self.delete_mode = True
            self.btn_delete.setChecked(True)

            for item in self.scene.items():
                if isinstance(item, ComponentItem):
                    item.setFlag(
                        QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False
                    )


    def add_component_at(self, x, y):
        w, h = 80, 40
        item = ComponentItem(0, 0, w, h)
        item.editor = self
        
        # centralizar o item no clique:
        item.setPos(x - w/2, y - h/2)

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
