# workflows/image_processor.py
import logging
import time
import requests # Để tải ảnh
import urllib.parse # Để encode keyword
from utils.api_clients import ( # Đã import perform_search ở file trước
    call_openai_chat, 
    perform_search, # Sử dụng perform_search thay vì google_search trực tiếp
    upload_wp_media
)
# from utils.redis_handler import RedisHandler # Sẽ được thay thế bởi RunContext
from utils.image_utils import resize_image
from prompts import image_prompts
# from utils.config_loader import APP_CONFIG # Import config của bạn

logger = logging.getLogger(__name__)

# --- Constants (có thể lấy từ APP_CONFIG) ---
# MAX_IMAGE_SELECTION_ATTEMPTS = 3 # Số lần thử chọn ảnh khác nhau cho 1 section
# IMAGE_DOWNLOAD_TIMEOUT = 10 # giây
# IMAGE_PROCESS_RETRY_DELAY = 5 # giây

def _get_redis_keys(config, unique_run_id):
    """Helper to generate Redis keys for this image processing run."""
    return {
        "image_array": f"{config.get('REDIS_KEY_IMAGE_ARRAY_PREFIX', 'fvp_image_array_')}{unique_run_id}",
        "failed_urls": f"{config.get('REDIS_KEY_FAILED_IMAGE_URLS_PREFIX', 'fvp_failed_image_urls_')}{unique_run_id}",
        "used_urls": f"{config.get('REDIS_KEY_USED_IMAGE_URLS_PREFIX', 'fvp_used_image_urls_')}{unique_run_id}",
        "current_image_search_results_prefix": f"fvp_img_search_results_{unique_run_id}_section_"
    }

def _should_skip_image(section_data):
    """Kiểm tra xem có nên bỏ qua việc chèn ảnh cho section này không."""
    section_name = section_data.get('sectionName', '').lower()
    section_name_tag = section_data.get('sectionNameTag', '').lower()
    mother_chapter = section_data.get('motherChapter', 'no').lower()

    if section_name_tag in ["introduction", "conclusion", "faqs"]:
        logger.info(f"Skipping image for section '{section_data.get('sectionName')}' due to sectionNameTag: {section_name_tag}")
        return True
    if mother_chapter == 'yes':
        logger.info(f"Skipping image for section '{section_data.get('sectionName')}' because it's a motherChapter.")
        return True
    # Thêm các điều kiện skip khác nếu cần, ví dụ sectionName cụ thể
    # if section_name in ["introduction", "faqs", "conclusion"]:
    #     logger.info(f"Skipping image for section '{section_data.get('sectionName')}' due to specific name.")
    #     return True
    return False

def _parse_search_results_for_images(standardized_search_results):
    """
    Chuyển đổi kết quả tìm kiếm ảnh đã được chuẩn hóa 
    thành list các dict {imageUrl, imageDes, imageWidth, imageHeight, sourceUrl} cho việc chọn lựa.
    standardized_search_results: list các dict từ perform_search (đã chuẩn hóa).
    """
    if not standardized_search_results:
        return []
    images_data = []
    for item in standardized_search_results:
        image_url = item.get('imageUrl') # Key chuẩn hóa
        # imageDes lấy từ snippet hoặc title (đã được chuẩn hóa trong api_clients)
        image_des = item.get('snippet', item.get('title', 'No description available')) 
        if image_url:
            images_data.append({
                'imageUrl': image_url, 
                'imageDes': image_des,
                'imageWidth': item.get('imageWidth'), # Thêm để có thể dùng trong prompt nếu muốn
                'imageHeight': item.get('imageHeight'),# Thêm để có thể dùng trong prompt nếu muốn
                'sourceUrl': item.get('sourceUrl') # Thêm để có thể dùng trong prompt nếu muốn
            })
    return images_data

def _filter_image_search_results(image_search_list, failed_urls_list):
    if not failed_urls_list:
        return image_search_list
    return [img for img in image_search_list if img.get('imageUrl') not in failed_urls_list]


