# test_main_logic.py (hoặc tests/test_main_logic.py)
import logging
import unittest
from unittest import mock
import time
import json

# Import các module cần thiết
from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from workflows.main_logic import orchestrate_article_creation # Hàm chính cần test

# --- Cấu hình ban đầu cho Test ---
try:
    APP_CONFIG = load_app_config()
    APP_CONFIG['DEBUG_MODE'] = True
    APP_CONFIG['REDIS_DB'] = APP_CONFIG.get('REDIS_TEST_DB', 15)
    # Giả lập các API key nếu chưa có trong .env để tránh lỗi config
    APP_CONFIG.setdefault('OPENAI_API_KEY', "fake_openai_key_for_test")
    APP_CONFIG.setdefault('GOOGLE_API_KEY', "fake_google_key_for_test")
    APP_CONFIG.setdefault('YOUTUBE_API_KEY', "fake_youtube_key_for_test")
    APP_CONFIG.setdefault('GOOGLE_CX_ID_FOR_SERP_ANALYSIS', "fake_cx_serp")
    APP_CONFIG.setdefault('GOOGLE_CX_ID_EXTERNAL_LINKS', "fake_cx_extlinks")
    APP_CONFIG.setdefault('GOOGLE_IMAGES_CX_ID', "fake_cx_images")
    APP_CONFIG.setdefault('PINECONE_API_KEY', "fake_pinecone_key")
    APP_CONFIG.setdefault('PINECONE_ENVIRONMENT', "fake_pinecone_env")
    APP_CONFIG.setdefault('PINECONE_INDEX_NAME', "fake-pinecone-index")
    APP_CONFIG.setdefault('WP_USER', "fake_wp_user")
    APP_CONFIG.setdefault('WP_PASSWORD', "fake_wp_pass")
    APP_CONFIG.setdefault('WP_BASE_URL', "https://fake-wp.com")
    APP_CONFIG.setdefault('GSHEET_SPREADSHEET_ID', "fake_gsheet_id")
    APP_CONFIG.setdefault('MYSQL_HOST', "fakemysql")


    log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
    setup_logging(log_level_str=log_level, log_to_file=False)
    logger = logging.getLogger(__name__)
except ValueError as e:
    print(f"Error loading configuration for test_main_logic: {e}.")
    exit()

# --- Dữ liệu mẫu ---
TEST_KEYWORD = "best affordable electric guitar"
TEST_RUN_ID_BASE = "test_affordable_guitar"

# --- Mock Data ---
# Bước 1 Mocks
mock_chosen_author = {"name": "Test Author", "info": "Expert in testing.", "ID": "99"}
mock_serp_data_string = "Title: Guitar Review 1\nSnippet: Great guitar\nURL: http://example.com/1\n---"
mock_keyword_analysis = {
    "searchIntent": "Commercial Investigation",
    "contentFormat": "Review",
    "articleType": "Type 1: Best Product List", # Hoặc "Type 2: Informational" để test nhánh khác
    "selectedModel": "AIDA",
    "semanticKeyword": ["budget guitar", "beginner electric guitar", "value guitar"]
}

