def _collapse_repeated_suffix(words: list[str]) -> list[str]:
    """
    Collapse exact repeated suffix patterns like ["bro", "bro"] -> ["bro"].

    This is intentionally conservative: it only collapses a name when the
    whole list is an exact repetition of a smaller sequence.
    """
    if len(words) < 2:
        return words

    total = len(words)
    for unit_size in range(1, (total // 2) + 1):
        if total % unit_size != 0:
            continue
        unit = words[:unit_size]
        if unit * (total // unit_size) == words:
            return unit
    return words


def normalize_name_parts(first_name: str, last_name: str) -> tuple[str, str]:
    """
    Normalize duplicated cross-field name data.

    Examples:
    - first_name="rocky bro", last_name="bro" -> ("rocky", "bro")
    - first_name="rocky", last_name="bro bro" -> ("rocky", "bro")
    """
    first_words = (first_name or '').strip().split()
    last_words = _collapse_repeated_suffix((last_name or '').strip().split())

    if last_words and len(first_words) > len(last_words):
        if first_words[-len(last_words):] == last_words:
            first_words = first_words[:-len(last_words)]

    clean_first = ' '.join(first_words).strip()
    clean_last = ' '.join(last_words).strip()

    return clean_first[:30], clean_last[:30]


def split_display_name(display_name: str) -> tuple[str, str]:
    """
    Split a Firebase display name into first_name / last_name and normalize it.
    """
    clean = (display_name or '').strip()
    if not clean:
        return '', ''

    parts = clean.split()
    first_name = parts[0]
    last_name = ' '.join(parts[1:]) if len(parts) > 1 else ''
    return normalize_name_parts(first_name, last_name)
