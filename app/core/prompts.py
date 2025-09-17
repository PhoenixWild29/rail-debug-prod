# app/core/prompts.py
from langfuse import get_client

def get_production_analyzer_prompt():
    """Fetches the active production prompt for the rail debug analyzer."""
    try:
        langfuse = get_client()
        # Fetch the prompt version currently labeled "production"
        prompt_object = langfuse.get_prompt("rail-debug-analyzer", label="production")
        return prompt_object.get_prompt()  # Returns the prompt string
    except Exception as e:
        # Fallback to a default prompt if the service is unavailable
        return "Default fallback prompt..."