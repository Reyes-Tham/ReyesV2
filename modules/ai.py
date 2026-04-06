import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

client = anthropic.Anthropic(
    api_key=ANTHROPIC_API_KEY,
    default_headers={"anthropic-beta": "web-search-2025-03-05"}
)

def chat(user_message: str, history: list = None) -> str:
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=messages,
    )

    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(text_parts)


def quick_insight(prompt: str, max_tokens: int = 200) -> str:
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    return "\n".join(text_parts)
