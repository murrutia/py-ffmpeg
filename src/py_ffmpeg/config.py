from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EncodingConfig:
    """Configuration for video encoding operations"""

    # Default encoding parameters
    default_video_codec: str = "libx264"
    default_audio_codec: str = "aac"
    default_container: str = "mp4"
    default_crf: int = 23
    default_preset: str = "medium"

    # Input/Output settings
    supported_input_formats: list[str] = field(
        default_factory=lambda: ["*.mp4", "*.avi", "*.mkv", "*.mov", "*.wmv", "*.flv"]
    )
    supported_output_formats: list[str] = field(default_factory=lambda: ["*.mp4", "*.mkv"])

    # Processing settings
    max_concurrent_encodings: int = 1
    progress_update_interval: float = 1.0  # seconds
    timeout_seconds: int | None = None

    # UI settings
    output_suffix: str = ".reenc"
    log_max_lines: int = 1000

    def get_default_encoding_params(self) -> dict[str, Any]:
        """Get default FFmpeg encoding parameters"""
        return {
            "c:v": self.default_video_codec,
            "c:a": self.default_audio_codec,
            "crf": str(self.default_crf),
            "preset": self.default_preset,
        }

    def get_file_filters(self) -> str:
        """Get file dialog filters string"""
        input_formats = " ".join(self.supported_input_formats)
        return f"Fichiers vidéo ({input_formats});;Tous les fichiers (*)"

    def suggest_output_filepath(self, input_filepath: str | Path | None) -> str:
        """Suggest an output filename based on the input filename"""
        if not input_filepath:
            return f"output{self.output_suffix}.{self.default_container}"
        file_path = Path(input_filepath)
        return str(
            file_path.parent / f"{file_path.stem}{self.output_suffix}.{self.default_container}"
        )
