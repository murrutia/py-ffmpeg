#!/usr/bin/env python3

import argparse
import signal
import sys
from pathlib import Path

from py_utils.datetime import duration_human
from py_utils.dl_binaries import download_binaries, get_architecture, get_system
from py_utils.misc import add_dir_to_path
from tqdm import tqdm

from py_ffmpeg.config import EncodingConfig
from py_ffmpeg.encoder import EncodingState, VideoEncoder
from py_ffmpeg.media_info import MediaInfo  # Utilisé pour l'annotation de type

# Instances globales pour y accéder depuis les callbacks et le gestionnaire de signal
pbar: tqdm | None = None
encoder_instance: VideoEncoder | None = None


def on_progress_update(percent_complete: float, time_remaining_seconds: int):
    """Callback pour mettre à jour la barre de progression."""
    global pbar
    if pbar:
        pbar.n = int(percent_complete)  # Met à jour la progression actuelle
        if time_remaining_seconds > 0:
            pbar.set_postfix_str(
                f"{duration_human(time_remaining_seconds, short=True)}", refresh=True
            )
        else:
            pbar.set_postfix_str("calcul...", refresh=True)


def on_state_changed(new_state: EncodingState):
    """Callback pour les changements d'état de l'encodeur."""
    global pbar
    status_text = str(new_state)  # Utilise la méthode __str__ de EncodingState
    if pbar:
        pbar.set_description_str(status_text, refresh=True)
    else:
        # Au cas où l'état changerait avant l'initialisation de pbar ou après sa fermeture
        print(f"État: {status_text}")


def on_encoding_finished(success: bool, message: str, output_media_info: MediaInfo | None):
    """Callback pour la fin de l'encodage."""
    global pbar
    if pbar:
        # Assure que la barre de progression atteint 100% en cas de succès
        if success and pbar.n < 100:
            pbar.n = 100
            pbar.refresh()
        pbar.close()
        print("\n" + "=" * 30)  # Séparateur après la barre de progression

    if success:
        print(f"✅ Succès : {message}")
        if output_media_info:
            print(f"Fichier de sortie : {output_media_info.filepath}")
    else:
        print(f"❌ Échec/Annulation : {message}")


def sigint_handler(sig, frame):
    """Gestionnaire pour le signal SIGINT (Ctrl+C)."""
    global encoder_instance, pbar
    print("\nInterruption détectée (Ctrl+C). Tentative d'annulation...")
    if pbar and not pbar.disable:  # pbar.disable est True si pbar est fermé
        pbar.set_description_str("Annulation en cours...", refresh=True)
    if encoder_instance:
        encoder_instance.cancel()
    # Le callback on_encoding_finished sera appelé par VideoEncoder pour finaliser.


def main(input_path: Path):
    global pbar, encoder_instance

    if not input_path.is_file():
        print(f"Erreur : Fichier d'entrée non trouvé : {input_path}", file=sys.stderr)
        sys.exit(1)

    config = EncodingConfig()
    output_path = Path(config.suggest_output_filepath(str(input_path)))

    print(f"Vidéo d'entrée : {input_path.resolve()}")
    print(f"Vidéo de sortie : {output_path.resolve()}")

    encoder_instance = VideoEncoder(
        input_path=str(input_path),
        output_path=str(output_path),
        # Les paramètres d'encodage par défaut de VideoEncoder seront utilisés
    )

    encoder_instance.on_progress_callback = on_progress_update
    encoder_instance.on_state_changed_callback = on_state_changed
    encoder_instance.on_finished_callback = on_encoding_finished
    # Optionnel: encoder_instance.on_log_callback = lambda msg: print(f"LOG: {msg}")

    signal.signal(signal.SIGINT, sigint_handler)

    print("Démarrage de l'encodage... (Ctrl+C pour annuler)")
    try:
        with tqdm(
            total=100,
            unit="%",
            desc="Initialisation",
            bar_format="{desc} |{bar}| {percentage:3.0f}% | {elapsed} | ETA: {postfix}",
        ) as local_pbar:
            pbar = local_pbar  # Assigner à la variable globale
            encoder_instance.start()  # Appel bloquant
    except Exception as e:  # Gère les erreurs inattendues non interceptées par VideoEncoder
        if pbar and not pbar.disable:
            pbar.close()
        print(f"\nUne erreur inattendue est survenue hors de l'encodeur : {e}", file=sys.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Encodeur vidéo CLI minimaliste avec py-ffmpeg.")
    parser.add_argument("input_file", type=str, help="Chemin vers le fichier vidéo d'entrée.")
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

    input_path = Path(args.input_file)

    main(input_path)
