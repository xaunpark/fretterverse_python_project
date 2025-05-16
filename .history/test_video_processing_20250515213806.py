import logging
import time
import json # Để kiểm tra Redis value nếu cần
from unittest import mock

# Import các module cần thiết từ dự án của bạn
from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from workflows.video_processor import process_videos_for_article, _get_redis_video_array_key
from utils.redis_handler import RedisHandler # Để dọn dẹp Redis sau test

# --- Cấu hình ban đầu cho Test ---
try:
    APP_CONFIG = load_app_config()
    APP_CONFIG['DEBUG_MODE'] = True
    APP_CONFIG['VIDEO_INSERTION_PROBABILITY'] = 1.0  # Luôn thử tìm video khi test
    APP_CONFIG['YOUTUBE_SEARCH_NUM_RESULTS'] = 3     # Lấy ít kết quả hơn cho test
    APP_CONFIG['REDIS_DB'] = APP_CONFIG.get('REDIS_TEST_DB', 15) # Dùng DB Redis riêng cho test
    # Đảm bảo các API keys có giá trị (dù là giả) để không bị lỗi thiếu config
    APP_CONFIG['OPENAI_API_KEY'] = APP_CONFIG.get('OPENAI_API_KEY', "fake_openai_key")
    APP_CONFIG['YOUTUBE_API_KEY'] = APP_CONFIG.get('YOUTUBE_API_KEY', "fake_youtube_key")


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
SAMPLE_ARTICLE_TITLE_VID = "Mastering Guitar Scales"
UNIQUE_RUN_ID_VID_TEST = f"test_video_run_{int(time.time())}"

SAMPLE_SECTIONS_DATA_VID = [
    {"sectionName": "Introduction", "sectionType": "chapter", "sectionNameTag": "Introduction", "motherChapter": "no", "sectionIndex": 1, "originalIndex": 0},
    {"sectionName": "Pentatonic Scales", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 2, "originalIndex": 1}, # Sẽ bị skip nếu logic _should_skip_video có sectionIndex=2
    {"sectionName": "Blues Scale Variations", "sectionType": "subchapter", "parentChapterName": "Pentatonic Scales", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 3, "originalIndex": 2},
    {"sectionName": "Modes Explained", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "yes", "sectionIndex": 4, "originalIndex": 3}, # Sẽ bị skip
    {"sectionName": "Top Rated Guitars for Scales", "sectionType": "chapter", "sectionNameTag": "Top Rated", "motherChapter": "no", "sectionIndex": 5, "originalIndex": 4}, # Sẽ bị skip
    {"sectionName": "Practicing Effectively", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 6, "originalIndex": 5} # Section này nên có video
]

# --- Mocking Functions ---

MOCK_VIDEO_DB = {
    "pentatonic scales practice": [
        {'id': {'kind': 'youtube#video', 'videoId': 'vid_penta_1'}, 'snippet': {'title': 'Easy Pentatonic Licks', 'description': 'Learn pentatonic scales easily.'}},
        {'id': {'kind': 'youtube#video', 'videoId': 'vid_penta_2'}, 'snippet': {'title': 'Advanced Pentatonics', 'description': 'Go beyond basics.'}}
    ],
    "blues scale guitar lesson": [
        {'id': {'kind': 'youtube#video', 'videoId': 'vid_blues_1'}, 'snippet': {'title': 'Master the Blues Scale', 'description': 'Essential blues licks.'}}
    ],
    "effective guitar practice routines": [
        {'id': {'kind': 'youtube#video', 'videoId': 'vid_practice_1'}, 'snippet': {'title': 'Best Guitar Practice Routine', 'description': 'How to practice smart.'}},
        {'id': {'kind': 'youtube#video', 'videoId': 'vid_practice_empty_desc'}, 'snippet': {'title': 'Daily Practice Tips', 'description': ''}} # Test mô tả rỗng
    ]
}

