import logging
import os
import shutil # Để xóa thư mục test nếu cần
import time
from unittest import mock

import requests # Thư viện mock rất quan trọng

# Import các module cần thiết từ dự án của bạn
from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from workflows.image_processor import process_images_for_article # Import hàm cần test
from workflows.main_logic import RunContext # Import RunContext

# --- Cấu hình ban đầu cho Test ---
# Load config và thiết lập logging
# Giả sử file này chạy từ thư mục gốc của dự án
try:
    APP_CONFIG = load_app_config()
    # Ghi đè một số config cho testing nếu cần
    APP_CONFIG['DEBUG_MODE'] = True
    APP_CONFIG['MAX_IMAGE_SELECTION_ATTEMPTS'] = 2 # Giảm số lần thử cho test nhanh
    APP_CONFIG['GOOGLE_SEARCH_NUM_RESULTS_IMAGES'] = 3 # Lấy ít ảnh hơn (đã có trong settings.py, có thể không cần ghi đè)
    # Thêm GOOGLE_IMAGES_CX_ID vào APP_CONFIG nếu chưa có từ .env hoặc settings.py
    if 'GOOGLE_IMAGES_CX_ID' not in APP_CONFIG or not APP_CONFIG['GOOGLE_IMAGES_CX_ID']:
        APP_CONFIG['GOOGLE_IMAGES_CX_ID'] = "YOUR_TEST_CX_ID_HERE_OR_MOCK_IT" # Quan trọng

    log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
    setup_logging(log_level_str=log_level, log_to_file=False) # Log ra console cho dễ theo dõi
    logger = logging.getLogger(__name__)
except ValueError as e:
    print(f"Error loading configuration: {e}. Ensure .env and settings.py are correct.")
    exit()
except Exception as e:
    print(f"An unexpected error occurred during setup: {e}")
    exit()


# --- Dữ liệu mẫu cho Test ---
SAMPLE_ARTICLE_TITLE = "Exploring Unique Guitar Tones"
UNIQUE_RUN_ID_TEST = f"test_image_run_{int(time.time())}" # ID duy nhất cho mỗi lần chạy test

SAMPLE_SECTIONS_DATA = [
    {"sectionName": "Introduction", "sectionType": "chapter", "sectionNameTag": "Introduction", "motherChapter": "no", "sectionIndex": 1, "originalIndex": 0},
    {"sectionName": "The Magic of Spruce Tops", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 2, "originalIndex": 1},
    {"sectionName": "Mahogany's Warmth", "sectionType": "subchapter", "parentChapterName": "The Magic of Spruce Tops", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 3, "originalIndex": 2},
    {"sectionName": "Advanced Techniques", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "yes", "sectionIndex": 4, "originalIndex": 3}, # Sẽ bị skip (motherChapter)
    {"sectionName": "FAQs", "sectionType": "chapter", "sectionNameTag": "FAQs", "motherChapter": "no", "sectionIndex": 5, "originalIndex": 4},
    {"sectionName": "Another Content Section", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 6, "originalIndex": 5}
]

# --- Mocking Functions ---
# Đây là phần quan trọng nhất để test không phụ thuộc API thật

