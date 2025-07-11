import sys
from pathlib import Path

from py_utils.datetime import duration_human
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from py_ffmpeg.config import EncodingConfig
from py_ffmpeg.encoder import EncodingState, VideoEncoder
from py_ffmpeg.ffprobe import FFprobe
from py_ffmpeg.media_info import MediaInfo
from py_ffmpeg.qthreads import EncoderWorker


class EncoderViewModelSignals(QObject):
    log_updated = Signal(str)
    progress_updated = Signal(float, int)
    state_changed = Signal(EncodingState)
    encoding_started = Signal(MediaInfo, dict)
    encoding_finished = Signal(bool, str, MediaInfo)


class EncoderViewModel(QObject):

    def __init__(self):
        super().__init__()
        self._encoder_worker: EncoderWorker | None = None
        self._input_path: str | None = None
        self._output_path: str | None = None

        self.signals = EncoderViewModelSignals()

    @property
    def input_path(self):
        return Path(self._input_path)

    @property
    def output_path(self):
        return Path(self._output_path)

    @input_path.setter
    def input_path(self, value):
        if self._input_path != value:
            self._input_path = value
            self._output_path = EncodingConfig().suggest_output_filepath(value)
            self._start_encoding()

    def _start_encoding(self):
        encoder = VideoEncoder(self._input_path, self._output_path)
        self._encoder_worker = EncoderWorker(encoder)
        self._encoder_worker.signals.started_with_options.connect(self.signals.encoding_started)
        self._encoder_worker.signals.finished.connect(self.signals.encoding_finished)
        self._encoder_worker.signals.progress_updated.connect(self.signals.progress_updated)
        self._encoder_worker.signals.state_changed.connect(self.signals.state_changed)
        self._encoder_worker.signals.log_updated.connect(self.signals.log_updated)
        self._encoder_worker.start()

    def quit_cleanly(self):
        if self._encoder_worker:
            self._encoder_worker.cancel()
            self._encoder_worker.wait()


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.vm = EncoderViewModel()
        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.choose_btn = QPushButton("Choisir un fichier à encoder")
        layout.addWidget(self.choose_btn)

        self.cancel_btn = QPushButton("Annuler l'encodage")
        self.cancel_btn.setVisible(False)
        layout.addWidget(self.cancel_btn)

        self.setup_input_infos()
        self.setup_progress()
        self.setup_log_area()
        self.setup_output_infos()

    def setup_input_infos(self):
        self.input_infos = QWidget()
        self.input_infos.setVisible(False)
        self.layout().addWidget(self.input_infos)

        layout = QVBoxLayout()
        self.input_infos.setLayout(layout)

        self.input_filename = QLabel()
        layout.addWidget(self.input_filename)

        self.input_folder = QLabel()
        layout.addWidget(self.input_folder)

        self.input_data = QLabel()
        layout.addWidget(self.input_data)

    def setup_log_area(self):
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setVisible(False)
        self.layout().addWidget(self.log_area)

    def setup_output_infos(self):
        self.output_infos = QWidget()
        self.output_infos.setVisible(False)
        self.layout().addWidget(self.output_infos)

        layout = QVBoxLayout()
        self.output_infos.setLayout(layout)

        self.output_filename = QLabel()
        layout.addWidget(self.output_filename)

        self.output_folder = QLabel()
        layout.addWidget(self.output_folder)

        self.output_data = QLabel()
        layout.addWidget(self.output_data)

    def setup_progress(self):

        self.progress = QWidget()
        self.progress.setVisible(False)
        self.layout().addWidget(self.progress)

        layout = QHBoxLayout()
        self.progress.setLayout(layout)

        self.status = QLabel()
        layout.addWidget(self.status)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.remaining_time = QLabel()
        layout.addWidget(self.remaining_time)

    def setup_connections(self):
        self.choose_btn.clicked.connect(self.choose_file)
        self.cancel_btn.clicked.connect(self.vm.quit_cleanly)
        self.vm.signals.state_changed.connect(lambda state: self.status.setText(str(state)))
        self.vm.signals.progress_updated.connect(self.on_progress_updated)
        self.vm.signals.encoding_started.connect(self.on_encoding_started)
        self.vm.signals.encoding_finished.connect(self.on_encoding_finished)
        self.vm.signals.log_updated.connect(self.log_area.append)

    def on_progress_updated(self, percent, remaining):
        self.progress_bar.setValue(int(percent))
        self.remaining_time.setText(f"Temps restant : {duration_human(remaining)}")

    def on_encoding_started(self, input_mediainfo, options):
        self.choose_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.input_filename.setText(self.vm.input_path.name)
        self.input_folder.setText(f"Dossier : {self.vm.input_path.parent}")
        self.input_data.setText(input_mediainfo.summary_str)

        self.input_infos.setVisible(True)
        self.log_area.setVisible(True)
        self.progress.setVisible(True)

    def on_encoding_finished(self, success, message, output_mediainfo):
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        if output_mediainfo:
            self.output_filename.setText(self.vm.output_path.name)
            self.output_folder.setText(f"Dossier : {self.vm.output_path.parent}")
            self.output_data.setText(output_mediainfo.summary_str)
        else:
            self.output_filename.setText(message)

        self.output_filename.setStyleSheet("color: green" if success else "color: red")

        self.output_infos.setVisible(True)

    def choose_file(self):
        self.vm.input_path, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner un fichier vidéo", "", EncodingConfig().get_file_filters()
        )

    def closeEvent(self, event):
        self.vm.quit_cleanly()
        return super().closeEvent(event)


def main():
    app = QApplication()
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
