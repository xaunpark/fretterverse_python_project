# workflows/main_logic.py
import logging
import json
import re
import time # Cho việc sleep nếu cần
from utils.api_clients import call_openai_chat, google_search, call_openai_embeddings # Thêm call_openai_embeddings
from utils.google_sheets_handler import GoogleSheetsHandler # Giả sử là class
from utils.pinecone_handler import PineconeHandler # Giả sử là class
from prompts import main_prompts
# from utils.config_loader import APP_CONFIG # Import hoặc nhận APP_CONFIG

logger = logging.getLogger(__name__)

#####################################################
### --- Bước 1: Phân tích Keyword và Chuẩn bị --- ###
#####################################################

def choose_author_for_topic(topic_or_keyword, author_personas_json_string, config):
    """
    Gọi LLM để chọn tác giả phù hợp nhất cho chủ đề/keyword.
    author_personas_json_string: Chuỗi JSON của danh sách author personas.
    """
    logger.info(f"Choosing author for topic: '{topic_or_keyword}'")
    prompt = main_prompts.CHOOSE_AUTHOR_PROMPT.format(
        topic_title=topic_or_keyword,
        authors_json_string=author_personas_json_string
    )
    try:
        chosen_author_data = call_openai_chat(
            prompt_messages=[{"role": "user", "content": prompt}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'), # Hoặc DEFAULT_GEMINI_MODEL nếu bạn dùng Gemini cho việc này
            api_key=config.get('OPENAI_API_KEY'), # Hoặc GEMINI_API_KEY
            is_json_output=True
        )
        if chosen_author_data and isinstance(chosen_author_data, dict) and \
           'name' in chosen_author_data and 'ID' in chosen_author_data:
            logger.info(f"Author chosen: {chosen_author_data.get('name')} (ID: {chosen_author_data.get('ID')})")
            return chosen_author_data
        else:
            logger.error(f"Failed to get valid author data from LLM. Response: {chosen_author_data}")
            # Fallback to default author from config or raise error
            default_author_id = config.get('DEFAULT_AUTHOR_ID', 1)
            default_author_name = "Default Author" # Cần có thông tin author mặc định đầy đủ hơn
            default_author_info = "Default author information for general topics."
            logger.warning(f"Falling back to default author: ID {default_author_id}")
            # Tìm trong AUTHOR_PERSONAS hoặc tạo một author mặc định
            author_personas = config.get('AUTHOR_PERSONAS', [])
            default_author = next((author for author in author_personas if str(author.get("ID")) == str(default_author_id)), None)
            if default_author:
                return default_author
            return {"name": default_author_name, "info": default_author_info, "ID": default_author_id}

    except Exception as e:
        logger.error(f"Error during author selection: {e}", exc_info=True)
        return None


def get_serp_data_for_keyword(keyword, config):
    """Gọi Google Search để lấy dữ liệu SERP."""
    logger.info(f"Fetching SERP data for keyword: '{keyword}'")
    try:
        search_items = google_search(
            query=keyword,
            api_key=config.get('GOOGLE_API_KEY'),
            cx_id=config.get('GOOGLE_CX_ID_FOR_SERP_ANALYSIS'), # Cần CX_ID riêng cho việc này
            num_results=config.get('GOOGLE_SEARCH_NUM_RESULTS', 10)
        )
        if search_items:
            # Chuyển đổi thành chuỗi để đưa vào prompt
            serp_data_list = []
            for item in search_items:
                title = item.get('title', 'N/A')
                snippet = item.get('snippet', 'N/A')
                link = item.get('link', 'N/A')
                serp_data_list.append(f"Title: {title}\nSnippet: {snippet}\nURL: {link}\n---")
            serp_data_string = "\n".join(serp_data_list)
            logger.info(f"Successfully fetched and formatted SERP data for '{keyword}'.")
            return serp_data_string
        else:
            logger.warning(f"No SERP data returned from Google Search for '{keyword}'.")
            return None
    except Exception as e:
        logger.error(f"Error fetching SERP data for '{keyword}': {e}", exc_info=True)
        return None

def analyze_serp_and_keyword(keyword, serp_data_string, config):
    """
    Gọi LLM để phân tích SERP và keyword, trả về searchIntent, contentFormat, etc.
    """
    if not serp_data_string:
        logger.warning("SERP data string is empty, cannot perform analysis.")
        return None
        
    logger.info(f"Analyzing SERP and keyword: '{keyword}'")
    prompt = main_prompts.ANALYZE_KEYWORD_FROM_SERP_PROMPT.format(
        keyword=keyword,
        search_results_data=serp_data_string
    )
    try:
        analysis_result = call_openai_chat(
            prompt_messages=[{"role": "user", "content": prompt}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'),
            api_key=config.get('OPENAI_API_KEY'),
            is_json_output=True
        )
        if analysis_result and isinstance(analysis_result, dict) and \
           all(k in analysis_result for k in ['searchIntent', 'contentFormat', 'articleType', 'selectedModel', 'semanticKeyword']):
            logger.info(f"Keyword analysis successful for '{keyword}'. ArticleType: {analysis_result.get('articleType')}")
            return analysis_result
        else:
            logger.error(f"Invalid or incomplete analysis result from LLM for '{keyword}'. Response: {analysis_result}")
            return None
    except Exception as e:
        logger.error(f"Error during keyword analysis for '{keyword}': {e}", exc_info=True)
        return None

def check_keyword_suitability(keyword, config, gsheet_handler):
    """Kiểm tra tính phù hợp của keyword."""
    logger.info(f"Checking suitability for keyword: '{keyword}'")
    prompt = main_prompts.CHECK_KEYWORD_SUITABILITY_PROMPT.format(keyword=keyword)
    try:
        suitability_response = call_openai_chat(
            prompt_messages=[{"role": "user", "content": prompt}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'),
            api_key=config.get('OPENAI_API_KEY'),
            is_json_output=True # Prompt yêu cầu JSON với key "suitable"
        )
        if suitability_response and isinstance(suitability_response, dict) and \
           suitability_response.get('suitable', '').lower() == 'yes':
            logger.info(f"Keyword '{keyword}' is suitable.")
            return True
        else:
            logger.warning(f"Keyword '{keyword}' deemed unsuitable by LLM. Response: {suitability_response}")
            if gsheet_handler: # Chỉ cập nhật nếu có gsheet_handler
                update_data = {
                    config.get('GSHEET_USED_COLUMN'): "1", # Đánh dấu đã xử lý
                    config.get('GSHEET_SUITABLE_COLUMN'): "no"
                }
                gsheet_handler.update_sheet_row_by_matching_column(
                    spreadsheet_id_or_url=config.get('GSHEET_SPREADSHEET_ID'),
                    sheet_name_or_gid=config.get('GSHEET_KEYWORD_SHEET_NAME'),
                    match_column_header=config.get('GSHEET_KEYWORD_COLUMN'),
                    match_value=keyword,
                    data_to_update_dict=update_data
                )
                logger.info(f"Updated Google Sheet: Keyword '{keyword}' marked as Used=1, Suitable=no.")
            return False
    except Exception as e:
        logger.error(f"Error checking keyword suitability for '{keyword}': {e}", exc_info=True)
        return False # Mặc định là không phù hợp nếu có lỗi

def normalize_keyword_for_pinecone_id(keyword):
    """Chuẩn hóa keyword để làm ID an toàn cho Pinecone (tương tự code node)."""
    if not keyword: return ''
    # Bỏ dấu tiếng Việt
    s = keyword.lower()
    s = re.sub(r'[àáạảãâầấậẩẫăằắặẳẵ]', 'a', s)
    s = re.sub(r'[èéẹẻẽêềếệểễ]', 'e', s)
    s = re.sub(r'[òóọỏõôồốộổỗơờớợởỡ]', 'o', s)
    s = re.sub(r'[ìíịỉĩ]', 'i', s)
    s = re.sub(r'[ùúụủũưừứựửữ]', 'u', s)
    s = re.sub(r'[ỳýỵỷỹ]', 'y', s)
    s = re.sub(r'[đ]', 'd', s)
    # Loại bỏ ký tự đặc biệt, giữ lại chữ, số, gạch dưới, gạch ngang
    s = re.sub(r'[^a-z0-9_\-]', '_', s) # Thay thế bằng gạch dưới
    s = re.sub(r'[_]+', '_', s) # Nhiều gạch dưới thành 1
    s = s.strip('_')
    return s

def check_keyword_uniqueness_and_upsert(keyword, config, gsheet_handler, pinecone_handler):
    """
    Kiểm tra tính duy nhất của keyword dùng Pinecone.
    Nếu unique, upsert vào Pinecone và cập nhật Google Sheet.
    Trả về True nếu unique và xử lý thành công, False nếu không unique hoặc có lỗi.
    """
    logger.info(f"Checking uniqueness for keyword: '{keyword}'")
    if not pinecone_handler or not pinecone_handler.is_connected():
        logger.error("Pinecone handler not available or not connected. Cannot check uniqueness.")
        return False # Không thể tiếp tục nếu không có Pinecone

    # 1. Tạo embedding cho keyword
    embedding_vector = call_openai_embeddings(
        text_input=keyword,
        model_name=config.get('DEFAULT_OPENAI_EMBEDDINGS_MODEL'),
        api_key=config.get('OPENAI_API_KEY')
    )
    if not embedding_vector:
        logger.error(f"Failed to generate embedding for keyword '{keyword}'.")
        return False

    # 2. Cắt giảm chiều và chuẩn hóa L2 (logic từ Code6 node của bạn)
    cut_dim_vector = embedding_vector[:config.get('PINECONE_EMBEDDING_DIMENSION', 256)]
    norm_sq = sum(x*x for x in cut_dim_vector)
    if norm_sq == 0:
        normalized_embedding = cut_dim_vector # Tránh chia cho 0, giữ nguyên nếu là vector 0
    else:
        norm = norm_sq**0.5
        normalized_embedding = [x / norm for x in cut_dim_vector]
    
    # 3. Query Pinecone
    query_response = pinecone_handler.query_vectors(
        vector=normalized_embedding,
        top_k=1,
        include_values=False, # Không cần giá trị vector
        include_metadata=False # Không cần metadata
    )

    is_unique = True
    if query_response and query_response.matches:
        top_match = query_response.matches[0]
        score = top_match.score
        logger.info(f"Pinecone query for '{keyword}': Top match ID '{top_match.id}', Score: {score:.4f}")
        if score > config.get('PINECONE_SIMILARITY_THRESHOLD', 0.8):
            is_unique = False
            logger.warning(f"Keyword '{keyword}' is NOT unique. Similar to '{top_match.id}' with score {score:.4f}.")
    elif query_response is None : # Có lỗi khi query
        logger.error(f"Error during Pinecone query for '{keyword}'. Assuming not unique to be safe.")
        return False # Không thể xác định, dừng lại

    # 4. Xử lý kết quả
    gsheet_update_data = {config.get('GSHEET_USED_COLUMN'): "1"} # Mặc định đánh dấu đã xử lý

    if is_unique:
        logger.info(f"Keyword '{keyword}' is unique.")
        pinecone_id = normalize_keyword_for_pinecone_id(keyword) # Dùng keyword đã chuẩn hóa làm ID
        if not pinecone_id:
            logger.error(f"Generated empty Pinecone ID for keyword '{keyword}'. Cannot upsert.")
            return False

        upsert_result = pinecone_handler.upsert_vectors(
            vectors_with_ids=[{"id": pinecone_id, "values": normalized_embedding}] 
            # metadata có thể thêm nếu cần, ví dụ: {"original_keyword": keyword}
        )
        if upsert_result and upsert_result.upserted_count > 0:
            logger.info(f"Successfully upserted embedding for '{keyword}' (ID: {pinecone_id}) to Pinecone.")
            gsheet_update_data[config.get('GSHEET_UNIQUE_COLUMN')] = "yes"
        else:
            logger.error(f"Failed to upsert embedding for '{keyword}' to Pinecone. Response: {upsert_result}")
            # Quyết định xem có nên dừng ở đây không, hay vẫn coi là unique nhưng không upsert được
            return False # Dừng nếu không upsert được
    else: # Not unique
        gsheet_update_data[config.get('GSHEET_UNIQUE_COLUMN')] = "no"

    # Cập nhật Google Sheet
    if gsheet_handler:
        gsheet_handler.update_sheet_row_by_matching_column(
            spreadsheet_id_or_url=config.get('GSHEET_SPREADSHEET_ID'),
            sheet_name_or_gid=config.get('GSHEET_KEYWORD_SHEET_NAME'),
            match_column_header=config.get('GSHEET_KEYWORD_COLUMN'),
            match_value=keyword,
            data_to_update_dict=gsheet_update_data
        )
        logger.info(f"Updated Google Sheet for keyword '{keyword}': Used=1, Unique={gsheet_update_data.get(config.get('GSHEET_UNIQUE_COLUMN'))}")
    
    return is_unique # Trả về True nếu unique (và đã upsert thành công), False nếu không


def analyze_and_prepare_keyword(keyword_to_process, config, gsheet_handler, pinecone_handler):
    """
    Hàm tổng hợp cho Bước 1: Phân tích Keyword và Chuẩn bị.
    `keyword_to_process` là một string (từ Google Sheet).
    Trả về một dictionary chứa tất cả thông tin đã thu thập nếu thành công và keyword hợp lệ,
    nếu không thì trả về None.
    """
    preparation_data = {"original_keyword": keyword_to_process}

    # 0. Kiểm tra tính phù hợp (suitability) trước
    # Nếu Google Sheet đã có cột 'Suitable' và 'Uniqe', có thể check trước
    # Trong ví dụ này, ta giả sử luôn chạy check suitability nếu chưa được đánh dấu.
    if not check_keyword_suitability(keyword_to_process, config, gsheet_handler):
        logger.warning(f"Process stopped: Keyword '{keyword_to_process}' is not suitable.")
        return None # Dừng quy trình
    preparation_data["is_suitable"] = True

    # 1. Kiểm tra tính duy nhất (uniqueness) và upsert nếu unique
    # Nếu Google Sheet đã có cột 'Uniqe' và nó là 'yes', có thể bỏ qua check Pinecone lại
    # if keyword_data_from_sheet.get(config.get('GSHEET_UNIQUE_COLUMN')) == 'yes':
    #    logger.info(f"Keyword '{keyword_to_process}' already marked as unique. Skipping Pinecone check.")
    #    is_unique = True
    # else:
    is_unique = check_keyword_uniqueness_and_upsert(keyword_to_process, config, gsheet_handler, pinecone_handler)
    
    if not is_unique:
        logger.warning(f"Process stopped: Keyword '{keyword_to_process}' is not unique or error during uniqueness check.")
        return None # Dừng quy trình
    preparation_data["is_unique"] = True


    # 2. Chọn tác giả
    # Lấy author_personas từ config, chuyển thành chuỗi JSON
    author_personas_list = config.get('AUTHOR_PERSONAS', [])
    author_personas_json = json.dumps(author_personas_list)
    chosen_author = choose_author_for_topic(keyword_to_process, author_personas_json, config)
    if not chosen_author:
        logger.error(f"Failed to choose an author for keyword '{keyword_to_process}'. Cannot proceed.")
        return None # Lỗi nghiêm trọng, dừng lại
    preparation_data["chosen_author"] = chosen_author

    # 3. Lấy SERP data
    serp_data_str = get_serp_data_for_keyword(keyword_to_process, config)
    if not serp_data_str:
        # Có thể quyết định vẫn tiếp tục mà không có SERP, hoặc dừng lại
        logger.warning(f"Could not fetch SERP data for '{keyword_to_process}'. Analysis might be less accurate.")
        # Nếu SERP là bắt buộc cho bước tiếp theo, return None
        # return None 
    preparation_data["serp_data_string"] = serp_data_str # Có thể là None

    # 4. Phân tích SERP và Keyword
    keyword_analysis = analyze_serp_and_keyword(keyword_to_process, serp_data_str, config)
    if not keyword_analysis:
        logger.error(f"Failed to analyze keyword and SERP for '{keyword_to_process}'. Cannot proceed.")
        return None # Lỗi nghiêm trọng, dừng lại
    preparation_data["keyword_analysis"] = keyword_analysis
    
    logger.info(f"Step 1 (Analyze and Prepare Keyword) completed successfully for '{keyword_to_process}'.")
    return preparation_data


# --- main_orchestrator.py sẽ gọi hàm tương tự như sau ---
# if __name__ == "__main__":
#     # Đây là ví dụ, không phải code chạy thực tế ở đây
#     APP_CONFIG = load_app_config()
#     setup_logging(log_level_str="DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO")

#     # Khởi tạo handlers
#     gsheet_h = GoogleSheetsHandler(config=APP_CONFIG) # Cần file service_account.json
#     pinecone_h = PineconeHandler(config=APP_CONFIG)

#     if not gsheet_h.is_connected():
#         logger.critical("Could not connect to Google Sheets. Exiting.")
#         exit()
#     if not pinecone_h.is_connected():
#         logger.critical("Could not connect to Pinecone. Exiting.")
#         exit()
        
#     # Giả sử lấy keyword từ Google Sheet
#     # keyword_data_from_sheet = gsheet_h.get_sheet_data(...)
#     # current_keyword = keyword_data_from_sheet[0].get(APP_CONFIG.get('GSHEET_KEYWORD_COLUMN'))
#     current_keyword = "best budget electric guitar for beginners" # Ví dụ

#     if current_keyword:
#         analysis_and_preparation_result = analyze_and_prepare_keyword(
#             keyword_to_process=current_keyword,
#             config=APP_CONFIG,
#             gsheet_handler=gsheet_h,
#             pinecone_handler=pinecone_h
#         )

#         if analysis_and_preparation_result:
#             logger.info("=== Keyword Analysis and Preparation Result ===")
#             logger.info(json.dumps(analysis_and_preparation_result, indent=2))
#             # Tiếp tục với Bước 2: Tạo Outline
#             # outline_data = generate_initial_outline(analysis_and_preparation_result, APP_CONFIG)
#             # ...
#         else:
#             logger.error(f"Failed to analyze and prepare keyword: {current_keyword}")
#     else:
#         logger.info("No keyword to process.")