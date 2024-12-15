import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

class LLAMAModel:
    def __init__(self, model_name="gpt2"):  # Using GPT-2 as it's more reliable to load
        """
        Initialize model with GPT-2 (smaller and more reliable)
        """
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name,
                torch_dtype=torch.float32,  # Using float32 for better compatibility
                device_map="auto" if torch.cuda.is_available() else "cpu"
            )
        except Exception as e:
            print(f"Error loading model: {e}")
            raise

    def generate_text(self, prompt, max_length=200):
        """
        Generate text response for a given prompt
        """
        try:
            input_ids = self.tokenizer.encode(prompt, return_tensors="pt").to(self.model.device)
            output = self.model.generate(
                input_ids,
                max_length=max_length,
                num_return_sequences=1,
                no_repeat_ngram_size=2,
                pad_token_id=self.tokenizer.eos_token_id
            )
            return self.tokenizer.decode(output[0], skip_special_tokens=True)
        except Exception as e:
            print(f"Error generating text: {e}")
            return f"Error: {str(e)}"