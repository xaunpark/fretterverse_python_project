# test_main_orchestration.py
import logging
import random
import re
import time
import json
from unittest import mock

from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from workflows.main_logic import orchestrate_article_creation # Hàm chính cần test

# --- Mock Classes for Handlers ---
class MockGoogleSheetsHandler:
    def __init__(self, config=None): self.config = config; logger.info("MockGoogleSheetsHandler Initialized")
    def is_connected(self): return True
    def update_sheet_row_by_matching_column(self, *args, **kwargs): logger.info(f"MOCK GSHEET: update_sheet_row_by_matching_column called with {args}, {kwargs}"); return True
    # Thêm các mock phương thức khác nếu orchestrate_article_creation gọi chúng trực tiếp

class MockPineconeHandler:
    def __init__(self, config=None): self.config = config; logger.info("MockPineconeHandler Initialized")
    def is_connected(self): return True
    def query_vectors(self, *args, **kwargs): logger.info(f"MOCK PINECONE: query_vectors called"); return mock.Mock(matches=[mock.Mock(score=0.7)]) # Giả sử unique
    def upsert_vectors(self, *args, **kwargs): logger.info(f"MOCK PINECONE: upsert_vectors called"); return mock.Mock(upserted_count=1)
    # Thêm các mock phương thức khác

class MockMySQLHandler:
    def __init__(self, config=None): self.config = config; logger.info("MockMySQLHandler Initialized")
    def is_connected(self): return True # Giả định connect() được gọi bên trong nếu cần
    def connect(self): return True
    def disconnect(self): pass
    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False, is_transaction=False):
        logger.info(f"MOCK MYSQL: execute_query: {query[:50]}... with params {params}")
        if "SELECT meta_id FROM wp_postmeta WHERE post_id = %s AND meta_key = 'ilj_linkdefinition'" in query:
            return None # Giả sử chưa có ILJ, sẽ trigger INSERT
        return 1 # Giả sử 1 row affected
    # Thêm các mock phương thức khác

# --- Cấu hình Test ---
try:
    APP_CONFIG = load_app_config()
    APP_CONFIG['DEBUG_MODE'] = True
    # Ghi đè các config có thể ảnh hưởng đến thời gian chạy hoặc chi phí
    APP_CONFIG['VIDEO_INSERTION_PROBABILITY'] = 0.0 # Không tìm video cho test này
    APP_CONFIG['EXTERNAL_LINKS_PER_SECTION_MAX'] = 1
    APP_CONFIG['DEFAULT_CHAPTER_LENGTH'] = 50 # Độ dài ngắn cho content
    APP_CONFIG['DEFAULT_SUBCHAPTER_LENGTH'] = 30
    # Đảm bảo các API keys có giá trị giả để các hàm con không báo lỗi thiếu key
    for key_to_check in ['OPENAI_API_KEY', 'GOOGLE_API_KEY', 'YOUTUBE_API_KEY', 
                         'GOOGLE_CX_ID_FOR_SERP_ANALYSIS', 'GOOGLE_CX_ID_EXTERNAL_LINKS',
                         'GOOGLE_IMAGES_CX_ID', 'PINECONE_API_KEY', 'PINECONE_ENVIRONMENT',
                         'PINECONE_INDEX_NAME', 'WP_USER', 'WP_PASSWORD', 'WP_BASE_URL',
                         'GSHEET_SPREADSHEET_ID']:
        if key_to_check not in APP_CONFIG or not APP_CONFIG[key_to_check]:
            APP_CONFIG[key_to_check] = f"FAKE_{key_to_check}_VALUE"


    log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
    setup_logging(log_level_str=log_level, log_to_file=False)
    logger = logging.getLogger(__name__)
except Exception as e:
    print(f"Critical error during test setup: {e}")
    exit()

# --- Dữ liệu Keyword Mẫu ---
TEST_KEYWORD = "best affordable acoustic guitars"
TEST_RUN_ID = f"main_orch_test_{int(time.time())}"

