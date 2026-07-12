"""Small shared helpers used across handlers."""
from bot.texts import STATUS_LABELS


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status.replace("_", " ").title())


def format_timestamp(iso_string: str | None) -> str:
    if not iso_string:
        return "—"
    # Supabase returns ISO 8601; keep it human-readable without pulling in
    # extra timezone-conversion dependencies.
    return iso_string.split("T")[0]


def is_valid_amount(text: str) -> bool:
    """Loose validation — accepts things like '$1,250.00' or '1250'."""
    cleaned = text.replace("$", "").replace(",", "").strip()
    try:
        float(cleaned)
        return True
    except ValueError:
        return False
