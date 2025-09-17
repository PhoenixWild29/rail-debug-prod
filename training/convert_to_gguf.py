# training/convert_to_gguf.py
from transformers import AutoModelForCausalLM, AutoTokenizer
from llama_cpp import convert_hf_to_gguf

def convert_model_to_gguf():
    # Load the fine-tuned model
    model = AutoModelForCausalLM.from_pretrained("./fine-tuned-adapter")
    tokenizer = AutoTokenizer.from_pretrained("meta-llama/Meta-Llama-3-8B")

    # Convert to GGUF format
    convert_hf_to_gguf.convert_hf_to_gguf(
        model=model,
        tokenizer=tokenizer,
        out_path="./rail-debug-model.gguf",
        out_type="f16",  # Use f16 for balance of size and quality
    )

if __name__ == "__main__":
    convert_model_to_gguf()