def mock_openai_for_video(*args, **kwargs):
    # Hàm mock này nhận *args vì call_openai_chat có thể được gọi với tham số vị trí
    prompt_messages_list = args[0] if args else kwargs.get('prompt_messages', [])
    is_json = kwargs.get('is_json_output', False)

    if not prompt_messages_list or not isinstance(prompt_messages_list[0], dict):
        logger.error(f"Mock OpenAI (Video) called with unexpected prompt_messages: {prompt_messages_list}")
        return {} if is_json else None

    prompt_content = prompt_messages_list[0].get('content', '').lower()
    logger.debug(f"Mock OpenAI (Video) called. JSON: {is_json}. Prompt starts with: {prompt_content[:150]}")

    if "recommend for a relevant video search" in prompt_content:
        logger.info("Mock OpenAI (Video): Matched prompt for generating video search keyword.")
        if "pentatonic scales" in prompt_content: return "pentatonic scales practice"
        if "blues scale variations" in prompt_content: return "blues scale guitar lesson"
        if "practicing effectively" in prompt_content: return "effective guitar practice routines"
        return "generic guitar video keyword"

    elif "which video best represents" in prompt_content and is_json:
        logger.info("Mock OpenAI (Video): Matched prompt for choosing best video ID.")
        # Giả lập chọn video đầu tiên từ options
        options_str = prompt_messages_list[0].get('content', '')
        if "vid_penta_1" in options_str:
            return {"videoID": "vid_penta_1", "videoTitle": "Easy Pentatonic Licks", "videoDescription": "Learn pentatonic scales easily."}
        if "vid_blues_1" in options_str:
            return {"videoID": "vid_blues_1", "videoTitle": "Master the Blues Scale", "videoDescription": "Essential blues licks."}
        if "vid_practice_1" in options_str:
             return {"videoID": "vid_practice_1", "videoTitle": "Best Guitar Practice Routine", "videoDescription": "How to practice smart."}
        
        logger.warning("Mock OpenAI (Video): No specific video ID matched in CHOOSE_BEST_VIDEO_ID options. Returning first plausible or None.")
        # Fallback: thử tìm một videoID bất kỳ trong options
        import re
        match = re.search(r"videoID: (\w+)", options_str)
        if match:
            vid_id = match.group(1)
            title_match = re.search(rf"Video Title: (.*?), Video Description: .*?, videoID: {vid_id}", options_str, re.IGNORECASE)
            desc_match = re.search(rf"Video Description: (.*?), videoID: {vid_id}", options_str, re.IGNORECASE)
            title = title_match.group(1) if title_match else "Mocked Title"
            description = desc_match.group(1) if desc_match else "Mocked Description"
            return {"videoID": vid_id, "videoTitle": title, "videoDescription": description}
            
        return {"videoID": None, "videoTitle": "AI_NoVideoSelected", "videoDescription": "AI could not select a video from mock options."}
    
    logger.warning(f"Unhandled mock OpenAI (Video) prompt: {prompt_content[:150]}")
    return {} if is_json else None

def mock_youtube_search(*args, **kwargs):
    query = kwargs.get('query', '').lower()
    logger.debug(f"Mock YouTube Search called for query: {query}")
    return MOCK_VIDEO_DB.get(query, [])


# --- Hàm dọn dẹp Redis ---
def cleanup_redis_for_video_test(config, run_id):
    try:
        redis_h = RedisHandler(config=config)
        if redis_h.is_connected():
            video_array_key = _get_redis_video_array_key(config, run_id)
            redis_h.delete_key(video_array_key)
            logger.info(f"Cleaned up Redis key for video run_id: {run_id}")
    except Exception as e:
        logger.error(f"Error during Redis cleanup for video test: {e}")

