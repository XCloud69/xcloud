from ollama import list as list_models
from ollama import AsyncClient
import os

current_model = "qwen2.5:7b-instruct-q4_K_M"


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


extra_context = ""


async def ollama_streamer(prompt: str):
    full_prompt = f"Context: {extra_context}\n\nUser Question: {prompt}"
    async for part in await AsyncClient().chat(
        model=current_model,
        messages=[{'role': 'user', 'content': full_prompt}],
        stream=True,
    ):
        yield part['message']['content']
