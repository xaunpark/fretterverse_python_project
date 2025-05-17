# workflows/video_processor.py
import logging
import random
import json # Để parse JSON từ OpenAI nếu cần (mặc dù prompt yêu cầu JSON object)
from utils.api_clients import call_openai_chat, perform_search # Sử dụng perform_search
# from utils.redis_handler import RedisHandler # Sẽ được thay thế bởi RunContext
from prompts import video_prompts
# from utils.config_loader import APP_CONFIG # Import config của bạn

logger = logging.getLogger(__name__)

# --- Constants (có thể lấy từ APP_CONFIG) ---
# VIDEO_SEARCH_RESULTS_COUNT = 5 # Số video lấy từ YouTube để chọn

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

def _parse_video_search_results(standardized_video_results):
    """
    Chuyển đổi kết quả tìm kiếm video đã được chuẩn hóa từ perform_search
    thành list các dict {videoID, videoTitle, videoDescription} cho việc chọn lựa.
    standardized_video_results: list các dict từ perform_search (đã chuẩn hóa).
    """
    if not standardized_video_results:
        return []
    videos_data = []
    for item in standardized_video_results:
        # perform_search đã chuẩn hóa kết quả, nên ta dùng trực tiếp các key đã định nghĩa
        video_id = item.get('videoID')
        title = item.get('videoTitle', 'N/A')
        description = item.get('videoDescription', 'No description available')
        
        if video_id: # Chỉ thêm nếu có videoID hợp lệ
            videos_data.append({
                'videoID': video_id,
                'videoTitle': title,
                'videoDescription': description
            })
    return videos_data


def process_single_section_video(section_data, article_title, parent_chapter_name_for_subchapter,
                                 run_context, # Thay redis_handler bằng run_context
                                 config, openai_api_key, 
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
        api_key=openai_api_key, # OpenAI API key gốc
        target_api="openrouter",
        openrouter_api_key=config.get('OPENROUTER_API_KEY'),
        openrouter_base_url=config.get('OPENROUTER_BASE_URL')
    )
    if not video_keyword:
        logger.error(f"Failed to generate video keyword for section: {section_data.get('sectionName')}")
        video_result_for_section["videoID"] = "none"
        video_result_for_section["videoTitle"] = "Error generating video keyword"
        return video_result_for_section
    
    logger.info(f"Generated video keyword: '{video_keyword}' for section '{section_data.get('sectionName')}'")

    # --- BƯỚC 2: Tìm kiếm video trên YouTube ---
    # Thay thế youtube_search bằng perform_search
    video_search_items_standardized = perform_search(
        query=video_keyword,
        search_type='video',
        config=config, # perform_search sẽ lấy API key từ config
        num_results=video_search_count
    )
    video_options_list = _parse_video_search_results(video_search_items_standardized)

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
        api_key=openai_api_key, # OpenAI API key gốc
        is_json_output=True, # Yêu cầu OpenAI trả về JSON
        target_api="openrouter",
        openrouter_api_key=config.get('OPENROUTER_API_KEY'),
        openrouter_base_url=config.get('OPENROUTER_BASE_URL')
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


def process_videos_for_article(sections_data_list, article_title, run_context, config):
    """
    Hàm chính để xử lý video cho tất cả các section trong một bài viết.
    sections_data_list: List các dict, mỗi dict là thông tin của một section.
    run_context: Đối tượng RunContext chứa trạng thái và dữ liệu cho lần chạy này.
    """
    logger.info(f"Starting video processing for article: '{article_title}' with run_id: {run_context.unique_run_id}")

    openai_api_key = config.get('OPENAI_API_KEY')
    # youtube_api_key không cần lấy ở đây nữa vì perform_search sẽ tự xử lý

    if not openai_api_key: # Chỉ cần check OpenAI key ở đây
        logger.error("Missing OpenAI API key in config for video processing.")
        # Sẽ trả về list rỗng hoặc list các lỗi, nhưng run_context.processed_video_data sẽ rỗng
        return [] 

    # run_context.processed_video_data đã được khởi tạo là list rỗng
    article_video_results = [] # List để thu thập kết quả video cho từng section
    parent_chapter_name_for_current_subchapters = None

    for section in sections_data_list:
        if section.get('sectionType') == 'chapter':
            parent_chapter_name_for_current_subchapters = section.get('sectionName')
        
        video_data_for_section = process_single_section_video(
            section_data=section,
            article_title=article_title,
            parent_chapter_name_for_subchapter=parent_chapter_name_for_current_subchapters if section.get('sectionType') == 'subchapter' else None,
            run_context=run_context, 
            config=config,
            openai_api_key=openai_api_key,
            unique_run_id=run_context.unique_run_id 
        )
        article_video_results.append({
            "videoID": video_data_for_section.get("videoID", "none"), # Đảm bảo "none" nếu null
            "index": section.get("sectionIndex") # Giữ lại index để map với section
            # Bạn có thể muốn thêm videoTitle, videoDescription vào đây nếu cần ở main_logic
        })

    # Đảm bảo rằng videoID là "none" nếu nó là None từ process_single_section_video
    # và lưu vào run_context.processed_video_data
    run_context.processed_video_data.clear() # Xóa dữ liệu cũ nếu có (mặc dù nó được khởi tạo rỗng)
    for res in article_video_results:
        run_context.processed_video_data.append({
            "videoID": res.get("videoID") if res.get("videoID") is not None else "none",
            "index": res.get("index")
            # Bạn có thể thêm các trường khác nếu Full HTML cần, ví dụ title, description của video được chọn
            # "videoTitle": res.get("videoTitle"),
            # "videoDescription": res.get("videoDescription")
        })
    
    logger.info(f"Finished video processing for article '{article_title}'. Final video data stored in RunContext.")
    logger.debug(f"Data in RunContext: {run_context.processed_video_data}")
    
    # Hàm này có thể trả về run_context.processed_video_data để main_logic sử dụng trực tiếp
    # Hoặc main_logic sẽ tự đọc từ Redis key sau khi hàm này chạy xong.
    # Trả về để tiện sử dụng:
    return run_context.processed_video_data


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