# --- Mock API Client Functions (Simplified for Orchestration Test) ---
# Mục tiêu là test luồng, không phải chi tiết của từng API call ở đây
# Chúng ta sẽ mock các hàm cấp cao hơn hoặc các hàm con trong main_logic nếu cần

def mock_call_openai_chat_general(*args, **kwargs):
    prompt_messages = args[0] if args else kwargs.get('prompt_messages', [])
    is_json = kwargs.get('is_json_output', False)
    prompt_content = prompt_messages[0]['content'].lower() if prompt_messages else ""
    logger.debug(f"MOCK OpenAI General: Called. JSON: {is_json}. Prompt: {prompt_content[:100]}...")

    if "analyze the list of 10 google search results" in prompt_content: # SERP Analysis
        return {"searchIntent": "Commercial Investigation", "contentFormat": "Listicle", "articleType": "Type 1: Best Product List", "selectedModel": "AIDA", "semanticKeyword": ["budget acoustic", "beginner guitar", "top acoustic guitars"]}
    if "identify the most suitable author" in prompt_content: # Choose Author
        return {"name": "Test Author", "info": "Expert in test guitars.", "ID": "99"}
    if "evaluate whether the keyword" in prompt_content: # Check Suitability
        return {"suitable": "yes"}
    if "create a structured article outline" in prompt_content: # Initial Outline
        return {"title": f"The Ultimate Guide to {TEST_KEYWORD}", "slug": TEST_KEYWORD.replace(" ", "-"), "description": "A great guide.", "chapters": [{"chapterName": "Intro", "modelRole": "Attention", "separatedSemanticKeyword": ["intro"], "length": 50, "subchapters": []}, {"chapterName": "Top Picks", "modelRole": "Interest", "separatedSemanticKeyword": ["picks"], "length": 100, "subchapters": [{"subchapterName": "Guitar A", "modelRole": "Desire", "separatedSemanticKeyword": ["guitar a"], "length": 70, "headline": "Best for Budget"}]}, {"chapterName": "Conclusion", "modelRole": "Action", "separatedSemanticKeyword": ["conclusion"], "length": 50, "subchapters": []}]}
    if "enrich the outline" in prompt_content: # Enrich Outline
        # Trả về outline đã được enrich (giả lập)
        # Lấy initial_outline_json_string từ prompt
        initial_outline_str_match = re.search(r"initial article outline:\s*(\{.*\})", prompt_messages[0]['content'], re.DOTALL | re.IGNORECASE)
        if initial_outline_str_match:
            initial_outline = json.loads(initial_outline_str_match.group(1))
            for ch in initial_outline.get("chapters", []):
                ch["authorInfo"] = "Test author info for chapter."
                ch["sectionHook"] = "Test hook for chapter."
                for sub_ch in ch.get("subchapters", []):
                    sub_ch["authorInfo"] = "Test author info for sub."
                    sub_ch["sectionHook"] = "Test hook for sub."
            return initial_outline
        return {} # Lỗi
    if "generate content strictly in html format" in prompt_content: # Write Content
        return f"<p>This is test HTML content for section based on: {prompt_content[:50]}...</p>"
    if "adheres to the faq schema" in prompt_content: # FAQ Content
        return "<div itemscope itemtype=\"https://schema.org/FAQPage\"><div itemscope itemprop=\"mainEntity\" itemtype=\"https://schema.org/Question\"><h3 itemprop=\"name\">Q?</h3><div itemscope itemprop=\"acceptedAnswer\" itemtype=\"https://schema.org/Answer\"><div itemprop=\"text\">A.</div></div></div></div>"
    if "generate an html formatted comparison table" in prompt_content: # Comparison Table
        return "<table><tr><td>Test Table</td></tr></table>"
    if "dall-e 3. the image should creatively embody" in prompt_content: # DALL-E Prompt
        return "A stunning featured image prompt about guitars."
    if "generate a list of related and contextually relevant keywords" in prompt_content: # ILJ Keywords
        return ["test ilj keyword 1", "test ilj keyword 2"]
    if "recommend the most appropriate and specific category" in prompt_content: # Recommend Category
        return {"recommendation": {"category": "Guitars"}, "isNew": "no", "suggestedName": None}
    elif "recommend the most appropriate and specific category" in prompt_content.lower() and is_json:
        logger.info("MOCK OpenAI General: Matched RECOMMEND_CATEGORY_PROMPT")
        # Giả sử LLM đề xuất một category hiện có
        return {
            "recommendation": {"category": "Guitars"}, # Tên category giả
            "isNew": "no",
            "suggestedName": None
        }
    logger.warning(f"MOCK OpenAI General: Unhandled prompt - {prompt_content[:100]}")
    return {} if is_json else "<p>Unhandled mock content.</p>"