# Mock cho call_openai_chat
def mock_openai_chat_responses(prompt_messages_list, model_name_arg, api_key_arg, 
                               is_json_output=False, # Thêm default cho is_json_output
                               *args, **kwargs): # Bắt các args/kwargs còn lại nếu có
    
    if not prompt_messages_list or not isinstance(prompt_messages_list[0], dict):
        logger.error(f"Mock OpenAI Chat called with unexpected prompt_messages format: {prompt_messages_list}")
        return {} if is_json_output else None # Sử dụng is_json_output ở đây
        
    prompt_content = prompt_messages_list[0].get('content', '').lower()
    
    # Sử dụng is_json_output được truyền vào, không phải kwargs.get('is_json_output') nữa
    logger.debug(f"Mock OpenAI Chat called. Model: {model_name_arg}, API_Key_Used: {'******' if api_key_arg else 'None'}, JSON output: {is_json_output}. Prompt starts with: {prompt_content[:150]}")

    if "identify the central theme" in prompt_content and "recommend for a relevant image search" in prompt_content:
        # Đây là lúc is_json_output=False (mặc định)
        logger.info("Mock OpenAI: Matched prompt for generating image search keyword.")
        if "spruce tops" in prompt_content:
            return "acoustic guitar spruce top"
        elif "mahogany's warmth" in prompt_content:
            return "mahogany guitar body"
        elif "another content section" in prompt_content:
            return "cool guitar photo" 
        return "generic guitar image" 
    
    elif "which image best visually represents" in prompt_content and is_json_output: # Kiểm tra is_json_output ở đây
        logger.info("Mock OpenAI: Matched prompt for choosing best image URL.")
        options_str_from_prompt = prompt_messages_list[0].get('content', '')
        
        if "http://example.com/spruce.jpg" in options_str_from_prompt:
            return {"imageURL": "http://example.com/spruce.jpg", "imageDes": "A beautiful spruce top guitar"}
        if "http://example.com/mahogany.jpg" in options_str_from_prompt:
            return {"imageURL": "http://example.com/mahogany.jpg", "imageDes": "Warm mahogany guitar"}
        if "http://example.com/cool_guitar.jpg" in options_str_from_prompt:
            return {"imageURL": "http://example.com/cool_guitar.jpg", "imageDes": "A very cool guitar"}
        if "http://example.com/generic1.jpg" in options_str_from_prompt:
            return {"imageURL": "http://example.com/generic1.jpg", "imageDes": "A generic guitar"}
            
        logger.warning("Mock OpenAI: No specific image URL matched in CHOOSE_BEST_IMAGE_URL_PROMPT options.")
        return {"imageURL": None, "imageDes": "AI could not select an image from mock options"}
    
    logger.warning(f"Unhandled mock OpenAI chat prompt. Prompt content (first 150 chars): {prompt_content[:150]}")
    return {} if is_json_output else None

# Mock cho google_search (image type)
def mock_google_image_search(*args, **kwargs):
    query = kwargs.get('query', '').lower()
    logger.debug(f"Mock Google Image Search called for query: {query}")
    if "spruce" in query:
        return [
            {'link': 'http://example.com/spruce.jpg', 'snippet': 'Spruce Guitar Image 1', 'title': 'Spruce Guitar 1'},
            {'link': 'http://example.com/spruce_琴.jpg', 'snippet': 'Spruce Guitar Image 2 with non-ascii', 'title': 'Spruce Guitar 2 琴'}
        ]
    elif "mahogany" in query:
        return [
            {'link': 'http://example.com/mahogany.jpg', 'snippet': 'Mahogany Guitar Image', 'title': 'Mahogany Guitar'}
        ]
    elif "generic" in query:
         return [
            {'link': 'http://example.com/generic1.jpg', 'snippet': 'Generic Guitar 1', 'title': 'Generic Guitar 1'},
            {'link': 'http://example.com/generic2.jpg', 'snippet': 'Generic Guitar 2', 'title': 'Generic Guitar 2'}
        ]
    return []

# Mock cho requests.get (để tải ảnh)
mock_image_content_jpg = b"dummy jpg image data" # Nội dung file ảnh giả
mock_image_content_png = b"dummy png image data"
class MockResponse:
    def __init__(self, content, status_code, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {'content-type': 'image/jpeg'}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"Mock HTTP Error {self.status_code}")

def mock_requests_get(url, timeout, stream, **kwargs):
    logger.debug(f"Mock requests.get called for URL: {url}")
    if "spruce.jpg" in url or "mahogany.jpg" in url or "generic1.jpg" in url :
        return MockResponse(mock_image_content_jpg, 200)
    elif "琴.jpg" in url: # Test URL có ký tự đặc biệt
        return MockResponse(mock_image_content_jpg, 200)
    elif "fail_download.jpg" in url: # URL giả để test lỗi download
        raise requests.exceptions.ConnectionError("Mock connection error")
    elif "not_an_image.txt" in url:
        return MockResponse(b"this is text", 200, {'content-type': 'text/plain'})
    return MockResponse(b"not found", 404)


