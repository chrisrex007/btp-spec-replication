"""Representation and validation of generated candidate source code."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


SUPPORTED_LANGUAGES = {
    "python": ".py",
    "cpp": ".cpp",
}

DEFAULT_FILENAMES = {
    "python": "main.py",
    "cpp": "main.cpp",
}


@dataclass(frozen=True)
class CandidateSource:
    language: str
    source: str
    filename: str | None = None

    def __post_init__(self) -> None:
        language = self.language.strip().lower()
        if language not in SUPPORTED_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
            raise ValueError(
                f"unsupported language {self.language!r}; expected one of: {supported}"
            )
        object.__setattr__(self, "language", language)

        filename = self.filename or DEFAULT_FILENAMES[language]
        if not filename or Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError("filename must be a plain file name, not a path")
        if not filename.endswith(SUPPORTED_LANGUAGES[language]):
            raise ValueError(
                f"{language} candidate filename must end with "
                f"{SUPPORTED_LANGUAGES[language]}"
            )
        if "\x00" in filename:
            raise ValueError("filename must not contain NUL")
        filename.encode("utf-8")
        object.__setattr__(self, "filename", filename)

        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("candidate source must be a non-empty string")
        self.source.encode("utf-8")

    @classmethod
    def from_dict(cls, data: dict) -> "CandidateSource":
        return cls(
            language=data["language"],
            filename=data.get("filename"),
            source=data["source"],
        )

    def to_dict(self) -> dict:
        return asdict(self)
