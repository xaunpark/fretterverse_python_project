import logging
import re
import time
import json
import random
from unittest import mock

# Import các module cần thiết
from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from workflows.external_links_processor import (
    process_external_links_for_article, 
    _get_redis_exlinks_array_key,
    _extract_text_from_html # Test hàm này riêng nếu cần
)
from utils.redis_handler import RedisHandler

# --- Cấu hình ban đầu cho Test ---
try:
    APP_CONFIG = load_app_config()
    APP_CONFIG['DEBUG_MODE'] = True
    APP_CONFIG['EXTERNAL_LINKS_PER_SECTION_MIN'] = 1 # Để test dễ hơn
    APP_CONFIG['EXTERNAL_LINKS_PER_SECTION_MAX'] = 1 # Chỉ tìm 1 link cho mỗi section test
    APP_CONFIG['GOOGLE_SEARCH_NUM_RESULTS_EXT_LINKS'] = 2 # Lấy ít kết quả Google
    APP_CONFIG['REDIS_DB'] = APP_CONFIG.get('REDIS_TEST_DB', 15)
    APP_CONFIG['OPENAI_API_KEY'] = APP_CONFIG.get('OPENAI_API_KEY', "fake_openai_key")
    APP_CONFIG['GOOGLE_API_KEY'] = APP_CONFIG.get('GOOGLE_API_KEY', "fake_google_key")
    if 'GOOGLE_CX_ID_EXTERNAL_LINKS' not in APP_CONFIG or not APP_CONFIG['GOOGLE_CX_ID_EXTERNAL_LINKS']:
        APP_CONFIG['GOOGLE_CX_ID_EXTERNAL_LINKS'] = "YOUR_TEST_CX_ID_FOR_EXT_LINKS"

    log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
    setup_logging(log_level_str=log_level, log_to_file=False)
    logger = logging.getLogger(__name__)
except ValueError as e:
    print(f"Error loading configuration: {e}. Ensure .env and settings.py are correct.")
    exit()
except Exception as e:
    print(f"An unexpected error occurred during setup: {e}")
    exit()

# --- Dữ liệu mẫu cho Test ---
SAMPLE_ARTICLE_TITLE_EXT = "The History and Evolution of Electric Guitars"
UNIQUE_RUN_ID_EXT_TEST = f"test_extlink_run_{int(time.time())}"

SAMPLE_SECTIONS_CONTENT_EXT = [
    {
        "sectionName": "Introduction", "sectionType": "chapter", "sectionIndex": 1, 
        "sectionNameTag": "Introduction", "motherChapter": "no",
        "current_html_content": "<p>This is the introduction to electric guitars. It covers early models.</p>",
        "originalIndex": 0
    },
    {
        "sectionName": "Early Innovations", "sectionType": "chapter", "sectionIndex": 2, 
        "sectionNameTag": "", "motherChapter": "no",
        "current_html_content": "<p>The first electric guitar was invented by George Beauchamp in 1931. This was a major breakthrough. Les Paul also made significant contributions later on with solid-body designs.</p><p>The Fender Stratocaster, released in 1954, became an iconic model.</p>",
        "originalIndex": 1
    },
    {
        "sectionName": "Modern Era", "sectionType": "chapter", "sectionIndex": 3,
        "sectionNameTag": "", "motherChapter": "no",
        "current_html_content": "<p>Today, digital modeling technology has changed how guitars are used. Many artists prefer vintage instruments for their unique sound.</p>",
        "originalIndex": 2
    },
    {
        "sectionName": "Conclusion", "sectionType": "chapter", "sectionIndex": 4, 
        "sectionNameTag": "Conclusion", "motherChapter": "no",
        "current_html_content": "<p>Electric guitars continue to evolve.</p>",
        "originalIndex": 3
    }
]

# --- Mocking Functions ---
MOCK_ANCHORS_DB = {
    "early innovations": [{"anchortext": "George Beauchamp in 1931"}, {"anchortext": "Fender Stratocaster"}],
    "modern era": [{"anchortext": "digital modeling technology"}, {"anchortext": "vintage instruments"}]
}

MOCK_CITATION_KEYWORDS_DB = {
    "george beauchamp in 1931": "George Beauchamp electric guitar invention",
    "fender stratocaster": "Fender Stratocaster history",
    "digital modeling technology": "guitar digital modeling amps",
    "vintage instruments": "value of vintage guitars"
}

