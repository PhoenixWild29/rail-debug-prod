# app/agents/quantized_analyzer.py
from llama_cpp import Llama
import logging

class QuantizedAnalyzerService:
    def __init__(self, model_path: str, n_gpu_layers: int = -1):
        """
        Initializes the service with a quantized GGUF model.

        Args:
            model_path: Path to the GGUF model file.
            n_gpu_layers: Number of layers to offload to the GPU. -1 means offload all possible.
        """
        # A critical prerequisite is that llama-cpp-python must be installed with CUDA support.
        # This is typically done via: CMAKE_ARGS="-DLLAMA_CUBLAS=on" pip install llama-cpp-python
        try:
            self.llm = Llama(
                model_path=model_path,
                n_ctx=4096,          # Context window size
                n_gpu_layers=n_gpu_layers,
                verbose=True,
            )
            logging.info(f"Quantized model loaded from {model_path} with {n_gpu_layers} layers offloaded to GPU.")
        except Exception as e:
            logging.error(f"Failed to load GGUF model: {e}")
            self.llm = None

    def analyze(self, query: str, context: str) -> str:
        if not self.llm:
            return "Error: Model not loaded."

        prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert rail systems debugging assistant. Analyze the user's query and the provided documentation context to suggest a fix.
Step 1: Identify the core error from the user's query: '{query}'.
Step 2: Find the most relevant information in the provided context.
Step 3: Propose a solution with a clear explanation and a code snippet for the rail environment.<|eot_id|><|start_header_id|>user<|end_header_id|>

Context:
{context}

Query:
{query}<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""

        output = self.llm(prompt, max_tokens=512, stop=["<|eot_id|>"], echo=False)
        return output['choices'][0]['text']