# Bước 2 Mocks
mock_initial_outline = {
    "title": "Test Title: Best Affordable Electric Guitars",
    "slug": "test-best-affordable-electric-guitars",
    "description": "Test SEO description for affordable guitars.",
    "chapters": [
        {"chapterName": "Introduction", "modelRole": "Attention", "separatedSemanticKeyword": ["intro"], "length": 100, "subchapters": []},
        {"chapterName": "Top Picks", "modelRole": "Interest", "separatedSemanticKeyword": ["picks"], "length": 100, 
         "subchapters": [
             {"subchapterName": "Guitar A", "modelRole": "Desire", "separatedSemanticKeyword": ["guitar a"], "length": 150, "headline": "Best for Budget"},
             {"subchapterName": "Guitar B", "modelRole": "Desire", "separatedSemanticKeyword": ["guitar b"], "length": 150, "headline": "Best for Versatility"}
         ]},
        {"chapterName": "Conclusion", "modelRole": "Action", "separatedSemanticKeyword": ["conclusion"], "length": 100, "subchapters": []}
    ]
}
# enriched_outline sẽ thêm authorInfo và sectionHook vào mock_initial_outline
mock_enriched_outline = json.loads(json.dumps(mock_initial_outline)) # Deep copy
for ch in mock_enriched_outline["chapters"]:
    ch["authorInfo"] = "Test author info for " + ch["chapterName"]
    ch["sectionHook"] = "Test hook for " + ch["chapterName"]
    if "subchapters" in ch and ch["subchapters"]:
        for sub_ch in ch["subchapters"]:
            sub_ch["authorInfo"] = "Test author info for " + sub_ch["subchapterName"]
            sub_ch["sectionHook"] = "Test hook for " + sub_ch["subchapterName"]

mock_processed_sections = [ # Dữ liệu sau khi `process_sections_from_outline`
    {"sectionName": "Introduction", "sectionType": "chapter", "sectionIndex": 1, "html_content": "", "sectionNameTag": "Introduction", "motherChapter": "no", "original_keyword": TEST_KEYWORD, "article_title": mock_enriched_outline["title"], "article_slug": mock_enriched_outline["slug"], "article_description": mock_enriched_outline["description"], "authorInfo": "...", "sectionHook":"...", "separatedSemanticKeyword": [], "modelRole": "Attention", "length": 100},
    {"sectionName": "Top Picks", "sectionType": "chapter", "sectionIndex": 2, "html_content": "", "sectionNameTag": "Top Rated", "motherChapter": "yes", "authorInfo": "...", "sectionHook":"...", "separatedSemanticKeyword": [], "modelRole": "Interest", "length": 100},
    {"sectionName": "Guitar A", "sectionType": "subchapter", "sectionIndex": 3, "html_content": "", "sectionNameTag": "Product", "motherChapter": "no", "parentChapterName": "Top Picks", "headline": "Best for Budget", "authorInfo": "...", "sectionHook":"...", "separatedSemanticKeyword": [], "modelRole": "Desire", "length": 150},
    {"sectionName": "Guitar B", "sectionType": "subchapter", "sectionIndex": 4, "html_content": "", "sectionNameTag": "Product", "motherChapter": "no", "parentChapterName": "Top Picks", "headline": "Best for Versatility", "authorInfo": "...", "sectionHook":"...", "separatedSemanticKeyword": [], "modelRole": "Desire", "length": 150},
    {"sectionName": "Conclusion", "sectionType": "chapter", "sectionIndex": 5, "html_content": "", "sectionNameTag": "Conclusion", "motherChapter": "no", "authorInfo": "...", "sectionHook":"...", "separatedSemanticKeyword": [], "modelRole": "Action", "length": 100}
]


# Bước 3 Mocks
mock_sections_with_content = []
for sec in mock_processed_sections:
    new_sec = dict(sec)
    if sec.get("sectionName") == "Top Picks": # Container chapter
        new_sec["html_content"] = "<!-- Container Chapter - No Content Needed -->"
    else:
        new_sec["html_content"] = f"<p>Content for {sec.get('sectionName')}. Hook: {sec.get('sectionHook')}</p>"
    mock_sections_with_content.append(new_sec)


# Bước 4 Mocks
mock_sections_after_ext_links = []
for sec in mock_sections_with_content:
    new_sec = dict(sec)
    if "Content for" in new_sec["html_content"]: # Chỉ thêm link vào section có content thật
        new_sec["html_content"] = new_sec["html_content"].replace("Content for", '<a href="http://mocklink.com">Linked Content</a> for')
    mock_sections_after_ext_links.append(new_sec)