def process_single_section_image(section_data, article_title, parent_section_name_for_subchapter,
                                 redis_handler, config, openai_api_key, google_api_key,
                                 wp_auth_tuple, unique_run_id, section_index_for_redis_key): # google_api_key có thể không cần trực tiếp nữa
    """
    Xử lý tìm, chọn, và upload ảnh cho MỘT section.
    Trả về dict chứa thông tin ảnh đã upload (url, index) hoặc thông tin lỗi.
    section_index_for_redis_key: dùng để tạo key redis duy nhất cho image_search_results của section này.
    """
    max_selection_attempts = config.get('MAX_IMAGE_SELECTION_ATTEMPTS', 3)
    download_timeout = config.get('IMAGE_DOWNLOAD_TIMEOUT', 10)
    retry_delay = config.get('IMAGE_PROCESS_RETRY_DELAY', 5)
    
    redis_keys = _get_redis_keys(config, unique_run_id)
    current_section_image_search_key = f"{redis_keys['current_image_search_results_prefix']}{section_index_for_redis_key}"

    # ----- BƯỚC 1: Lấy hoặc tạo từ khóa tìm ảnh -----
    logger.info(f"Processing image for section: {section_data.get('sectionName')}")
    parent_context_str = ""
    if section_data.get('sectionType') == 'subchapter' and parent_section_name_for_subchapter:
        parent_context_str = f"from the section \"{parent_section_name_for_subchapter}\" "

    prompt_img_keyword = image_prompts.GENERATE_IMAGE_SEARCH_KEYWORD_PROMPT.format(
        section_type=section_data.get('sectionType', 'section'),
        section_name=section_data.get('sectionName'),
        parent_context_string=parent_context_str,
        article_title=article_title
    )
    image_keyword = call_openai_chat(
        [{"role": "user", "content": prompt_img_keyword}],
        config.get('DEFAULT_OPENAI_CHAT_MODEL'),
        api_key=openai_api_key, # OpenAI API key gốc
        target_api="openrouter",
        openrouter_api_key=config.get('OPENROUTER_API_KEY'),
        openrouter_base_url=config.get('OPENROUTER_BASE_URL')
    )
    if not image_keyword:
        logger.error(f"Failed to generate image keyword for section: {section_data.get('sectionName')}")
        return {"url": "error_generating_keyword", "index": section_data.get('sectionIndex')}
    
    logger.info(f"Generated image keyword: '{image_keyword}' for section '{section_data.get('sectionName')}'")
    encoded_keyword = urllib.parse.quote_plus(image_keyword)

    # ----- BƯỚC 2: Tìm kiếm ảnh trên Google -----
    # Lấy danh sách image search results từ Redis nếu đã có (cho lần thử lại của section này)
    # Hoặc tìm mới và lưu vào Redis
    image_search_results = redis_handler.get_value(current_section_image_search_key)
    if not image_search_results:
        logger.info(f"No cached image search results for section {section_data.get('sectionName')}. Searching Google...")

        # Sử dụng perform_search thay vì google_search trực tiếp
        # perform_search sẽ tự xử lý việc gọi Google hoặc Serper dựa trên config
        # và cũng tự xử lý việc lấy API keys từ config.
        search_results_standardized = perform_search(
            query=encoded_keyword,
            search_type='image',
            config=config, # perform_search sẽ lấy API keys và provider từ đây
            num_results=config.get('GOOGLE_SEARCH_NUM_RESULTS_IMAGES', 10),
            # imgSize sẽ được truyền vào kwargs. perform_search sẽ xử lý nó.
            # Nếu provider là Google, imgSize sẽ được dùng.
            # Nếu là Serper, min_width/min_height từ config sẽ được dùng bởi call_serper_search.
            imgSize=config.get('GOOGLE_IMAGE_SIZE_FILTER', "large") # Ví dụ: "large", "xlarge", "xxlarge"
        )
        
        image_search_results = _parse_search_results_for_images(search_results_standardized)
        if image_search_results:
            redis_handler.set_value(current_section_image_search_key, image_search_results) # Cache lại
        else:
            logger.warning(f"No images found from Google Search for keyword: '{image_keyword}'")
            return {"url": "no_images_found_google", "index": section_data.get('sectionIndex')}
    else:
        logger.info(f"Using cached image search results for section {section_data.get('sectionName')}")


    # ----- BƯỚC 3: Vòng lặp chọn, tải, xử lý và upload ảnh -----
    for attempt in range(max_selection_attempts):
        logger.info(f"Image selection attempt {attempt + 1}/{max_selection_attempts} for section '{section_data.get('sectionName')}'")

        # Lọc bỏ các URL đã thất bại (từ Redis global failed_urls)
        failed_urls_global = redis_handler.get_value(redis_keys['failed_urls']) or []
        current_image_options_list = _filter_image_search_results(image_search_results, failed_urls_global)

        if not current_image_options_list:
            logger.warning(f"No image options left to try for section '{section_data.get('sectionName')}' after filtering failed URLs.")
            break # Thoát vòng lặp nếu không còn ảnh nào để thử

        # Tạo chuỗi options cho prompt OpenAI
        options_parts = []
        for i, img_data in enumerate(current_image_options_list):
            desc = img_data.get('imageDes', 'N/A')
            url = img_data.get('imageUrl', 'N/A')
            # Nếu muốn OpenAI cân nhắc kích thước, có thể thêm vào đây:
            # width = img_data.get('imageWidth', 'N/A')
            # height = img_data.get('imageHeight', 'N/A')
            options_parts.append(f"{i+1}. Image Description: {desc}, imageURL: {url}") # , Width: {width}, Height: {height}
        image_options_str = "\n".join(options_parts)
        if not image_options_str: # Double check
             image_options_str = "No image options available."


        # Tạo context cho prompt chọn ảnh
        section_context_str_select = ""
        s_type = section_data.get('sectionType')
        s_name = section_data.get('sectionName')
        if s_type == 'chapter':
            section_context_str_select = f", the section \"{s_name}\""
        elif s_type == 'subchapter' and parent_section_name_for_subchapter:
            section_context_str_select = f", and its specific sub-section \"{s_name}\" (of chapter \"{parent_section_name_for_subchapter}\")"
        else:
            section_context_str_select = f", regarding the section/sub-section \"{s_name}\""

        prompt_choose_image = image_prompts.CHOOSE_BEST_IMAGE_URL_PROMPT.format(
            article_title=article_title,
            # Đảm bảo tên key ở đây khớp với placeholder trong image_prompts.py
            parent_context_string_for_selection=section_context_str_select, 
            # section_name=s_name, # Không cần nữa nếu parent_context_string_for_selection đã bao gồm
            image_options_string=image_options_str
        )
        
        chosen_image_info = call_openai_chat(
            [{"role": "user", "content": prompt_choose_image}],
            config.get('DEFAULT_OPENAI_CHAT_MODEL'),
            api_key=openai_api_key, # OpenAI API key gốc
            is_json_output=True,
            target_api="openrouter",
            openrouter_api_key=config.get('OPENROUTER_API_KEY'),
            openrouter_base_url=config.get('OPENROUTER_BASE_URL')
        )

        if not chosen_image_info or not chosen_image_info.get('imageURL'):
            logger.warning(f"OpenAI did not select an image or returned an error for section '{s_name}'. Response: {chosen_image_info}")
            # Nếu OpenAI không chọn được, có thể coi như hết lựa chọn cho lần này
            # Hoặc bạn có thể thử lại với cùng list (nhưng có thể lặp vô hạn nếu prompt/data có vấn đề)
            # Tốt nhất là coi như không chọn được và để vòng lặp thử ảnh khác (nếu có)
            # Hoặc nếu OpenAI trả lỗi rõ ràng, có thể đánh dấu URL này là failed.
            # Hiện tại, nếu không chọn được, vòng lặp sẽ tiếp tục nếu max_selection_attempts chưa hết
            # nhưng image_search_results không thay đổi, nên cần logic để loại bỏ ảnh đã thử.
            # Cách đơn giản: Nếu OpenAI không chọn, thì không có ảnh nào phù hợp từ list hiện tại.
            logger.info(f"No suitable image selected by AI from the current list for section '{s_name}'.")
            break # Không còn ảnh phù hợp trong list hiện tại

        selected_image_url = chosen_image_info.get('imageURL')
        selected_image_des = chosen_image_info.get('imageDes', s_name) # Dùng section name làm alt text nếu không có des

        # Kiểm tra xem URL này đã được sử dụng cho bài viết này chưa (từ Redis global used_urls)
        # Để tránh ảnh bị trùng lặp quá nhiều trong cùng một bài.
        used_urls_global = redis_handler.get_value(redis_keys['used_urls']) or []
        if selected_image_url in used_urls_global:
            logger.info(f"Image URL '{selected_image_url}' has already been used in this article. Adding to failed list for this section and retrying.")
            # Thêm vào failed_urls_global để không thử lại URL này cho bất kỳ section nào nữa
            # Và loại nó khỏi image_search_results của section hiện tại để không bị OpenAI chọn lại
            failed_urls_global.append(selected_image_url)
            redis_handler.set_value(redis_keys['failed_urls'], list(set(failed_urls_global))) # Lưu lại list unique
            
            # Cập nhật image_search_results của section này (trong Redis) bằng cách loại bỏ URL vừa thử
            image_search_results = [img for img in image_search_results if img.get('imageUrl') != selected_image_url]
            redis_handler.set_value(current_section_image_search_key, image_search_results)
            
            time.sleep(retry_delay) # Chờ trước khi thử lại với các ảnh còn lại
            continue # Thử chọn ảnh khác từ list đã được lọc


        # Tải ảnh
        image_binary_downloaded = None
        try:
            logger.info(f"Downloading image: {selected_image_url}")
            response = requests.get(selected_image_url, timeout=download_timeout, stream=True)
            response.raise_for_status()
            # Kiểm tra content type (tùy chọn nhưng nên có)
            content_type = response.headers.get('content-type', '').lower()
            if 'image' not in content_type:
                logger.warning(f"URL '{selected_image_url}' does not seem to be an image (Content-Type: {content_type}). Marking as failed.")
                raise ValueError("Not an image content type")
            image_binary_downloaded = response.content
            logger.info(f"Image downloaded successfully (size: {len(image_binary_downloaded)} bytes).")
        except Exception as e:
            logger.error(f"Failed to download image '{selected_image_url}': {e}")
            # Thêm vào failed_urls_global và cập nhật image_search_results của section
            failed_urls_global.append(selected_image_url)
            redis_handler.set_value(redis_keys['failed_urls'], list(set(failed_urls_global)))
            image_search_results = [img for img in image_search_results if img.get('imageUrl') != selected_image_url]
            redis_handler.set_value(current_section_image_search_key, image_search_results)
            time.sleep(retry_delay)
            continue # Thử chọn ảnh khác

        # Resize ảnh
        # Xác định output format, ví dụ luôn là JPEG
        output_img_format = "JPEG"
        resized_image_data = resize_image(
            image_binary_downloaded,
            width=config.get('IMAGE_RESIZE_WIDTH'),
            height=config.get('IMAGE_RESIZE_HEIGHT'), # Có thể để None nếu chỉ muốn resize theo width
            output_format=output_img_format,
            quality=config.get('IMAGE_RESIZE_QUALITY', 85)
        )
        if not resized_image_data:
            logger.error(f"Failed to resize image from URL: {selected_image_url}")
            failed_urls_global.append(selected_image_url)
            redis_handler.set_value(redis_keys['failed_urls'], list(set(failed_urls_global)))
            image_search_results = [img for img in image_search_results if img.get('imageUrl') != selected_image_url]
            redis_handler.set_value(current_section_image_search_key, image_search_results)
            time.sleep(retry_delay)
            continue # Thử chọn ảnh khác

        # Upload WordPress
        # Tạo filename (ví dụ: section-name-sanitized.jpg)
        section_slug = "".join(c if c.isalnum() else '-' for c in s_name.lower()).strip('-')
        wp_filename = f"{section_slug}-{section_data.get('sectionIndex', 'img')}.{output_img_format.lower()}"
        mime_type = f"image/{output_img_format.lower()}"

        wp_media_response = upload_wp_media(
            config.get('WP_BASE_URL'),
            wp_auth_tuple[0], wp_auth_tuple[1],
            resized_image_data,
            wp_filename,
            mime_type
        )

        if wp_media_response and wp_media_response.get('source_url'):
            wp_image_url = wp_media_response.get('source_url')
            logger.info(f"Image successfully uploaded to WordPress for section '{s_name}'. URL: {wp_image_url}")
            
            # Thêm vào used_urls_global để không dùng lại cho section khác
            used_urls_global.append(selected_image_url) # Lưu URL gốc đã chọn, không phải URL WP
            redis_handler.set_value(redis_keys['used_urls'], list(set(used_urls_global)))

            # Xóa cache image_search_results của section này vì đã xử lý xong
            redis_handler.delete_key(current_section_image_search_key)

            return {"url": wp_image_url, "index": section_data.get('sectionIndex'), "alt_text": selected_image_des}
        else:
            logger.error(f"Failed to upload image to WordPress for section '{s_name}'. Original URL: {selected_image_url}. Response: {wp_media_response}")
            failed_urls_global.append(selected_image_url)
            redis_handler.set_value(redis_keys['failed_urls'], list(set(failed_urls_global)))
            image_search_results = [img for img in image_search_results if img.get('imageUrl') != selected_image_url]
            redis_handler.set_value(current_section_image_search_key, image_search_results)
            time.sleep(retry_delay)
            # continue # Thử chọn ảnh khác (vòng lặp sẽ tự làm)

    # Nếu hết vòng lặp mà không thành công
    logger.warning(f"Exhausted all attempts or options for section '{section_data.get('sectionName')}'. No image uploaded.")
    redis_handler.delete_key(current_section_image_search_key) # Dọn dẹp cache
    return {"url": "error_max_attempts_or_no_options", "index": section_data.get('sectionIndex')}


