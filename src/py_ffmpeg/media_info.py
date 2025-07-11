import re
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Any, get_type_hints

from dateutil.parser import parse as parse_date
from py_utils.datetime import (
    DATETIME_HUMAN_FORMAT,
    datetime_human,
    duration_human,
    get_date_from_filepath,
    parse_datetime,
    tzlocutc,
)
from py_utils.misc import demultiply_value

# --- Classes pour représenter les données structurées ---


class _BaseInfo:
    """Classe de base pour les informations de média, fournissant une introspection."""

    def get_available_properties(self) -> list[dict[str, Any]]:
        """
        Retourne une liste de dictionnaires décrivant les propriétés publiques
        de l'objet.
        Chaque dictionnaire contient:
        - 'name': Le nom de la propriété.
        - 'type': Le type de la propriété (ex: int, str, float, Optional[str]).
        - 'calculated': True si c'est une propriété calculée (@property), False si un attribut direct.
        - 'description': Docstring de la propriété si disponible.
        """
        properties = []
        # Obtenir toutes les méthodes et attributs de la classe
        for name in dir(self.__class__):
            if not name.startswith("_"):  # Ignorer les attributs privés/protégés
                attr = getattr(self.__class__, name)
                if isinstance(attr, property):
                    # C'est une @property
                    prop_info = {
                        "name": name,
                        "calculated": True,
                        "description": (
                            attr.__doc__.strip() if attr.__doc__ else "No description available."
                        ),
                        "type": str(
                            get_type_hints(self.__class__).get(name, "Any")
                        ),  # Obtenir le type hint
                    }
                    properties.append(prop_info)
        return properties


class StreamInfo(_BaseInfo):
    """Représente les informations d'un seul stream (vidéo, audio, etc.)."""

    def __init__(self, raw_stream_data: dict[str, Any]):
        self._raw_data = raw_stream_data

    def get(self, key: str, default: Any = None) -> Any:
        return self._raw_data.get(key, default)

    def __getattr__(self, name: str) -> Any:
        """Accès dynamique aux attributs du stream."""
        if name in self._raw_data:
            return self._raw_data.get(name)

        # Si l'attribut n'existe vraiment pas, lever AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'.")

    @property
    def codec_type(self) -> str:
        """Type du codec (ex: 'video', 'audio')."""
        return self.get("codec_type", "unknown")

    @property
    def codec_name(self) -> str | None:
        """Nom du codec (ex: 'h264', 'aac')."""
        return self.get("codec_name")

    @property
    def profile(self) -> str:
        return self.get("profile", "")

    @property
    def index(self) -> int:
        """Index du stream."""
        return self.get("index", -1)

    @property
    def tags(self) -> dict[str, str]:
        """Dictionnaire des tags du stream."""
        return self.get("tags", {})

    @property
    def disposition(self) -> dict[str, int]:
        """Dictionnaire des dispositions du stream."""
        return self.get("disposition", {})

    @property
    def side_data_list(self) -> list[dict[str, Any]]:
        """Liste des données secondaires du stream."""
        return self.get("side_data_list", [])

    def get_available_properties(self) -> list[dict[str, Any]]:
        """
        Retourne une liste de dictionnaires décrivant les propriétés publiques
        de l'objet StreamInfo, incluant celles déléguées.
        """
        props = super().get_available_properties()
        # Ajouter les clés directes de _raw_data comme propriétés "non calculées"
        for key in self._raw_data:
            if key not in [p["name"] for p in props] and not key.startswith("_"):
                props.append(
                    {
                        "name": key,
                        "calculated": False,
                        "description": f"Direct value from ffprobe raw data for '{key}'.",
                        "type": str(type(self._raw_data[key])),
                    }
                )
        return props

    def properties(self):
        """
        Retourne les propriétés de StreamInfo et les clés directes de _raw_data.
        """
        props = self.get_available_properties()
        return [p["name"] for p in props]


