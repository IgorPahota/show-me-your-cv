import torch
from transformers import AutoTokenizer
from transformers.models.paligemma import PaliGemmaForConditionalGeneration
import os

class PaLiGemmaModel:
    def __init__(self):
        """
        Initialize PaLiGemma model using local files
        """
        current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_path = os.path.join(current_dir, "models", "paligemma-2-transformers-paligemma2-3b-pt-224-v1")
        
        print(f"Loading model from: {model_path}")
        self.device = torch.device('mps' if torch.backends.mps.is_available() else 'cpu')
        print(f"Using device: {self.device}")
        
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                local_files_only=True,
                trust_remote_code=True,
                model_max_length=512
            )
            
            self.model = PaliGemmaForConditionalGeneration.from_pretrained(
                model_path,
                torch_dtype=torch.bfloat16,
                local_files_only=True
            ).to(self.device)
            
            print("PaLiGemma model loaded successfully!")
            
        except Exception as e:
            print(f"Error loading PaLiGemma model: {e}")
            raise

    def generate_text(self, prompt, max_length=200):
        """
        Generate text response
        """
        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            ).to(self.device)
            
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_length,
                num_return_sequences=1,
                temperature=0.7,
                do_sample=True,
                pad_token_id=self.tokenizer.pad_token_id,
                bos_token_id=2,
                eos_token_id=1
            )
            
            return self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        except Exception as e:
            print(f"Error generating text: {e}")
            return f"Error: {str(e)}"