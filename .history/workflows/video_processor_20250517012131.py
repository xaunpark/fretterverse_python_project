# workflows/video_processor.py
import logging
import random
import json # Để parse JSON từ OpenAI nếu cần (mặc dù prompt yêu cầu JSON object)
from utils.api_clients import call_openai_chat, youtube_search
from utils.redis_handler import RedisHandler
from prompts import video_prompts
# from utils.config_loader import APP_CONFIG # Import config của bạn

logger = logging.getLogger(__name__)

# --- Constants (có thể lấy từ APP_CONFIG) ---
# VIDEO_SEARCH_RESULTS_COUNT = 5 # Số video lấy từ YouTube để chọn

def _get_redis_video_array_key(config, unique_run_id):
    """Helper to generate Redis key for the video array for this run."""
    return f"{config.get('REDIS_KEY_VIDEO_ARRAY_PREFIX', 'fvp_video_array_')}{unique_run_id}"

def _should_skip_video(section_data):
    """
    Kiểm tra xem có nên bỏ qua việc chèn video cho section này không.
    Dựa trên logic của IF3 node trong fretterverse-v9_video.
    """
    section_name = section_data.get('sectionName', '').lower()
    section_name_tag = section_data.get('sectionNameTag', '').lower()
    mother_chapter = section_data.get('motherChapter', 'no').lower()
    section_index = section_data.get('sectionIndex') # Đây là số thứ tự của section trong toàn bài

    # Các điều kiện skip từ IF3 node (có thể cần điều chỉnh cho chính xác)
    # "Introduction", "FAQs", "Conclusion"
    # "sectionIndex" == 2 (Node IF3 có điều kiện number, nhưng có vẻ bạn dùng string "2" trong n8n)
    # "sectionName" contains "top rated"
    # "sectionNameTag" là "Introduction", "Conclusion", "FAQs"
    # "motherChapter" == "yes"

    skip_conditions = [
        section_name == "introduction",
        section_name == "faqs",
        section_name == "conclusion",
        section_name_tag == "introduction",
        section_name_tag == "conclusion",
        section_name_tag == "faqs",
        mother_chapter == "yes",
        "top rated" in section_name, # Kiểm tra sectionName có chứa "top rated"
        # section_index == 2 # Cẩn thận kiểu dữ liệu khi so sánh
    ]
    # Trong n8n, IF3 có vẻ có điều kiện sectionIndex (number) = 2 và sectionIndex (string) = "2"
    # Nếu sectionIndex là số:
    if isinstance(section_index, int) and section_index == 2:
         skip_conditions.append(True)
    # Nếu sectionIndex là string (ít có khả năng từ code tạo section_data):
    # elif isinstance(section_index, str) and section_index == "2":
    #      skip_conditions.append(True)


    if any(skip_conditions):
        logger.info(f"Skipping video for section '{section_data.get('sectionName')}' due to skip conditions.")
        return True
    return False

def _parse_youtube_search_results(youtube_items_list):
    """Chuyển đổi kết quả từ YouTube Search API thành list các dict mong muốn."""
    if not youtube_items_list:
        return []
    videos_data = []
    for item in youtube_items_list:
        if item.get('id', {}).get('kind') == 'youtube#video': # Chỉ lấy video, không lấy channel/playlist
            video_id = item.get('id', {}).get('videoId')
            snippet = item.get('snippet', {})
            title = snippet.get('title', 'N/A')
            description = snippet.get('description', 'No description available')
            if video_id:
                videos_data.append({
                    'videoID': video_id,
                    'videoTitle': title,
                    'videoDescription': description
                })
    return videos_data