mock_final_image_data = [
    {"url": "skipped_section_type", "index": 1, "alt_text": "Introduction"},
    {"url": "wp_url_for_top_picks_img.jpg", "index": 2, "alt_text": "Top Picks"}, # Giả sử mother chapter cũng có ảnh (logic image_processor sẽ quyết định)
    {"url": "wp_url_for_guitar_a_img.jpg", "index": 3, "alt_text": "Guitar A"},
    {"url": "wp_url_for_guitar_b_img.jpg", "index": 4, "alt_text": "Guitar B"},
    {"url": "skipped_section_type", "index": 5, "alt_text": "Conclusion"}
]
mock_final_video_data = [
    {"videoID": "none", "index": 1},
    {"videoID": "vid_top_picks", "index": 2},
    {"videoID": "vid_guitar_a", "index": 3},
    {"videoID": "none", "index": 4}, # Guitar B không có video
    {"videoID": "none", "index": 5}
]
mock_sub_workflow_results = {
    "sections_final_content_structure": mock_sections_after_ext_links, # HTML đã có ext links
    "final_image_data_list": mock_final_image_data,
    "final_video_data_list": mock_final_video_data
}

# Bước 5 Mocks
mock_comparison_table_html = "<table><tr><td>Mock Comparison Table</td></tr></table>"
mock_full_html_output = "<html><body><h1>Test Title</h1>...</body></html>" # HTML hoàn chỉnh

# Bước 6 Mocks
mock_dalle_prompt_desc = "A stunning featured image for guitars."
mock_dalle_image_url = "http://dalle.example.com/featured.png"
mock_resized_featured_binary = b"resized_featured_image_data"
mock_wp_featured_media_response = {"id": 12345, "source_url": "http://fake-wp.com/uploads/featured.jpg"}
mock_category_id = 10
mock_created_wp_post_response = {"id": 987, "link": "http://fake-wp.com/test-post-url"}
mock_ilj_keywords_list = ["affordable guitar", "electric guitar for sale"]
mock_php_serialized_ilj = 'a:2:{i:0;s:17:"affordable guitar";i:1;s:24:"electric guitar for sale";}'


