# utils/config_loader.py
import os
from dotenv import load_dotenv
from config import settings # Import từ file settings.py cùng cấp hoặc trong package config

def load_app_config():
    """
    Loads configuration from .env file and merges/overrides with settings.py.
    Returns a dictionary-like object or a custom config object.
    """
    # Đường dẫn đến thư mục gốc của dự án (giả sử utils nằm trong thư mục con của project root)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dotenv_path = os.path.join(project_root, 'config', '.env')

    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
    else:
        # Cân nhắc việc raise lỗi hoặc log warning nếu file .env không tìm thấy
        # khi không ở DEBUG_MODE
        print(f"Warning: .env file not found at {dotenv_path}. Using default settings or environment variables.")

    # Tạo một đối tượng config đơn giản để dễ truy cập
    # Bạn có thể dùng class nếu muốn phức tạp hơn
    config = {}

    # Load từ settings.py trước (các giá trị mặc định)
    for key in dir(settings):
        if key.isupper(): # Chỉ lấy các biến viết hoa (quy ước cho hằng số)
            config[key] = getattr(settings, key)

    # Override/thêm từ biến môi trường (đã load từ .env hoặc có sẵn trong HĐH)
    # Các biến trong .env nên trùng tên với các biến trong settings.py để dễ override
    config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
    config['GOOGLE_API_KEY'] = os.getenv('GOOGLE_API_KEY')
    config['YOUTUBE_API_KEY'] = os.getenv('YOUTUBE_API_KEY')
    config['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')

    config['WP_BASE_URL'] = os.getenv('WP_BASE_URL', config.get('WP_BASE_URL_PLACEHOLDER'))
    config['WP_USER'] = os.getenv('WP_USER')
    config['WP_PASSWORD'] = os.getenv('WP_PASSWORD')

    config['REDIS_HOST'] = os.getenv('REDIS_HOST', 'localhost')
    config['REDIS_PORT'] = int(os.getenv('REDIS_PORT', 6379))
    config['REDIS_PASSWORD'] = os.getenv('REDIS_PASSWORD', None)
    config['REDIS_DB'] = int(os.getenv('REDIS_DB', 0))

    config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', 'localhost')
    config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT', 3306))
    config['MYSQL_USER'] = os.getenv('MYSQL_USER')
    config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
    config['MYSQL_DATABASE'] = os.getenv('MYSQL_DATABASE')

    config['GSHEET_SPREADSHEET_ID'] = os.getenv('GSHEET_SPREADSHEET_ID', config.get('GSHEET_SPREADSHEET_ID_PLACEHOLDER'))
    # config['GOOGLE_APPLICATION_CREDENTIALS'] = os.getenv('GOOGLE_APPLICATION_CREDENTIALS') # Nếu dùng service account

    config['GOOGLE_CX_ID_FOR_SERP_ANALYSIS'] = os.getenv('GOOGLE_CX_ID_FOR_SERP_ANALYSIS')

    config['PINECONE_API_KEY'] = os.getenv('PINECONE_API_KEY')
    config['PINECONE_ENVIRONMENT'] = os.getenv('PINECONE_ENVIRONMENT')
    config['PINECONE_INDEX_NAME'] = os.getenv('PINECONE_INDEX_NAME', config.get('PINECONE_INDEX_NAME_PLACEHOLDER'))

    # Ví dụ cách lấy một giá trị từ settings.py nếu không có trong .env
    config['DEBUG_MODE'] = os.getenv('DEBUG_MODE', str(config.get('DEBUG_MODE', False))).lower() in ['true', '1', 't']


    # Kiểm tra các key quan trọng
    required_keys = ['OPENAI_API_KEY', 'WP_BASE_URL', 'WP_USER', 'WP_PASSWORD', 'GSHEET_SPREADSHEET_ID', 'PINECONE_API_KEY', 'PINECONE_ENVIRONMENT', 'PINECONE_INDEX_NAME']
    missing_keys = [key for key in required_keys if not config.get(key)]
    if missing_keys:
        raise ValueError(f"Missing required configuration keys: {', '.join(missing_keys)}")

    return config

# Có thể tạo một instance config toàn cục để dễ import và sử dụng
# Hoặc gọi hàm này mỗi khi cần config
# APP_CONFIG = load_app_config()

# Cách sử dụng ví dụ:
# from utils.config_loader import APP_CONFIG
# print(APP_CONFIG['OPENAI_API_KEY'])