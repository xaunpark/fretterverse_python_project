# utils/config_loader.py
import os
import logging
import json
from dotenv import load_dotenv
from config import settings # Import từ file settings.py cùng cấp hoặc trong package config
import streamlit as st # Để sử dụng st.secrets

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
    {'env_var': 'ORCHESTRATOR_LOG_FILE_PATH'},
    {'env_var': 'ENABLE_FEATURED_IMAGE_GENERATION', 'type': bool},
    {'env_var': 'FEATURED_IMAGE_MODEL'},
    {'env_var': 'DEFAULT_POST_STATUS'},
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

def _get_typed_value(value_str, var_type, source_info_for_log=""):
    """Helper function to convert string value to a specific type."""
    if value_str is None:
        return None
    
    # streamlit.secrets can return non-string types directly
    if var_type == int:
        try:
            return int(value_str)
        except (ValueError, TypeError):
            logger.warning(f"Invalid integer value from {source_info_for_log}: '{value_str}'.")
            return None
    elif var_type == bool:
        if isinstance(value_str, bool): # Already a bool from st.secrets or direct assignment
            return value_str
        return str(value_str).lower() in ('true', '1', 't', 'yes', 'y')
    return str(value_str) # Default to string

def _apply_mapped_configurations(config_dict, mapping, site_name=None):
    """
    Applies configurations from st.secrets or os.environ based on ENV_CONFIG_MAPPING.
    Priority for each mapped key:
    1. st.secrets (SITE_NAME_UPPER_ENV_KEY)
    2. st.secrets (ENV_KEY)
    3. st.secrets (CONFIG_KEY_IN_DICT) - fallback if env_key is different
    4. os.environ (which reflects site .env -> global .env)
    Updates config_dict in place.
    """
    for item in mapping: # Iterate through ENV_CONFIG_MAPPING
        env_key = item['env_var']
        config_key_in_dict = item.get('config_key', env_key)
        var_type = item.get('type')
        value_from_source = None
        source_name = ""

        # 1. Try st.secrets (highest precedence)
        if hasattr(st, 'secrets') and st.secrets:
            # a. Site-specific secret using env_key
            if site_name:
                site_specific_secret_key = f"{site_name.upper()}_{env_key}"
                if st.secrets.get(site_specific_secret_key) is not None:
                    value_from_source = _get_typed_value(st.secrets.get(site_specific_secret_key), var_type, f"st.secrets['{site_specific_secret_key}']")
                    source_name = f"st.secrets['{site_specific_secret_key}']"
            # b. Global secret using env_key
            if value_from_source is None and st.secrets.get(env_key) is not None:
                value_from_source = _get_typed_value(st.secrets.get(env_key), var_type, f"st.secrets['{env_key}']")
                source_name = f"st.secrets['{env_key}']"
            # c. Global secret using config_key_in_dict (fallback if env_key is different)
            if value_from_source is None and env_key != config_key_in_dict and st.secrets.get(config_key_in_dict) is not None:
                value_from_source = _get_typed_value(st.secrets.get(config_key_in_dict), var_type, f"st.secrets['{config_key_in_dict}']")
                source_name = f"st.secrets['{config_key_in_dict}'] (fallback)"
        
        # 2. If not in st.secrets, try os.environ (reflects .env files loaded earlier)
        if value_from_source is None and os.getenv(env_key) is not None:
            value_from_source = _get_typed_value(os.getenv(env_key), var_type, f"env['{env_key}']")
            source_name = f"os.environ (via {env_key})"

        if value_from_source is not None:
            if config_dict.get(config_key_in_dict) != value_from_source:
                 logger.debug(f"Config '{config_key_in_dict}' set to '{value_from_source}' from {source_name} (was: '{config_dict.get(config_key_in_dict)}').")
            config_dict[config_key_in_dict] = value_from_source
        # If not found in st.secrets or os.environ, the value from settings.py/site_config.json (if any for this key) remains.

