# utils/config_loader.py
import os
import logging
import json
from dotenv import load_dotenv
from config import settings # Import từ file settings.py cùng cấp hoặc trong package config

logger = logging.getLogger(__name__)

# Define keys expected from environment variables and their types
# 'config_key' is the key used in the APP_CONFIG dict. Defaults to 'env_var' if not specified.
# 'type' can be int, bool, or defaults to string.
ENV_CONFIG_MAPPING = [
    # General API Keys
    {'env_var': 'OPENAI_API_KEY'},
    {'env_var': 'OPENROUTER_API_KEY'},
    {'env_var': 'OPENROUTER_BASE_URL'},
    {'env_var': 'SERPER_API_KEY'},
    {'env_var': 'SERPER_BASE_URL'},
    {'env_var': 'GOOGLE_API_KEY'},
    {'env_var': 'YOUTUBE_API_KEY'},
    {'env_var': 'GEMINI_API_KEY'},
    
    # Google Custom Search
    {'env_var': 'GOOGLE_CX_ID'},
    # {'env_var': 'GOOGLE_IMAGES_CX_ID'}, # Thêm nếu bạn có CX_ID riêng cho ảnh từ .env
    # {'env_var': 'GOOGLE_CX_ID_EXTERNAL_LINKS'}, # Thêm nếu có CX_ID riêng cho external links từ .env

    # WordPress Credentials
    {'env_var': 'WP_BASE_URL'},
    {'env_var': 'WP_USER'},
    {'env_var': 'WP_PASSWORD'},
    {'env_var': 'WP_TABLE_PREFIX'}, # Quan trọng cho ILJ
    
    # MySQL Configuration
    {'env_var': 'MYSQL_HOST'},
    {'env_var': 'MYSQL_PORT', 'type': int},
    {'env_var': 'MYSQL_USER'},
    {'env_var': 'MYSQL_PASSWORD'},
    {'env_var': 'MYSQL_DATABASE'},
    
    # Google Sheets
    {'env_var': 'GSHEET_SPREADSHEET_ID'},
    {'env_var': 'GSHEET_KEYWORD_SHEET_NAME'},
    {'env_var': 'GSHEET_KEYWORD_SHEET_NAME_USED_0'},
    {'env_var': 'GSHEET_KEYWORD_COLUMN'},
    {'env_var': 'GSHEET_USED_COLUMN'},
    {'env_var': 'GSHEET_UNIQUE_COLUMN'},
    {'env_var': 'GSHEET_SUITABLE_COLUMN'},
    {'env_var': 'GSHEET_POST_TITLE_COLUMN'},
    {'env_var': 'GSHEET_POST_ID_COLUMN'},
    {'env_var': 'GSHEET_POST_URL_COLUMN'},
    {'env_var': 'GSHEET_STATUS_COLUMN'},
    {'env_var': 'GOOGLE_APPLICATION_CREDENTIALS'}, # Đường dẫn tới file service account JSON
    
    # Pinecone Configuration
    {'env_var': 'PINECONE_API_KEY'},
    {'env_var': 'PINECONE_ENVIRONMENT'},
    {'env_var': 'PINECONE_INDEX_NAME'},
    {'env_var': 'PINECONE_EMBEDDING_DIMENSION', 'type': int},

    # Application Settings
    {'env_var': 'MAX_KEYWORDS_PER_RUN', 'type': int},
    {'env_var': 'DELAY_BETWEEN_KEYWORDS_SEC', 'type': int},
    {'env_var': 'DEBUG_MODE', 'type': bool, 'config_key': 'DEBUG_MODE'},
    {'env_var': 'SEARCH_PROVIDER'}, # 'google' or 'serper'
    {'env_var': 'IMAGE_SEARCH_MIN_WIDTH', 'type': int},
    {'env_var': 'IMAGE_SEARCH_MIN_HEIGHT', 'type': int},
    {'env_var': 'YOUTUBE_SEARCH_NUM_RESULTS', 'type': int},
    {'env_var': 'LOG_FILE_PATH'},
    {'env_var': 'LOG_TO_CONSOLE', 'type': bool},
    {'env_var': 'LOG_TO_FILE', 'type': bool},
    {'env_var': 'ENABLE_FEATURED_IMAGE_GENERATION', 'type': bool},
    {'env_var': 'FEATURED_IMAGE_MODEL'},
    {'env_var': 'FEATURED_IMAGE_SIZE'},
    {'env_var': 'USER_AGENT'},

    # Past Date Publishing
    {'env_var': 'PAST_DATE_PUBLISHING_ENABLED', 'type': bool},
    {'env_var': 'PAST_DATE_PUBLISHING_START_DATE'}, # Defaults to string
    {'env_var': 'PAST_DATE_PUBLISHING_END_DATE'},   # Defaults to string
    # Schedule settings
    {'env_var': 'SCHEDULE_ENABLED', 'type': bool, 'config_key': 'SCHEDULE_ENABLED'},
    {'env_var': 'SCHEDULE_INTERVAL_HOURS', 'type': int, 'config_key': 'SCHEDULE_INTERVAL_HOURS'},
    {'env_var': 'SCHEDULE_INTERVAL_MINUTES', 'type': int, 'config_key': 'SCHEDULE_INTERVAL_MINUTES'},

    {'env_var': 'SLACK_WEBHOOK_URL'},
]

