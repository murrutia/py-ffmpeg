from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton, QVBoxLayout, QWidget

from py_ffmpeg.config import EncodingConfig
from py_ffmpeg.qthreads import EncoderWorker


class EncoderViewModel(QObject):
    encoding_started = Signal()
    encoding_finished = Signal()
    progress_updated = Signal(float, int)

    def __init__(self):
        super().__init__()
        self._encoder_worker: EncoderWorker | None = None


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
        self.vm.input_path = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier vidéo", "", EncodingConfig().get_file_filters()
        )


def main():
    app = QApplication()


if __name__ == "__main__":
    main()