class TestMainLogic(unittest.TestCase):

    # Mock các handlers để chúng không thực hiện kết nối thật
    @mock.patch('workflows.main_logic.GoogleSheetsHandler')
    @mock.patch('workflows.main_logic.PineconeHandler')
    @mock.patch('workflows.main_logic.MySQLHandler') # Giả sử bạn đã import MySQLHandler
    # Mock các hàm con của chính main_logic.py
    @mock.patch('workflows.main_logic.analyze_and_prepare_keyword')
    @mock.patch('workflows.main_logic.create_article_outline_step')
    @mock.patch('workflows.main_logic.write_content_for_all_sections_step')
    @mock.patch('workflows.main_logic.process_sub_workflows_step')
    @mock.patch('workflows.main_logic.assemble_full_html_step')
    @mock.patch('workflows.main_logic.finalize_and_publish_article_step')
    def test_orchestrate_article_creation_success_flow(
        self, 
        mock_finalize_publish, mock_assemble_html, mock_process_subs, 
        mock_write_content, mock_create_outline, mock_analyze_keyword,
        MockMySQLHandler, MockPineconeHandler, MockGSheetHandler
        ):
        logger.info("Starting test_orchestrate_article_creation_success_flow")

        # Thiết lập giá trị trả về cho các mock handler
        mock_gsheet_instance = MockGSheetHandler.return_value
        mock_gsheet_instance.is_connected.return_value = True
        
        mock_pinecone_instance = MockPineconeHandler.return_value
        mock_pinecone_instance.is_connected.return_value = True
        
        mock_mysql_instance = MockMySQLHandler.return_value
        mock_mysql_instance.connect.return_value = True # Giả sử connect trả về True/False
        mock_mysql_instance.connection.is_connected.return_value = True # Để check sau khi connect
        mock_mysql_instance.disconnect.return_value = True


        # Thiết lập giá trị trả về cho các hàm con của main_logic
        mock_analyze_keyword.return_value = {
            "original_keyword": TEST_KEYWORD,
            "is_suitable": True,
            "is_unique": True,
            "chosen_author": mock_chosen_author,
            "serp_data_string": mock_serp_data_string,
            "keyword_analysis": mock_keyword_analysis
        }
        mock_create_outline.return_value = {
            "initial_outline_raw": mock_initial_outline,
            "enriched_outline_raw": mock_enriched_outline,
            "processed_sections_list": mock_processed_sections,
            "article_meta": {
                "title": mock_enriched_outline["title"],
                "slug": mock_enriched_outline["slug"],
                "description": mock_enriched_outline["description"],
                "article_type": mock_keyword_analysis["articleType"],
                "chosen_author_id": mock_chosen_author["ID"],
                "original_keyword": TEST_KEYWORD
            }
        }
        mock_write_content.return_value = mock_sections_with_content
        mock_process_subs.return_value = mock_sub_workflow_results
        mock_assemble_html.return_value = mock_full_html_output
        mock_finalize_publish.return_value = {"post_id": 987, "post_url": "http://fake-wp.com/test-post-url", "status": "published"}

        # Gọi hàm chính cần test
        result = orchestrate_article_creation(TEST_KEYWORD, APP_CONFIG, TEST_RUN_ID_BASE)

        # Assertions
        self.assertIsNotNone(result)
        self.assertEqual(result.get("status"), "published")
        self.assertEqual(result.get("post_id"), 987)

        # Kiểm tra xem các hàm con có được gọi không
        mock_analyze_keyword.assert_called_once()
        mock_create_outline.assert_called_once()
        mock_write_content.assert_called_once()
        mock_process_subs.assert_called_once()
        mock_assemble_html.assert_called_once()
        mock_finalize_publish.assert_called_once()
        
        # Kiểm tra các handler có được khởi tạo và kết nối
        MockGSheetHandler.assert_called_once_with(config=APP_CONFIG)
        mock_gsheet_instance.is_connected.assert_called_once()
        
        MockPineconeHandler.assert_called_once_with(config=APP_CONFIG)
        mock_pinecone_instance.is_connected.assert_called_once()

        MockMySQLHandler.assert_called_once_with(config=APP_CONFIG)
        mock_mysql_instance.connect.assert_called_once()
        mock_mysql_instance.disconnect.assert_called_once() # Kiểm tra disconnect được gọi

        logger.info("test_orchestrate_article_creation_success_flow PASSED")

    @mock.patch('workflows.main_logic.GoogleSheetsHandler')
    @mock.patch('workflows.main_logic.PineconeHandler')
    @mock.patch('workflows.main_logic.MySQLHandler')
    @mock.patch('workflows.main_logic.analyze_and_prepare_keyword')
    def test_orchestrate_keyword_not_suitable_or_unique(
        self, mock_analyze_keyword,
        MockMySQLHandler, MockPineconeHandler, MockGSheetHandler
    ):
        logger.info("Starting test_orchestrate_keyword_not_suitable_or_unique")
        mock_gsheet_instance = MockGSheetHandler.return_value
        mock_gsheet_instance.is_connected.return_value = True
        mock_pinecone_instance = MockPineconeHandler.return_value
        mock_pinecone_instance.is_connected.return_value = True
        mock_mysql_instance = MockMySQLHandler.return_value
        mock_mysql_instance.connect.return_value = True
        mock_mysql_instance.connection.is_connected.return_value = True


        # Giả lập analyze_and_prepare_keyword trả về None (do không suitable/unique)
        mock_analyze_keyword.return_value = None

        result = orchestrate_article_creation(TEST_KEYWORD, APP_CONFIG, TEST_RUN_ID_BASE)
        
        self.assertIsNone(result) # Mong đợi hàm chính trả về None
        mock_analyze_keyword.assert_called_once()
        # Các bước sau không được gọi
        # mock_create_outline.assert_not_called() # Cần import create_article_outline_step vào mock_calls
        logger.info("test_orchestrate_keyword_not_suitable_or_unique PASSED")


if __name__ == '__main__':
    unittest.main()