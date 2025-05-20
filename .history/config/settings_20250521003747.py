# config/settings.py

# --- Cấu hình chung cho ứng dụng ---
APP_NAME = "FretterVerse Python Project"
DEBUG_MODE = True  # Chuyển thành False khi deploy
MAX_KEYWORDS_PER_RUN = 20  # Giới hạn số lần thử xử lý các keyword bị lỗi (nếu không có trong site_config)
DELAY_BETWEEN_KEYWORDS_SEC = 5 # Thời gian nghỉ (giây) giữa các keyword

# --- Cấu hình cho WordPress ---
# Các giá trị này sẽ là fallback nếu site_config.json không định nghĩa
WP_BASE_URL_FALLBACK = "http://default-wp.local"
DEFAULT_POST_STATUS_FALLBACK = "draft"
DEFAULT_AUTHOR_ID_FALLBACK = 1
DEFAULT_CATEGORY_ID_FALLBACK = 1 # Thường là "Uncategorized"
IMAGE_RESIZE_WIDTH_FALLBACK = 800
IMAGE_RESIZE_HEIGHT_FALLBACK = None # Giữ tỷ lệ
FEATURED_IMAGE_RESIZE_WIDTH_FALLBACK = 1200
WP_TABLE_PREFIX_FALLBACK = "wp_"
USER_AGENT_FALLBACK = "GenericPythonBot/1.0"

# --- Cấu hình cho OpenAI & LLMs ---
DEFAULT_OPENAI_CHAT_MODEL = "openai/gpt-4o-mini" # Model mặc định cho OpenRouter
DEFAULT_OPENAI_CHAT_MODEL_FOR_OUTLINE = "openai/gpt-4.1" # Model cho outline qua OpenRouter
DEFAULT_OPENAI_CHAT_MODEL_FOR_CONTENT = "openai/gpt-4.1" # Model cho viết content qua OpenRouter
DEFAULT_OPENAI_CHAT_MODEL_FOR_FINALIZING = "openai/gpt-4.1" # Model cho hoàn thiện nội dung
DEFAULT_OPENAI_EMBEDDINGS_MODEL = "text-embedding-3-small"
DEFAULT_GEMINI_MODEL = "gemini-pro" # Nếu bạn vẫn dùng Gemini cho một số tác vụ
OPENROUTER_API_KEY = None # Sẽ được override bởi .env
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# --- Cấu hình cho tìm kiếm ---
GOOGLE_CX_ID = "YOUR_SINGLE_CX_ID_FROM_ENV" # Sẽ được load từ .env
GOOGLE_SEARCH_NUM_RESULTS = 10 # Số kết quả lấy từ Google Search cho phân tích intent
SERPER_API_KEY = None # Sẽ được override bởi .env
SERPER_BASE_URL = "https://google.serper.dev"
SEARCH_PROVIDER = "serper" # Giá trị có thể là "google" hoặc "serper"
IMAGE_SEARCH_MIN_WIDTH = 800 # Kích thước chiều rộng tối thiểu cho ảnh từ Serper
IMAGE_SEARCH_MIN_HEIGHT = 600 # Kích thước chiều cao tối thiểu cho ảnh từ Serper
YOUTUBE_SEARCH_NUM_RESULTS = 5

# --- Cấu hình logic nghiệp vụ ---
VIDEO_INSERTION_PROBABILITY = 0.3 # Xác suất chèn video (0.0 đến 1.0)
EXTERNAL_LINKS_PER_SECTION_MIN = 2
EXTERNAL_LINKS_PER_SECTION_MAX = 4
PINECONE_SIMILARITY_THRESHOLD = 0.8 # Ngưỡng để coi keyword là không unique

# --- Cấu hình Google Sheets ---
GSHEET_SPREADSHEET_ID_PLACEHOLDER = "1YdItQM7Acf_H3OvrkVMVOqqjcLiSUniw5Yuei_1Z_Gs"
GSHEET_KEYWORD_SHEET_NAME = "Keyword" # Tên sheet chứa keyword
GSHEET_KEYWORD_SHEET_NAME_USED_0 = "Keyword Used = 0" # Tên sheet đã filter
GSHEET_KEYWORD_COLUMN = "Keyword"
GSHEET_USED_COLUMN = "Used"
GSHEET_UNIQUE_COLUMN = "Uniqe" # Chú ý lỗi chính tả "Uniqe" trong file n8n
GSHEET_SUITABLE_COLUMN = "Suitable"
GSHEET_POST_TITLE_COLUMN = "Post Title"
GSHEET_POST_ID_COLUMN = "Post ID"
GSHEET_POST_URL_COLUMN = "Post URL"

# --- Cấu hình Pinecone ---
PINECONE_INDEX_NAME_PLACEHOLDER = "fretterverse"
PINECONE_EMBEDDING_DIMENSION = 256 # Sau khi cắt từ OpenAI embeddings

# --- Cấu hình đường dẫn file (nếu có) ---
LOG_FILE_PATH = "app.log" # Đường dẫn file log

# --- Các hằng số khác ---
USER_AGENT = "FretterVersePythonBot/1.0 (+http://yourwebsite.com/bot-info)" # User agent cho HTTP requests