MOCK_GOOGLE_SEARCH_EXT_LINKS_DB = {
    "george+beauchamp+electric+guitar+invention": [ # Dùng +
        {'link': 'http://example.com/beauchamp-bio', 'title': 'George Beauchamp Biography'},
        {'link': 'http://wikipedia.org/George_Beauchamp', 'title': 'George Beauchamp - Wikipedia'}
    ],
    "fender+stratocaster+history": [ # Dùng +
        {'link': 'http://fender.com/strat-history', 'title': 'Official Strat History - Fender'},
        {'link': 'http://guitarmuseum.org/stratocaster', 'title': 'Stratocaster at Guitar Museum'}
    ],
    "guitar+digital+modeling+amps": [ # Dùng +
        {'link': 'http://techcrunch.com/guitar-modeling', 'title': 'The Rise of Digital Amps - TechCrunch'},
        {'link': 'http://soundonsound.com/reviews/guitar-amp-modeling', 'title': 'Review: Amp Modeling Software - SoundOnSound'}
    ],
    "value+of+vintage+guitars": [ # Dùng +
        {'link': 'http://antiquesroadshow.com/guitars', 'title': 'Vintage Guitars on Antiques Roadshow'},
        {'link': 'http://alreadyusedlink.com/info', 'title': 'Info about vintage guitars'}
    ]
}

MOCK_CHOSEN_URLS_DB = {
    "george beauchamp in 1931": "http://wikipedia.org/George_Beauchamp",
    "fender stratocaster": "http://guitarmuseum.org/stratocaster",
    "digital modeling technology": "http://techcrunch.com/guitar-modeling",
    "vintage instruments": "http://antiquesroadshow.com/guitars", # URL này sẽ được chọn
    "vintage instruments_second_try": "NO_SUITABLE_LINK_FOUND" # Nếu link đầu bị duplicate
}


def mock_openai_for_ext_links(*args, **kwargs):
    prompt_messages_list = args[0]
    prompt_content = prompt_messages_list[0]['content'] # Không cần lower() vì key trong DB đã là lower
    is_json = kwargs.get('is_json_output', False)
    
    logger.debug(f"Mock OpenAI (ExtLink) called. JSON: {is_json}. Prompt starts with: {prompt_content[:150]}")

    if "identify the" in prompt_content.lower() and "key phrases" in prompt_content.lower() and is_json:
        logger.info("Mock OpenAI (ExtLink): Matched IDENTIFY_ANCHOR_TEXTS")
        
        # Trích xuất phần section_content_text từ prompt_content
        # Điều này hơi mong manh vì nó phụ thuộc vào cấu trúc prompt
        actual_text_to_analyze_marker = "here is my text:"
        marker_index = prompt_content.lower().find(actual_text_to_analyze_marker)
        text_to_analyze = ""
        if marker_index != -1:
            text_to_analyze = prompt_content[marker_index + len(actual_text_to_analyze_marker):].strip().lower()
        
        logger.debug(f"Mock IDENTIFY_ANCHOR_TEXTS: Extracted text to analyze (first 100 chars): {text_to_analyze[:100]}")

        for section_name_key_from_db, anchors in MOCK_ANCHORS_DB.items():
            # Kiểm tra xem section_name_key_from_db có liên quan đến text_to_analyze không
            # Cách đơn giản: Nếu section_name_key_from_db có trong tên section đang xử lý
            # (cần truyền section_name vào mock hoặc tìm cách lấy từ prompt_content)
            # Hoặc, nếu mock này chỉ dựa vào nội dung text_to_analyze:
            if section_name_key_from_db == "early innovations" and "george beauchamp" in text_to_analyze:
                logger.info(f"Mock IDENTIFY_ANCHOR_TEXTS: Matched for 'early innovations' based on content.")
                return anchors # anchors là MOCK_ANCHORS_DB["early innovations"]
            if section_name_key_from_db == "modern era" and "digital modeling technology" in text_to_analyze:
                logger.info(f"Mock IDENTIFY_ANCHOR_TEXTS: Matched for 'modern era' based on content.")
                return anchors # anchors là MOCK_ANCHORS_DB["modern era"]

        logger.warning(f"Mock IDENTIFY_ANCHOR_TEXTS: No specific content match for anchors. Prompt content (first 300): {prompt_content[:300]}")
        return []
    
    elif "suggest a highly relevant keyword" in prompt_content.lower(): # generate citation search keyword
        logger.info("Mock OpenAI (ExtLink): Matched GENERATE_CITATION_SEARCH_KEYWORD")
        # Tìm anchor_text trong prompt
        anchor_match = re.search(r"Anchor Text: (.*?)\n", prompt_content, re.IGNORECASE)
        if anchor_match:
            anchor = anchor_match.group(1).strip().lower()
            return MOCK_CITATION_KEYWORDS_DB.get(anchor, "generic search keyword")
        return "generic search keyword"
        
    elif "which of the following urls is the most relevant" in prompt_content.lower(): # choose best exlink
        logger.info("Mock OpenAI (ExtLink): Matched CHOOSE_BEST_EXTERNAL_LINK")
        anchor_match = re.search(r'anchor text "(.*?)"', prompt_content, re.IGNORECASE)
        if anchor_match:
            anchor = anchor_match.group(1).strip().lower()
            # Nếu link đầu tiên (ví dụ, http://alreadyusedlink.com/info) đã được dùng,
            # thì trong lần gọi tiếp theo cho cùng anchor (nếu có retry logic),
            # OpenAI nên trả về "NO_SUITABLE_LINK_FOUND" hoặc link khác.
            # Mock này đơn giản là trả về link đã định nghĩa.
            # Logic retry và kiểm tra duplicate sẽ nằm trong code chính.
            
            # Kiểm tra xem link_options_string có chứa URL đã được "dùng" không
            # Đây là phần phức tạp để mock, vì nó phụ thuộc vào trạng thái của Redis
            # Tạm thời, nếu anchor là "vintage instruments" và link đầu tiên đã bị loại,
            # thì sẽ không tìm thấy link phù hợp
            if anchor == "vintage instruments" and "http://antiquesroadshow.com/guitars" not in prompt_content:
                 return MOCK_CHOSEN_URLS_DB.get(f"{anchor}_second_try", "NO_SUITABLE_LINK_FOUND")
            return MOCK_CHOSEN_URLS_DB.get(anchor, "NO_SUITABLE_LINK_FOUND")
        return "NO_SUITABLE_LINK_FOUND"
        
    logger.warning(f"Unhandled mock OpenAI (ExtLink) prompt type: {prompt_content[:100]}")
    return {} if is_json else None