def process_single_section_video(section_data, article_title, parent_chapter_name_for_subchapter,
                                 redis_handler, config, openai_api_key, youtube_api_key,
                                 unique_run_id):
    """
    Xử lý tìm và chọn video cho MỘT section.
    Trả về một dict chứa videoID (hoặc None), videoTitle, videoDescription và sectionIndex.
    """
    video_insertion_probability = config.get('VIDEO_INSERTION_PROBABILITY', 0.3)
    video_search_count = config.get('YOUTUBE_SEARCH_NUM_RESULTS', 5)
    
    # Thông tin mặc định nếu không tìm thấy video hoặc bị skip
    video_result_for_section = {
        "videoID": None, # Sẽ là "none" string như trong n8n nếu không chèn
        "videoTitle": "No video processed",
        "videoDescription": "Video processing skipped or no suitable video found.",
        "index": section_data.get('sectionIndex') # Giữ lại index để sắp xếp
    }

    if _should_skip_video(section_data):
        video_result_for_section["videoID"] = "none" # Theo logic n8n
        video_result_for_section["videoTitle"] = "Video skipped for this section type"
        video_result_for_section["videoDescription"] = "Section type does not require a video."
        return video_result_for_section

    # Quyết định có chèn video không (dựa trên xác suất)
    if random.random() > video_insertion_probability:
        logger.info(f"Video insertion skipped for section '{section_data.get('sectionName')}' due to probability ({video_insertion_probability*100}%).")
        video_result_for_section["videoID"] = "none"
        video_result_for_section["videoTitle"] = "Video skipped by probability"
        video_result_for_section["videoDescription"] = f"Random chance ({100-video_insertion_probability*100}%) determined no video here."
        return video_result_for_section

    logger.info(f"Attempting to find video for section: {section_data.get('sectionName')}")

    # --- BƯỚC 1: Tạo từ khóa tìm video ---
    # (prompt này không phân biệt rõ chapter/subchapter trong n8n, dùng section_name chung)
    prompt_vid_keyword = video_prompts.GENERATE_VIDEO_SEARCH_KEYWORD_PROMPT.format(
        section_name=section_data.get('sectionName'),
        article_title=article_title
    )
    video_keyword = call_openai_chat(
        [{"role": "user", "content": prompt_vid_keyword}],
        config.get('DEFAULT_OPENAI_CHAT_MODEL'),
        openai_api_key,
        # Thêm các tham số mới cho OpenRouter
        openrouter_base_url=config.get('OPENROUTER_API_BASE_URL'),
        user_agent=config.get('USER_AGENT')
    )
    if not video_keyword:
        logger.error(f"Failed to generate video keyword for section: {section_data.get('sectionName')}")
        video_result_for_section["videoID"] = "none"
        video_result_for_section["videoTitle"] = "Error generating video keyword"
        return video_result_for_section
    
    logger.info(f"Generated video keyword: '{video_keyword}' for section '{section_data.get('sectionName')}'")

    # --- BƯỚC 2: Tìm kiếm video trên YouTube ---
    youtube_items = youtube_search(
        query=video_keyword,
        api_key=youtube_api_key,
        num_results=video_search_count
    )
    video_options_list = _parse_youtube_search_results(youtube_items)

    if not video_options_list:
        logger.warning(f"No videos found from YouTube Search for keyword: '{video_keyword}'")
        video_result_for_section["videoID"] = "none"
        video_result_for_section["videoTitle"] = "No videos found on YouTube"
        return video_result_for_section

    # --- BƯỚC 3: Chọn video tốt nhất (OpenAI) ---
    options_parts = []
    for i, vid_data in enumerate(video_options_list):
        title = vid_data.get('videoTitle', 'N/A')
        desc = vid_data.get('videoDescription', 'N/A')[:150] + "..." # Giới hạn độ dài mô tả
        vid_id = vid_data.get('videoID', 'N/A')
        options_parts.append(f"{i+1}. Video Title: {title}, Video Description: {desc}, videoID: {vid_id}")
    video_options_str = "\n".join(options_parts)
    if not video_options_str: # Double check
            video_options_str = "No video options available from YouTube search."

    # Tạo context cho prompt chọn video
    section_context_str = ""
    s_type = section_data.get('sectionType')
    s_name = section_data.get('sectionName')
    if s_type == 'chapter':
        section_context_str = f", the section \"{s_name}\""
    elif s_type == 'subchapter' and parent_chapter_name_for_subchapter:
        section_context_str = f", and its specific sub-section \"{s_name}\" (of chapter \"{parent_chapter_name_for_subchapter}\")"
    else:
        section_context_str = f", regarding the section/sub-section \"{s_name}\""

    prompt_choose_video = video_prompts.CHOOSE_BEST_VIDEO_ID_PROMPT.format(
        article_title=article_title,
        section_context_string=section_context_str,
        video_options_string=video_options_str
    )
    
    chosen_video_info = call_openai_chat(
        [{"role": "user", "content": prompt_choose_video}],
        config.get('DEFAULT_OPENAI_CHAT_MODEL'),
        openai_api_key,
        openrouter_base_url=config.get('OPENROUTER_API_BASE_URL'),
        user_agent=config.get('USER_AGENT'),
        is_json_output=True # Yêu cầu OpenAI trả về JSON
    )

    if chosen_video_info and chosen_video_info.get('videoID'):
        logger.info(f"AI selected video '{chosen_video_info.get('videoTitle')}' (ID: {chosen_video_info.get('videoID')}) for section '{s_name}'.")
        video_result_for_section["videoID"] = chosen_video_info.get('videoID')
        video_result_for_section["videoTitle"] = chosen_video_info.get('videoTitle')
        video_result_for_section["videoDescription"] = chosen_video_info.get('videoDescription')
    else:
        logger.warning(f"OpenAI did not select a suitable video for section '{s_name}'. Response: {chosen_video_info}")
        video_result_for_section["videoID"] = "none" # Theo logic n8n
        video_result_for_section["videoTitle"] = chosen_video_info.get("videoTitle", "AI could not select a video")
        video_result_for_section["videoDescription"] = chosen_video_info.get("videoDescription", "No suitable video was identified by the AI from the options.")
        
    return video_result_for_section