class VideoStreamInfo(StreamInfo):
    """Informations spécifiques aux streams vidéo.

    Certains attributs sont accessibles grâce `StreamInfo.__getattr__(name)`.
    Ex: `codec_name`, `duration`, `bit_rate`, `pix_fmt`, `start_pts`, etc.
    """

    @property
    def width(self) -> int:
        """Largeur de la vidéo en pixels."""
        return self.get("width", 0)

    @property
    def height(self) -> int:
        """Hauteur de la vidéo en pixels."""
        return self.get("height", 0)

    @property
    def resolution(self) -> str:
        """Résolution de la vidéo au format 'WxH'."""
        return f"{self.width}x{self.height}"

    @property
    def frame_rate(self) -> float:
        """Fréquence d'images de la vidéo (frames par seconde)."""
        rate_str = self.get("r_frame_rate", "0/1")
        try:
            num, den = map(int, rate_str.split("/"))
            return num / den if den != 0 else 0.0
        except ValueError:
            return 0.0

    @property
    def frame_rate_str(self):
        """Fréquence d'images de la vidéo tel que représenté dans les metadata (généralement une fraction)."""
        return self.get("r_frame_rate", "0/1")

    @property
    def bit_rate(self) -> int:
        """Débit binaire de la vidéo en bits par seconde."""
        return int(self.get("bit_rate", 0))

    @property
    def bit_rate_human(self) -> str:
        return demultiply_value(self.bit_rate) + "b/s"

    @property
    def byte_rate_human(self) -> str:
        return demultiply_value(self.bit_rate / 8) + "B/s"

    @property
    def sample_aspect_ratio(self) -> str | None:
        """Ratio d'aspect des pixels (SAR)."""
        return self.get("sample_aspect_ratio", "1/1").replace(":", "/")

    @property
    def sar(self) -> str | None:
        """Ratio d'aspect des pixels (SAR)."""
        return self.sample_aspect_ratio

    @property
    def display_aspect_ratio(self) -> str | None:
        """Ratio d'aspect d'affichage (DAR)."""
        if "display_aspect_ratio" in self._raw_data:
            return self.get("display_aspect_ratio").replace(":", "/")

        if not self.width or not self.height:
            return None

        try:
            sarf = Fraction(self.sample_aspect_ratio.replace(":", "/"))
            darf = sarf * Fraction(self.width, self.height)
            return str(darf)
        except (ValueError, ZeroDivisionError):
            pass

        # NOTE : a priori on ne devrait jamais tomber sur ce code depuis les dernières modifications
        # Fallback pour les résolutions communes si SAR/DAR ne sont pas clairs
        if self.width == 720 and self.height == 576:
            return "4/3"
        if self.width == 960 and self.height == 720:
            return "16/9"
        if self.width == 1440 and self.height == 1080:
            return "16/9"

        return str(Fraction(self.width, self.height))

    @property
    def dar(self) -> str | None:
        """Ratio d'aspect d'affichage (DAR)."""
        return self.display_aspect_ratio

    @property
    def nb_frames(self) -> int:
        """Nombre total de frames dans le stream vidéo."""
        if "nb_frames" in self._raw_data:
            return int(self._raw_data["nb_frames"])

        # Fallback: calculer nb_frames à partir du framerate et de la durée
        if self.frame_rate > 0 and self.duration > 0:
            return int(self.main_video_stream.frame_rate * self.duration)
        return 0

    @property
    def bits_per_pixel(self):
        """Nombre de bits par pixel (bpp)."""
        try:
            return round(self.bit_rate / self.frame_rate / self.width / self.height, 6)
        except:
            return 0.0

    @property
    def bpp(self):
        return self.bits_per_pixel

    @property
    def rotation(self) -> int:
        """Rotation de la vidéo en degrés (0, 90, 180, 270)."""
        r = 0
        if "tags" in self._raw_data and "rotate" in self._raw_data["tags"]:
            r = int(self._raw_data["tags"]["rotate"])
        if self.side_data_list:
            for side_data in self.side_data_list:
                if "rotation" in side_data:
                    r = int(side_data["rotation"]) % 360
                    break
        return r


