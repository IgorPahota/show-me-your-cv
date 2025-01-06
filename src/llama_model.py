from llama_cpp import Llama
import os


class LLAMAModel:
    def __init__(self):
        """
        Initialize LLAMA model using llama-cpp-python with Metal support
        """
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(current_dir, "models", "llama-2-7b.gguf")

        print(f"Loading model from: {model_path}")
        try:
            self.model = Llama(
                model_path=model_path,
                n_ctx=2048,  # Context window
                n_threads=6,  # Adjust based on your CPU
                n_gpu_layers=1,  # Use -1 for all layers on GPU
            )
            print("LLAMA model loaded successfully!")
        except Exception as e:
            print(f"Error loading model: {e}")
            raise

    def generate_text(self, prompt, max_length=200):
        """
        Generate text response for a given prompt
        """
        try:
            output = self.model(
                prompt,
                max_tokens=max_length,
                temperature=0.7,
                stop=["</s>"],
                echo=False,
            )
            return output["choices"][0]["text"]
        except Exception as e:
            print(f"Error generating text: {e}")
            return f"Error: {str(e)}"
