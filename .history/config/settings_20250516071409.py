# config/settings.py

# --- Cấu hình chung cho ứng dụng ---
APP_NAME = "FretterVerse Python Project"
DEBUG_MODE = True  # Chuyển thành False khi deploy

# --- Cấu hình cho WordPress ---
WP_BASE_URL_PLACEHOLDER = "YOUR_WORDPRESS_BASE_URL" # Sẽ được override bởi .env
DEFAULT_POST_STATUS = "publish" # Hoặc 'draft', 'pending'
DEFAULT_AUTHOR_ID = 1 # ID của tác giả mặc định nếu không tìm thấy
DEFAULT_CATEGORY_ID = 86 # ID category "Uncategorized" hoặc một category mặc định khác
IMAGE_RESIZE_WIDTH = 700
IMAGE_RESIZE_HEIGHT = 700 # Để trống nếu muốn giữ tỷ lệ theo width
FEATURED_IMAGE_RESIZE_WIDTH = 800
FEATURED_IMAGE_MODEL = "dall-e-3"
FEATURED_IMAGE_SIZE = "1792x1024" # Kích thước DALL-E 3 hỗ trợ

# --- Cấu hình cho OpenAI & LLMs ---
DEFAULT_OPENAI_CHAT_MODEL = "gpt-4o-mini" # Hoặc "gpt-4o", "gpt-3.5-turbo"
DEFAULT_OPENAI_CHAT_MODEL_FOR_OUTLINE = "gpt-4o-mini" # Hoặc "gpt-4o", "gpt-3.5-turbo"
DEFAULT_OPENAI_EMBEDDINGS_MODEL = "text-embedding-3-small"
DEFAULT_GEMINI_MODEL = "gemini-pro" # Nếu bạn vẫn dùng Gemini cho một số tác vụ

# --- Cấu hình cho tìm kiếm ---
GOOGLE_SEARCH_NUM_RESULTS = 10 # Số kết quả lấy từ Google Search cho phân tích intent
YOUTUBE_SEARCH_NUM_RESULTS = 5

# --- Cấu hình logic nghiệp vụ ---
VIDEO_INSERTION_PROBABILITY = 0.3 # Xác suất chèn video (0.0 đến 1.0)
EXTERNAL_LINKS_PER_SECTION_MIN = 2
EXTERNAL_LINKS_PER_SECTION_MAX = 4
PINECONE_SIMILARITY_THRESHOLD = 0.8 # Ngưỡng để coi keyword là không unique

# --- Cấu hình Redis Keys ---
# Để dễ quản lý và tránh trùng lặp key
REDIS_KEY_IMAGE_ARRAY_PREFIX = "fvp_image_array_" # fvp: fretterverse python
REDIS_KEY_VIDEO_ARRAY_PREFIX = "fvp_video_array_"
REDIS_KEY_EXLINKS_ARRAY_PREFIX = "fvp_exlinks_array_"
REDIS_KEY_FAILED_IMAGE_URLS_PREFIX = "fvp_failed_image_urls_"
REDIS_KEY_USED_IMAGE_URLS_PREFIX = "fvp_used_image_urls_" # Để kiểm tra trùng ảnh trong image_processor

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

# --- Cấu hình Author Personas (có thể chuyển vào file JSON riêng nếu quá dài) ---
# Tuy nhiên, trong n8n bạn đã hardcode vào prompt, nên ở đây cũng có thể làm tương tự
# hoặc load từ một file JSON/YAML nếu muốn linh hoạt hơn.
# Ví dụ (để ngắn gọn):
AUTHOR_PERSONAS = [
    {
      "name": "Robert Williams",
      "info": "Teja Gerken, born in Germany in 1970...",
      "ID": "9"
    },
    {
      "name": "Michael Brown",
      "info": "Adam Perlmutter, a distinguished figure...",
      "ID": "10"
    },
    {
      "name": "David Garcia",
      "info": "Teja Gerken, born in Germany in 1970...",
      "ID": "11"
    },
    {
      "name": "Richard Miller",
      "info": "Adam Perlmutter, a distinguished figure...",
      "ID": "12"
    },    
    {
      "name": "Charles Davis",
      "info": "Teja Gerken, born in Germany in 1970...",
      "ID": "13"
    }  
]

# Bạn có thể thêm các cấu hình khác tùy theo nhu cầu