def mock_call_openai_dalle(*args, **kwargs):
    logger.debug("MOCK DALL-E: Called")
    return "http://example.com/dalle_featured_image.jpg"

def mock_call_openai_embeddings(*args, **kwargs):
    logger.debug("MOCK Embeddings: Called")
    return [0.1] * APP_CONFIG.get('PINECONE_EMBEDDING_DIMENSION', 256) # Trả về vector đúng kích thước

def mock_google_search_serp(*args, **kwargs):
    logger.debug("MOCK Google SERP Search: Called")
    return [{"title": "SERP Result 1", "snippet": "Snippet 1", "link": "http://example.com/serp1"}]

# Mock các hàm của sub-processors để chúng trả về kết quả nhanh chóng
def mock_process_images(sections_data_list, article_title, config, unique_run_id):
    logger.info(f"MOCK Image Processor: Called for article '{article_title}', run_id '{unique_run_id}'. Processing {len(sections_data_list)} sections.")
    
    mock_results = []
    for section in sections_data_list:
        s_index = section.get('sectionIndex')
        s_name = section.get('sectionName', 'UnknownSection')
        s_name_tag = section.get('sectionNameTag', '').lower()
        s_mother_chapter = section.get('motherChapter', 'no').lower()

        # Giả lập logic skip
        should_skip_mock = any([
            s_name_tag in ["introduction", "conclusion", "faqs"],
            s_mother_chapter == "yes",
            # Thêm các điều kiện skip khác nếu image_processor có logic tương tự
        ])

        if should_skip_mock:
            mock_results.append({"url": "skipped_by_mock_rules", "index": s_index, "alt_text": s_name})
        else:
            # Giả lập một URL ảnh thành công
            # Slugify section name để tạo tên file giả
            slugified_name = "".join(c if c.isalnum() else '-' for c in s_name.lower()).strip('-')
            mock_results.append({
                "url": f"https://mock-wp.com/uploads/{slugified_name}-{s_index}.jpg", 
                "index": s_index, 
                "alt_text": f"Mock image for {s_name}"
            })
            
    logger.info("MOCK Image Processor: Finished and returning dummy image data.")
    return mock_results

def mock_process_videos(sections_data_list, article_title, config, unique_run_id):
    logger.info(f"MOCK Video Processor: Called for article '{article_title}', run_id '{unique_run_id}'. Processing {len(sections_data_list)} sections.")
    
    mock_results = []
    # Lấy xác suất từ config để mock cho giống thật hơn một chút
    video_insertion_probability = config.get('VIDEO_INSERTION_PROBABILITY', 0.3) 

    for section in sections_data_list:
        s_index = section.get('sectionIndex')
        s_name = section.get('sectionName', 'UnknownSection')
        s_name_tag = section.get('sectionNameTag', '').lower()
        s_mother_chapter = section.get('motherChapter', 'no').lower()
        s_section_idx_val = section.get('sectionIndex')

        # Giả lập logic skip từ _should_skip_video
        should_skip_mock = any([
            s_name_tag in ["introduction", "conclusion", "faqs"],
            s_mother_chapter == "yes",
            "top rated" in s_name,
            (isinstance(s_section_idx_val, int) and s_section_idx_val == 2) # Giả sử skip index 2
        ])

        if should_skip_mock:
            mock_results.append({"videoID": "none", "index": s_index})
        else:
            # Giả lập quyết định chèn video dựa trên xác suất
            if random.random() <= video_insertion_probability:
                 # Giả lập một videoID thành công
                mock_results.append({
                    "videoID": f"mock_vid_{slugify(s_name)}_{s_index}", # Tạo videoID giả
                    "index": s_index,
                    # "videoTitle": f"Mock Video for {s_name}", # Thêm nếu cần test
                    # "videoDescription": "A great mock video."
                })
            else:
                mock_results.append({"videoID": "none", "index": s_index}) # Skip do xác suất
            
    logger.info("MOCK Video Processor: Finished and returning dummy video data.")
    return mock_results

