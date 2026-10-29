# src/api/streaming.py
# Turns the pipeline's (event_name, data) pairs into Server-Sent Events text for the browser.
# The pipeline decides WHAT happens; this file only decides how it looks on the wire.
import json
import logging

logger = logging.getLogger(__name__)


def sse(event, data):
    """One Server-Sent Event. The payload is JSON, so a newline inside a token
    can never break the event framing."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def sse_stream(events):
    """Wrap the pipeline's events as SSE text. If the pipeline fails half way, the
    browser gets one clean `error` event (details go to the log, never to the user)."""
    try:
        for name, data in events:
            yield sse(name, data)
    except Exception:
        logger.exception("answer stream failed")
        yield sse("error", {"message": "Something went wrong while answering. Please try again."})