class AudioStreamInfo(StreamInfo):
    """Informations spécifiques aux streams audio.

    Certains attributs sont accessibles grâce `StreamInfo.__getattr__(name)`.
    Ex: `codec_name`, `duration`, `bit_rate`, `sample_rate`, `channels`, etc.
    """

    @property
    def sample_rate(self) -> int:
        """Taux d'échantillonnage audio en Hz."""
        return int(self.get("sample_rate", 0))

    @property
    def channels(self) -> int:
        """Nombre de canaux audio."""
        return int(self.get("channels", 0))

    @property
    def bit_rate(self) -> int:
        """Débit binaire audio en bits par seconde."""
        return int(self.get("bit_rate", 0))

    @property
    def bit_rate_human(self) -> str:
        return demultiply_value(self.bit_rate) + "b/s"

    @property
    def channel_layout(self) -> str:
        return self.get("channel_layout", "")


class MediaFormatInfo(_BaseInfo):
    """Représente les informations du format global du média."""

    def __init__(self, raw_format_data: dict[str, Any]):
        self._raw_data = raw_format_data

    def get(self, key: str, default: Any = None) -> Any:
        return self._raw_data.get(key, default)

    def __getattr__(self, name: str) -> Any:
        """Accès dynamique aux attributs du stream."""
        if name in self._raw_data:
            return self._raw_data.get(name)

        # Si l'attribut n'existe vraiment pas, lever AttributeError
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'.")

    @property
    def duration(self) -> float:
        """Durée totale du média en secondes."""
        return float(self.get("duration", 0.0))

    @property
    def size(self) -> int:
        """Taille totale du média en octets."""
        return int(self.get("size", 0))

    @property
    def tags(self) -> dict[str, str]:
        """Dictionnaire des tags du format global."""
        return self.get("tags", {})

    def get_available_properties(self) -> list[dict[str, Any]]:
        """
        Retourne une liste de dictionnaires décrivant les propriétés publiques
        de l'objet MediaInfo, incluant celles déléguées.
        """
        props = super().get_available_properties()
        for key in self._raw_data:
            if key not in [p["name"] for p in props] and not key.startswith("_"):
                props.append(
                    {
                        "name": key,
                        "calculated": False,
                        "description": f"Direct value from ffprobe raw format data for '{key}'.",
                        "type": str(type(self._raw_data[key])),
                    }
                )
        return props

    def properties(self):
        """
        Retourne les propriétés de MediaFormatInfo et les clés directes de _raw_data.
        """
        props = self.get_available_properties()
        return [p["name"] for p in props]


