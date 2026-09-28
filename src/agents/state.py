from typing import TypedDict, List


class ContentState(TypedDict):
    topic: str
    research_notes: str
    sources: List[str]
    draft: str