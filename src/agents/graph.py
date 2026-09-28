from langgraph.graph import StateGraph, END
from src.agents.state import ContentState
from src.agents.researcher import researcher_node
from src.agents.writer import writer_node


def build_graph():
    graph = StateGraph(ContentState)
    graph.add_node("researcher", researcher_node)
    graph.add_node("writer", writer_node)
    graph.set_entry_point("researcher")
    graph.add_edge("researcher", "writer")
    graph.add_edge("writer", END)
    return graph.compile()


def run_content_pipeline(topic: str) -> ContentState:
    app = build_graph()
    return app.invoke({"topic": topic, "research_notes": "", "sources": [], "draft": ""})


if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "winter camping tents"
    result = run_content_pipeline(topic)
    print("RESEARCH NOTES:\n", result["research_notes"])
    print("\nSOURCES:", result["sources"])
    print("\nDRAFT:\n", result["draft"])