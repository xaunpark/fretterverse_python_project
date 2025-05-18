# utils/config_loader.py
import os
import logging
import json
from dotenv import load_dotenv
from config import settings # Import từ file settings.py cùng cấp hoặc trong package config

logger = logging.getLogger(__name__)

def load_app_config(site_name=None):
    """
    Loads configuration from .env file and merges/overrides with settings.py.
    If site_name is provided, it also loads site-specific config from
    site_profiles/{site_name}/site_config.json and site_profiles/{site_name}/.env.
    Returns a dictionary-like object or a custom config object.
    """
    # Đường dẫn đến thư mục gốc của dự án (giả sử utils nằm trong thư mục con của project root)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Load .env gốc (config/.env)
    global_dotenv_path = os.path.join(project_root, 'config', '.env')
    if os.path.exists(global_dotenv_path):
        load_dotenv(global_dotenv_path, override=True) # override=True để biến trong .env ghi đè biến môi trường hệ thống nếu trùng
        logger.info(f"Loaded global .env file from: {global_dotenv_path}")
    else:
        logger.warning(f"Global .env file not found at {global_dotenv_path}. Using default settings or system environment variables.")


    # Tạo một đối tượng config đơn giản để dễ truy cập
    # Bạn có thể dùng class nếu muốn phức tạp hơn
    config = {}

    # Load từ settings.py trước (các giá trị mặc định)
    for key in dir(settings):
        if key.isupper(): # Chỉ lấy các biến viết hoa (quy ước cho hằng số)
            config[key] = getattr(settings, key)

    # 3. Override/thêm từ biến môi trường (đã load từ .env gốc hoặc có sẵn trong HĐH)
    # Các biến trong .env nên trùng tên với các biến trong settings.py để dễ override
    # Các giá trị này sẽ là fallback nếu site_config.json hoặc site .env không có
    config['OPENROUTER_API_KEY'] = os.getenv('OPENROUTER_API_KEY', config.get('OPENROUTER_API_KEY'))
    config['OPENROUTER_BASE_URL'] = os.getenv('OPENROUTER_BASE_URL', config.get('OPENROUTER_BASE_URL'))
    config['SERPER_API_KEY'] = os.getenv('SERPER_API_KEY', config.get('SERPER_API_KEY'))
    config['SERPER_BASE_URL'] = os.getenv('SERPER_BASE_URL', config.get('SERPER_BASE_URL'))
    config['SEARCH_PROVIDER'] = os.getenv('SEARCH_PROVIDER', config.get('SEARCH_PROVIDER', 'google')).lower()
    config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
    config['GOOGLE_API_KEY'] = os.getenv('GOOGLE_API_KEY')
    config['YOUTUBE_API_KEY'] = os.getenv('YOUTUBE_API_KEY')
    config['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')

    config['WP_BASE_URL'] = os.getenv('WP_BASE_URL', config.get('WP_BASE_URL_PLACEHOLDER'))
    config['WP_USER'] = os.getenv('WP_USER')
    config['WP_PASSWORD'] = os.getenv('WP_PASSWORD')

    config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
    config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT', 3306))
    config['MYSQL_USER'] = os.getenv('MYSQL_USER')
    config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
    config['MYSQL_DATABASE'] = os.getenv('MYSQL_DATABASE')

    config['GSHEET_SPREADSHEET_ID'] = os.getenv('GSHEET_SPREADSHEET_ID', config.get('GSHEET_SPREADSHEET_ID_PLACEHOLDER'))
    # config['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS') # Nếu dùng service account

    config['GOOGLE_CX_ID'] = os.getenv('GOOGLE_CX_ID')

    config['PINECONE_API_KEY'] = os.getenv('PINECONE_API_KEY')
    config['PINECONE_ENVIRONMENT'] = os.getenv('PINECONE_ENVIRONMENT')
    config['PINECONE_INDEX_NAME'] = os.getenv('PINECONE_INDEX_NAME', config.get('PINECONE_INDEX_NAME_PLACEHOLDER'))
    
    # 4. Load cấu hình site-specific nếu site_name được cung cấp
    if site_name:
        logger.info(f"Loading configuration for site: {site_name}")
        site_config_dir = os.path.join(project_root, 'site_profiles', site_name)
        
        # 4a. Load site_config.json
        site_config_json_path = os.path.join(site_config_dir, 'site_config.json')
        if os.path.exists(site_config_json_path):
            try:
                with open(site_config_json_path, 'r') as f:
                    site_specific_json_config = json.load(f)
                config.update(site_specific_json_config) # Ghi đè các giá trị từ settings.py/global .env
                logger.info(f"Loaded site-specific JSON config from: {site_config_json_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from {site_config_json_path}: {e}")
            except Exception as e:
                logger.error(f"Error loading site-specific JSON config from {site_config_json_path}: {e}")
        else:
            logger.warning(f"Site-specific JSON config file not found for site '{site_name}' at {site_config_json_path}")

        # 4b. Load site-specific .env (ghi đè tất cả những gì đã load trước đó cho site này)
        site_dotenv_path = os.path.join(site_config_dir, '.env')
        if os.path.exists(site_dotenv_path):
            load_dotenv(site_dotenv_path, override=True)
            logger.info(f"Loaded site-specific .env file from: {site_dotenv_path}")
            # Tải lại các biến môi trường có thể bị ghi đè bởi site .env
            # Lặp lại các os.getenv calls ở trên hoặc chỉ những cái bạn mong đợi có trong site .env
            # Ví dụ:
            config['GOOGLE_CX_ID'] = os.getenv('GOOGLE_CX_ID', config.get('GOOGLE_CX_ID'))
            config['WP_BASE_URL'] = os.getenv('WP_BASE_URL', config.get('WP_BASE_URL'))
            # ... thêm các biến khác bạn muốn site .env có thể override ...
        else:
            logger.info(f"No site-specific .env file found for site '{site_name}' at {site_dotenv_path}")


    config['MAX_KEYWORDS_PER_RUN'] = int(os.getenv('MAX_KEYWORDS_PER_RUN', str(config.get('MAX_KEYWORDS_PER_RUN', 1))))
    config['DELAY_BETWEEN_KEYWORDS_SEC'] = int(os.getenv('DELAY_BETWEEN_KEYWORDS_SEC', str(config.get('DELAY_BETWEEN_KEYWORDS_SEC', 5))))
    # config['GSHEET_KEYWORD_SHEET_NAME_USED_0'] = os.getenv('GSHEET_KEYWORD_SHEET_NAME_USED_0', 'Keyword Used = 0')
    config['IMAGE_SEARCH_MIN_WIDTH'] = int(os.getenv('IMAGE_SEARCH_MIN_WIDTH', str(config.get('IMAGE_SEARCH_MIN_WIDTH', 1000))))
    config['IMAGE_SEARCH_MIN_HEIGHT'] = int(os.getenv('IMAGE_SEARCH_MIN_HEIGHT', str(config.get('IMAGE_SEARCH_MIN_HEIGHT', 600))))

    config['GSHEET_STATUS_COLUMN'] = os.getenv('GSHEET_STATUS_COLUMN', config.get('GSHEET_STATUS_COLUMN'))

    config['ENABLE_FEATURED_IMAGE_GENERATION'] = os.getenv('ENABLE_FEATURED_IMAGE_GENERATION', str(config.get('ENABLE_FEATURED_IMAGE_GENERATION', True))).lower() in ['true', '1', 't']

    # Ví dụ cách lấy một giá trị từ settings.py nếu không có trong .env
    config['DEBUG_MODE'] = os.getenv('DEBUG_MODE', str(config.get('DEBUG_MODE', False))).lower() in ['true', '1', 't']


    # Kiểm tra các key quan trọng
    required_keys = [
        'OPENAI_API_KEY', # Vẫn cần cho DALL-E và Embeddings
        'OPENROUTER_API_KEY', # Thêm key cho OpenRouter
        'WP_BASE_URL',
        'WP_USER', 'WP_PASSWORD',
        'GSHEET_SPREADSHEET_ID',
        'PINECONE_API_KEY', 'PINECONE_ENVIRONMENT', 'PINECONE_INDEX_NAME',
    ]

    # Thêm các keys bắt buộc dựa trên SEARCH_PROVIDER
    # Nếu muốn cả hai luôn sẵn sàng, thì thêm SERPER_API_KEY và giữ GOOGLE_API_KEY, GOOGLE_CX_ID
    required_keys.append('SERPER_API_KEY') # Luôn yêu cầu nếu bạn muốn có tùy chọn Serper
    required_keys.append('GOOGLE_API_KEY') # Luôn yêu cầu nếu bạn muốn có tùy chọn Google
    required_keys.append('GOOGLE_CX_ID')   # Luôn yêu cầu nếu bạn muốn có tùy chọn Google

    # Loại bỏ trùng lặp nếu có
    required_keys = list(set(required_keys))

    missing_keys = [key for key in required_keys if not config.get(key)]
    if missing_keys:
        raise ValueError(f"Missing required configuration keys: {', '.join(missing_keys)}")

    logger.info(f"Search provider configured: {config.get('SEARCH_PROVIDER')}")

    return config

# Có thể tạo một instance config toàn cục để dễ import và sử dụng
# Hoặc gọi hàm này mỗi khi cần config
# APP_CONFIG = load_app_config()

# Cách sử dụng ví dụ:
# from utils.config_loader import APP_CONFIG
# print(APP_CONFIG['OPENAI_API_KEY'])