def _apply_env_vars_to_config(config_dict, mapping):
    """Helper function to update config_dict from os.environ based on mapping."""
    for item in mapping:
        env_key = item['env_var']
        config_key = item.get('config_key', env_key) # Key in the config dict
        var_type = item.get('type')
        
        env_value_str = os.getenv(env_key)
        
        if env_value_str is not None: # Only update if env var is actually set
            if var_type == int:
                try:
                    config_dict[config_key] = int(env_value_str)
                except ValueError:
                    logger.warning(f"Invalid integer value for env var {env_key}: '{env_value_str}'. "
                                   f"Keeping current config value for {config_key}: {config_dict.get(config_key)}")
            elif var_type == bool:
                config_dict[config_key] = env_value_str.lower() in ('true', '1', 't', 'yes', 'y')
            else: # string
                config_dict[config_key] = env_value_str
        # If env_value_str is None, the value in config_dict (from settings.py or site_config.json) remains.

def load_app_config(site_name=None):
    """
    Loads configuration in the following order of precedence (later overrides earlier):
    1. Defaults from config/settings.py
    2. Values from config/.env (global .env)
    3. Values from site_profiles/{site_name}/site_config.json (if site_name provided)
    4. Values from site_profiles/{site_name}/.env (site-specific .env, if site_name provided)
    Returns a dictionary-like object.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = {}

    # 1. Load defaults from settings.py
    for key in dir(settings):
        if key.isupper(): # Chỉ lấy các biến viết hoa (quy ước cho hằng số)
            config[key] = getattr(settings, key)
    logger.debug(f"Initial config from settings.py loaded.")

    # 2. Load global .env (config/.env) - this updates os.environ
    # Then apply these os.environ values to the config dictionary
    global_dotenv_path = os.path.join(project_root, 'config', '.env')
    if os.path.exists(global_dotenv_path):
        load_dotenv(global_dotenv_path, override=True) 
        logger.info(f"Loaded global .env file: {global_dotenv_path}")
        _apply_env_vars_to_config(config, ENV_CONFIG_MAPPING) # Apply to config dict
        logger.debug(f"Config after global .env applied.")
    else:
        logger.warning(f"Global .env file not found at {global_dotenv_path}.")
        # Still apply from system env vars if global .env is missing
        _apply_env_vars_to_config(config, ENV_CONFIG_MAPPING)
        logger.debug(f"Config after system env (no global .env) applied.")

    # 3. Load site-specific configurations if site_name is provided
    if site_name:
        logger.info(f"Loading configuration for site: {site_name}")
        site_config_dir = os.path.join(project_root, 'site_profiles', site_name)
        
        # 3a. Load site_config.json (overrides settings.py and global .env values in config dict)
        site_config_json_path = os.path.join(site_config_dir, 'site_config.json')
        if os.path.exists(site_config_json_path):
            try:
                with open(site_config_json_path, 'r', encoding='utf-8') as f:
                    site_specific_json_config = json.load(f)
                config.update(site_specific_json_config) 
                logger.info(f"Loaded site-specific JSON config: {site_config_json_path}")
                logger.debug(f"Config after site_config.json applied.")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {site_config_json_path}: {e}")
            except Exception as e:
                logger.error(f"Error loading site-specific JSON config from {site_config_json_path}: {e}")
        else:
            logger.warning(f"Site-specific JSON config file not found for site '{site_name}' at {site_config_json_path}")

        # 3b. Load site-specific .env (site_profiles/{site_name}/.env)
        # This loads into os.environ, overriding relevant vars from global .env or system env vars.
        # Then, re-apply ENV_CONFIG_MAPPING to update the config dict with these site-specific .env values.
        site_dotenv_path = os.path.join(site_config_dir, '.env')
        if os.path.exists(site_dotenv_path):
            load_dotenv(site_dotenv_path, override=True)
            logger.info(f"Loaded site-specific .env file from: {site_dotenv_path}")
            _apply_env_vars_to_config(config, ENV_CONFIG_MAPPING) # Re-apply to pick up site-specific .env overrides
            logger.debug(f"Config after site-specific .env applied.")
        else:
            logger.info(f"No site-specific .env file found for site '{site_name}' at {site_dotenv_path}")
    
    # Final checks and fallbacks for critical configurations
    if config.get('MAX_KEYWORDS_PER_RUN') is None:
        logger.warning("MAX_KEYWORDS_PER_RUN not configured, defaulting to 1.")
        config['MAX_KEYWORDS_PER_RUN'] = 1
    elif not isinstance(config.get('MAX_KEYWORDS_PER_RUN'), int):
        try:
            config['MAX_KEYWORDS_PER_RUN'] = int(config['MAX_KEYWORDS_PER_RUN'])
        except (ValueError, TypeError):
            logger.warning(f"MAX_KEYWORDS_PER_RUN ('{config.get('MAX_KEYWORDS_PER_RUN')}') is not a valid integer. Defaulting to 1.")
            config['MAX_KEYWORDS_PER_RUN'] = 1
    
    # Ensure SEARCH_PROVIDER has a default if not set
    if not config.get('SEARCH_PROVIDER'):
        config['SEARCH_PROVIDER'] = 'google' # Default to Google if not specified

    # Check for required keys
    required_keys = [
        'OPENAI_API_KEY', 'OPENROUTER_API_KEY',
        'WP_BASE_URL', 'WP_USER', 'WP_PASSWORD', 'WP_TABLE_PREFIX',
        'GSHEET_SPREADSHEET_ID',
        'PINECONE_API_KEY', 'PINECONE_INDEX_NAME', # PINECONE_ENVIRONMENT is for pod-based, not always needed for serverless
        'MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE', 'MYSQL_PORT'
    ]
    # Add search provider specific keys
    if config.get('SEARCH_PROVIDER') == 'serper':
        required_keys.append('SERPER_API_KEY')
        required_keys.append('SERPER_BASE_URL')
    else: # Default or 'google'
        required_keys.append('GOOGLE_API_KEY')
        required_keys.append('GOOGLE_CX_ID')

    missing_keys = [key for key in required_keys if not config.get(key)]
    if missing_keys:
        # Log a warning instead of raising an error immediately,
        # as some scripts (like delete_keywords_from_pinecone.py) might not need all keys.
        # The calling script should handle the absence of critical keys if it proceeds.
        logger.warning(f"Missing configuration keys that might be required: {', '.join(missing_keys)}")
        # Consider raising ValueError here if all keys are always mandatory for any operation:
        # raise ValueError(f"Missing required configuration keys: {', '.join(missing_keys)}")

    logger.info(f"Configuration loading complete. Search provider: {config.get('SEARCH_PROVIDER')}")

    # Ensure boolean flags and their associated settings have valid defaults and types

    # Past Date Publishing settings
    if not isinstance(config.get('PAST_DATE_PUBLISHING_ENABLED'), bool):
        original_value = config.get('PAST_DATE_PUBLISHING_ENABLED')
        if original_value is not None: # It was set, but not as a bool
            logger.warning(f"PAST_DATE_PUBLISHING_ENABLED ('{original_value}') is not a valid boolean. Defaulting to False.")
        else: # It was not set at all
            logger.debug(f"PAST_DATE_PUBLISHING_ENABLED not set. Defaulting to False.")
        config['PAST_DATE_PUBLISHING_ENABLED'] = False

    if config.get('PAST_DATE_PUBLISHING_ENABLED'):
        if not config.get('PAST_DATE_PUBLISHING_START_DATE'):
            logger.warning("PAST_DATE_PUBLISHING_ENABLED is true, but PAST_DATE_PUBLISHING_START_DATE is not set in config.")
        if not config.get('PAST_DATE_PUBLISHING_END_DATE'):
            logger.warning("PAST_DATE_PUBLISHING_ENABLED is true, but PAST_DATE_PUBLISHING_END_DATE is not set in config.")

    # Schedule settings
    if not isinstance(config.get('SCHEDULE_ENABLED'), bool):
        logger.warning(f"SCHEDULE_ENABLED ('{config.get('SCHEDULE_ENABLED')}') is not a valid boolean or not set. Defaulting to False.")
        config['SCHEDULE_ENABLED'] = False

    try:
        config['SCHEDULE_INTERVAL_HOURS'] = int(config.get('SCHEDULE_INTERVAL_HOURS', 0))
        if config['SCHEDULE_INTERVAL_HOURS'] < 0:
            logger.warning(f"SCHEDULE_INTERVAL_HOURS ('{config['SCHEDULE_INTERVAL_HOURS']}') is negative. Setting to 0.")
            config['SCHEDULE_INTERVAL_HOURS'] = 0
    except (ValueError, TypeError):
        logger.warning(f"Invalid SCHEDULE_INTERVAL_HOURS: {config.get('SCHEDULE_INTERVAL_HOURS')}. Defaulting to 0.")
        config['SCHEDULE_INTERVAL_HOURS'] = 0

    try:
        config['SCHEDULE_INTERVAL_MINUTES'] = int(config.get('SCHEDULE_INTERVAL_MINUTES', 0))
        if config['SCHEDULE_INTERVAL_MINUTES'] < 0:
            logger.warning(f"SCHEDULE_INTERVAL_MINUTES ('{config['SCHEDULE_INTERVAL_MINUTES']}') is negative. Setting to 0.")
            config['SCHEDULE_INTERVAL_MINUTES'] = 0
    except (ValueError, TypeError):
        logger.warning(f"Invalid SCHEDULE_INTERVAL_MINUTES: {config.get('SCHEDULE_INTERVAL_MINUTES')}. Defaulting to 0.")
        config['SCHEDULE_INTERVAL_MINUTES'] = 0

    logger.debug(f"Final APP_CONFIG (first level keys): {list(config.keys())}")
    return config
