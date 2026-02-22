from ollama import list as list_models
from ollama import AsyncClient
import os
import json
from dataclasses import dataclass, field

# ---- Settings persistence ------------------------------------------------- #

SETTINGS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "settings.json")
)


def _load_settings() -> dict:
    """Load settings.json, creating it with defaults if missing."""
    defaults = {"default_model": "auto"}
    if not os.path.exists(SETTINGS_PATH):
        _save_settings(defaults)
        return defaults
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        _save_settings(defaults)
        return defaults


def _save_settings(settings: dict) -> None:
    """Write settings dict to settings.json."""
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


def get_settings() -> dict:
    """Return the full settings dict."""
    return _load_settings()


def get_default_model() -> str | None:
    """
    Resolve the default model.
    - If settings has a specific model name, return it.
    - If "auto", detect the first model installed in Ollama.
    - Returns None if no models are available.
    """
    settings = _load_settings()
    model_pref = settings.get("default_model", "auto")

    if model_pref and model_pref != "auto":
        return model_pref

    # Auto-detect: pick the first available Ollama model
    models = get_available_models()
    if isinstance(models, list) and models:
        return models[0]
    return None


def save_default_model(model_name: str) -> dict:
    """
    Persist the chosen model to settings.json.
    Pass "auto" to reset to auto-detection.
    """
    settings = _load_settings()
    settings["default_model"] = model_name
    _save_settings(settings)
    return settings


SYSTEM_PROMPT = """You are Xcloud, an intelligent AI assistant created by Rashad.
You are knowledgeable, precise, and helpful. You communicate clearly and concisely.

Core traits:
- You think step-by-step when solving complex problems.
- You are honest about what you know and don't know.
- When given context from documents or web search, you use it accurately and cite sources.
- You are conversational but professional.
- You can help with coding, analysis, writing, math, and general knowledge.

When provided with context from various sources (documents, web search results, etc.),
use the provided context to answer the user's question accurately.
If the context contains web search results, cite the sources.
If you don't know the answer even with the provided context, say so honestly.
"""

SUGGESTED_PROMPTS = [
    {
        "title": "Explain a concept",
        "prompt": "Explain how {topic} works in simple terms",
        "category": "learning",
    },
    {
        "title": "Write code",
        "prompt": "Write a {language} function that {description}",
        "category": "coding",
    },
    {
        "title": "Debug help",
        "prompt": "Help me debug this error: {error_message}",
        "category": "coding",
    },
    {
        "title": "Summarize text",
        "prompt": "Summarize the following text in bullet points: {text}",
        "category": "writing",
    },
    {
        "title": "Compare options",
        "prompt": "Compare the pros and cons of {option_a} vs {option_b}",
        "category": "analysis",
    },
    {
        "title": "Brainstorm ideas",
        "prompt": "Give me 5 creative ideas for {topic}",
        "category": "creative",
    },
    {
        "title": "Translate text",
        "prompt": "Translate the following to {language}: {text}",
        "category": "language",
    },
    {
        "title": "Review code",
        "prompt": "Review this code for bugs and improvements:\n```\n{code}\n```",
        "category": "coding",
    },
]


def read_context_from_folder(folder_path: str):
    combined_text = ""
    for filename in os.listdir(folder_path):
        if filename.endswith(".md"):
            with open(os.path.join(folder_path, filename), "r") as f:
                combined_text += f.read() + "\n"
    return combined_text


def get_available_models():
    try:
        response = list_models()
        return [m.model for m in response.models]
    except Exception as e:
        return {"error": str(e)}


def get_suggested_prompts(category: str = None) -> list:
    """Return suggested prompts, optionally filtered by category."""
    if category:
        return [p for p in SUGGESTED_PROMPTS if p["category"] == category]
    return SUGGESTED_PROMPTS


@dataclass
class LLMSession:
    model: str = ""
    extra_context: str = ""
    conversation_history: list = field(default_factory=list)

    def __post_init__(self):
        if not self.model:
            self.model = get_default_model() or ""

    def clear_history(self):
        """Reset conversation history."""
        self.conversation_history = []

    async def stream(self, prompt: str, think: bool = False):
        """
        Stream a response from the LLM.

        Args:
            prompt: The user's message.
            think: If True, request extended thinking from the model.

        Yields:
            JSON-encoded chunks with type "thinking" or "content".
        """
        import json

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        if self.extra_context:
            messages.append(
                {"role": "system", "content": f"Context:\n{self.extra_context}"}
            )
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": prompt})

        assistant_reply = ""
        thinking_content = ""

        if think:
            # Use thinking mode - request extended thinking via Ollama
            async for part in await AsyncClient().chat(
                model=self.model,
                messages=messages,
                stream=True,
                think=True,
            ):
                msg = part.get("message", {})

                # Handle thinking content
                if msg.get("thinking"):
                    thinking_chunk = msg["thinking"]
                    thinking_content += thinking_chunk
                    yield (
                        json.dumps(
                            {"type": "thinking", "content": thinking_chunk})
                        + "\n"
                    )

                # Handle regular content
                if msg.get("content"):
                    chunk = msg["content"]
                    assistant_reply += chunk
                    yield json.dumps({"type": "content", "content": chunk}) + "\n"
        else:
            # Standard streaming (no thinking)
            async for part in await AsyncClient().chat(
                model=self.model,
                messages=messages,
                stream=True,
            ):
                chunk = part["message"]["content"]
                assistant_reply += chunk
                yield json.dumps({"type": "content", "content": chunk}) + "\n"

        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append(
            {"role": "assistant", "content": assistant_reply}
        )

        # Yield done signal with thinking content if any
        yield (
            json.dumps(
                {
                    "type": "done",
                    "thinking": thinking_content if thinking_content else None,
                }
            )
            + "\n"
        )


# Global session for backwards compat (used by non-authed endpoints)
session = LLMSession(model=get_default_model() or "")
