#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

from py_utils.datetime import duration_human
from py_utils.dl_binaries import download_binaries, get_architecture, get_system
from py_utils.misc import add_dir_to_path
from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from py_ffmpeg.config import EncodingConfig
from py_ffmpeg.encoder import EncodingState, VideoEncoder
from py_ffmpeg.media_info import MediaInfo
from py_ffmpeg.qthreads import EncoderWorker


class EncoderViewModelSignals(QObject):
    log_updated = Signal(str)
    progress_updated = Signal(float, int)
    state_changed = Signal(EncodingState)
    encoding_started = Signal()
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

        self.setup_progress()

        self.message = QLabel()
        self.message.setVisible(False)
        self.message.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.message)

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
        self.vm.signals.log_updated.connect(lambda msg: print(msg))
        self.vm.signals.state_changed.connect(lambda state: self.status.setText(str(state)))
        self.vm.signals.progress_updated.connect(self.on_progress_updated)
        self.vm.signals.encoding_started.connect(self.on_encoding_started)
        self.vm.signals.encoding_finished.connect(self.on_encoding_finished)

    def on_progress_updated(self, percent, remaining):
        self.progress_bar.setValue(int(percent))
        self.remaining_time.setText(f"Temps restant : {duration_human(remaining)}")

    def on_encoding_started(self):
        self.choose_btn.setVisible(False)
        self.progress.setVisible(True)
        self.message.setText(f"{self.vm.input_path}\n⇣\n{self.vm.output_path}")
        self.message.setVisible(True)

    def on_encoding_finished(self, success, message, output_mediainfo):
        self.progress.setVisible(False)
        self.message.setVisible(True)
        if success:
            msg = f"<h3>{message}</h3>"
            url = QUrl.fromLocalFile(self.vm.output_path).toString()
            msg += f'<a href="{url}">{self.vm.output_path}</a>'
            self.message.setText(msg)
            self.message.setOpenExternalLinks(True)
        else:
            self.message.setText(f"<pre>{message}</pre>")

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
    parser = argparse.ArgumentParser(
        description="Encodeur vidéo PySide6 minimaliste avec py-ffmpeg."
    )
    parser.add_argument(
        "--download-binaries", "-b", action="store_true", help="Télécharge les binaires"
    )
    args = parser.parse_args()

    bin_dir = Path(__file__).parent.parent / "bin"
    add_dir_to_path(bin_dir)

    if args.download_binaries:
        print("Téléchargement des binaires...")
        tmp_dir = Path("/tmp/binary_downloads")
        result = download_binaries(
            dl_dir=tmp_dir,
            dest_dir=bin_dir,
            filter_names=["ffmpeg", "ffprobe"],
        )

    main()