def slugify(text):
    if not text: return "default"
    text = text.lower()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^a-z0-9-]', '', text)
    return text.strip('-') if text.strip('-') else "section"

def mock_process_external_links(sections_with_content_list, article_title_main, config, unique_run_id):
    logger.info(f"MOCK External Links Processor: Called for article '{article_title_main}', run_id '{unique_run_id}'. Processing {len(sections_with_content_list)} sections.")
    
    # Tạo một bản copy của danh sách section để không thay đổi list gốc một cách không mong muốn
    updated_sections = []
    for section in sections_with_content_list:
        section_copy = dict(section) # Tạo bản copy của từng section dict
        original_content = section_copy.get('current_html_content', '') # Lấy key đúng
        
        # Giả lập việc thêm link
        # Chỉ thêm link vào các section không bị skip theo logic của external_links_processor
        # (logic skip này nằm trong hàm thật, mock này có thể không cần tái tạo hoàn toàn)
        s_name = section_copy.get("sectionName", "").lower()
        s_name_tag = section_copy.get("sectionNameTag", "").lower()
        s_mother_chapter = section_copy.get("motherChapter", "no").lower()
        s_index = section_copy.get("sectionIndex")

        should_skip_mock = any([
            s_name_tag in ["introduction", "conclusion", "faqs"],
            s_mother_chapter == "yes",
            "top rated" in s_name,
            # (thêm điều kiện section_index == 2 nếu bạn có logic đó trong _should_skip_external_links)
        ])

        if not should_skip_mock and original_content:
            if "george beauchamp" in original_content.lower():
                 section_copy['current_html_content'] = original_content.replace(
                    "George Beauchamp", 
                    '<a href="http://mock.com/beauchamp">George Beauchamp</a>'
                )
            elif "digital modeling" in original_content.lower():
                section_copy['current_html_content'] = original_content.replace(
                    "digital modeling technology", 
                    '<a href="http://mock.com/digital-modeling">digital modeling technology</a>'
                )
            else:
                # Không thêm link nếu không khớp từ khóa cụ thể
                section_copy['current_html_content'] = original_content + "<!-- Mock: No specific ext link added -->"
        else:
            section_copy['current_html_content'] = original_content # Giữ nguyên nếu skip

        updated_sections.append(section_copy)
        
    logger.info("MOCK External Links Processor: Finished and returning modified content.")
    return updated_sections

# Mock các hàm upload và tạo post WordPress
def mock_upload_wp_media_main(*args, **kwargs): # Đặt tên khác để không xung đột với mock trong image_processor test
    filename = args[4] if len(args) > 4 else "unknown_file"
    logger.info(f"MOCK WP Upload Media (Main): Called for {filename}")
    return {"id": int(time.time()), "source_url": f"http://wp.example.com/uploads/{filename}"}

def mock_create_wp_post_main(*args, **kwargs):
    title = kwargs.get('title', 'Mock Post Title')
    logger.info(f"MOCK WP Create Post (Main): Called for title '{title}'")
    return {"id": int(time.time() + 1000), "link": f"http://wp.example.com/{title.lower().replace(' ','-')}"}