def process_images_for_article(sections_data_list, article_title, run_context, config):
    """
    Hàm chính để xử lý ảnh cho tất cả các section trong một bài viết.
    sections_data_list: List các dict, mỗi dict là thông tin của một section 
                        (bao gồm sectionName, sectionType, sectionNameTag, motherChapter, sectionIndex).
    run_context: Đối tượng RunContext chứa trạng thái và dữ liệu cho lần chạy này.
    """
    logger.info(f"Starting image processing for article: '{article_title}' with run_id: {run_context.unique_run_id}")
    
    # Load credentials và config cần thiết
    openai_api_key = config.get('OPENAI_API_KEY')
    google_api_key = config.get('GOOGLE_API_KEY')
    wp_user = config.get('WP_USER')
    wp_pass = config.get('WP_PASSWORD')
    wp_auth = (wp_user, wp_pass)

    if not all([openai_api_key, google_api_key, wp_user, wp_pass, config.get('GOOGLE_CX_ID')]):
        logger.error("Missing critical API keys, WordPress credentials, or Google CX ID in config for image processing.")
        return [{"url": "config_error", "index": s.get('sectionIndex')} for s in sections_data_list]

    # redis_handler = RedisHandler(config=config) # Sẽ thay thế bằng run_context
    # if not redis_handler.is_connected():
    #     logger.error("Cannot connect to Redis. Aborting image processing.")
    #     return [{"url": "redis_connection_error", "index": s.get('sectionIndex')} for s in sections_data_list]

    # Khởi tạo các key Redis cần thiết cho lần chạy này
    # redis_keys = _get_redis_keys(config, run_context.unique_run_id) # Sẽ dùng run_context trực tiếp
    # run_context đã được khởi tạo với các list/set rỗng
    # redis_handler.initialize_array_if_not_exists(redis_keys['image_array'], "[]")
    # redis_handler.initialize_array_if_not_exists(redis_keys['failed_urls'], "[]")
    # redis_handler.initialize_array_if_not_exists(redis_keys['used_urls'], "[]")

    # final_image_array_from_redis = [] # Sẽ lưu vào run_context.processed_image_data
    parent_chapter_name = None # Theo dõi chapter cha cho các subchapter
    for i, section in enumerate(sections_data_list):
        if section.get('sectionType') == 'chapter':
            parent_chapter_name = section.get('sectionName')

        current_image_data_for_section = {"url": "not_inserted_by_default", "index": section.get('sectionIndex'), "alt_text": section.get('sectionName')}

        if _should_skip_image(section):
            current_image_data_for_section["url"] = "skipped_section_type"
            logger.info(f"Image skipped for section {section.get('sectionName')}, added placeholder to array.")
        else:
            # Thực sự xử lý ảnh
            # Truyền parent_chapter_name nếu section hiện tại là subchapter
            parent_name_for_sub = parent_chapter_name if section.get('sectionType') == 'subchapter' else None
            
            image_result = process_single_section_image(
                section_data=section,
                article_title=article_title,
                parent_section_name_for_subchapter=parent_name_for_sub,
                # redis_handler=redis_handler, # Sẽ truyền run_context vào process_single_section_image
                run_context=run_context, # Tạm thời truyền vào đây, hàm con sẽ cần sửa để dùng
                config=config,
                openai_api_key=openai_api_key,
                google_api_key=google_api_key,
                wp_auth_tuple=wp_auth,
                unique_run_id=run_context.unique_run_id, # Vẫn cần unique_run_id cho _get_redis_keys bên trong process_single_section_image (sẽ sửa sau)
                section_index_for_redis_key=i # Dùng index trong list làm ID cho key cache
            )
            current_image_data_for_section = image_result
        
        # Cập nhật image_array trong Redis sau mỗi section (hoặc có thể làm cuối cùng)
        # Logic này tương tự node "imageArray2" -> "Set imageArray to Redis2"
        # current_global_image_array = redis_handler.get_value(redis_keys['image_array']) or [] # Sẽ đọc từ run_context
        # Đảm bảo không thêm trùng entry cho cùng một index nếu có retry ở mức cao hơn
        # Hoặc, cách đơn giản hơn là chỉ build list ở Python rồi set một lần vào Redis ở cuối.
        # Tạm thời build ở Python trước:
        run_context.processed_image_data.append(current_image_data_for_section)


    # Sắp xếp lại run_context.processed_image_data theo 'index' nếu cần thiết (nếu xử lý song song)
    # Nếu xử lý tuần tự thì nó đã theo thứ tự.
    # Loại bỏ trùng lặp theo index nếu có (hiếm khi xảy ra với logic tuần tự)
    # unique_images_by_index = {img['index']: img for img in run_context.processed_image_data}
    # sorted_unique_images = sorted(unique_images_by_index.values(), key=lambda x: x['index'])

    # Không cần lưu vào Redis nữa, vì đã lưu vào run_context.processed_image_data
    # Điều này đơn giản hơn việc đọc/ghi Redis liên tục cho image_array chính.
    # redis_handler.set_value(redis_keys['image_array'], run_context.processed_image_data) 
    
    logger.info(f"Finished image processing for article '{article_title}'. Final image data for this run (stored in RunContext): {run_context.processed_image_data}")
    
    # Hàm này chỉ trả về kết quả của lần chạy này.
    # Việc đọc `imageArray` từ Redis và sort/merge cuối cùng (như node `imageArray completed`)
    # nên được thực hiện bởi `main_logic.py` SAU KHI workflow này hoàn thành.
    return final_image_array_from_redis