def mock_google_search_for_ext_links(*args, **kwargs):
    query_from_code = kwargs.get('query', '') # Đây là chuỗi đã quote_plus
    # query_cleaned sẽ là chuỗi đã quote_plus và không có -inurl:
    query_cleaned = query_from_code.split(' -inurl:')[0].strip() 
    logger.debug(f"Mock Google Search (ExtLink) called for query: {query_from_code} (cleaned for DB lookup: {query_cleaned})")
    return MOCK_GOOGLE_SEARCH_EXT_LINKS_DB.get(query_cleaned.lower(), []) # Chuyển cleaned query sang lower để khớp key


# --- Hàm dọn dẹp Redis ---
def cleanup_redis_for_ext_links_test(config, run_id):
    try:
        redis_h = RedisHandler(config=config)
        if redis_h.is_connected():
            exlinks_array_key = _get_redis_exlinks_array_key(config, run_id)
            redis_h.delete_key(exlinks_array_key)
            logger.info(f"Cleaned up Redis key for ext_links run_id: {run_id}")
    except Exception as e:
        logger.error(f"Error during Redis cleanup for ext_links test: {e}")


# --- Chạy Test ---
def run_ext_links_test():
    logger.info(f"--- Starting External Links Processing Test for run_id: {UNIQUE_RUN_ID_EXT_TEST} ---")
    
    # Mock RedisHandler để kiểm soát exlinksArray dễ hơn
    mock_redis_db = {}
    def mock_redis_get_value(key):
        return mock_redis_db.get(key)
    def mock_redis_set_value(key, value, ex=None):
        mock_redis_db[key] = value
        return True
    def mock_redis_init_array(key, default_value="[]"):
        if key not in mock_redis_db:
             # Lưu ý: get_value của RedisHandler tự parse JSON, nên ở đây lưu list Python
            mock_redis_db[key] = json.loads(default_value) 
        return True

    with mock.patch('workflows.external_links_processor.call_openai_chat', side_effect=mock_openai_for_ext_links), \
         mock.patch('workflows.external_links_processor.google_search', side_effect=mock_google_search_for_ext_links), \
         mock.patch.object(RedisHandler, 'get_value', side_effect=mock_redis_get_value), \
         mock.patch.object(RedisHandler, 'set_value', side_effect=mock_redis_set_value), \
         mock.patch.object(RedisHandler, 'initialize_array_if_not_exists', side_effect=mock_redis_init_array):
        
        # Khởi tạo Redis key thủ công cho mock_redis_db
        exlinks_key_for_mock = _get_redis_exlinks_array_key(APP_CONFIG, UNIQUE_RUN_ID_EXT_TEST)
        mock_redis_db[exlinks_key_for_mock] = ["http://alreadyusedlink.com/info"] # Giả lập link này đã có
        
        # Tạo RedisHandler instance (nó sẽ dùng các phương thức đã được mock)
        # redis_handler_instance_for_test = RedisHandler(config=APP_CONFIG)

        updated_sections = process_external_links_for_article(
            sections_with_content_list=SAMPLE_SECTIONS_CONTENT_EXT,
            article_title_main=SAMPLE_ARTICLE_TITLE_EXT,
            config=APP_CONFIG, # Sẽ được dùng để tạo RedisHandler bên trong process_external_links_for_article
            unique_run_id=UNIQUE_RUN_ID_EXT_TEST
        )

    logger.info("--- External Links Processing Test Finished ---")
    
    found_beauchamp_link = False
    found_strat_link = False
    found_modeling_link = False
    found_vintage_link = False # Mong đợi link này được chèn

    for section in updated_sections:
        logger.info(f"Section: {section.get('sectionName')}")
        logger.info(f"Updated Content:\n{section.get('current_html_content')}\n-----------------")
        content = section.get('current_html_content', '')
        if "George Beauchamp" in content and 'href="http://wikipedia.org/George_Beauchamp"' in content:
            found_beauchamp_link = True
        if "Fender Stratocaster" in content and 'href="http://guitarmuseum.org/stratocaster"' in content:
            found_strat_link = True
        if "digital modeling technology" in content and 'href="http://techcrunch.com/guitar-modeling"' in content:
            found_modeling_link = True
        if "vintage instruments" in content and 'href="http://antiquesroadshow.com/guitars"' in content:
            found_vintage_link = True


    assert updated_sections[0].get('current_html_content') == "<p>This is the introduction to electric guitars. It covers early models.</p>", "Introduction should not be modified."
    logger.info("Assertion for Introduction (no links) passed.")
    
    assert found_beauchamp_link, "Link for George Beauchamp not found or incorrect."
    logger.info("Assertion for George Beauchamp link passed.")
    
    assert found_strat_link, "Link for Fender Stratocaster not found or incorrect."
    logger.info("Assertion for Fender Stratocaster link passed.")

    assert found_modeling_link, "Link for digital modeling technology not found or incorrect."
    logger.info("Assertion for digital modeling link passed.")
    
    # Kiểm tra trường hợp link bị duplicate. "vintage instruments" có 2 link tiềm năng, 
    # một là "http://alreadyusedlink.com/info" (đã có trong mock_redis_db)
    # và "http://antiquesroadshow.com/guitars" (nên được chọn và chèn)
    assert found_vintage_link, "Link for vintage instruments (non-duplicate) not found or incorrect."
    logger.info("Assertion for vintage instruments (non-duplicate) link passed.")
    
    # Kiểm tra xem link "http://alreadyusedlink.com/info" không bị chèn lần nữa cho "vintage instruments"
    vintage_section_content = next(s.get('current_html_content') for s in updated_sections if s.get('sectionName') == "Modern Era")
    assert 'href="http://alreadyusedlink.com/info"' not in vintage_section_content or \
           vintage_section_content.count('vintage instruments') == vintage_section_content.count('href="http://antiquesroadshow.com/guitars"'), \
           "Duplicate link 'alreadyusedlink.com' might have been inserted for 'vintage instruments' or non-duplicate link was missed."
    logger.info("Assertion for duplicate link handling for 'vintage instruments' passed.")


    logger.info("All external link assertions passed!")

if __name__ == "__main__":
    # Không cần cleanup Redis nếu RedisHandler được mock hoàn toàn và dùng mock_redis_db
    # Nếu bạn đang test với Redis thật (không mock RedisHandler), thì cần cleanup
    # try:
    run_ext_links_test()
    # finally:
    #     logger.info("--- Cleaning up External Links Test Data (if Redis was not mocked) ---")
    #     cleanup_redis_for_ext_links_test(APP_CONFIG, UNIQUE_RUN_ID_EXT_TEST)
    #     logger.info("--- External Links Test Cleanup Finished ---")