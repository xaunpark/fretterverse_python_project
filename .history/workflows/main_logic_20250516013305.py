# workflows/main_logic.py
import logging
import json
import re
import time # Cho việc sleep nếu cần
import html
import requests
from utils.api_clients import (
    call_openai_dalle, 
    create_wp_category, 
    get_wp_categories,
    upload_wp_media,
    create_wp_post, 
    update_wp_post,
    call_openai_chat,
    google_search,
    call_openai_embeddings
)
from utils.google_sheets_handler import GoogleSheetsHandler
from utils.redis_handler import RedisHandler
from utils.pinecone_handler import PineconeHandler
from utils.image_utils import resize_image
from utils.db_handler import MySQLHandler
from prompts import main_prompts, content_prompts, misc_prompts, image_prompts
from workflows import image_processor
from workflows import video_processor
from workflows import external_links_processor

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

###################################
### --- Bước 2: Tạo Outline --- ###
###################################

def generate_initial_outline(keyword_to_process, preparation_data, config):
    """
    Tạo outline ban đầu (title, slug, description, chapters) dựa trên kết quả phân tích.
    """
    keyword_analysis = preparation_data.get("keyword_analysis")
    if not keyword_analysis:
        logger.error("Keyword analysis data is missing. Cannot generate outline.")
        return None

    article_type = keyword_analysis.get("articleType", "Type 2: Informational") # Mặc định nếu không có
    logger.info(f"Generating initial outline for article type: {article_type}")

    if "type 1" in article_type.lower(): # "Type 1: Best Product List"
        prompt_template = main_prompts.OUTLINE_GENERATION_TYPE1_PROMPT
    else: # "Type 2: Informational" hoặc các loại khác
        prompt_template = main_prompts.OUTLINE_GENERATION_TYPE2_PROMPT

    semantic_keywords_list = keyword_analysis.get("semanticKeyword", [])
    semantic_keywords_str = ", ".join(semantic_keywords_list) if isinstance(semantic_keywords_list, list) else ""
    
    # Xử lý trường hợp semantic_keywords_list có thể là None hoặc không phải list
    if not semantic_keywords_str and isinstance(semantic_keywords_list, str):
        semantic_keywords_str = semantic_keywords_list # Nếu nó đã là string rồi

    formatted_prompt = prompt_template.format(
        keyword=keyword_to_process,
        search_intent=keyword_analysis.get("searchIntent", "N/A"),
        content_format=keyword_analysis.get("contentFormat", "N/A"),
        article_type=article_type,
        selected_model=keyword_analysis.get("selectedModel", "N/A"),
        semantic_keyword_list_string=semantic_keywords_str
    )

    try:
        initial_outline_json = call_openai_chat(
            prompt_messages=[{"role": "user", "content": formatted_prompt}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL_FOR_OUTLINE', config.get('DEFAULT_OPENAI_CHAT_MODEL')), # Có thể dùng model mạnh hơn cho outline
            api_key=config.get('OPENAI_API_KEY'),
            is_json_output=True # Prompt yêu cầu JSON
        )

        if initial_outline_json and isinstance(initial_outline_json, dict) and \
           all(k in initial_outline_json for k in ['title', 'slug', 'description', 'chapters']):
            logger.info(f"Successfully generated initial outline for '{keyword_to_process}'. Title: {initial_outline_json.get('title')}")
            # Đảm bảo 'chapters' là một list
            if not isinstance(initial_outline_json.get('chapters'), list):
                logger.error(f"Initial outline 'chapters' is not a list: {initial_outline_json.get('chapters')}")
                initial_outline_json['chapters'] = [] # Hoặc xử lý lỗi khác
            return initial_outline_json
        else:
            logger.error(f"Invalid or incomplete initial outline from LLM for '{keyword_to_process}'. Response: {initial_outline_json}")
            return None
    except Exception as e:
        logger.error(f"Error generating initial outline for '{keyword_to_process}': {e}", exc_info=True)
        return None

def enrich_outline_with_author_hooks(keyword_to_process, initial_outline_dict, chosen_author_data, config):
    """
    Thêm authorInfo và sectionHook vào mỗi chapter/subchapter của outline.
    """
    if not initial_outline_dict or not isinstance(initial_outline_dict.get("chapters"), list):
        logger.error("Initial outline is invalid or missing chapters. Cannot enrich.")
        return None
    if not chosen_author_data or not chosen_author_data.get("name") or not chosen_author_data.get("info"):
        logger.error("Chosen author data is invalid. Cannot enrich outline.")
        return None # Hoặc dùng author mặc định nếu có

    logger.info(f"Enriching outline with author info for '{chosen_author_data.get('name')}' and section hooks.")
    
    try:
        initial_outline_json_string = json.dumps(initial_outline_dict) # Chuyển dict thành chuỗi JSON cho prompt
    except TypeError as e:
        logger.error(f"Could not serialize initial_outline_dict to JSON: {e}", exc_info=True)
        return None


    prompt = main_prompts.ENRICH_OUTLINE_WITH_AUTHOR_AND_HOOKS_PROMPT.format(
        keyword=keyword_to_process,
        initial_outline_json_string=initial_outline_json_string,
        author_name=chosen_author_data.get("name"),
        author_bio=chosen_author_data.get("info")
    )

    try:
        enriched_outline_json = call_openai_chat(
            prompt_messages=[{"role": "user", "content": prompt}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL_FOR_OUTLINE', config.get('DEFAULT_OPENAI_CHAT_MODEL')),
            api_key=config.get('OPENAI_API_KEY'),
            is_json_output=True # Prompt yêu cầu JSON
        )

        if enriched_outline_json and isinstance(enriched_outline_json, dict) and \
           isinstance(enriched_outline_json.get('chapters'), list):
            # Kiểm tra sơ bộ xem các chapter có key mới không
            if enriched_outline_json['chapters']:
                first_chapter = enriched_outline_json['chapters'][0]
                if 'authorInfo' not in first_chapter or 'sectionHook' not in first_chapter:
                    logger.warning("Enriched outline chapters might be missing 'authorInfo' or 'sectionHook'.")
            logger.info(f"Successfully enriched outline for '{keyword_to_process}'.")
            return enriched_outline_json # Trả về toàn bộ object outline đã được enrich
        else:
            logger.error(f"Invalid or incomplete enriched outline from LLM for '{keyword_to_process}'. Response: {enriched_outline_json}")
            # Fallback: trả về initial_outline_dict nếu enrich thất bại để quy trình có thể tiếp tục (tùy chọn)
            logger.warning("Falling back to initial outline due to enrichment failure.")
            return initial_outline_dict 
            # return None # Hoặc dừng nếu enrich là bắt buộc
    except Exception as e:
        logger.error(f"Error enriching outline for '{keyword_to_process}': {e}", exc_info=True)
        return initial_outline_dict # Fallback

def process_sections_from_outline(enriched_outline_dict, keyword_to_process, keyword_analysis_data, config):
    """
    Chuyển đổi cấu trúc 'chapters' từ LLM thành một danh sách phẳng các section.
    Tương đương logic của Code Node "sectionName & sectionType" (ID 9c186d86...).
    Thêm sectionNameTag, motherChapter.
    """
    if not enriched_outline_dict or not isinstance(enriched_outline_dict.get("chapters"), list):
        logger.error("Enriched outline is invalid or missing chapters. Cannot process sections.")
        return []

    processed_sections = []
    section_index_counter = 1 # Bắt đầu từ 1
    
    title = enriched_outline_dict.get("title", "N/A Title")
    slug = enriched_outline_dict.get("slug", "n-a-slug")
    description = enriched_outline_dict.get("description", "N/A description")
    
    article_type_str = keyword_analysis_data.get("articleType", "").lower()
    is_type1_buying_guide = "type 1" in article_type_str

    chapters_from_llm = enriched_outline_dict.get("chapters", [])
    total_chapters_in_llm_outline = len(chapters_from_llm)

    for i, chapter_llm in enumerate(chapters_from_llm):
        section_name_tag = ""
        if i == 0:
            section_name_tag = "Introduction"
        elif i == 1 and is_type1_buying_guide:
            # Chapter thứ hai của Type 1 là "Top Rated Products"
            # LLM có thể đặt tên khác, nhưng tag này giúp nhận diện vai trò
            section_name_tag = "Top Rated" 
        elif i == total_chapters_in_llm_outline - 1:
            section_name_tag = "Conclusion"
        elif i == total_chapters_in_llm_outline - 2 and total_chapters_in_llm_outline > 1: # Đảm bảo không phải là chapter cuối nếu chỉ có 1-2 chapter
            # Kiểm tra xem chapter này có phải là FAQs không (LLM thường đặt tên là "FAQs" hoặc "Frequently Asked Questions")
            if "faq" in chapter_llm.get("chapterName", "").lower() or \
               "frequently asked questions" in chapter_llm.get("chapterName", "").lower():
                section_name_tag = "FAQs"
        
        has_subchapters = isinstance(chapter_llm.get("subchapters"), list) and len(chapter_llm.get("subchapters")) > 0
        mother_chapter_status = "yes" if has_subchapters else "no"

        chapter_data_for_list = {
            "sectionName": chapter_llm.get("chapterName", f"Unnamed Chapter {i+1}"),
            "sectionType": 'chapter',
            "sectionIndex": section_index_counter,
            "headline": None, # Chapters không có headline theo logic n8n
            "modelRole": chapter_llm.get("modelRole", "N/A"),
            "length": chapter_llm.get("length", config.get("DEFAULT_CHAPTER_LENGTH", 200)),
            "motherChapter": mother_chapter_status,
            "sectionNameTag": section_name_tag,
            "authorInfo": chapter_llm.get("authorInfo", ""), # Từ outline đã enrich
            "separatedSemanticKeyword": chapter_llm.get("separatedSemanticKeyword", []), # Từ outline
            "sectionHook": chapter_llm.get("sectionHook", ""), # Từ outline đã enrich
            # Thông tin chung của bài viết
            "article_title": title,
            "article_slug": slug,
            "article_description": description,
            "original_keyword": keyword_to_process,
            "originalIndex": section_index_counter -1 # Giữ index gốc 0-based nếu cần
        }
        processed_sections.append(chapter_data_for_list)
        section_index_counter += 1

        if has_subchapters:
            parent_chapter_name = chapter_llm.get("chapterName")
            for sub_idx, subchapter_llm in enumerate(chapter_llm.get("subchapters", [])):
                sub_section_name_tag = ""
                # Nếu chapter cha là "Top Rated", các sub của nó là "Product"
                if section_name_tag == "Top Rated" and is_type1_buying_guide:
                    sub_section_name_tag = "Product"
                
                subchapter_data_for_list = {
                    "sectionName": subchapter_llm.get("subchapterName", f"Unnamed Subchapter {i+1}.{sub_idx+1}"),
                    "sectionType": 'subchapter',
                    "sectionIndex": section_index_counter,
                    "headline": subchapter_llm.get("headline"), # Subchapters (đặc biệt là product) có thể có headline
                    "modelRole": subchapter_llm.get("modelRole", "N/A"),
                    "length": subchapter_llm.get("length", config.get("DEFAULT_SUBCHAPTER_LENGTH", 150)),
                    "motherChapter": "no", # Subchapters không phải là mother
                    "sectionNameTag": sub_section_name_tag,
                    "authorInfo": subchapter_llm.get("authorInfo", ""),
                    "separatedSemanticKeyword": subchapter_llm.get("separatedSemanticKeyword", []),
                    "sectionHook": subchapter_llm.get("sectionHook", ""),
                    "parentChapterName": parent_chapter_name, # Thêm thông tin chapter cha
                    # Thông tin chung của bài viết
                    "article_title": title,
                    "article_slug": slug,
                    "article_description": description,
                    "original_keyword": keyword_to_process,
                    "originalIndex": section_index_counter -1
                }
                processed_sections.append(subchapter_data_for_list)
                section_index_counter += 1
    
    logger.info(f"Processed {len(processed_sections)} sections from LLM outline for '{keyword_to_process}'.")
    return processed_sections


def create_article_outline_step(keyword_to_process, preparation_data, config):
    """
    Hàm tổng hợp cho Bước 2: Tạo Outline.
    Sử dụng `preparation_data` từ Bước 1.
    Trả về một dictionary chứa 'initial_outline', 'enriched_outline', và 'processed_sections_list'.
    Hoặc None nếu có lỗi.
    """
    if not preparation_data:
        logger.error("Preparation data is missing, cannot proceed with outline creation.")
        return None

    # 1. Tạo outline ban đầu
    initial_outline = generate_initial_outline(keyword_to_process, preparation_data, config)
    if not initial_outline:
        logger.error(f"Failed to generate initial outline for '{keyword_to_process}'.")
        return None
    
    # 2. Enrich outline với authorInfo và sectionHook
    chosen_author = preparation_data.get("chosen_author")
    enriched_outline = enrich_outline_with_author_hooks(keyword_to_process, initial_outline, chosen_author, config)
    if not enriched_outline: # Nếu enrich thất bại, có thể dùng initial_outline (nếu logic cho phép)
        logger.warning(f"Failed to enrich outline for '{keyword_to_process}', using initial outline for further processing.")
        enriched_outline = initial_outline # Hoặc `return None` nếu enrich là bắt buộc

    # 3. Xử lý/Flatten danh sách section từ outline đã enrich
    keyword_analysis = preparation_data.get("keyword_analysis")
    processed_sections = process_sections_from_outline(enriched_outline, keyword_to_process, keyword_analysis, config)
    if not processed_sections:
        logger.error(f"Failed to process sections from outline for '{keyword_to_process}'.")
        return None # Không có section để viết

    logger.info(f"Step 2 (Create Outline) completed successfully for '{keyword_to_process}'.")
    return {
        "initial_outline_raw": initial_outline, # LLM output gốc cho outline ban đầu
        "enriched_outline_raw": enriched_outline, # LLM output gốc cho outline đã enrich
        "processed_sections_list": processed_sections, # Danh sách section đã flatten và chuẩn hóa
        "article_meta": { # Thu thập các meta data quan trọng ở đây
            "title": enriched_outline.get("title"),
            "slug": enriched_outline.get("slug"),
            "description": enriched_outline.get("description"), # SEO description / Excerpt
            "article_type": keyword_analysis.get("articleType"),
            "chosen_author_id": chosen_author.get("ID"),
            "original_keyword": keyword_to_process
        }
    }

##################################################
### --- Bước 3: Viết Nội dung từng Section --- ###
##################################################

def _generate_prompt_for_section_content(section_data, article_meta, chosen_author_data, 
                                         all_section_names_list_str, preparation_data, config):
    """
    Tạo prompt cụ thể để LLM viết nội dung cho một section.
    """
    s_name = section_data.get("sectionName")
    s_type = section_data.get("sectionType")
    s_name_tag = section_data.get("sectionNameTag", "").lower()
    s_model_role = section_data.get("modelRole", "N/A")
    s_length = section_data.get("length", 200) # Độ dài mặc định
    s_hook_text = section_data.get("sectionHook", "")
    s_author_info = section_data.get("authorInfo", chosen_author_data.get("info", "")) # Dùng author info chung nếu section không có info riêng
    s_semantic_keywords_list = section_data.get("separatedSemanticKeyword", [])
    s_semantic_keywords_str = ", ".join(s_semantic_keywords_list) if isinstance(s_semantic_keywords_list, list) else (s_semantic_keywords_list or "")

    article_title = article_meta.get("title", "N/A Article Title")
    # article_type = article_meta.get("article_type", "N/A Type") # Có thể cần cho một số prompt
    selected_model = preparation_data.get("keyword_analysis", {}).get("selectedModel", "N/A") # Lấy từ preparation_data
    
    author_name = chosen_author_data.get("name", "The Author")

    prompt_section_hook_instruction = ""
    if s_hook_text:
        prompt_section_hook_instruction = f"Incorporate an engaging hook '{s_hook_text}' at a point where it best enhances the narrative. The hook should be strategically placed to captivate the reader's interest and lead seamlessly into the pivotal content of the chapter, setting the tone and context for what's to come."

    prompt_template = None

    if s_name_tag == "introduction":
        # Sử dụng prompt có lựa chọn hook, cần thêm {keyword_for_hook}
        # Giả sử keyword_for_hook là original_keyword
        keyword_for_hook = section_data.get("original_keyword", article_title)
        prompt_template = content_prompts.WRITE_INTRODUCTION_PROMPT_WITH_HOOK_CHOICES
        return prompt_template.format(
            length=s_length,
            article_title=article_title,
            keyword_for_hook=keyword_for_hook, # Placeholder mới
            semantic_keywords=s_semantic_keywords_str,
            author_name=author_name,
            author_info=s_author_info, # authorInfo cụ thể cho section Intro
            section_names_list=all_section_names_list_str
        )
    elif s_name_tag == "conclusion":
        prompt_template = content_prompts.WRITE_CONCLUSION_PROMPT
    elif s_name_tag == "faqs":
        prompt_template = content_prompts.WRITE_FAQ_SECTION_PROMPT
        # FAQ prompt chỉ cần article_title
        return prompt_template.format(article_title=article_title)

    # Xử lý các chapter/subchapter thông thường
    elif s_type == 'chapter':
        # Kiểm tra nếu chapter này chỉ là container (ví dụ: motherChapter='yes' và không có tag đặc biệt)
        # Dựa trên logic n8n của bạn: `sectionType === 'chapter' && nextSection?.sectionType === 'subchapter'`
        # Điều này khó xác định ở đây nếu chỉ dựa vào `section_data` đơn lẻ.
        # Giả định: nếu là motherChapter và không phải Intro/Conclusion/FAQ/TopRated, thì có thể là container.
        if section_data.get("motherChapter") == "yes" and s_name_tag not in ["introduction", "conclusion", "faqs", "top rated"]:
             logger.info(f"Section '{s_name}' is a motherChapter and not a special type, using 'SAY_I_LOVE_YOU_PROMPT'.")
             return content_prompts.SAY_I_LOVE_YOU_PROMPT # Không cần format
        prompt_template = content_prompts.WRITE_CHAPTER_PROMPT
    
    elif s_type == 'subchapter':
        if s_name_tag == "product": # Đây là Product Review Subchapter
            prompt_template = content_prompts.WRITE_PRODUCT_REVIEW_SUBCHAPTER_PROMPT
            # Product review cần thêm {headline} và {product_list}
            # product_list cần được tạo từ danh sách các subchapter có sectionNameTag="Product"
            # Việc này nên được thực hiện ở hàm gọi và truyền vào đây.
            # Tạm thời để placeholder, sẽ cần logic tạo product_list_str riêng.
            return prompt_template.format(
                length=s_length,
                section_name=s_name,
                headline=section_data.get("headline", f"Review of {s_name}"), # Lấy headline từ section_data
                parent_section_name=section_data.get("parentChapterName", "the main topic"),
                article_title=article_title,
                model_role=s_model_role,
                selected_model=selected_model,
                prompt_section_hook=prompt_section_hook_instruction,
                semantic_keywords=s_semantic_keywords_str,
                author_name=author_name,
                author_info=s_author_info,
                product_list=section_data.get("product_list_for_comparison", "other related products"), # Cần truyền vào
                section_names_list=all_section_names_list_str
            )
        else: # Subchapter thông thường
            prompt_template = content_prompts.WRITE_SUBCHAPTER_PROMPT
            return prompt_template.format(
                length=s_length,
                section_name=s_name,
                parent_section_name=section_data.get("parentChapterName", "the main topic"),
                article_title=article_title,
                model_role=s_model_role,
                selected_model=selected_model,
                prompt_section_hook=prompt_section_hook_instruction,
                semantic_keywords=s_semantic_keywords_str,
                author_name=author_name,
                author_info=s_author_info,
                section_names_list=all_section_names_list_str
            )
    
    if not prompt_template: # Trường hợp không xác định được template (không nên xảy ra)
        logger.error(f"Could not determine prompt template for section: {s_name}, type: {s_type}, tag: {s_name_tag}")
        return None

    # Format cho các prompt còn lại (Conclusion, Chapter)
    return prompt_template.format(
        length=s_length,
        section_name=s_name, # Chỉ có ở WRITE_CHAPTER_PROMPT
        article_title=article_title,
        model_role=s_model_role,
        selected_model=selected_model,
        prompt_section_hook=prompt_section_hook_instruction,
        semantic_keywords=s_semantic_keywords_str,
        author_name=author_name,
        author_info=s_author_info,
        section_names_list=all_section_names_list_str
    )

def write_content_for_all_sections_step(processed_sections_list, article_meta, preparation_data, config):
    """
    Lặp qua từng section và gọi LLM để viết nội dung HTML.
    Trả về một list các dictionaries, mỗi dict chứa thông tin section và 'html_content'.
    """
    if not processed_sections_list:
        logger.error("No processed sections to write content for.")
        return []

    chosen_author_data = preparation_data.get("chosen_author")
    if not chosen_author_data:
        logger.error("Chosen author data is missing. Cannot write section content.")
        return [] # Hoặc trả về sections_list gốc với content rỗng

    sections_with_written_content = []
    all_section_names = [s.get("sectionName") for s in processed_sections_list if s.get("sectionName")]
    all_section_names_list_str = ", ".join(all_section_names)

    # Chuẩn bị product_list_for_comparison cho các product review subchapters
    product_names_for_comparison = [
        s.get("sectionName") for s in processed_sections_list 
        if s.get("sectionType") == "subchapter" and s.get("sectionNameTag", "").lower() == "product"
    ]
    product_list_for_comparison_str = ", ".join(product_names_for_comparison) if product_names_for_comparison else "other available products"

    # Gán product_list_for_comparison vào từng section_data nếu là product
    for section_data in processed_sections_list:
        if section_data.get("sectionType") == "subchapter" and section_data.get("sectionNameTag", "").lower() == "product":
            section_data["product_list_for_comparison"] = product_list_for_comparison_str


    for section_data in processed_sections_list:
        section_copy = dict(section_data) # Làm việc trên bản copy
        logger.info(f"--- Writing content for section: {section_copy.get('sectionName')} (Index: {section_copy.get('sectionIndex')}) ---")

        prompt_for_llm = _generate_prompt_for_section_content(
            section_data=section_copy,
            article_meta=article_meta,
            chosen_author_data=chosen_author_data,
            all_section_names_list_str=all_section_names_list_str,
            preparation_data=preparation_data, # TRUYỀN VÀO ĐÂY
            config=config
        )

        html_content = ""
        if prompt_for_llm == content_prompts.SAY_I_LOVE_YOU_PROMPT:
            logger.info(f"Section '{section_copy.get('sectionName')}' is a container, content will be 'I love you' (ignored).")
            html_content = "<!-- Container Chapter - No Content Needed -->" # Hoặc để rỗng
        elif prompt_for_llm:
            logger.debug(f"Prompt for LLM (section: {section_copy.get('sectionName')}):\n{prompt_for_llm[:300]}...") # Log phần đầu prompt
            
            # Sử dụng model mạnh hơn cho content writing nếu cần
            content_model = config.get('DEFAULT_OPENAI_CHAT_MODEL_FOR_CONTENT', config.get('DEFAULT_OPENAI_CHAT_MODEL'))
            if section_copy.get('sectionNameTag', '').lower() == 'faqs': # FAQ có thể dùng model thường
                content_model = config.get('DEFAULT_OPENAI_CHAT_MODEL')

            llm_response = call_openai_chat(
                prompt_messages=[{"role": "user", "content": prompt_for_llm}],
                model_name=content_model,
                api_key=config.get('OPENAI_API_KEY'),
                is_json_output=False # Nội dung là HTML string, không phải JSON
            )
            if llm_response:
                # Kiểm tra nếu LLM trả về "I love you" (dù không nên nếu prompt khác)
                if "i love you" in llm_response.lower() and len(llm_response) < 20:
                    logger.info(f"LLM responded with 'I love you' for section '{section_copy.get('sectionName')}'. Treating as no content.")
                    html_content = "<!-- LLM Fallback to ILY - No Content -->"
                else:
                    html_content = llm_response
                    # Optional: Basic HTML sanitization or validation if needed
                    logger.info(f"Successfully generated content for section '{section_copy.get('sectionName')}' (Length: {len(html_content)}).")
            else:
                logger.error(f"Failed to generate content from LLM for section '{section_copy.get('sectionName')}'.")
                html_content = f"<!-- Error generating content for {section_copy.get('sectionName')} -->"
        else:
            logger.warning(f"No prompt generated for section '{section_copy.get('sectionName')}'. Skipping content generation.")
            html_content = "<!-- No prompt for this section -->"
            
        section_copy["html_content"] = html_content
        sections_with_written_content.append(section_copy)
        
        # Thêm delay nhỏ giữa các API call để tránh rate limit (tùy chỉnh)
        # time.sleep(config.get("API_CALL_DELAY_CONTENT", 1)) 

    logger.info("Step 3 (Write Content for All Sections) completed.")
    return sections_with_written_content


###################################################
### --- Bước 4: Xử lý Sub-Workflows và Tổng hợp ###
###################################################

def _initialize_redis_keys_for_subworkflows(redis_handler, config, unique_run_id):
    """Khởi tạo/reset các key Redis cần thiết cho các sub-workflows."""
    if not redis_handler or not redis_handler.is_connected():
        logger.error("Redis not connected. Cannot initialize keys for sub-workflows.")
        return False

    # Image processor keys
    img_keys = image_processor._get_redis_keys(config, unique_run_id) # Giả sử hàm này có trong image_processor
    redis_handler.initialize_array_if_not_exists(img_keys['image_array'], "[]")
    redis_handler.initialize_array_if_not_exists(img_keys['failed_urls'], "[]")
    redis_handler.initialize_array_if_not_exists(img_keys['used_urls'], "[]")
    # Không cần xóa current_image_search_results_prefix ở đây, hàm con sẽ tự quản lý

    # Video processor key
    vid_key = video_processor._get_redis_video_array_key(config, unique_run_id) # Giả sử hàm này có
    redis_handler.initialize_array_if_not_exists(vid_key, "[]")

    # External links processor key
    ext_key = external_links_processor._get_redis_exlinks_array_key(config, unique_run_id) # Giả sử
    redis_handler.initialize_array_if_not_exists(ext_key, "[]")
    
    logger.info(f"Initialized Redis keys for sub-workflows with run_id: {unique_run_id}")
    return True


def process_sub_workflows_step(sections_with_initial_content, article_meta, config, unique_run_id):
    """
    Gọi các sub-workflow để xử lý images, videos, external links.
    sections_with_initial_content: List các section với html_content từ Bước 3.
    article_meta: Chứa article_title.
    unique_run_id: ID duy nhất cho lần chạy này.

    Trả về một dictionary chứa:
        - 'sections_after_external_links': list các section với HTML đã chèn external links.
        - 'final_image_data_list': list thông tin ảnh cho từng section.
        - 'final_video_data_list': list thông tin video cho từng section.
    Hoặc None nếu có lỗi nghiêm trọng.
    """
    if not sections_with_initial_content:
        logger.error("No sections with initial content provided for sub-workflow processing.")
        return None

    article_title = article_meta.get("title", "Untitled Article")
    logger.info(f"--- Starting Step 4: Sub-Workflow Processing for article '{article_title}', run_id: {unique_run_id} ---")

    redis_h = RedisHandler(config=config)
    if not _initialize_redis_keys_for_subworkflows(redis_h, config, unique_run_id):
        logger.error("Failed to initialize Redis keys. Aborting sub-workflow processing.")
        return None

    # 1. Xử lý External Links trước (vì nó thay đổi html_content)
    # sections_with_initial_content là list các dict, mỗi dict có key 'current_html_content'
    # mà external_links_processor cần đọc và cập nhật.
    # Đổi tên key cho rõ ràng hơn
    sections_for_ext_links = []
    for sec_data in sections_with_initial_content:
        copy_sec = dict(sec_data)
        # external_links_processor mong đợi key 'current_html_content'
        copy_sec['current_html_content'] = sec_data.get('html_content', '') 
        sections_for_ext_links.append(copy_sec)

    logger.info("Starting external links processing...")
    sections_after_external_links = external_links_processor.process_external_links_for_article(
        sections_with_content_list=sections_for_ext_links, # Truyền list section có html_content
        article_title_main=article_title,
        config=config,
        unique_run_id=unique_run_id
    )
    if not sections_after_external_links:
        logger.error("External links processing failed. Proceeding without external links.")
        # Quyết định: Dừng lại hay tiếp tục? Tạm thời tiếp tục và dùng content cũ.
        sections_after_external_links = sections_with_initial_content
    else:
        # Cập nhật lại key 'html_content' trong list gốc để các bước sau dùng
        temp_dict_after_ext_links = {s['sectionIndex']: s['current_html_content'] for s in sections_after_external_links}
        for i, sec in enumerate(sections_with_initial_content):
            sections_with_initial_content[i]['html_content'] = temp_dict_after_ext_links.get(
                sec['sectionIndex'], 
                sec['html_content'] # Fallback nếu sectionIndex không tìm thấy (không nên xảy ra)
            )
        logger.info("External links processing completed.")


    # 2. Xử lý Images
    # image_processor cần list các section_data (không nhất thiết phải có html_content)
    # Nó sẽ tự đọc/lưu image_array vào Redis dựa trên unique_run_id.
    logger.info("Starting image processing...")
    # `process_images_for_article` nên trả về list các image_data mà nó đã xử lý trong lần chạy đó
    # hoặc main_logic có thể đọc trực tiếp từ Redis sau khi hàm này chạy xong.
    # Để đơn giản, giả sử nó trả về list kết quả.
    final_image_data_list = image_processor.process_images_for_article(
        sections_data_list=sections_with_initial_content, # Truyền list section đã có index, type, name, etc.
        article_title=article_title,
        config=config,
        unique_run_id=unique_run_id
    )
    if not final_image_data_list:
        logger.warning("Image processing did not return data. Assuming no images or errors occurred.")
        final_image_data_list = [] # Đảm bảo là list
    logger.info("Image processing completed.")

    # 3. Xử lý Videos
    # Tương tự image_processor
    logger.info("Starting video processing...")
    final_video_data_list = video_processor.process_videos_for_article(
        sections_data_list=sections_with_initial_content,
        article_title=article_title,
        config=config,
        unique_run_id=unique_run_id
    )
    if not final_video_data_list:
        logger.warning("Video processing did not return data. Assuming no videos or errors occurred.")
        final_video_data_list = [] # Đảm bảo là list
    logger.info("Video processing completed.")

    logger.info(f"--- Step 4 (Sub-Workflow Processing) completed for run_id: {unique_run_id} ---")
    
    return {
        # Trả về list section với html_content đã được cập nhật bởi external_links_processor
        "sections_final_content_structure": sections_with_initial_content,
        "final_image_data_list": final_image_data_list,
        "final_video_data_list": final_video_data_list
    }

######################################################
#### --- Bước 5: Tạo Nội dung HTML Hoàn chỉnh --- ####
######################################################

def _generate_comparison_table_if_needed(article_meta, processed_sections_list, config):
    """
    Nếu là Article Type 1, tạo productList và gọi LLM để tạo HTML bảng so sánh.
    processed_sections_list: Danh sách section đã được flatten từ Bước 2 (dùng để lấy productList).
    """
    article_type = article_meta.get("article_type", "").lower()
    article_title = article_meta.get("title", "N/A")

    if "type 1" not in article_type:
        logger.info("Not a Type 1 article, skipping comparison table generation.")
        return None

    # Trích xuất productList từ processed_sections_list (các subchapter của "Top Rated" chapter)
    product_names = []
    is_top_rated_chapter_found = False
    for section in processed_sections_list:
        # Tìm chapter "Top Rated"
        if section.get("sectionType") == "chapter" and section.get("sectionNameTag", "").lower() == "top rated":
            is_top_rated_chapter_found = True
            continue # Bỏ qua chính chapter "Top Rated"
        
        # Nếu đã tìm thấy "Top Rated" và section hiện tại là subchapter của nó
        if is_top_rated_chapter_found and section.get("sectionType") == "subchapter" and section.get("sectionNameTag", "").lower() == "product":
            product_names.append(section.get("sectionName"))
        
        # Nếu gặp chapter tiếp theo sau "Top Rated", dừng lại
        if is_top_rated_chapter_found and section.get("sectionType") == "chapter" and section.get("sectionNameTag", "").lower() != "top rated":
            break # Dừng tìm product nếu đã qua khỏi các sub của Top Rated

    if not product_names:
        logger.warning(f"Type 1 article '{article_title}' but no product names found in outline for comparison table.")
        return None

    product_list_string = ", ".join(product_names)
    logger.info(f"Generating comparison table for products: {product_list_string}")

    prompt = misc_prompts.GENERATE_HTML_COMPARISON_TABLE_PROMPT.format(
        article_title_for_table=article_title,
        product_list_string=product_list_string
    )

    try:
        # Có thể dùng model mạnh hơn cho việc này vì nó cần suy luận nhiều
        table_model = config.get('DEFAULT_OPENAI_CHAT_MODEL_FOR_TABLE', config.get('DEFAULT_OPENAI_CHAT_MODEL'))
        comparison_table_html = call_openai_chat(
            prompt_messages=[{"role": "user", "content": prompt}],
            model_name=table_model,
            api_key=config.get('OPENAI_API_KEY'),
            is_json_output=False # Mong đợi HTML string
        )
        if comparison_table_html and "<table>" in comparison_table_html:
            logger.info("Successfully generated HTML comparison table.")
            # Trong workflow n8n, bạn có node "Regex extractedTable".
            # Nếu LLM trả về nhiều text hơn chỉ là table, bạn cần trích xuất table.
            # Giả sử LLM trả về HTML table sạch.
            match = re.search(r'(<table[\s\S]*?<\/table>)', comparison_table_html, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1)
            else:
                logger.warning("Could not extract <table> from LLM response for comparison table. Using full response.")
                return comparison_table_html # Hoặc xử lý lỗi
        else:
            logger.error(f"Failed to generate valid HTML for comparison table. Response: {comparison_table_html[:200]}...")
            return None
    except Exception as e:
        logger.error(f"Error generating comparison table: {e}", exc_info=True)
        return None


def _generate_youtube_iframe_html(video_id):
    """Tạo mã HTML iframe cho YouTube video."""
    if not video_id or video_id.lower() == "none":
        return ""
    # Sử dụng html.escape cho video_id nếu có ký tự đặc biệt (mặc dù ID YouTube thường an toàn)
    escaped_video_id = html.escape(video_id)
    return f"""
<div style="text-align:center; margin-top: 20px; margin-bottom: 20px;">
    <iframe width="560" height="315" src="https://www.youtube.com/embed/{escaped_video_id}" 
            frameborder="0" 
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" 
            referrerpolicy="strict-origin-when-cross-origin" 
            allowfullscreen>
    </iframe>
</div>
"""

def _generate_section_id_from_name(section_name):
    """Tạo ID HTML an toàn từ tên section (tương tự logic slugify)."""
    if not section_name: return ""
    s = section_name.lower()
    s = re.sub(r'\s+', '-', s) # Thay khoảng trắng bằng gạch ngang
    s = re.sub(r'[^a-z0-9-]', '', s) # Bỏ ký tự không phải chữ, số, gạch ngang
    s = s.strip('-')
    return s if s else "section" # Fallback nếu tên rỗng sau khi chuẩn hóa


def assemble_full_html_step(sub_workflow_results, article_meta, processed_sections_list_from_step2, config):
    """
    Ghép nối tất cả nội dung, ảnh, video, bảng so sánh thành một chuỗi HTML hoàn chỉnh.
    sub_workflow_results: Kết quả từ Bước 4.
    processed_sections_list_from_step2: Dùng để lấy productList cho bảng so sánh.
    """
    if not sub_workflow_results or not sub_workflow_results.get("sections_final_content_structure"):
        logger.error("Missing processed sections from sub-workflows. Cannot assemble HTML.")
        return None

    sections_to_assemble = sub_workflow_results.get("sections_final_content_structure")
    image_data_map = {item['index']: item for item in sub_workflow_results.get("final_image_data_list", []) if item.get('url') and 'error' not in item.get('url') and 'skip' not in item.get('url')}
    video_data_map = {item['index']: item for item in sub_workflow_results.get("final_video_data_list", []) if item.get('videoID') and item.get('videoID') != 'none'}

    # 1. Tạo bảng so sánh nếu cần
    comparison_table_html_content = _generate_comparison_table_if_needed(
        article_meta,
        processed_sections_list_from_step2, # Cần list section gốc từ Bước 2
        config
    )

    full_html_parts = []
    is_comparison_table_inserted = False

    for section_data in sections_to_assemble:
        s_name = section_data.get("sectionName", "Unnamed Section")
        s_type = section_data.get("sectionType")
        s_index = section_data.get("sectionIndex")
        s_html_content_with_ext_links = section_data.get("html_content", "") # Đã có external links
        s_headline = section_data.get("headline")
        s_name_tag = section_data.get("sectionNameTag", "").lower()
        s_mother_chapter = section_data.get("motherChapter", "no").lower()

        section_html_parts = []

        # --- A. Thêm tiêu đề section (H2 cho chapter, H3 cho subchapter) ---
        # Bỏ qua tiêu đề cho Introduction (thường tiêu đề bài viết đã đủ)
        # và FAQs, Conclusion (LLM thường tự tạo tiêu đề bên trong content)
        # Hoặc bạn có thể nhất quán luôn tạo H2/H3
        section_id = _generate_section_id_from_name(s_name)

        if s_type == "chapter" and s_name_tag not in ["introduction"]: # Không thêm H2 cho Intro
            section_html_parts.append(f'<h2 id="{section_id}">{html.escape(s_name)}</h2>')
        elif s_type == "subchapter":
            section_html_parts.append(f'<h3 id="{section_id}" style="text-align: center;">{html.escape(s_name)}</h3>')
            if s_headline: # Headline cho subchapter (thường là product review)
                section_html_parts.append(f'<h4 style="text-align: center;">{html.escape(s_headline)}</h4>')
        
        # --- B. Chèn bảng so sánh ---
        # Chèn sau chapter "Top Rated Products" (nếu có) hoặc sau chapter mẹ đầu tiên có sub (nếu là Type 1)
        # Logic n8n: chèn vào "chapter đầu tiên có motherChapter là 'yes'"
        if comparison_table_html_content and not is_comparison_table_inserted and \
           s_type == "chapter" and s_mother_chapter == "yes" and \
           "type 1" in article_meta.get("article_type", "").lower(): # Chỉ cho Type 1
            # Hoặc bạn có thể có một sectionNameTag cụ thể để chèn bảng (ví dụ: "ComparisonSection")
            # Hoặc chèn sau chapter có tag "Top Rated"
            if s_name_tag == "top rated" or config.get("INSERT_TABLE_AFTER_FIRST_MOTHER_CHAPTER_TYPE1", True):
                logger.info(f"Inserting comparison table after/in section: {s_name}")
                section_html_parts.append(comparison_table_html_content)
                is_comparison_table_inserted = True # Chỉ chèn một lần

        # --- C. Chèn Ảnh ---
        # Ảnh không chèn cho Intro, FAQ, Conclusion, motherChapter (theo logic image_processor)
        image_info = image_data_map.get(s_index)
        if image_info and image_info.get('url') not in ["skipped_section_type", "not_inserted_by_default"] and "error" not in image_info.get('url'):
            # image_processor._should_skip_image đã xử lý việc không chèn vào các section đặc biệt
            # và mother chapters. Vậy ở đây chỉ cần check URL hợp lệ.
             alt_text = html.escape(image_info.get('alt_text', s_name))
             section_html_parts.append(f"""
<figure style="text-align:center; margin-top: 20px; margin-bottom: 20px;">
    <img src="{html.escape(image_info['url'])}" alt="{alt_text}" />
</figure>
""")
        
        # --- D. Chèn Nội dung Section (đã có external links) ---
        if s_html_content_with_ext_links and "<!-- Container Chapter" not in s_html_content_with_ext_links and "<!-- No prompt for this section -->" not in s_html_content_with_ext_links:
            section_html_parts.append(s_html_content_with_ext_links)

        # --- E. Chèn Video ---
        video_info = video_data_map.get(s_index)
        if video_info and video_info.get('videoID'):
            section_html_parts.append(_generate_youtube_iframe_html(video_info['videoID']))
        
        # Ghép các phần của section này lại
        if section_html_parts: # Chỉ thêm nếu section có nội dung/tiêu đề
            full_html_parts.append("\n".join(section_html_parts))

    # Ghép tất cả các section lại
    final_html_output = "\n\n".join(full_html_parts)
    logger.info(f"Successfully assembled full HTML content (Length: {len(final_html_output)}).")
    return final_html_output

##############################################
#### --- Bước 6: Đăng bài và Hoàn tất --- ####
##############################################

def _determine_category_id(article_meta, keyword_analysis_data, preparation_data, config, wp_auth):
    """
    Xác định categoryID cho bài viết.
    Sử dụng logic tương tự như trong n8n (gọi LLM, kiểm tra, tạo mới nếu cần).
    wp_auth: tuple (wp_user, wp_pass)
    """
    article_title = article_meta.get("title", "N/A Title") # Lấy từ article_meta
    logger.info(f"Determining category for article: {article_title}")
    
    wp_categories_raw = []
    try:
        wp_categories_raw = get_wp_categories(
            config.get('WP_BASE_URL'), 
            wp_auth[0], wp_auth[1], 
            params={'per_page': 100, 'orderby': 'count', 'order': 'desc', '_fields': 'id,name,parent'} # Chỉ lấy các trường cần thiết
        )
    except Exception as e:
        logger.error(f"Failed to fetch WordPress categories: {e}")

    category_structure_str = "Available categories (Parent: Subcategories list or just Parent if no subs):\n"
    if wp_categories_raw and isinstance(wp_categories_raw, list):
        parents = {c['id']: html.unescape(c['name']) for c in wp_categories_raw if c.get('parent') == 0}
        children_map = {}
        for c in wp_categories_raw:
            parent_id = c.get('parent')
            if parent_id != 0 and parent_id in parents:
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(html.unescape(c['name']))
        
        for pid, pname in parents.items():
            category_structure_str += f"- {pname}"
            if pid in children_map:
                category_structure_str += f" (Subcategories: {', '.join(children_map[pid])})\n"
            else:
                category_structure_str += "\n"
    else:
        category_structure_str += "No categories found or error fetching them.\n"

    original_keyword_for_cat = preparation_data.get("original_keyword", article_meta.get("title", "N/A"))
    prompt = main_prompts.RECOMMEND_CATEGORY_PROMPT.format(
        category_list_string=category_structure_str,
        keyword=original_keyword_for_cat, # Sử dụng keyword gốc
        search_intent=keyword_analysis_data.get("searchIntent", "N/A")
    )

    category_recommendation = call_openai_chat(
        prompt_messages=[{"role": "user", "content": prompt}],
        model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'),
        api_key=config.get('OPENAI_API_KEY'),
        is_json_output=True
    )

    if not category_recommendation or not isinstance(category_recommendation, dict):
        logger.error(f"Failed to get category recommendation from LLM. Response: {category_recommendation}")
        return config.get('DEFAULT_CATEGORY_ID', 86)

    is_new_category = category_recommendation.get('isNew', 'no').lower() == 'yes'
    recommended_cat_name_from_llm = category_recommendation.get('recommendation', {}).get('category')
    suggested_new_name_from_llm = category_recommendation.get('suggestedName')

    final_category_id = None
    final_category_name = None

    if is_new_category and suggested_new_name_from_llm:
        logger.info(f"LLM suggests creating a new category: '{suggested_new_name_from_llm}'")
        new_cat_response = create_wp_category( # Đảm bảo hàm này được import và định nghĩa đúng
            base_url=config.get('WP_BASE_URL'),
            auth_user=wp_auth[0], auth_pass=wp_auth[1],
            name=suggested_new_name_from_llm
        )
        if new_cat_response and new_cat_response.get('id'):
            final_category_id = new_cat_response.get('id')
            final_category_name = suggested_new_name_from_llm # Hoặc new_cat_response.get('name')
            logger.info(f"Successfully created new WordPress category '{final_category_name}' with ID: {final_category_id}")
        else:
            logger.error(f"Failed to create new category '{suggested_new_name_from_llm}' on WordPress. Response: {new_cat_response}")
            final_category_id = config.get('DEFAULT_CATEGORY_ID', 86)
    elif recommended_cat_name_from_llm:
        found_cat = None
        if wp_categories_raw and isinstance(wp_categories_raw, list):
            for cat in wp_categories_raw:
                if html.unescape(cat.get('name','').lower()) == html.unescape(recommended_cat_name_from_llm.lower()):
                    found_cat = cat
                    break
        if found_cat:
            final_category_id = found_cat.get('id')
            logger.info(f"Using existing category: '{html.unescape(found_cat.get('name'))}' (ID: {final_category_id})")
        else:
            logger.warning(f"Recommended category '{recommended_cat_name_from_llm}' not found. Falling back to default or trying to create it.")
            # Cân nhắc: Nếu category được LLM recommend không tìm thấy, có nên tạo nó không?
            # Hoặc chỉ fallback. Hiện tại đang fallback.
            final_category_id = config.get('DEFAULT_CATEGORY_ID', 86)
    else:
        logger.warning("LLM did not provide a valid category recommendation. Falling back to default.")
        final_category_id = config.get('DEFAULT_CATEGORY_ID', 86)
        
    return final_category_id

def _php_serialize_internal_link_keywords(keywords_list):
    """
    Chuyển đổi list các keyword thành chuỗi PHP serialized cho Internal Link Juicer.
    """
    if not keywords_list or not isinstance(keywords_list, list):
        return 'a:0:{}' 

    serialized_parts = []
    for i, keyword in enumerate(keywords_list):
        if not isinstance(keyword, str): # Đảm bảo keyword là string
            logger.warning(f"Non-string keyword found in ILJ list: {keyword}. Skipping.")
            continue
        escaped_keyword = keyword.replace('\\', '\\\\').replace("'", "\\'")
        # Sử dụng độ dài byte của chuỗi UTF-8
        byte_length = len(keyword.encode('utf-8'))
        serialized_parts.append(f'i:{i};s:{byte_length}:"{escaped_keyword}";')

    return f'a:{len(serialized_parts)}:{{{"".join(serialized_parts)}}}'


def finalize_and_publish_article_step(
    full_article_html, article_meta, preparation_data,
    config, gsheet_handler, db_handler, 
    unique_run_id 
    ):
    """
    Bước cuối: Tạo featured image, đăng bài lên WordPress, cập nhật GSheet, xử lý ILJ.
    """
    logger.info(f"--- Starting Step 6: Finalize and Publish Article '{article_meta.get('title')}' ---")
    
    wp_base_url = config.get('WP_BASE_URL')
    wp_user = config.get('WP_USER')
    wp_pass = config.get('WP_PASSWORD')
    wp_auth = (wp_user, wp_pass)

    # 1. Tạo Featured Image
    logger.info("Generating DALL-E prompt for featured image...")
    # Sử dụng article_meta.get('title') vì nó là tiêu đề cuối cùng của bài viết
    dalle_prompt_content = image_prompts.GENERATE_DALLE_FEATURED_IMAGE_DESCRIPTION_PROMPT.format(
        article_title_raw=article_meta.get('title', "Untitled Article") # Đảm bảo có giá trị fallback
    )
    dalle_prompt_description = call_openai_chat(
        prompt_messages=[{"role": "user", "content": dalle_prompt_content}],
        model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'),
        api_key=config.get('OPENAI_API_KEY')
    )

    featured_image_wp_id = None
    if dalle_prompt_description:
        logger.info(f"DALL-E Prompt: {dalle_prompt_description[:150]}...")
        featured_image_url_from_dalle = call_openai_dalle(
            prompt=dalle_prompt_description,
            size=config.get('FEATURED_IMAGE_SIZE', "1792x1024"),
            api_key=config.get('OPENAI_API_KEY'),
            model=config.get('FEATURED_IMAGE_MODEL', "dall-e-3")
        )
        if featured_image_url_from_dalle:
            logger.info(f"Featured image generated by DALL-E: {featured_image_url_from_dalle}")
            try:
                response = requests.get(featured_image_url_from_dalle, stream=True, timeout=30)
                response.raise_for_status()
                image_binary = response.content
                
                resized_featured_image_binary = resize_image(
                    image_binary,
                    width=config.get('FEATURED_IMAGE_RESIZE_WIDTH', 800),
                    output_format='JPEG',
                    quality=85
                )
                if resized_featured_image_binary:
                    slug_for_filename = article_meta.get('slug', 'featured').replace('-', '_') # Sử dụng slug từ article_meta
                    featured_filename = f"{slug_for_filename}_featured_image.jpg"
                    
                    wp_media_resp = upload_wp_media( # Đảm bảo hàm này được import và định nghĩa đúng
                        wp_base_url, wp_user, wp_pass,
                        resized_featured_image_binary,
                        featured_filename,
                        "image/jpeg"
                    )
                    if wp_media_resp and wp_media_resp.get('id'):
                        featured_image_wp_id = wp_media_resp.get('id')
                        logger.info(f"Featured image uploaded to WordPress. Media ID: {featured_image_wp_id}, URL: {wp_media_resp.get('source_url')}")
                    else:
                        logger.error(f"Failed to upload featured image to WordPress. Response: {wp_media_resp}")
                else:
                    logger.error("Failed to resize DALL-E featured image.")
            except Exception as e:
                logger.error(f"Error processing DALL-E featured image: {e}", exc_info=True)
        else:
            logger.error("Failed to generate featured image from DALL-E.")
    else:
        logger.error("Failed to generate DALL-E prompt for featured image.")

    # 2. Xác định Category ID
    keyword_analysis = preparation_data.get("keyword_analysis", {})
    # SỬA: Truyền article_meta vào _determine_category_id
    category_id_for_post = _determine_category_id(article_meta, keyword_analysis, preparation_data, config, wp_auth)
    logger.info(f"Determined Category ID for post: {category_id_for_post}")

    # 3. Đăng bài lên WordPress
    logger.info(f"Attempting to create WordPress post: '{article_meta.get('title')}'")
    
    post_payload = {
        "title": article_meta.get('title'),
        "content": full_article_html,
        "slug": article_meta.get('slug'),
        "status": config.get('DEFAULT_POST_STATUS', 'publish'),
        "categories": [category_id_for_post] if category_id_for_post else [config.get('DEFAULT_CATEGORY_ID', 86)],
        "author": article_meta.get('chosen_author_id', config.get('DEFAULT_AUTHOR_ID')),
        "excerpt": article_meta.get('description')
    }
    # Không truyền featured_media ở đây, sẽ update sau
    
    created_post_response = create_wp_post(
        base_url=wp_base_url, auth_user=wp_user, auth_pass=wp_pass,
        **post_payload
    )

    post_id = None
    post_url = None
    if created_post_response and created_post_response.get('id'):
        post_id = created_post_response.get('id')
        post_url = created_post_response.get('link')
        logger.info(f"WordPress post created successfully! ID: {post_id}, URL: {post_url}")

        if featured_image_wp_id:
            time.sleep(config.get('WP_UPDATE_DELAY', 2)) 
            update_payload = {"featured_media": featured_image_wp_id}
            # Nếu bài viết cũng cần excerpt và meta description, có thể cập nhật luôn ở đây
            # current_excerpt = article_meta.get('description')
            # if current_excerpt:
            #     update_payload['excerpt'] = {"raw": current_excerpt, "rendered": f"<p>{current_excerpt}</p>"}
            
            updated_post_resp = update_wp_post(wp_base_url, wp_user, wp_pass, post_id, update_payload)
            if updated_post_resp and updated_post_resp.get('featured_media') == featured_image_wp_id:
                logger.info(f"Successfully set featured image (ID: {featured_image_wp_id}) for post ID: {post_id}")
            else:
                logger.error(f"Failed to set featured image for post ID: {post_id}. Update response: {updated_post_resp}")
    else:
        logger.error(f"Failed to create WordPress post. Response: {created_post_response}")
        return False

    # 4. Cập nhật Google Sheet
    if gsheet_handler and post_id: # Chỉ cập nhật nếu có gsheet_handler và post_id
        gsheet_update_data = {
            config.get('GSHEET_USED_COLUMN'): "1",
            config.get('GSHEET_POST_TITLE_COLUMN'): article_meta.get('title'),
            config.get('GSHEET_POST_ID_COLUMN'): str(post_id),
            config.get('GSHEET_POST_URL_COLUMN'): post_url
        }
        success_gsheet = gsheet_handler.update_sheet_row_by_matching_column(
            spreadsheet_id_or_url=config.get('GSHEET_SPREADSHEET_ID'),
            sheet_name_or_gid=config.get('GSHEET_KEYWORD_SHEET_NAME'),
            match_column_header=config.get('GSHEET_KEYWORD_COLUMN'),
            match_value=preparation_data.get('original_keyword'),
            data_to_update_dict=gsheet_update_data
        )
        if success_gsheet:
            logger.info(f"Google Sheet updated successfully for keyword '{preparation_data.get('original_keyword')}'.")
        else:
            logger.error(f"Failed to update Google Sheet for keyword '{preparation_data.get('original_keyword')}'.")

    # 5. Xử lý Internal Link Juicer
    if db_handler and post_id: # Chỉ xử lý nếu có db_handler và post_id
        logger.info(f"Processing Internal Link Juicer for post ID: {post_id}")
        prompt_ilj_keywords = main_prompts.INTERNAL_LINKING_KEYWORDS_PROMPT.format(
            base_keyword=preparation_data.get('original_keyword'),
            article_title_for_backlinks=article_meta.get('title')
        )
        ilj_keywords_response = call_openai_chat(
            prompt_messages=[{"role": "user", "content": prompt_ilj_keywords}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'),
            api_key=config.get('OPENAI_API_KEY'),
            is_json_output=True 
        )
        if ilj_keywords_response and isinstance(ilj_keywords_response, list) and ilj_keywords_response: # Kiểm tra list không rỗng
            serialized_php_string = _php_serialize_internal_link_keywords(ilj_keywords_response)
            logger.debug(f"Serialized PHP for ILJ: {serialized_php_string}")

            # Xóa meta_key ilj_linkdefinition cũ (nếu có nhiều hơn 1)
            # Query này đã được điều chỉnh để chỉ xóa các bản ghi thừa, giữ lại bản ghi có meta_id lớn nhất.
            # Nếu không có bản ghi nào, nó sẽ không xóa gì.
            # Nếu chỉ có 1 bản ghi, nó cũng không xóa gì.
            delete_duplicate_ilj_query = """
            DELETE FROM wp_postmeta
            WHERE post_id = %s AND meta_key = 'ilj_linkdefinition'
            AND meta_id NOT IN (
                SELECT meta_id_to_keep FROM (
                    SELECT MAX(meta_id) as meta_id_to_keep
                    FROM wp_postmeta
                    WHERE post_id = %s AND meta_key = 'ilj_linkdefinition'
                ) AS temp_table
            );
            """
            # Chạy query xóa trước, nếu có nhiều hơn 1 record thì nó sẽ giữ lại 1.
            db_handler.execute_query(delete_duplicate_ilj_query, params=(post_id, post_id))
            logger.info(f"Attempted to clean duplicate ILJ entries for post ID {post_id}.")

            # Insert hoặc Update (UPSERT)
            # Kiểm tra xem có record nào còn lại không sau khi xóa duplicate
            check_existing_query = "SELECT meta_id FROM wp_postmeta WHERE post_id = %s AND meta_key = 'ilj_linkdefinition' LIMIT 1"
            existing_ilj_meta = db_handler.execute_query(check_existing_query, params=(post_id,), fetch_one=True)

            if existing_ilj_meta: # Nếu còn record, thì UPDATE nó
                update_ilj_query = "UPDATE wp_postmeta SET meta_value = %s WHERE post_id = %s AND meta_key = 'ilj_linkdefinition' AND meta_id = %s"
                result_ilj_db = db_handler.execute_query(update_ilj_query, params=(serialized_php_string, post_id, existing_ilj_meta['meta_id']))
                logger.info(f"Updated existing ILJ data for post ID {post_id}. Rows affected: {result_ilj_db}")
            else: # Nếu không còn record nào, thì INSERT mới
                insert_ilj_query = "INSERT INTO wp_postmeta (post_id, meta_key, meta_value) VALUES (%s, 'ilj_linkdefinition', %s)"
                result_ilj_db = db_handler.execute_query(insert_ilj_query, params=(post_id, serialized_php_string))
                logger.info(f"Inserted new ILJ data for post ID {post_id}. Rows affected: {result_ilj_db}")

            if result_ilj_db is None: # Nếu execute_query trả về None là có lỗi
                 logger.error(f"Failed to update/insert Internal Link Juicer data for post ID {post_id}.")
        elif isinstance(ilj_keywords_response, list) and not ilj_keywords_response:
             logger.info(f"LLM returned an empty list for ILJ keywords for post ID {post_id}. No ILJ data to set.")
        else:
            logger.warning(f"Could not generate ILJ keywords or invalid format from LLM for post ID {post_id}. Response: {ilj_keywords_response}")
    else:
        logger.warning("MySQL handler not available or no post_id. Skipping Internal Link Juicer.")


    # 6. Google Indexing (Tùy chọn)
    if config.get('ENABLE_GOOGLE_INDEXING', False) and post_url:
        logger.info(f"Submitting URL to Google Indexing API: {post_url}")
        # from utils.api_clients import submit_to_google_indexing # Giả sử bạn có hàm này
        # ... (logic gọi API) ...
        pass

    # 7. Chia sẻ mạng xã hội (Tùy chọn)
    if config.get('ENABLE_SOCIAL_SHARING', False) and post_url:
        logger.info(f"Initiating social sharing for: {post_url}")
        # ... (logic gọi API/workflow chia sẻ) ...
        pass

    logger.info(f"--- Step 6 (Finalize and Publish) completed for post ID: {post_id} ---")
    return {"post_id": post_id, "post_url": post_url, "status": "published" if post_id else "failed"}

################################################
#### --- Bước HỖ TRỢ TẠO TEST --- ####
################################################

def orchestrate_article_creation(keyword_to_process: str, config: dict, 
                                 gsheet_handler_instance: GoogleSheetsHandler, 
                                 pinecone_handler_instance: PineconeHandler, 
                                 db_handler_instance: MySQLHandler,
                                 unique_run_id_override: str = None): # Thêm unique_run_id_override cho test
    """
    Hàm chính điều phối toàn bộ quá trình tạo bài viết cho một keyword.
    """
    logger.info(f"=== STARTING ARTICLE ORCHESTRATION FOR KEYWORD: '{keyword_to_process}' ===")

    if unique_run_id_override:
        current_run_id = unique_run_id_override
    else:
        # Tạo unique_run_id nếu không được cung cấp (ví dụ cho production)
        keyword_slug = "".join(c if c.isalnum() else '-' for c in keyword_to_process.lower()).strip('-')
        current_run_id = f"{keyword_slug[:50]}_{int(time.time())}" # Giới hạn độ dài slug
    
    logger.info(f"Using run_id: {current_run_id}")

    # --- Bước 1: Phân tích Keyword và Chuẩn bị ---
    logger.info("--- Running Step 1: Analyze and Prepare Keyword ---")
    preparation_results = analyze_and_prepare_keyword(
        keyword_to_process=keyword_to_process,
        config=config,
        gsheet_handler=gsheet_handler_instance,
        pinecone_handler=pinecone_handler_instance
    )
    if not preparation_results:
        logger.error(f"Step 1 failed for keyword '{keyword_to_process}'. Aborting orchestration.")
        return {"status": "failed", "step": 1, "reason": "Keyword analysis/preparation failed", "keyword": keyword_to_process}

    # --- Bước 2: Tạo Outline ---
    logger.info("--- Running Step 2: Create Article Outline ---")
    outline_results = create_article_outline_step(
        keyword_to_process=keyword_to_process,
        preparation_data=preparation_results,
        config=config
    )
    if not outline_results or not outline_results.get("processed_sections_list"):
        logger.error(f"Step 2 failed for keyword '{keyword_to_process}'. Aborting orchestration.")
        # Cân nhắc cập nhật GSheet ở đây nếu phù hợp (ví dụ, lỗi không phải do keyword không phù hợp)
        return {"status": "failed", "step": 2, "reason": "Outline creation failed", "keyword": keyword_to_process}

    # --- Bước 3: Viết Nội dung từng Section ---
    logger.info("--- Running Step 3: Write Content for All Sections ---")
    sections_with_content = write_content_for_all_sections_step(
        processed_sections_list=outline_results.get("processed_sections_list"),
        article_meta=outline_results.get("article_meta"),
        preparation_data=preparation_results, # Cần chosen_author từ đây
        config=config
    )
    if not sections_with_content:
        logger.error(f"Step 3 failed for keyword '{keyword_to_process}'. Aborting orchestration.")
        return {"status": "failed", "step": 3, "reason": "Content writing failed", "keyword": keyword_to_process}

    # --- Bước 4: Xử lý Sub-Workflows (Images, Videos, External Links) ---
    logger.info("--- Running Step 4: Process Sub-Workflows ---")
    sub_workflow_outputs = process_sub_workflows_step(
        sections_with_initial_content=sections_with_content,
        article_meta=outline_results.get("article_meta"),
        config=config,
        unique_run_id=current_run_id # Truyền unique_run_id
    )
    if not sub_workflow_outputs:
        logger.error(f"Step 4 failed for keyword '{keyword_to_process}'. Aborting orchestration.")
        return {"status": "failed", "step": 4, "reason": "Sub-workflow processing failed", "keyword": keyword_to_process}

    # --- Bước 5: Tạo Nội dung HTML Hoàn chỉnh ---
    logger.info("--- Running Step 5: Assemble Full HTML ---")
    full_html = assemble_full_html_step(
        sub_workflow_results=sub_workflow_outputs,
        article_meta=outline_results.get("article_meta"),
        processed_sections_list_from_step2=outline_results.get("processed_sections_list"),
        config=config
    )
    if not full_html:
        logger.error(f"Step 5 failed for keyword '{keyword_to_process}'. Aborting orchestration.")
        return {"status": "failed", "step": 5, "reason": "HTML assembly failed", "keyword": keyword_to_process}

    # --- Bước 6: Đăng bài và Hoàn tất ---
    logger.info("--- Running Step 6: Finalize and Publish Article ---")
    publish_results = finalize_and_publish_article_step(
        full_article_html=full_html,
        article_meta=outline_results.get("article_meta"),
        preparation_data=preparation_results,
        config=config,
        gsheet_handler=gsheet_handler_instance,
        db_handler=db_handler_instance,
        unique_run_id=current_run_id # Truyền unique_run_id
    )
    if not publish_results or not publish_results.get("post_id"):
        logger.error(f"Step 6 failed for keyword '{keyword_to_process}'. Article may not be published.")
        return {"status": "failed", "step": 6, "reason": "Publishing failed", "keyword": keyword_to_process, "details": publish_results}

    logger.info(f"=== ARTICLE ORCHESTRATION COMPLETED SUCCESSFULLY FOR: '{keyword_to_process}' ===")
    return {
        "status": "success", 
        "keyword": keyword_to_process, 
        "post_id": publish_results.get("post_id"),
        "post_url": publish_results.get("post_url")
    }