def process_videos_for_article(sections_data_list, article_title, config, unique_run_id):
    """
    Hàm chính để xử lý video cho tất cả các section trong một bài viết.
    sections_data_list: List các dict, mỗi dict là thông tin của một section.
    unique_run_id: ID duy nhất cho lần chạy xử lý bài viết này.
    """
    logger.info(f"Starting video processing for article: '{article_title}' with run_id: {unique_run_id}")

    openai_api_key = config.get('OPENAI_API_KEY')
    youtube_api_key = config.get('YOUTUBE_API_KEY') # Hoặc GOOGLE_API_KEY nếu dùng chung

    if not all([openai_api_key, youtube_api_key]):
        logger.error("Missing OpenAI or YouTube API key in config for video processing.")
        return [{"videoID": "config_error", "index": s.get('sectionIndex')} for s in sections_data_list]

    redis_handler = RedisHandler(config=config)
    if not redis_handler.is_connected():
        logger.error("Cannot connect to Redis. Aborting video processing.")
        return [{"videoID": "redis_error", "index": s.get('sectionIndex')} for s in sections_data_list]

    video_array_key = _get_redis_video_array_key(config, unique_run_id)
    redis_handler.initialize_array_if_not_exists(video_array_key, "[]") # Khởi tạo mảng rỗng trong Redis

    article_video_results = [] # List để thu thập kết quả video cho từng section
    parent_chapter_name_for_current_subchapters = None

    for section in sections_data_list:
        if section.get('sectionType') == 'chapter':
            parent_chapter_name_for_current_subchapters = section.get('sectionName')
        
        video_data_for_section = process_single_section_video(
            section_data=section,
            article_title=article_title,
            parent_chapter_name_for_subchapter=parent_chapter_name_for_current_subchapters if section.get('sectionType') == 'subchapter' else None,
            redis_handler=redis_handler, # Mặc dù không dùng nhiều trong hàm con này, nhưng có thể cần nếu logic phức tạp hơn
            config=config,
            openai_api_key=openai_api_key,
            youtube_api_key=youtube_api_key,
            unique_run_id=unique_run_id # Có thể không cần unique_run_id trong hàm con nếu không có cache theo section
        )
        article_video_results.append({
            "videoID": video_data_for_section.get("videoID", "none"), # Đảm bảo "none" nếu null
            "index": section.get("sectionIndex") # Giữ lại index để map với section
            # Bạn có thể muốn thêm videoTitle, videoDescription vào đây nếu cần ở main_logic
        })

    # Lưu toàn bộ mảng kết quả video vào Redis một lần
    # Format lưu vào Redis cần giống với n8n (list các videoID hoặc object nếu cần thêm thông tin)
    # Workflow n8n của bạn cuối cùng tạo ra list các object {json: {videoID: ..., index: ...}} từ node "videoArray completed1"
    # Vậy, chúng ta nên lưu một list các dict có videoID và index.
    # Hiện tại article_video_results đã có format đó.
    
    # Logic của node "Parse videoArray from Redis", "add videoID to videoArray", "Set videoArray to Redis"
    # trong n8n khá phức tạp, nó đọc, parse, push, rồi stringify lại.
    # Ở đây, chúng ta build toàn bộ list ở Python rồi set một lần.
    
    # Đảm bảo rằng videoID là "none" nếu nó là None từ process_single_section_video
    final_video_array_for_redis = []
    for res in article_video_results:
        final_video_array_for_redis.append({
            "videoID": res.get("videoID") if res.get("videoID") is not None else "none",
            "index": res.get("index")
            # Bạn có thể thêm các trường khác nếu Full HTML cần, ví dụ title, description của video được chọn
            # "videoTitle": res.get("videoTitle"),
            # "videoDescription": res.get("videoDescription")
        })


    redis_handler.set_value(video_array_key, final_video_array_for_redis) # Lưu list các dict
    
    logger.info(f"Finished video processing for article '{article_title}'. Final video data saved to Redis key '{video_array_key}'.")
    logger.debug(f"Data saved to Redis: {final_video_array_for_redis}")
    
    # Hàm này có thể trả về final_video_array_for_redis để main_logic sử dụng trực tiếp
    # Hoặc main_logic sẽ tự đọc từ Redis key sau khi hàm này chạy xong.
    # Trả về để tiện sử dụng:
    return final_video_array_for_redis


