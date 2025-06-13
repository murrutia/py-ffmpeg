from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton, QVBoxLayout, QWidget

from py_ffmpeg.config import EncodingConfig
from py_ffmpeg.encoder import VideoEncoder
from py_ffmpeg.qthreads import EncoderWorker


class EncoderViewModel(QObject):
    encoding_started = Signal()
    encoding_finished = Signal()
    progress_updated = Signal(float, int)

    def __init__(self):
        super().__init__()
        self._encoder_worker: EncoderWorker | None = None
        self._input_path: str | None = None
        self._output_path: str | None = None

    @property
    def input_path(self):
        return self._input_path

    @input_path.setter
    def input_path(self, value):
        if self._input_path != value:
            self._input_path = value
            self._output_path = EncodingConfig().suggest_output_filepath(value)
            self._start_encoding()

    def _start_encoding(self):
        encoder = VideoEncoder(self._input_path, self._output_path)
        self._encoder_worker = EncoderWorker(encoder)
        self._encoder_worker.signals.started_with_options.connect(self.encoding_started)
        self._encoder_worker.signals.finished.connect(self.encoding_finished)


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.vm = EncoderViewModel()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.choose_btn = QPushButton("Choisir un fichier")
        self.choose_btn.clicked.connect(self.choose_file)

    def choose_file(self):
        self.vm.input_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier vidéo", "", EncodingConfig().get_file_filters()
        )


def main():
    app = QApplication()


if __name__ == "__main__":
    main()
