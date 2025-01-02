import google.generativeai as genai
from src.api_keys import GEMINI_API_KEY


class GeminiModel:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def generate_text(self, prompt: str, max_length: int = 200) -> str:
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Error generating text with Gemini: {str(e)}")