# --- Example Usage (sẽ được gọi từ main_logic.py) ---
# if __name__ == "__main__":
#     # Cần mock APP_CONFIG, RedisHandler, và các hàm API
#     # from utils.config_loader import load_app_config
#     # from utils.logging_config import setup_logging
#     # APP_CONFIG = load_app_config()
#     # setup_logging(log_level_str="DEBUG")

#     # mock_config = { # ... (điền các config cần thiết) ...
#     #     'OPENAI_API_KEY': "test_key_openai",
#     #     'YOUTUBE_API_KEY': "test_key_youtube",
#     #     'REDIS_HOST': 'localhost', 'REDIS_PORT': 6379, 'REDIS_DB': 0,
#     #     'DEFAULT_OPENAI_CHAT_MODEL': 'gpt-3.5-turbo',
#     #     'VIDEO_INSERTION_PROBABILITY': 1.0, # Để luôn thử tìm video khi test
#     #     'YOUTUBE_SEARCH_NUM_RESULTS': 2,
#     #     'REDIS_KEY_VIDEO_ARRAY_PREFIX': 'fvp_video_array_'
#     # }

#     # sample_sections = [
#     #     {"sectionName": "Introduction", "sectionType": "chapter", "sectionNameTag": "Introduction", "motherChapter": "no", "sectionIndex": 1},
#     #     {"sectionName": "Guitar Basics", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 2}, # Sẽ bị skip do index = 2
#     #     {"sectionName": "Playing Chords", "sectionType": "subchapter", "parentChapterName": "Guitar Basics", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 3},
#     #     {"sectionName": "Advanced Soloing", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 4},
#     # ]
#     # article_title_test = "Learn Guitar Fast"
#     # run_id_test = "testvideorun123"

#     # # Cần mock các hàm API calls
#     # import unittest.mock as mock
#     # def mock_openai_for_video(*args, **kwargs):
#     #     prompt_content = args[0][0]['content'].lower() # Lấy prompt_messages
#     #     is_json = kwargs.get('is_json_output', False)
#     #     if "recommend for a relevant video search" in prompt_content:
#     #         if "chords" in prompt_content: return "how to play guitar chords"
#     #         return "guitar solo lesson"
#     #     elif "which video best represents" in prompt_content and is_json:
#     #         if "vid_chords_1" in prompt_content: # Giả sử vid_chords_1 là ID của video được chọn
#     #             return {"videoID": "vid_chords_1", "videoTitle": "Easy Guitar Chords", "videoDescription": "Learn basic chords."}
#     #         return {"videoID": "vid_solo_1", "videoTitle": "Amazing Guitar Solo", "videoDescription": "Watch this solo."}
#     #     return None

#     # def mock_yt_search(*args, **kwargs):
#     #     query = kwargs.get('query', '').lower()
#     #     if "chords" in query:
#     #         return [{'id': {'kind': 'youtube#video', 'videoId': 'vid_chords_1'}, 'snippet': {'title': 'Easy Guitar Chords', 'description': 'Desc1'}},
#     #                 {'id': {'kind': 'youtube#video', 'videoId': 'vid_chords_2'}, 'snippet': {'title': 'Advanced Chords', 'description': 'Desc2'}}]
#     #     return [{'id': {'kind': 'youtube#video', 'videoId': 'vid_solo_1'}, 'snippet': {'title': 'Amazing Guitar Solo', 'description': 'Desc_solo1'}}]

#     # with mock.patch('workflows.video_processor.call_openai_chat', side_effect=mock_openai_for_video), \
#     #      mock.patch('workflows.video_processor.youtube_search', side_effect=mock_yt_search):
#     #
#     #    final_videos = process_videos_for_article(sample_sections, article_title_test, mock_config, run_id_test)
#     #    logger.info(f"Final video data from test run: {final_videos}")
#     #    # Add assertions here