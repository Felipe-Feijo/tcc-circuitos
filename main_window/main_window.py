# main_window.py
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QGraphicsScene, QMessageBox, QGraphicsRectItem
)
from PyQt6.QtGui import QAction

from graphics.view import GraphicsView
from graphics.items.component_item import ComponentItem

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self._create_menus()
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
        self.update_scene_rect()

    def _create_menus(self):
        menu_bar = self.menuBar()

        # -----------------
        # FILE
        # -----------------
        file_menu = menu_bar.addMenu("File")

        new_action = QAction("New", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_scene)

        open_action = QAction("Open", self)
        open_action.setShortcut("Ctrl+O")

        save_action = QAction("Save", self)
        save_action.setShortcut("Ctrl+S")

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        # -----------------
        # EDIT
        # -----------------
        edit_menu = menu_bar.addMenu("Edit")

        delete_action = QAction("Delete", self)
        delete_action.setShortcut("Del")
        delete_action.triggered.connect(lambda: self.activate_mode("delete"))

        edit_menu.addAction(delete_action)

        # -----------------
        # VIEW
        # -----------------
        view_menu = menu_bar.addMenu("View")

        toggle_grid = QAction("Show Grid", self, checkable=True)
        toggle_grid.setChecked(True)

        view_menu.addAction(toggle_grid)

        # -----------------
        # HELP
        # -----------------
        help_menu = menu_bar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)

        help_menu.addAction(about_action)

    def new_scene(self):
        self.scene.clear()

    def show_about(self):
        QMessageBox.about(
            self,
            "About",
            "Simulador – Editor Gráfico\n"
            "Pneumatic and Hydraulic Systems\n\n"
            "Built with PyQt6"
        )

    def update_scene_rect(self):
        

        view = self.view

        # salvar posição atual da câmera
        h_scroll = view.horizontalScrollBar().value()
        v_scroll = view.verticalScrollBar().value()

        # área visível
        visible_rect = view.mapToScene(
            view.viewport().rect()
        ).boundingRect()

        # área dos itens
        items_rect = self.scene.itemsBoundingRect()
        margin = max(
            80,
            max(visible_rect.width(), visible_rect.height()) * 0.1
        )
        # união
        united = visible_rect.united(items_rect)

        self.scene.setSceneRect(
            united.adjusted(-margin, -margin, margin, margin)
        )

        # restaurar posição da câmera
        view.horizontalScrollBar().setValue(h_scroll)
        view.verticalScrollBar().setValue(v_scroll)