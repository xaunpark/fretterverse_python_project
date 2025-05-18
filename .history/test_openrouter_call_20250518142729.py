# i:\VS-Project\fretterverse_python_project\test_openrouter_call.py
import logging
import os
import sys

# ---- Setup Project Path ----
# This ensures that the script can find the 'utils' module correctly,
# assuming the script is run from the project root or this path logic correctly points to it.
try:
    # If this script is in the project root:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    # If your utils folder is directly under PROJECT_ROOT, this should be enough.
    # If you have a src folder, you might need to adjust:
    # PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')) # If script is in a 'tests' subdir
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
except NameError: # __file__ is not defined, e.g. in interactive interpreter
    PROJECT_ROOT = os.getcwd()
    if PROJECT_ROOT not in sys.path:
         sys.path.insert(0, PROJECT_ROOT)

try:
    from utils.config_loader import load_config, config as global_config
    from utils.api_clients import call_llm_api # Assuming this function exists and is set up
except ModuleNotFoundError as e:
    print(f"Error importing modules: {e}")
    print(f"Please ensure that the script is run from a location where 'utils' is accessible,")
    print(f"or that PROJECT_ROOT is correctly set. Current sys.path: {sys.path}")
    sys.exit(1)

# Configure basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    logger.info("Starting OpenRouter API call test...")

    try:
        # Load configuration (without site_name to use global .env by default)
        # This should populate the `global_config` dictionary that api_clients.py imports.
        load_config() 
        logger.info("Configuration loaded.")
        
        openrouter_key = global_config.get("OPENROUTER_API_KEY")
        if not openrouter_key:
            logger.error("OPENROUTER_API_KEY not found in loaded config. The API call will likely fail.")
        else:
            # Log only a portion of the key for security
            logger.debug(f"OpenRouter API Key found: {openrouter_key[:5]}...{openrouter_key[-5:]}")

    except Exception as e:
        logger.error(f"Failed to load configuration: {e}", exc_info=True)
        return

    messages = [
        {"role": "user", "content": "Translate 'Hello, world!' to French."}
    ]
    # Using a model known to be available and often free/low-cost on OpenRouter
    test_model = "mistralai/mistral-7b-instruct" 

    logger.info(f"Attempting to call OpenRouter with model: {test_model}")

    try:
        response_content = call_llm_api(
            messages=messages,
            model_name=test_model,
            api_provider="openrouter", # Crucial: specifies to use OpenRouter configuration
            temperature=0.5,
            max_tokens=100
        )
        logger.info(f"Successfully received response from OpenRouter: {response_content}")
    except Exception as e:
        logger.error(f"An error occurred during the OpenRouter API call: {e}", exc_info=True)

if __name__ == "__main__":
    main()