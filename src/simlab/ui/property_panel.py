from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QWidget

from simlab.models.actor import Actor
from simlab.models.transform import Transform


class PropertyPanel(QWidget):
    actor_name_changed = Signal(str, str)
    actor_transform_changed = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self.actor_id: str | None = None
        self._loading = False

        self.name_edit = QLineEdit()
        self.type_label = QLabel("-")
        self.asset_label = QLabel("-")
        self.fields: dict[str, QDoubleSpinBox] = {}

        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addRow("Name", self.name_edit)
        layout.addRow("Type", self.type_label)
        layout.addRow("Asset", self.asset_label)

        for key in (
            "position_x",
            "position_y",
            "position_z",
            "rotation_roll",
            "rotation_pitch",
            "rotation_yaw",
            "scale_x",
            "scale_y",
            "scale_z",
        ):
            field = QDoubleSpinBox()
            field.setDecimals(4)
            field.setRange(-100000.0, 100000.0)
            if key.startswith("scale"):
                field.setMinimum(0.0001)
            field.valueChanged.connect(self._emit_transform)
            self.fields[key] = field
            layout.addRow(key.replace("_", " ").title(), field)

        self.name_edit.editingFinished.connect(self._emit_name)
        self.set_actor(None)

    def set_actor(self, actor: Actor | None) -> None:
        self._loading = True
        self.actor_id = actor.id if actor else None
        enabled = actor is not None
        self.name_edit.setEnabled(enabled)
        for field in self.fields.values():
            field.setEnabled(enabled)

        if actor is None:
            self.name_edit.setText("")
            self.type_label.setText("-")
            self.asset_label.setText("-")
            values = Transform()
        else:
            self.name_edit.setText(actor.name)
            self.type_label.setText(actor.type)
            self.asset_label.setText(actor.asset_id)
            values = actor.transform

        self._set_values(values)
        self._loading = False

    def _set_values(self, transform: Transform) -> None:
        mapping = {
            "position_x": transform.position[0],
            "position_y": transform.position[1],
            "position_z": transform.position[2],
            "rotation_roll": transform.rotation[0],
            "rotation_pitch": transform.rotation[1],
            "rotation_yaw": transform.rotation[2],
            "scale_x": transform.scale[0],
            "scale_y": transform.scale[1],
            "scale_z": transform.scale[2],
        }
        for key, value in mapping.items():
            self.fields[key].setValue(float(value))

    def _emit_name(self) -> None:
        if self.actor_id and not self._loading:
            self.actor_name_changed.emit(self.actor_id, self.name_edit.text())

    def _emit_transform(self) -> None:
        if not self.actor_id or self._loading:
            return
        transform = Transform(
            position=[
                self.fields["position_x"].value(),
                self.fields["position_y"].value(),
                self.fields["position_z"].value(),
            ],
            rotation=[
                self.fields["rotation_roll"].value(),
                self.fields["rotation_pitch"].value(),
                self.fields["rotation_yaw"].value(),
            ],
            scale=[
                self.fields["scale_x"].value(),
                self.fields["scale_y"].value(),
                self.fields["scale_z"].value(),
            ],
        )
        self.actor_transform_changed.emit(self.actor_id, transform)
