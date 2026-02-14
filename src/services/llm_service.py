from ollama import list as list_models
from ollama import AsyncClient
import os
from dataclasses import dataclass, field


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

    async def stream(self, prompt: str):
        full_prompt = f"Context: {
            self.extra_context}\n\nUser Question: {prompt}"
        self.conversation_history.append(
            {"role": "user", "content": full_prompt})
        async for part in await AsyncClient().chat(
            model=self.model,
            messages=self.conversation_history,
            stream=True,
        ):
            yield part['message']['content']
