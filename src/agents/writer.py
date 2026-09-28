"""Turns the Researcher's plain facts into customer-facing copy. Never
touches the vectorstore directly - a wrong fact is the Researcher's bug
to fix, not something the Writer should silently paper over."""
from openai import OpenAI
from src.core.config import DEFAULT_MODEL
from src.agents.state import ContentState

_client = OpenAI()


def writer_node(state: ContentState) -> ContentState:
    prompt = f"""Write a short, engaging buying-guide paragraph for TrailPeak Outdoors
customers about: {state['topic']}

Use ONLY the facts below - don't invent specs or claims not present here. If the facts
mention a real limitation, be upfront about it rather than glossing over it.

Facts:
{state['research_notes']}"""

    response = _client.chat.completions.create(
        model=DEFAULT_MODEL, messages=[{"role": "user", "content": prompt}]
    )
    return {**state, "draft": response.choices[0].message.content}