# --- Chạy Test ---
def run_video_test():
    logger.info(f"--- Starting Video Processing Test for run_id: {UNIQUE_RUN_ID_VID_TEST} ---")
    
    with mock.patch('workflows.video_processor.call_openai_chat', side_effect=mock_openai_for_video), \
         mock.patch('workflows.video_processor.youtube_search', side_effect=mock_youtube_search):
        
        final_video_results = process_videos_for_article(
            sections_data_list=SAMPLE_SECTIONS_DATA_VID,
            article_title=SAMPLE_ARTICLE_TITLE_VID,
            config=APP_CONFIG,
            unique_run_id=UNIQUE_RUN_ID_VID_TEST
        )

    logger.info("--- Video Processing Test Finished ---")
    logger.info(f"Final Video Results ({len(final_video_results)} items):")
    for result in final_video_results:
        logger.info(f"  Index {result.get('index')}: VideoID='{result.get('videoID')}'")

    # Assertions
    assert len(final_video_results) == len(SAMPLE_SECTIONS_DATA_VID)

    # Kiểm tra các section bị skip
    intro_vid = next((r for r in final_video_results if r.get('index') == 1), {})
    assert intro_vid.get('videoID') == "none", f"Intro videoID was: {intro_vid.get('videoID')}"
    logger.info("Assertion for Introduction (skip) passed.")

    # Section "Pentatonic Scales" (index 2) - Kiểm tra logic skip sectionIndex=2
    # Logic skip sectionIndex=2 cần được thêm vào _should_skip_video nếu đó là yêu cầu
    # Hiện tại, _should_skip_video của bạn có thể chưa có điều kiện này một cách rõ ràng.
    # Giả sử nó không bị skip bởi index=2, nhưng có thể bị skip do xác suất (nếu PROBABILITY < 1.0)
    # Vì PROBABILITY = 1.0, nó sẽ được xử lý.
    penta_vid = next((r for r in final_video_results if r.get('index') == 2), {})
    # Nếu logic skip sectionIndex=2 được thêm vào _should_skip_video:
    # assert penta_vid.get('videoID') == "none", f"Pentatonic (index 2) videoID was: {penta_vid.get('videoID')}"
    # Nếu không, nó nên có videoID:
    assert penta_vid.get('videoID') == "vid_penta_1", f"Pentatonic videoID was: {penta_vid.get('videoID')}"
    logger.info("Assertion for Pentatonic Scales passed.")


    blues_vid = next((r for r in final_video_results if r.get('index') == 3), {})
    assert blues_vid.get('videoID') == "vid_blues_1", f"Blues Scale videoID was: {blues_vid.get('videoID')}"
    logger.info("Assertion for Blues Scale Variations passed.")

    modes_vid = next((r for r in final_video_results if r.get('index') == 4), {}) # motherChapter=yes
    assert modes_vid.get('videoID') == "none", f"Modes Explained videoID was: {modes_vid.get('videoID')}"
    logger.info("Assertion for Modes Explained (motherChapter skip) passed.")
    
    top_rated_vid = next((r for r in final_video_results if r.get('index') == 5), {}) # sectionNameTag="Top Rated"
    assert top_rated_vid.get('videoID') == "none", f"Top Rated videoID was: {top_rated_vid.get('videoID')}"
    logger.info("Assertion for Top Rated (skip) passed.")

    practice_vid = next((r for r in final_video_results if r.get('index') == 6), {})
    assert practice_vid.get('videoID') == "vid_practice_1", f"Practicing Effectively videoID was: {practice_vid.get('videoID')}"
    logger.info("Assertion for Practicing Effectively passed.")

    logger.info("All video assertions passed!")

    # Kiểm tra nội dung Redis (tùy chọn, nếu không mock RedisHandler)
    # redis_h_check = RedisHandler(config=APP_CONFIG)
    # if redis_h_check.is_connected():
    #     video_array_key_check = _get_redis_video_array_key(APP_CONFIG, UNIQUE_RUN_ID_VID_TEST)
    #     stored_array = redis_h_check.get_value(video_array_key_check)
    #     logger.info(f"Data in Redis for key '{video_array_key_check}': {stored_array}")
    #     assert isinstance(stored_array, list)
    #     assert len(stored_array) == len(SAMPLE_SECTIONS_DATA_VID)
    #     assert stored_array[2].get("videoID") == "vid_blues_1" # Check một item cụ thể

if __name__ == "__main__":
    try:
        run_video_test()
    finally:
        logger.info("--- Cleaning up Video Test Data ---")
        cleanup_redis_for_video_test(APP_CONFIG, UNIQUE_RUN_ID_VID_TEST)
        logger.info("--- Video Test Cleanup Finished ---")