class MediaInfo(_BaseInfo):
    """
    Objet principal pour encapsuler toutes les informations détaillées
    d'un fichier vidéo/audio, obtenues via FFprobe.
    """

    def __init__(self, filepath: Path | str, raw_probe_data: dict[str, Any]):
        self.filepath = Path(filepath)
        self._raw_probe_data = raw_probe_data
        self.failed = False
        self.failure_causes: list[str] = []

        self.format: MediaFormatInfo = MediaFormatInfo(raw_probe_data.get("format", {}))
        self.streams: dict[str, list[StreamInfo]] = {
            "video": [],
            "audio": [],
            "data": [],
            "chapters": [],
            "subtitle": [],
        }
        self.main_video_stream: VideoStreamInfo | None = None
        self.main_audio_stream: AudioStreamInfo | None = None

        self._parse_streams()
        self._check_integrity()

    def _parse_streams(self):
        """Parse les données brutes des streams en objets StreamInfo typés."""
        for s_data in self._raw_probe_data.get("streams", []):
            codec_type = s_data.get("codec_type")
            if codec_type == "video":
                stream = VideoStreamInfo(s_data)
                self.streams["video"].append(stream)
                if (
                    self.main_video_stream is None
                ):  # Assigner le premier stream vidéo comme principal
                    self.main_video_stream = stream
            elif codec_type == "audio":
                stream = AudioStreamInfo(s_data)
                self.streams["audio"].append(stream)
                if (
                    self.main_audio_stream is None
                ):  # Assigner le premier stream audio comme principal
                    self.main_audio_stream = stream
            elif codec_type in self.streams:  # Pour les autres types de streams déjà connus
                self.streams[codec_type].append(StreamInfo(s_data))
            else:  # Pour les types inconnus
                print(f"Codec type inconnu: {codec_type} pour {self.filepath}")
                self.streams.setdefault("other", []).append(StreamInfo(s_data))

    def _check_integrity(self):
        """Vérifie l'intégrité des informations de la vidéo."""
        if not self.main_video_stream and not self.main_audio_stream:
            self.failure_causes.append("Aucun stream vidéo ou audio principal détecté.")
            self.failed = True
            return

        if self.main_video_stream:
            if not self.main_video_stream.width:
                self.failure_causes.append("Pas d'info de largeur vidéo.")
            if not self.main_video_stream.height:
                self.failure_causes.append("Pas d'info de hauteur vidéo.")
            if not self.main_video_stream.frame_rate:
                self.failure_causes.append("Pas d'info de frame rate vidéo.")
            if not self.main_video_stream.bit_rate:
                self.failure_causes.append("Pas d'info de bit rate vidéo.")

        if self.failure_causes:
            self.failed = True

    # --- Propriétés et méthodes de façade pour un accès facile ---

    @property
    def path(self) -> Path:
        """Chemin du fichier média."""
        return self.filepath

    @property
    def duration(self) -> float:
        """Durée totale du média en secondes, déléguée à format.duration."""
        return self.format.duration

    def duration_human(self, short=True) -> str:
        """Durée du média formatée en chaîne lisible par l'homme."""
        return duration_human(self.duration, short)

    @property
    def size(self) -> int:
        """Taille du média en octets, déléguée à format.size avec fallback sur la taille du fichier."""
        if self.format.size > 0:
            return self.format.size
        return self.filepath.stat().st_size

    def size_human(self, unit="B") -> str:
        """Taille du média formatée en chaîne lisible par l'homme (KB, MB, GB)."""
        return demultiply_value(self.size) + unit

    @property
    def creation_time(self) -> datetime:
        """Date et heure de création du média, extraite des tags ou du chemin du fichier."""
        dates = []
        # Chercher dans les tags du format
        for key, value in self.format.tags.items():
            if re.search(r"(time|date)$", key, re.IGNORECASE):
                try:
                    parsed_date = tzlocutc(parse_datetime(value))
                    dates.append(parsed_date)
                except Exception:
                    pass  # Ignorer les dates mal formatées

        # Ajouter la date du chemin de fichier comme fallback ou potentiellement plus précise
        dates.append(get_date_from_filepath(self.filepath))

        # Trier et prendre la plus ancienne ou la plus pertinente selon la logique désirée
        # Pour une date de création, la plus ancienne est souvent la plus pertinente.
        dates.sort()
        return dates[0] if dates else datetime.now().astimezone()  # Fallback ultime

    def creation_time_human(self, fmt: str = DATETIME_HUMAN_FORMAT) -> str:
        """Date de création formatée en chaîne lisible par l'homme."""
        return datetime_human(self.creation_time, fmt)

    @property
    def has_video_stream(self) -> bool:
        return self.main_video_stream is not None

    @property
    def has_audio_stream(self) -> bool:
        return self.main_audio_stream is not None

    @property
    def summary(self):
        return f"Résumé : {self.resolution}, {self.duration_human()}, {self.size_human()}"

    @property
    def summary_str(self):
        s = f"Durée : {self.duration_human()} - Taille : {self.size_human('o')}\n"

        # Construction de la ligne d'infos vidéo (si une piste existe)
        if self.has_video_stream:
            s += "video : "
            s += f"{self.main_video_stream.codec_name} "
            s += f"({self.main_video_stream.profile}) " if self.main_video_stream.profile else ""
            s += f"{self.resolution} [SAR {self.sar} DAR {self.dar}] "
            s += f"{self.main_video_stream.byte_rate_human} {self.frame_rate}fps [BPP {self.bpp}]\n"

        # Construction et emission de la ligne d'infos audio (si une piste existe)
        if self.has_audio_stream:
            s += f"audio : "
            s += f"{self.main_audio_stream.codec_name} "
            s += f"({self.main_audio_stream.profile}) " if self.main_audio_stream.profile else ""
            s += f"{self.channels}ch "
            s += f"({self.channel_layout}) " if self.channel_layout else ""
            s += f"{self.main_audio_stream.sample_rate}Hz {self.main_audio_stream.bit_rate_human}\n"

        return s.strip()

    def __getattr__(self, name: str) -> Any:
        """
        Délègue l'accès aux attributs non trouvés à l'objet main_video_stream
        ou main_audio_stream si l'attribut est présent.
        """
        if hasattr(self.format, name):
            return getattr(self.format, name)
        if self.main_video_stream and hasattr(self.main_video_stream, name):
            return getattr(self.main_video_stream, name)
        if self.main_audio_stream and hasattr(self.main_audio_stream, name):
            return getattr(self.main_audio_stream, name)

        # Si l'attribut n'existe vraiment pas, lever AttributeError
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}' "
            f"and it's not found in main video/audio streams or format."
        )

    def get_available_properties(self) -> list[dict[str, Any]]:
        """
        Retourne une liste de dictionnaires décrivant les propriétés publiques
        de l'objet MediaInfo, incluant celles déléguées.
        """
        props = super().get_available_properties()

        # Ajouter les propriétés des streams principaux (avec un préfixe)
        if self.main_video_stream:
            for p in self.main_video_stream.get_available_properties():
                props.append(
                    {
                        "name": f"video_stream.{p['name']}",
                        "type": p["type"],
                        "calculated": p["calculated"],
                        "description": f"Video stream property: {p['description']}",
                    }
                )
        if self.main_audio_stream:
            for p in self.main_audio_stream.get_available_properties():
                props.append(
                    {
                        "name": f"audio_stream.{p['name']}",
                        "type": p["type"],
                        "calculated": p["calculated"],
                        "description": f"Audio stream property: {p['description']}",
                    }
                )
        # Ajouter les propriétés du format (avec un préfixe)
        for p in self.format.get_available_properties():
            props.append(
                {
                    "name": f"format.{p['name']}",
                    "type": p["type"],
                    "calculated": p["calculated"],
                    "description": f"Format property: {p['description']}",
                }
            )

        return props

    def properties(self):
        """
        Retourne les propriétés de MediaInfo, incluant celles déléguées.
        """
        props = self.get_available_properties()
        return [p["name"] for p in props]

    def to_dict(self, include_raw: bool = False) -> dict[str, Any]:
        """Convertit l'objet MediaInfo en dictionnaire pour affichage ou sérialisation."""
        data = {
            "path": str(self.filepath),
            "duration": self.duration,
            "duration_human": self.duration_human(),
            "size": self.size,
            "size_human": self.size_human(),
            "creation_time": self.creation_time.isoformat(),
            "creation_time_human": self.creation_time_human(),
            "failed": self.failed,
            "failure_causes": self.failure_causes,
            "has_video_stream": self.has_video_stream,
            "has_audio_stream": self.has_audio_stream,
        }

        if self.main_video_stream:
            data["video_stream"] = {
                "codec": self.main_video_stream.codec_name,
                "resolution": self.main_video_stream.resolution,
                "width": self.main_video_stream.width,
                "height": self.main_video_stream.height,
                "frame_rate": self.main_video_stream.frame_rate_str,
                "bit_rate": demultiply_value(self.main_video_stream.bit_rate) + "b/s",
                "rotation": self.main_video_stream.rotation,
                "sample_aspect_ratio": self.main_video_stream.sample_aspect_ratio,
                "display_aspect_ratio": self.main_video_stream.display_aspect_ratio,
                "nb_frames": self.main_video_stream.nb_frames,
                "bits_per_pixel": self.main_video_stream.bits_per_pixel,
            }
        if self.main_audio_stream:
            data["audio_stream"] = {
                "codec": self.main_audio_stream.codec_name,
                "channels": self.main_audio_stream.channels,
                "sample_rate": demultiply_value(self.main_audio_stream.sample_rate) + "Hz",
                "bit_rate": demultiply_value(self.main_audio_stream.bit_rate) + "b/s",
            }

        if include_raw:
            data["raw_format"] = self.format._raw_data
            data["raw_streams"] = [
                s._raw_data
                for s in self.streams["video"]
                + self.streams["audio"]
                + self.streams["data"]
                + self.streams["chapters"]
                + self.streams["subtitle"]
            ]
        return data
