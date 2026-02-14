from ollama import list as list_models
from ollama import AsyncClient
import os
from dataclasses import dataclass, field

SYSTEM_PROMPT = (
    "You are a helpful local assistant. "
    "Use the following context to answer questions accurately. "
    "If the context doesn't contain relevant information, say so. "
    "If you don't know the answer, say so."
)


def read_context_from_folder(folder_path: str):
    combined_text = ""
    for filename in os.listdir(folder_path):
        if filename.endswith(".md"):
            with open(os.path.join(folder_path, filename), 'r') as f:
                combined_text += f.read() + "\n"
    return combined_text


def get_available_models():
    try:
        response = list_models()
        return [m.model for m in response.models]
    except Exception as e:
        return {"error": str(e)}


@dataclass
class LLMSession:
    model: str = "qwen2.5:7b-instruct-q4_K_M"
    extra_context: str = ""
    conversation_history: list = field(default_factory=list)

    def clear_history(self):
        """Reset conversation history."""
        self.conversation_history = []

    async def stream(self, prompt: str):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]
        if self.extra_context:
            messages.append(
                {"role": "system",
                 "content": f"Context:\n{self.extra_context}"}
            )
        messages.extend(self.conversation_history)
        messages.append({"role": "user", "content": prompt})
        assistant_reply = ""
        async for part in await AsyncClient().chat(
            model=self.model,
            messages=messages,
            stream=True,
        ):
            chunk = part['message']['content']
            assistant_reply += chunk
            yield chunk
        self.conversation_history.append({"role": "user", "content": prompt})
        self.conversation_history.append(
            {"role": "assistant", "content": assistant_reply})


session = LLMSession()