# --- Example Usage (sẽ được gọi từ main_logic.py) ---
# if __name__ == "__main__":
#     # Cần mock APP_CONFIG, RedisHandler, và các hàm API
#     # Đây là ví dụ rất cơ bản
#     mock_config = {
#         'OPENAI_API_KEY': "test_key_openai",
#         'GOOGLE_API_KEY': "test_key_google",
#         'GOOGLE_IMAGES_CX_ID': "test_cx_id",
#         'WP_USER': "wp_user",
#         'WP_PASSWORD': "wp_pass",
#         'WP_BASE_URL': "http://localhost/wp", # Url WordPress test
#         'REDIS_HOST': 'localhost', 'REDIS_PORT': 6379, 'REDIS_DB': 0,
#         'DEFAULT_OPENAI_CHAT_MODEL': 'gpt-3.5-turbo',
#         'IMAGE_RESIZE_WIDTH': 700,
#         'MAX_IMAGE_SELECTION_ATTEMPTS': 1, # Để test nhanh
#         # ... các key prefix cho Redis ...
#     }
#     # setup_logging(log_level_str="DEBUG")

#     sample_sections = [
#         {"sectionName": "Introduction", "sectionType": "chapter", "sectionNameTag": "Introduction", "motherChapter": "no", "sectionIndex": 1},
#         {"sectionName": "Understanding Guitar Woods", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 2},
#         {"sectionName": "Spruce Tops", "sectionType": "subchapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 3},
#         {"sectionName": "FAQs", "sectionType": "chapter", "sectionNameTag": "FAQs", "motherChapter": "no", "sectionIndex": 4},
#     ]
#     article_title_test = "A Guide to Guitar Woods"
#     run_id_test = "testrun123"

#     # Cần mock các hàm API calls hoặc set up một môi trường test thực sự
#     # Ví dụ:
#     # import unittest.mock as mock
#     # with mock.patch('utils.api_clients.call_openai_chat', return_value="guitar wood"), \
#     #      mock.patch('utils.api_clients.google_search', return_value=[{'link': 'http://example.com/img.jpg', 'snippet': 'Test Image'}]), \
#     #      mock.patch('utils.api_clients.upload_wp_media', return_value={'source_url': 'http://wp.example.com/img.jpg'}):
#     #
#     #    final_images = process_images_for_article(sample_sections, article_title_test, mock_config, run_id_test)
#     #    logger.info(f"Final image data from test run: {final_images}")