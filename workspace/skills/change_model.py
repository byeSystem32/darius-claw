# Copyright (c) 2026 Darius Claw
# Licensed under the MIT License

"""
Skill to change the model configuration for OpenClaw using OpenRouter.
This skill allows switching models via OpenRouter's API.
"""

import os
import requests
import logging
from typing import Dict, Optional, Union

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenRouter Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_HOST = os.getenv("OPENROUTER_API_HOST", "https://openrouter.ai/api/v1")


def validate_openrouter_config() -> bool:
    """Validate OpenRouter API key and host."""
    if not OPENROUTER_API_KEY:
        logger.error("OpenRouter API key not set.")
        return False
    return True


def change_model(
    model_name: str,
    temperature: float = 0.7,
    max_tokens: int = 100,
    **kwargs
) -> Dict[str, Union[str, bool]]:
    """
    Change the model configuration for OpenClaw using OpenRouter.
    
    Args:
        model_name (str): Name of the model (e.g., "mistralai/mistral-tiny").
        temperature (float): Sampling temperature.
        max_tokens (int): Maximum tokens to generate.
        **kwargs: Additional OpenRouter parameters.
    
    Returns:
        Dict[str, Union[str, bool]]: Success status, model name, or error message.
    """
    if not validate_openrouter_config():
        return {"success": False, "error": "OpenRouter API key not configured."}

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "OpenClaw",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **kwargs
    }

    try:
        # Test the model by making a chat completion request
        response = requests.post(
            f"{OPENROUTER_API_HOST}/chat/completions",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        
        logger.info(f"Successfully switched to model: {model_name}")
        return {
            "success": True,
            "model": model_name,
            "status_code": response.status_code,
            "model_details": response.json().get("model", "Unknown")
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenRouter API error: {e}")
        return {"success": False, "error": str(e)}


# Example usage (for testing)
if __name__ == "__main__":
    # Set your OpenRouter API key (for testing)
    os.environ["OPENROUTER_API_KEY"] = "your_openrouter_api_key_here"
    
    # Test the skill
    result = change_model(
        model_name="mistralai/mistral-tiny",
        temperature=0.7,
        max_tokens=100
    )
    print(result)