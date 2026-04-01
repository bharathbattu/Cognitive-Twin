from hashlib import sha1
from pathlib import Path


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_slug(value: str) -> str:
    raw = value.strip()
    if not raw:
        return "default"

    sanitized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in raw)
    if sanitized == raw:
        return sanitized

    base = sanitized.strip("-") or "session"
    digest = sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"
