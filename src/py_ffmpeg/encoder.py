import traceback
from datetime import datetime
from enum import Enum, auto
from logging import getLogger
from pathlib import Path
from typing import Any, Callable

from ffmpeg.errors import FFmpegError

from py_ffmpeg.ffprobe import FFprobe
from py_ffmpeg.media_info import MediaInfo

from .context import FFmpegContext


class EncodingState(Enum):
    IDLE = auto()
    PREPARING = auto()
    ENCODING = auto()
    CANCELLING = auto()
    CANCELLED = auto()
    COMPLETED = auto()
    ERROR = auto()

    def __str__(self) -> str:
        _display_texts = {
            EncodingState.IDLE: "Inactif",
            EncodingState.PREPARING: "Préparation en cours",
            EncodingState.ENCODING: "Encodage en cours",
            EncodingState.CANCELLING: "Annulation en cours",
            EncodingState.CANCELLED: "Annulé",
            EncodingState.COMPLETED: "Terminé",
            EncodingState.ERROR: "Erreur",
        }
        # Retourne le texte correspondant ou le nom du membre par défaut si non trouvé
        # Usage : print(str(encoding_state))
        return _display_texts.get(self, self.name)

    @property
    def display_text(self) -> str:
        return str(self)


class EncodingSettings:
    """
    Représente les paramètres d'encodage vidéo.
    """

    def __init__(self):
        super().__init__()
        self._codec = "libx264"  # Codec vidéo par défaut
        self._crf = 23  # Constant Rate Factor par défaut
        self._preset = "medium"  # Preset d'encodage par défaut
        self._audio_codec = "aac"  # Codec audio par défaut
        self._audio_bitrate = "128k"  # Bitrate audio par défaut
        self._output_format = "mp4"  # Format de sortie par défaut

    @property
    def codec(self) -> str:
        return self._codec

    @codec.setter
    def codec(self, value: str):
        self._codec = value

    @property
    def crf(self) -> int:
        return self._crf

    @crf.setter
    def crf(self, value: int):
        if not 0 <= value <= 51:
            raise VideoSettingError("CRF doit être entre 0 et 51.")
        self._crf = value

    @property
    def preset(self) -> str:
        return self._preset

    @preset.setter
    def preset(self, value: str):
        valid_presets = [
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ]
        if value not in valid_presets:
            raise VideoSettingError(f"Preset invalide. Choisir parmi : {', '.join(valid_presets)}")
        self._preset = value

    @property
    def audio_codec(self) -> str:
        return self._audio_codec

    @audio_codec.setter
    def audio_codec(self, value: str):
        self._audio_codec = value

    @property
    def audio_bitrate(self) -> str:
        return self._audio_bitrate

    @audio_bitrate.setter
    def audio_bitrate(self, value: str):
        self._audio_bitrate = value

    @property
    def output_format(self) -> str:
        return self._output_format


class VideoEncodingError(Exception):
    pass


class VideoSettingError(VideoEncodingError):
    pass


class ValidationException(VideoEncodingError):
    pass


