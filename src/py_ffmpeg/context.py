import os
import sys
from datetime import datetime
import traceback

from ffmpeg import FFmpeg
from ffmpeg.errors import FFmpegError

from .ffprobe import FFprobe
from .media_info import MediaInfo

FFMPEG_EXECUTABLE = os.getenv("FFMPEG_EXECUTABLE", "ffmpeg")
FFPROBE_EXECUTABLE = os.getenv("FFPROBE_EXECUTABLE", "ffprobe")


class FFmpegContext(FFmpeg):
    def __init__(self, executable: str = FFMPEG_EXECUTABLE, *args, **kwargs):
        # Récupération d'éventuels arguments spécifiques pour ffprobe en les supprimant de kwargs avant de les envoyer à FFmpeg
        self._ffprobe_executable = kwargs.pop("ffprobe_executable", FFPROBE_EXECUTABLE)
        self._prevent_auto_probing = kwargs.pop("prevent_auto_probing", False)
        _input = kwargs.pop("input", None)

        super().__init__(*args, **kwargs)

        self._media_info: MediaInfo | None = None
        self._start_time: datetime | None = None

        if _input:
            self.input(_input)

    def execute(self, *args, **kwargs):
        self._start_time = datetime.now()
        super().execute(*args, **kwargs)

    def first_input_url(self) -> str:
        if len(self._options._input_files) == 0:
            raise FFmpegError("Aucun fichier d'entrée n'a été spécifié.")
        return self._options._input_files[0].url

    def probe(self) -> MediaInfo:
        ffprober = FFprobe(self._ffprobe_executable)
        self._media_info = ffprober.probe(self.first_input_url())
        return self._media_info

    def input(self, *args, **kwargs):
        super().input(*args, **kwargs)
        if len(self._options._input_files) == 1 and not self._prevent_auto_probing:
            self.probe()
        return self

    @property
    def media_info(self) -> MediaInfo | None:
        """Accès direct à l'objet MediaInfo analysé."""
        return self._media_info

    @property
    def is_terminating(self):
        return self._executed and self._terminated

    @property
    def is_terminated(self):
        return not self._executed and self._terminated

    def getinfo(self, attr, default=None):
        """
        Retourne une information spécifique du fichier vidéo.
        Prend en charge les attributs directs de MediaInfo ou les chemins de type 'stream_type.attribute'.
        """
        if self._media_info is None:
            raise FFmpegError(
                "Aucune information vidéo disponible. Assurez-vous d'avoir appelé 'probe()' ou 'input()' avec un fichier."
            )

        # Gérer les chemins de type 'stream_type.attribute'
        if "." in attr:
            parts = attr.split(".", 1)
            if len(parts) == 2:
                stream_type, stream_attr = parts
                if stream_type == "format":
                    source = self._media_info.format
                elif stream_type == "video_stream":  # Utiliser le nom de la propriété MediaInfo
                    source = self._media_info.main_video_stream
                elif stream_type == "audio_stream":  # Utiliser le nom de la propriété MediaInfo
                    source = self._media_info.main_audio_stream
                else:
                    # Permettre d'accéder à d'autres types de streams si nécessaire (ex: data.tags)
                    if (
                        stream_type in self._media_info.streams
                        and self._media_info.streams[stream_type]
                    ):
                        source = self._media_info.streams[stream_type][0]  # Premier stream du type
                    else:
                        raise FFmpegError(f"Type de flux inconnu ou non disponible : {stream_type}")

                if source is None:
                    return default  # Le stream demandé n'existe pas
                return getattr(source, stream_attr, default)

        # Sinon, tenter d'accéder directement à l'attribut de MediaInfo
        return getattr(self._media_info, attr, default)

    def __getattr__(self, name: str):
        """Accès dynamique aux attributs du fichier media."""
        value = self.getinfo(name)

        # Si l'attribut n'existe vraiment pas, lever AttributeError
        if value is not None:
            return value

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'.")


if __name__ == "__main__":
    # Exemple d'utilisation
    # python ffmpeg_context.py /path/to/video.mp4

    video_path = "/tmp/test.mp4" if len(sys.argv) < 2 else sys.argv[1]

    try:
        ffmpeg_ctx = FFmpegContext(input=video_path)

        print("\n--- Informations Globales ---")
        print(f"Video duration : {ffmpeg_ctx.getinfo('duration_human')}")
        print(f"File size : {ffmpeg_ctx.getinfo('size_human')}")
        print(f"Creation date : {ffmpeg_ctx.getinfo('creation_time_human')}")
        print(f"Has video stream : {ffmpeg_ctx.getinfo('has_video_stream')}")
        print(f"Has audio stream : {ffmpeg_ctx.getinfo('has_audio_stream')}")

        print("\n--- Informations Vidéo Principale ---")
        print(f"Video codec name : {ffmpeg_ctx.getinfo('video_stream.codec_name')}")
        print(f"Resolution : {ffmpeg_ctx.getinfo('video_stream.resolution')}")
        print(f"Frame rate : {ffmpeg_ctx.getinfo('video_stream.frame_rate')}")
        print(f"Video bitrate : {ffmpeg_ctx.getinfo('video_stream.bit_rate')}")
        print(f"Rotation : {ffmpeg_ctx.getinfo('video_stream.rotation')}")
        print(f"Display Aspect Ratio : {ffmpeg_ctx.getinfo('video_stream.display_aspect_ratio')}")
        print(f"Bits per pixel : {ffmpeg_ctx.getinfo('video_stream.bits_per_pixel')}")

        print("\n--- Informations Audio Principale ---")
        print(f"Audio codec name : {ffmpeg_ctx.getinfo('audio_stream.codec_name')}")
        print(f"Sample rate : {ffmpeg_ctx.getinfo('audio_stream.sample_rate')}")
        print(f"Channels : {ffmpeg_ctx.getinfo('audio_stream.channels')}")
        print(f"Audio bitrate : {ffmpeg_ctx.getinfo('audio_stream.bit_rate')}")

        print("\n--- Propriétés disponibles pour MediaInfo (via get_available_properties) ---")
        for prop in ffmpeg_ctx.media_info.get_available_properties():
            print(
                f"- {prop['name']} ({prop['type']}) - Calculated: {prop['calculated']} - {prop['description']}"
            )

        print("\n--- Propriétés disponibles pour le Main Video Stream ---")
        if ffmpeg_ctx.media_info and ffmpeg_ctx.media_info.main_video_stream:
            for prop in ffmpeg_ctx.media_info.main_video_stream.get_available_properties():
                print(
                    f"- {prop['name']} ({prop['type']}) - Calculated: {prop['calculated']} - {prop['description']}"
                )
        else:
            print("Pas de stream vidéo principal trouvé.")

        print("\n--- Propriétés disponibles pour le Main Audio Stream ---")
        if ffmpeg_ctx.media_info and ffmpeg_ctx.media_info.main_audio_stream:
            for prop in ffmpeg_ctx.media_info.main_audio_stream.get_available_properties():
                print(
                    f"- {prop['name']} ({prop['type']}) - Calculated: {prop['calculated']} - {prop['description']}"
                )
        else:
            print("Pas de stream audio principal trouvé.")

    except FileNotFoundError as e:
        print(f"Erreur : {e}")
    except FFmpegError as e:
        print(f"Erreur FFmpegContext : {e}")
    except Exception as e:
        print(traceback.format_exc())
        print(f"Une erreur inattendue s'est produite : {e}")
