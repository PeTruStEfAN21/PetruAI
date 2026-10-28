"""Full-page HTML rendering for CLI output."""
from mdconv.inline import escape


def render_page(body: str, title: str) -> str:
    """Return a full HTML5 page with the given body and title.

    The title is HTML-escaped. The body is inserted as-is.
    Returns the full page string ending with a newline.
    """
    escaped_title = escape(title)
    return (
        f"<!DOCTYPE html>\n"
        f"<html>\n"
        f"<head>\n"
        f'<meta charset="utf-8">\n'
        f"<title>{escaped_title}</title>\n"
        f"</head>\n"
        f"<body>\n"
        f"{body}\n"
        f"</body>\n"
        f"</html>\n"
    )
