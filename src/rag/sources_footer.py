# src/rag/sources_footer.py
# The streamed answer ends with a line the user should never see:
#
#     SOURCES: returns_policy.txt, shipping_policy.txt
#
# SourcesFooter removes that line from the stream while the answer is still arriving, and
# resolve_sources() turns what the model wrote into the list the UI shows as chips.
import re

MARKER = "SOURCES:"

# The footer starts on a new line: one or more line breaks (spaces allowed), then SOURCES:
_FOOTER_START = re.compile(r"(?:\n[ \t]*)+" + re.escape(MARKER))

# The end of the text so far might be the beginning of that, e.g. "...done.\n\nSOUR".
# Anything matching this is held back until the next piece shows what it really is.
_PARTIAL_START = re.compile(
    r"(?:\n[ \t]*)+(?:" + "|".join(re.escape(MARKER[:n]) for n in range(len(MARKER) - 1, 0, -1)) + r")?$"
)


class SourcesFooter:
    """Feed it the streamed pieces of ONE model reply. It hands back the text that is safe
    to show, and keeps the footer for later.

        footer = SourcesFooter()
        for piece in pieces:
            shown = footer.feed(piece)        # show this (may be "" while it waits)
        rest, footer_text = footer.finish()   # show `rest`; footer_text is None if there was no footer

    Why the waiting? A token like "SOUR" could be the start of the footer or just a word in
    the answer. So the end of the text is held back until it is clear."""

    def __init__(self):
        self._pending = ""    # received, not shown yet (might be the start of the footer)
        self._footer = None   # None until SOURCES: is seen, then everything written after it

    def feed(self, piece):
        if self._footer is not None:      # already inside the footer: collect it, show nothing
            self._footer += piece
            return ""

        self._pending += piece
        start = _FOOTER_START.search(self._pending)
        if start:
            shown = self._pending[:start.start()]
            self._footer = self._pending[start.end():]
            self._pending = ""
            return shown

        held = _PARTIAL_START.search(self._pending)
        cut = held.start() if held else len(self._pending)
        shown, self._pending = self._pending[:cut], self._pending[cut:]
        return shown

    def finish(self):
        """Call once the reply is over. Returns (text still to show, footer text or None)."""
        if self._footer is None:
            return self._pending, None   # no footer was written: whatever was held back is just text
        return "", self._footer


def resolve_sources(footer_text, retrieved):
    """The list of source files to show, given the footer the model wrote (or None) and the
    files that were actually retrieved for this question.

      no footer, or one naming nothing we retrieved  ->  all retrieved files (never show less
                                                         than we know could have been used)
      "SOURCES: none"                                ->  [] (the model used no document)
      names we retrieved                             ->  just those, in retrieval order

    Only files that were really retrieved can appear, so an invented name never reaches the UI."""
    if footer_text is None:
        return list(retrieved)
    named = [name for name in retrieved if name in footer_text]
    if named:
        return named
    if footer_text.strip().lower().startswith("none"):
        return []
    return list(retrieved)
