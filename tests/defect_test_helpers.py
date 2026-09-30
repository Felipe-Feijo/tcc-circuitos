"""Shared helpers for the parametric-defect test files."""

from PyQt6.QtWidgets import QFormLayout


def form_label_texts(dialog):
    labels = []
    for i in range(dialog._form_layout.rowCount()):
        item = dialog._form_layout.itemAt(i, QFormLayout.ItemRole.LabelRole)
        if item and item.widget():
            labels.append(item.widget().text())
    return labels