def mock_update_wp_post_main(*args, **kwargs):
    post_id = args[3] if len(args) > 3 else "unknown_post_id"
    data = args[4] if len(args) > 4 else {}
    logger.info(f"MOCK WP Update Post (Main): Called for post_id {post_id} with data {data}")
    return {"id": post_id, "featured_media": data.get("featured_media")}

def mock_create_wp_category_main(*args, **kwargs):
    name = kwargs.get('name', 'Mock Category')
    logger.info(f"MOCK WP Create Category (Main): Called for '{name}'")
    return {"id": int(time.time()+2000), "name": name}

def mock_get_wp_categories(base_url, auth_user, auth_pass, params=None):
    logger.debug(f"MOCK get_wp_categories called. Base URL: {base_url}")
    return [
        {"id": 10, "name": "Guitars", "parent": 0},
        {"id": 11, "name": "Acoustic Guitars", "parent": 10}, # Category này sẽ được chọn
        {"id": 86, "name": "Uncategorized", "parent": 0},
    ]

# --- Chạy Test ---
@mock.patch('workflows.main_logic.call_openai_chat', side_effect=mock_call_openai_chat_general)
@mock.patch('workflows.main_logic.call_openai_dalle', side_effect=mock_call_openai_dalle)
@mock.patch('workflows.main_logic.call_openai_embeddings', side_effect=mock_call_openai_embeddings)
@mock.patch('workflows.main_logic.google_search', side_effect=mock_google_search_serp)
@mock.patch('workflows.main_logic.image_processor.process_images_for_article', side_effect=mock_process_images)
@mock.patch('workflows.main_logic.video_processor.process_videos_for_article', side_effect=mock_process_videos)
@mock.patch('workflows.main_logic.external_links_processor.process_external_links_for_article', side_effect=mock_process_external_links)
@mock.patch('utils.api_clients.upload_wp_media', side_effect=mock_upload_wp_media_main) # Mock hàm trong api_clients
@mock.patch('utils.api_clients.create_wp_post', side_effect=mock_create_wp_post_main)
@mock.patch('utils.api_clients.update_wp_post', side_effect=mock_update_wp_post_main)
@mock.patch('utils.api_clients.create_wp_category', side_effect=mock_create_wp_category_main)
@mock.patch('utils.api_clients.get_wp_categories', side_effect=mock_get_wp_categories)
def run_orchestration_test(
    mock_get_wp_cat, mock_create_wp_cat, mock_update_wp_post, mock_create_wp_post, mock_upload_media,
    mock_ext_links_proc, mock_video_proc, mock_image_proc, 
    mock_gs_serp, mock_oai_emb, mock_oai_dalle, mock_oai_chat
    ): # Các tham số mock được inject bởi decorator
    logger.info(f"--- Starting Main Orchestration Test for Keyword: '{TEST_KEYWORD}', Run ID: {TEST_RUN_ID} ---")

    # Khởi tạo mock handlers
    mock_gsheet_h = MockGoogleSheetsHandler(config=APP_CONFIG)
    mock_pinecone_h = MockPineconeHandler(config=APP_CONFIG)
    mock_db_h = MockMySQLHandler(config=APP_CONFIG)

    result = orchestrate_article_creation(
        keyword_to_process=TEST_KEYWORD,
        config=APP_CONFIG,
        gsheet_handler_instance=mock_gsheet_h,
        pinecone_handler_instance=mock_pinecone_h,
        db_handler_instance=mock_db_h,
        unique_run_id_override=TEST_RUN_ID
    )

    logger.info("--- Main Orchestration Test Finished ---")
    logger.info(f"Orchestration Result: {json.dumps(result, indent=2)}")

    assert result is not None, "Orchestration result should not be None"
    assert result.get("status") == "success", f"Orchestration failed: {result.get('reason')}"
    assert result.get("keyword") == TEST_KEYWORD
    assert result.get("post_id") is not None
    assert result.get("post_url") is not None

    logger.info("All main orchestration assertions passed!")

if __name__ == "__main__":
    run_orchestration_test()
    logger.info("--- Test Script Completed ---")