# src/rag/events.py
# What the UI's "trail" says. Each builder returns one (event_name, data) pair for answer_stream().


# tool name -> (label while running, label when finished), for the trail the UI shows
TOOL_LABELS = {
    "CheckAvailability": ("Checking live stock", "Checked live stock"),
    "CalculateTotal": ("Adding the prices", "Added the prices"),
}


def search_step(label, detail="", status="done"):
    return "step", {"id": "search", "label": label, "detail": detail, "status": status}


def tool_step(request, args, status, result=""):
    running, finished = TOOL_LABELS.get(request.name, (request.name, request.name))
    if request.name == "CheckAvailability":
        detail = args.get("sku", "")
    else:
        detail = result if status == "done" else ""
    return "step", {"id": request.id, "label": running if status == "running" else finished,
                    "detail": detail, "status": status}
