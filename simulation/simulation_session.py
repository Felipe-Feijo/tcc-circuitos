"""Manages a simulation session's lifecycle."""

import logging
from dataclasses import dataclass

from graphics.items.base.connections.connection_item import ConnectionItem
from graphics.items.base.nodes.node_item import NodeItem
from editor.editor_controller import EditorController
from simulation.simulation_engine import SimulationEngine
from simulation.simulation_controller import SimulationController
from simulation.report import report_builder
from simulation.report.frame_recorder import FrameRecorder

logger = logging.getLogger(__name__)


@dataclass
class ReportResult:
    """Result of `SimulationSession.stop()`: where the report was
    built, ready for `resolve_report()` to decide its destination."""
    report_dir: str


class SimulationSession:
    """Controls a simulation's full lifecycle.

    Responsibilities:
    - Building the domain graph from the current graphics scene.
    - Creating and owning the SimulationEngine and SimulationController.
    - Wiring and unwiring graphics items to/from the simulation.
    - Exposing play/pause/toggle to the UI without exposing internal details.

    The dt, timer_interval and speed_index settings persist across
    sessions (start/stop) and are restored on each new start().
    """

    def __init__(self, scene):
        self.scene = scene
        self.engine = None
        self.controller = None
        self.active = False
        self._recorder: FrameRecorder | None = None

        # Settings persistent across sessions
        self.dt = 0.1
        self.timer_interval = 1000
        self.speed_index = 0

    def start(self) -> str | None:
        """Starts the simulation from the scene's current state.

        Builds the domain graph, instantiates the engine and
        controller, wires the graphics items and runs the first step.

        Returns:
            None if started successfully, or an error string if some
            component has a required property left unset. The caller
            is responsible for showing the message to the user.
        """
        if self.active:
            return None

        # Step 1: builds the domain graph
        editor = EditorController(self.scene)
        builder = editor.build_graph()

        # Step 2: creates the engine -- raises ValueError if required props are missing
        try:
            builder.raise_if_errors()
            self.engine = SimulationEngine(
                nodes=builder.nodes,
                connections=builder.connections,
            )
        except ValueError as e:
            return str(e)

        self.controller = SimulationController(self.engine)
        self.controller.on_update_node = builder.node_map
        self.controller.on_update_connection = builder.connection_map

        # Restores persistent settings
        self.controller.set_dt(self.dt)
        self.controller.timer_interval = self.timer_interval

        self.active = True

        self._recorder = FrameRecorder(self.engine, self.scene, self.dt)
        self.controller.state_changed.connect(self._recorder.capture_step)

        # Step 3: activates the graphics items in simulation mode
        self._activate_node_items()

        # Step 4: runs the first step to seed the visual state
        self.controller.request_step(1)
        return None

    def stop(self) -> ReportResult | None:
        """Stops the simulation, restores the visual state and builds the report.

        Returns:
            `ReportResult` pointing at the temp directory holding the
            built report, or None if the session wasn't active, or if
            building the report failed (e.g. an I/O error) -- in that
            case the directory may be incomplete and shouldn't be used.
        """
        if not self.active:
            return None

        self._deactivate_node_items()

        result = None
        try:
            if self._recorder is not None:
                data = self._recorder.finalize()
                report_builder.build(data.frames, data.temp_dir)
                result = ReportResult(report_dir=data.temp_dir)
        except Exception:
            logger.exception("failed to build the simulation report")
            result = None
        finally:
            self._recorder = None
            self.engine = None
            self.controller = None
            self.active = False

        return result

    def play(self):
        """Starts continuous timer-driven execution."""
        if not self.active:
            return
        self.controller.play()

    def pause(self):
        """Pauses continuous execution."""
        if not self.active:
            return
        self.controller.pause()

    def toggle_play(self):
        """Toggles between play and pause."""
        if not self.active:
            return
        if self.controller.playing:
            self.controller.pause()
        else:
            self.controller.play()

    def is_playing(self) -> bool:
        """Returns True if the simulation is running continuously."""
        return bool(self.active and self.controller and self.controller.playing)

    def set_dt(self, value: float) -> None:
        """Updates the session's `dt`, the controller's (if active) and
        the report recorder's (if active), keeping all three in sync."""
        self.dt = value
        if self.controller is not None:
            self.controller.set_dt(value)
        if self._recorder is not None:
            self._recorder.set_dt(value)

    # Internal methods

    def _activate_node_items(self):
        """Puts every NodeItem in the scene into simulation mode."""
        for item in self.scene.items():
            if not isinstance(item, NodeItem):
                continue
            item.simulation_mode = True
            item.on_simulation_activated()
            item.command.connect(self.controller.command)

    def _deactivate_node_items(self):
        """Restores the items' visual state and disconnects command signals."""
        for item in self.scene.items():
            if isinstance(item, NodeItem):
                item.reset_visual_state()
                try:
                    item.command.disconnect(self.controller.command)
                except TypeError:
                    pass  # signal already disconnected or never connected
            elif isinstance(item, ConnectionItem):
                item.reset_visual_state()