# Mock cho resize_image
def mock_resize_image(image_path_or_binary, **kwargs):
    output_format = kwargs.get('output_format', 'JPEG').lower()
    logger.debug(f"Mock resize_image called. Input type: {type(image_path_or_binary)}. Output format: {output_format}")
    if output_format == 'jpeg' or output_format == 'jpg':
        return mock_image_content_jpg # Trả về binary giả đã resize
    return mock_image_content_png


# Mock cho upload_wp_media
def mock_upload_wp_media(base_url, auth_user, auth_pass, file_binary, filename, mime_type):
    logger.debug(f"Mock upload_wp_media called. Filename: {filename}, MimeType: {mime_type}, Binary length: {len(file_binary)}")
    if "fail_upload" in filename: # File giả để test lỗi upload
        return None 
    return {
        'source_url': f"{base_url}/wp-content/uploads/test/{filename}", # URL giả trên WordPress
        'id': int(time.time() * 1000) # ID media giả
    }


# --- Chạy Test ---
def run_test():
    logger.info(f"--- Starting Image Processing Test for run_id: {UNIQUE_RUN_ID_TEST} ---")
    test_run_context = RunContext(unique_run_id=UNIQUE_RUN_ID_TEST)
    
    # Áp dụng mocks
    # Sử dụng `with mock.patch(...)` để mock các hàm bên ngoài
    # Patch vào đúng vị trí mà hàm được import và gọi (target)
    with mock.patch('workflows.image_processor.call_openai_chat', side_effect=mock_openai_chat_responses), \
         mock.patch('workflows.image_processor.google_search', side_effect=mock_google_image_search), \
         mock.patch('workflows.image_processor.perform_search', side_effect=mock_google_image_search), \
         mock.patch('workflows.image_processor.requests.get', side_effect=mock_requests_get), \
         mock.patch('workflows.image_processor.resize_image', side_effect=mock_resize_image), \
         mock.patch('workflows.image_processor.upload_wp_media', side_effect=mock_upload_wp_media):
        
        final_image_results = process_images_for_article(
            sections_data_list=SAMPLE_SECTIONS_DATA,
            article_title=SAMPLE_ARTICLE_TITLE,
            run_context=test_run_context, # Truyền RunContext
            config=APP_CONFIG
        )

    logger.info("--- Image Processing Test Finished ---")
    logger.info(f"Final Image Results ({len(final_image_results)} items):")
    for result in final_image_results:
        logger.info(f"  Index {result.get('index')}: URL='{result.get('url')}', Alt='{result.get('alt_text', 'N/A')}'")

    # Kiểm tra một vài kết quả mong đợi (Asserts cơ bản)
    # Đây là ví dụ, bạn nên có các asserts chi tiết hơn
    assert len(final_image_results) == len(SAMPLE_SECTIONS_DATA)
    
    intro_result = next((r for r in final_image_results if r.get('index') == 1), None)
    assert intro_result and intro_result.get('url') == "skipped_section_type"
    logger.info("Assertion for Introduction passed.")

    spruce_result = next((r for r in final_image_results if r.get('index') == 2), None)
    assert spruce_result and "test/the-magic-of-spruce-tops-2.jpeg" in spruce_result.get('url', '')
    logger.info("Assertion for Spruce Tops section passed.")
    
    mother_chapter_result = next((r for r in final_image_results if r.get('index') == 4), None)
    assert mother_chapter_result and mother_chapter_result.get('url') == "skipped_section_type"
    logger.info("Assertion for Mother Chapter skip passed.")

    logger.info("Basic assertions passed!")

if __name__ == "__main__":
    run_test()