class VideoEncoder:
    def __init__(
        self,
        input_path: str,
        output_path: str,
        encoding_params: dict[str, Any] | None = None,
        input_params: dict[str, Any] | None = None,
        ffmpeg_executable="ffmpeg",
        ffprobe_executable="ffprobe",
    ):
        self._input_path = Path(input_path)
        self._output_path = Path(output_path)
        self._input_params = input_params
        self._encoding_params = encoding_params or {}  # DEFAULT_ENCODING_PARAMS
        self._options_used = None
        self._current_state: EncodingState = EncodingState.IDLE
        self._error_details: str = ""
        self._ffmpeg_executable = ffmpeg_executable
        self._ffprobe_executable = ffprobe_executable

        self._ffmpeg: FFmpegContext | None = None
        self._cancelled = False

        # Callbacks for notifying progress, logs, and completion
        self.on_log_callback: Callable[[str], None] | None = None
        self.on_state_changed_callback: Callable[[EncodingState], None] | None = None
        self.on_started_callback: Callable[[MediaInfo, dict], None] | None = None
        self.on_progress_callback: Callable[[float, int], None] | None = None
        self.on_finished_callback: Callable[[bool, str, MediaInfo | None], None] | None = None

    def _log(self, msg: str):
        if self.on_log_callback:
            self.on_log_callback(msg)
        else:
            getLogger().info(msg)

    def _set_state(self, new_state: EncodingState):
        if self._current_state != new_state:
            self._current_state = new_state
            if self.on_state_changed_callback:
                self.on_state_changed_callback(new_state)

    @property
    def is_encoding(self):
        return bool(self._ffmpeg and self._ffmpeg._executed)

    @property
    def is_cancelling(self):
        return bool(self._ffmpeg and self._cancelled and self._ffmpeg._executed)

    @property
    def is_cancelled(self):
        return bool(self._ffmpeg and self._cancelled and not self._ffmpeg._executed)

    def start(self):
        self._cancelled = False
        self._set_state(EncodingState.PREPARING)
        try:

            self._validate_input()
            self._setup_ffmpeg()

            self._setup_ffmpeg_callbacks()

            self._log(f"Début de l'encodage avec la commande :")
            self._log(" ".join(self._ffmpeg.arguments))
            # L'état ENCODING sera défini dans on_stderr lorsque les options sont détectées
            self._ffmpeg.execute()

            self._handle_processing_result()

        except ValidationException as e:
            self._handle_error(f"Erreur de validation : {e}")
        except FFmpegError as e:
            self._handle_error(f"Erreur lors de l'exécution de FFmpeg : {e}")
        except Exception as e:
            print(traceback.format_exc())
            self._handle_error(f"Erreur inattendue lors de l'encodage : {e}")

    def _validate_input(self):
        if not Path(self._input_path).exists():
            raise ValidationException(f"Fichier source inexistant: {self._input_path}")

    def _setup_ffmpeg(self):
        self._ffmpeg = (
            FFmpegContext(
                executable=self._ffmpeg_executable, ffprobe_executable=self._ffprobe_executable
            )
            .input(str(self._input_path), options=self._input_params)
            .output(str(self._output_path), options=self._encoding_params)
            .option("y")
        )

        if not self._ffmpeg.has_video_stream:
            raise ValidationException(
                f"Le fichier {self._input_path} ne contient pas de piste vidéo."
            )

    def _handle_error(self, msg: str):
        self._error_details = msg
        if self.on_finished_callback:
            self.on_finished_callback(False, msg, None)

    def _setup_ffmpeg_callbacks(self):
        if self.on_progress_callback:

            @self._ffmpeg.on("progress")
            def on_progress(progress):
                if self._cancelled:
                    return None

                remaining = 0
                if self._ffmpeg._start_time:
                    elapsed = (datetime.now() - self._ffmpeg._start_time).seconds
                    processed = progress.time.seconds
                    speed = processed / elapsed if elapsed > 0 else 0
                    remaining = int((self._ffmpeg.duration - processed) / speed) if speed > 0 else 0

                percent = 0
                if hasattr(self._ffmpeg, "nb_frames") and self._ffmpeg.nb_frames > 0:
                    percent = min(100, (progress.frame / self._ffmpeg.nb_frames) * 100)

                self.on_progress_callback(percent, remaining)

            @self._ffmpeg.on("stderr")
            def on_stderr(line):
                """Au démarrage de ffmpeg, un observer analyse la sortie d'erreur jusqu'à voir la ligne contenant
                "options:" qui indique les paramètres x264 qui seront utilisés pour l'encodage (que l'on récupère).

                À ce niveau là, ffmpeg a validé l'input, les paramètres d'encodage et l'output, donc on peut considérer
                qu'on est dans l'état d'ENCODING.
                """
                if "options:" in line:
                    options_str = line.split("options:")[1].strip()
                    self._options_used = dict(x.split("=") for x in options_str.split(" "))
                    self._set_state(EncodingState.ENCODING)
                    if self.on_started_callback:
                        self.on_started_callback(self.input_mediainfo, self._options_used)
                    # Once options are found, remove the listener
                    self._ffmpeg.remove_listener("stderr", on_stderr)

    def _handle_processing_result(self):
        if self._cancelled:
            self._set_state(EncodingState.CANCELLED)
            if self.on_finished_callback:
                self.on_finished_callback(False, "Encodage annulé par l'utilisateur", None)
        elif self._ffmpeg._process.returncode == 0:
            self._set_state(EncodingState.COMPLETED)
            if self.on_progress_callback:
                self.on_progress_callback(100, 0)
            if self.on_finished_callback:
                self.on_finished_callback(
                    True,
                    "Encodage terminé avec succès !",
                    FFprobe(self._ffprobe_executable).probe(self._output_path),
                )
        else:
            self._set_state(EncodingState.ERROR)
            error_msg = f"Erreur d'encodage (code: {self._ffmpeg._process.returncode})"
            if self.on_finished_callback:
                self.on_finished_callback(False, error_msg, None)

    def cancel(self):
        if self._current_state not in [EncodingState.ENCODING, EncodingState.PREPARING]:
            return

        self._cancelled = True
        self._set_state(EncodingState.CANCELLING)
        if self._ffmpeg and hasattr(self._ffmpeg, "_process") and self._ffmpeg._process:
            if self._ffmpeg._process.poll() is None:
                self._log("Annulation de l'encodage en cours...")
                try:
                    self._ffmpeg.terminate()
                    self._log("Signal d'arrêt envoyé à FFmpeg")
                except Exception as e:
                    self._log(f"Erreur lors de l'arrêt: {e}")
                    try:
                        self._ffmpeg._process.kill()
                        self._log("Processus FFmpeg forcé à s'arrêter")
                    except Exception as kill_error:
                        self._log(f"Impossible d'arrêter le processus: {kill_error}")
                finally:
                    if self._output_path and self._output_path.exists():
                        self._output_path.unlink()
                        self._log("Fichier de sortie supprimé")

    @property
    def input_mediainfo(self):
        if self._ffmpeg:
            return self._ffmpeg.media_info

    def update_encoding_params(self, new_params: dict[str, Any]):
        if self.is_encoding or self.is_cancelling:
            raise VideoSettingError(
                "Il n'est pas possible de changer de paramètres pendant un encodage."
            )

        self._encoding_params.update(new_params)