def load_app_config(site_name=None):
    """
    Loads configuration in the following order of precedence (later overrides earlier):
    1. Defaults from config/settings.py
    2. Values from config/.env (global .env)
    3. Values from site_profiles/{site_name}/site_config.json (if site_name provided)
    4. Values from site_profiles/{site_name}/.env (site-specific .env, if site_name provided, updates os.environ)
    5. Values from st.secrets (SITE_KEY then GLOBAL_KEY) applied via ENV_CONFIG_MAPPING, overriding previous.
    Returns a dictionary-like object.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = {}

    # 1. Load defaults from settings.py
    for key in dir(settings):
        if key.isupper(): # Chỉ lấy các biến viết hoa (quy ước cho hằng số)
            config[key] = getattr(settings, key)
    logger.debug(f"Initial config from settings.py loaded.")

    # 2. Load global .env (config/.env) - this updates os.environ.
    #    It's loaded before site-specific .env so site-specific can override.
    global_dotenv_path = os.path.join(project_root, 'config', '.env')
    if os.path.exists(global_dotenv_path):
        load_dotenv(global_dotenv_path, override=True) 
        logger.info(f"Loaded global .env file into os.environ: {global_dotenv_path}")
    else:
        logger.warning(f"Global .env file not found at {global_dotenv_path}.")

    # 3. Load site-specific configurations if site_name is provided
    if site_name:
        logger.info(f"Loading configuration for site: {site_name}")
        site_config_dir = os.path.join(project_root, 'site_profiles', site_name)
        
        # 3a. Load site_config.json (overrides settings.py values in config dict)
        # This is loaded before ENV_CONFIG_MAPPING processing, so env/secrets can override these JSON values.
        site_config_json_path = os.path.join(site_config_dir, 'site_config.json')
        if os.path.exists(site_config_json_path):
            try:
                with open(site_config_json_path, 'r', encoding='utf-8') as f:
                    site_specific_json_config = json.load(f)
                config.update(site_specific_json_config) 
                logger.info(f"Loaded and applied site-specific JSON config: {site_config_json_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {site_config_json_path}: {e}")
            except Exception as e:
                logger.error(f"Error loading site-specific JSON config from {site_config_json_path}: {e}")
        else:
            logger.warning(f"Site-specific JSON config file not found for site '{site_name}' at {site_config_json_path}")

        # 3b. Load site-specific .env (site_profiles/{site_name}/.env) - this updates os.environ
        # This will override any vars from global .env if they share the same name in os.environ.
        site_dotenv_path = os.path.join(site_config_dir, '.env')
        if os.path.exists(site_dotenv_path):
            load_dotenv(site_dotenv_path, override=True) # Site .env overrides global .env and system env in os.environ
            logger.info(f"Loaded site-specific .env file into os.environ: {site_dotenv_path}")
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
    
    # 4. Apply ENV_CONFIG_MAPPING: st.secrets (site then global) -> os.environ (from .env files) -> existing config values
    # This function updates the 'config' dictionary with values from these sources for keys defined in ENV_CONFIG_MAPPING.
    _apply_mapped_configurations(config, ENV_CONFIG_MAPPING, site_name=site_name)
    
    # Ensure SEARCH_PROVIDER has a default if not set
    if not config.get('SEARCH_PROVIDER'):
        config['SEARCH_PROVIDER'] = 'google' # Default to Google if not specified

    # Check for required keys
    required_keys = [
        # 'OPENAI_API_KEY', # Có thể không bắt buộc nếu OpenRouter được dùng chính
        'OPENROUTER_API_KEY',
        'WP_BASE_URL', 'WP_USER', 'WP_PASSWORD', 'WP_TABLE_PREFIX',
        'GSHEET_SPREADSHEET_ID',
        'PINECONE_API_KEY', 'PINECONE_INDEX_NAME', 
        'MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE', 'MYSQL_PORT'
    ]
    # Add search provider specific keys
    if config.get('SEARCH_PROVIDER') == 'serper':
        required_keys.append('SERPER_API_KEY')
        required_keys.append('SERPER_BASE_URL')
    elif config.get('SEARCH_PROVIDER') == 'google': # Chỉ yêu cầu nếu là google
        required_keys.append('GOOGLE_API_KEY')
        required_keys.append('GOOGLE_CX_ID')

    missing_keys = [key for key in required_keys if not config.get(key)]
    if missing_keys:
        logger.warning(f"Missing configuration keys that might be required: {', '.join(missing_keys)}")

    logger.info(f"Configuration loading complete. Search provider: {config.get('SEARCH_PROVIDER')}")

    # Ensure boolean flags and their associated settings have valid defaults and types
    if not isinstance(config.get('PAST_DATE_PUBLISHING_ENABLED'), bool):
        original_value = config.get('PAST_DATE_PUBLISHING_ENABLED')
        if original_value is not None: 
            logger.warning(f"PAST_DATE_PUBLISHING_ENABLED ('{original_value}') is not a valid boolean. Defaulting to False.")
        else: 
            logger.debug(f"PAST_DATE_PUBLISHING_ENABLED not set. Defaulting to False.")
        config['PAST_DATE_PUBLISHING_ENABLED'] = False

    if config.get('PAST_DATE_PUBLISHING_ENABLED'):
        if not config.get('PAST_DATE_PUBLISHING_START_DATE'):
            logger.warning("PAST_DATE_PUBLISHING_ENABLED is true, but PAST_DATE_PUBLISHING_START_DATE is not set in config.")
        if not config.get('PAST_DATE_PUBLISHING_END_DATE'):
            logger.warning("PAST_DATE_PUBLISHING_ENABLED is true, but PAST_DATE_PUBLISHING_END_DATE is not set in config.")

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

    # Xử lý GOOGLE_APPLICATION_CREDENTIALS cho Streamlit Secrets
    # Nếu chạy trên Streamlit Cloud và GOOGLE_APPLICATION_CREDENTIALS_JSON_STR được set trong secrets
    if hasattr(st, 'secrets') and st.secrets and st.secrets.get("GOOGLE_APPLICATION_CREDENTIALS_JSON_STR"):
        logger.info("Found GOOGLE_APPLICATION_CREDENTIALS_JSON_STR in Streamlit secrets.")
        # Tạo một file tạm để gspread có thể đọc
        try:
            creds_json_str = st.secrets.get("GOOGLE_APPLICATION_CREDENTIALS_JSON_STR")
            # Đường dẫn file tạm trong môi trường Streamlit Cloud (thường là /tmp)
            # Cần một tên file duy nhất nếu nhiều instance chạy, nhưng cho 1 app thì có thể cố định
            temp_creds_path = os.path.join(project_root, ".streamlit_service_account.json") # Lưu ở gốc project cho dễ
            
            with open(temp_creds_path, "w") as f:
                f.write(creds_json_str)
            config['GOOGLE_APPLICATION_CREDENTIALS'] = temp_creds_path # Ghi đè đường dẫn
            logger.info(f"Created temporary service account file for Streamlit Cloud at {temp_creds_path}")
        except Exception as e_temp_creds:
            logger.error(f"Error creating temporary service account file from Streamlit secrets: {e_temp_creds}")
            # Nếu lỗi, GOOGLE_APPLICATION_CREDENTIALS có thể vẫn là giá trị từ .env (nếu có)
            # hoặc None, và GoogleSheetsHandler sẽ báo lỗi sau.
    elif not config.get('GOOGLE_APPLICATION_CREDENTIALS'):
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS path not found in any configuration source.")


    logger.debug(f"Final APP_CONFIG (first level keys): {list(config.keys())}")
    return config
