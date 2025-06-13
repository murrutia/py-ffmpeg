import json
import subprocess
from pathlib import Path

from .media_info import MediaInfo


class FFprobe:
    """
    Service pour interagir avec l'exécutable ffprobe et analyser les fichiers médias.
    """

    def __init__(self, executable: str = "ffprobe"):
        self.executable = executable

    def probe(self, filepath: str | Path) -> MediaInfo:
        """
        Exécute ffprobe sur le chemin donné et retourne un objet MediaInfo structuré.
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Le fichier n'existe pas : {filepath}")

        command = [
            self.executable,
            "-v",
            "error",  # Moins verbeux que 'quiet' pour les erreurs, mais supprime les infos de base
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(filepath.absolute()),
        ]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,  # Lève CalledProcessError si le code de retour est non nul
                encoding="utf-8",  # Assure un décodage correct
            )
            raw_probe_data = json.loads(process.stdout)
            return MediaInfo(filepath, raw_probe_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Erreur de décodage JSON de la sortie ffprobe : {e}") from e
        except subprocess.CalledProcessError as e:
            # Gérer spécifiquement les erreurs de ffprobe
            error_msg = f"Erreur lors de l'exécution de ffprobe pour {filepath}:\n{e.stderr}"
            raise RuntimeError(error_msg) from e
        except Exception as e:
            raise RuntimeError(f"Erreur inattendue lors du probing de {filepath}: {e}") from e
