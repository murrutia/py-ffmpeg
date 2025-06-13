from PySide6.QtCore import QObject, QThread, Signal

from .encoder import EncodingState, VideoEncoder


class EncoderWorkerSignals(QObject):
    log_updated = Signal(str)
    progress_updated = Signal(float, int)
    state_changed = Signal(EncodingState())  # To notify the UI to update button states etc.
    started_with_options = Signal(dict)
    finished = Signal(bool, str)  # success, message


class EncoderWorker(QThread):
    """Worker thread to run the VideoEncoder in a separate thread."""

    def __init__(self, video_encoder: VideoEncoder):
        super().__init__()
        self._encoder = video_encoder
        self.signals = EncoderWorkerSignals()

        self._encoder.on_log_callback = self.signals.log_updated.emit
        self._encoder.on_state_changed_callback = self.signals.state_changed.emit
        self._encoder.on_started_callback = self.signals.started_with_options.emit
        self._encoder.on_progress_callback = self.signals.progress_updated.emit
        self._encoder.on_finished_callback = self.signals.finished.emit

    def run(self):
        self._encoder.start()

    def cancel(self):
        self._encoder.cancel()
