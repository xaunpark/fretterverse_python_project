# workflows/external_links_processor.py
import logging
import random
import re # For finding context and validating URLs
import html # For escaping text to be inserted into HTML attributes or content
import urllib.parse # For encoding search keywords
from bs4 import BeautifulSoup # Optional: For better text extraction from HTML

from utils.api_clients import call_openai_chat, google_search
from utils.redis_handler import RedisHandler
from prompts import external_link_prompts
# from utils.config_loader import APP_CONFIG

logger = logging.getLogger(__name__)

# --- Constants (có thể lấy từ APP_CONFIG) ---
# MIN_EXTERNAL_LINKS_PER_SECTION = 2
# MAX_EXTERNAL_LINKS_PER_SECTION = 4
# GOOGLE_SEARCH_NUM_RESULTS_EXT_LINKS = 10

def _get_redis_exlinks_array_key(config, unique_run_id):
    """Helper to generate Redis key for the external links array for this run."""
    return f"{config.get('REDIS_KEY_EXLINKS_ARRAY_PREFIX', 'fvp_exlinks_array_')}{unique_run_id}"

def _should_skip_external_links(section_data):
    """
    Kiểm tra xem có nên bỏ qua việc chèn external links cho section này không.
    Dựa trên logic của IF1 node trong fretterverse-v9_external_links.
    """
    section_name = section_data.get('sectionName', '').lower()
    section_name_tag = section_data.get('sectionNameTag', '').lower()
    mother_chapter = section_data.get('motherChapter', 'no').lower()
    section_index = section_data.get('sectionIndex')

    # Điều kiện skip từ IF1 node trong v9_external_links
    skip_conditions = [
        section_name == "introduction",
        section_name == "faqs",
        section_name == "conclusion",
        section_name_tag == "introduction",
        section_name_tag == "conclusion",
        section_name_tag == "faqs",
        mother_chapter == "yes",
        "top rated" in section_name, # Từ prompt gốc, "top rated" cũng bị skip
        # section_index == 2 # (Nếu điều kiện này áp dụng cho external links)
    ]
    if isinstance(section_index, int) and section_index == 2: # Vẫn muốn skip index 2
         skip_conditions.append(True)

    if any(skip_conditions):
        logger.info(f"Skipping external links for section '{section_data.get('sectionName')}' due to skip conditions.")
        return True
    return False

def _extract_text_from_html(html_content):
    """
    (Optional but Recommended) Extracts plain text from HTML content for better analysis by LLM.
    """
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        # Loại bỏ các script và style tags
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()
        # Lấy text
        text = soup.get_text(separator=" ", strip=True)
        return text
    except Exception as e:
        logger.warning(f"Error extracting text from HTML, returning original: {e}")
        return html_content # Fallback to original if parsing fails

def _find_context_sentence(full_text, anchor_text, sentences_around=1):
    """
    Tìm câu chứa anchor_text và có thể lấy thêm các câu xung quanh.
    Đây là một phiên bản đơn giản.
    """
    if not full_text or not anchor_text:
        return anchor_text # Trả về anchor_text nếu không có context

    # Đơn giản hóa: tìm vị trí anchor_text
    # Cần regex cẩn thận hơn để xử lý dấu câu và khoảng trắng
    # Regex để chia câu (đơn giản)
    sentences = re.split(r'(?<=[.!?])\s+', full_text)
    
    cleaned_anchor = anchor_text.replace('.', '').strip().lower() # Làm sạch anchor để so sánh

    for i, sentence in enumerate(sentences):
        if cleaned_anchor in sentence.lower():
            # Lấy context gồm câu hiện tại và các câu xung quanh
            start_index = max(0, i - sentences_around)
            end_index = min(len(sentences), i + sentences_around + 1)
            context_sentences = sentences[start_index:end_index]
            return " ".join(context_sentences).strip()
            
    logger.warning(f"Could not find specific sentence context for anchor: '{anchor_text}'. Returning anchor itself.")
    return anchor_text # Fallback

def _is_valid_url(url_string):
    """Kiểm tra sơ bộ xem có phải là URL hợp lệ không."""
    if not url_string or not isinstance(url_string, str):
        return False
    # Regex đơn giản cho URL (có thể không bao trùm hết các trường hợp)
    # Workflow n8n của bạn có node "Regex sourceURL" để trích xuất URL, logic tương tự ở đây.
    regex = re.compile(
        r'^(?:http|ftp)s?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'  # ...or ipv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'  # ...or ipv6
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url_string) is not None

def _extract_first_valid_url_from_string(text_containing_url):
    """Trích xuất URL hợp lệ đầu tiên từ một chuỗi (tương tự node Regex sourceURL)."""
    if not text_containing_url:
        return None
    # Regex này tìm URL bắt đầu bằng http hoặc https, không có khoảng trắng
    match = re.search(r'https?://[^\s]+', text_containing_url)
    if match:
        url = match.group(0)
        # Loại bỏ các ký tự không mong muốn ở cuối URL (ví dụ dấu . , )
        url = re.sub(r'[.,)\]!]$', '', url)
        if _is_valid_url(url):
            return url
    return None


def process_external_links_for_section(
    section_data, article_title_main, 
    redis_handler, config, openai_api_key, google_api_key, 
    unique_run_id
):
    """
    Xử lý external links cho MỘT section.
    section_data: dict chứa 'sectionName', 'sectionType', 'sectionNameTag', 'motherChapter', 'sectionIndex',
                  và quan trọng nhất là 'current_html_content' (nội dung HTML hiện tại của section).
    Trả về updated_html_content cho section đó.
    """
    min_links = config.get('EXTERNAL_LINKS_PER_SECTION_MIN', 2)
    max_links = config.get('EXTERNAL_LINKS_PER_SECTION_MAX', 4)
    num_links_to_find = random.randint(min_links, max_links)

    original_html_content = section_data.get('current_html_content', '')
    updated_html_content = original_html_content # Bắt đầu với nội dung gốc

    if _should_skip_external_links(section_data) or not original_html_content.strip():
        logger.info(f"External links skipped or no content for section '{section_data.get('sectionName')}'.")
        return original_html_content # Trả về nội dung gốc không thay đổi

    logger.info(f"Processing external links for section: '{section_data.get('sectionName')}', aiming for ~{num_links_to_find} links.")

    # Nên trích xuất text thuần để OpenAI xác định anchor text
    plain_text_content = _extract_text_from_html(original_html_content)
    if not plain_text_content.strip() or len(plain_text_content.split()) < 15 : # Ngưỡng từ tối thiểu
        logger.warning(f"Not enough plain text content in section '{section_data.get('sectionName')}' to find citations.")
        return original_html_content

    # --- BƯỚC 1: Xác định Anchor Texts ---
    prompt_get_anchors = external_link_prompts.IDENTIFY_ANCHOR_TEXTS_FOR_CITATIONS_PROMPT.format(
        num_key_phrases=num_links_to_find,
        section_content_text=plain_text_content # Gửi text thuần
    )
    anchor_texts_info = call_openai_chat(
        [{"role": "user", "content": prompt_get_anchors}],
        config.get('DEFAULT_OPENAI_CHAT_MODEL'),
        openai_api_key,
        is_json_output=True
    )

    if not anchor_texts_info or not isinstance(anchor_texts_info, list):
        logger.warning(f"Failed to get valid anchor texts for section '{section_data.get('sectionName')}'. Response: {anchor_texts_info}")
        return original_html_content
    
    logger.debug(f"Anchor texts identified by AI for '{section_data.get('sectionName')}': {anchor_texts_info}")

    redis_exlinks_key = _get_redis_exlinks_array_key(config, unique_run_id)
    # Đảm bảo key tồn tại và là list trong Redis
    if not redis_handler.get_value(redis_exlinks_key): # Nếu key chưa có
        redis_handler.initialize_array_if_not_exists(redis_exlinks_key, "[]")


    links_inserted_count = 0
    # Sử dụng một set để theo dõi anchor texts đã được xử lý trong section này, tránh thay thế nhiều lần
    processed_anchors_in_section = set()

    for anchor_info in anchor_texts_info:
        if links_inserted_count >= num_links_to_find: # Đã đủ số link mong muốn
            break

        anchor_text_original = anchor_info.get('anchortext')
        if not anchor_text_original or not isinstance(anchor_text_original, str) or \
           anchor_text_original.lower() in processed_anchors_in_section:
            logger.debug(f"Skipping invalid or already processed anchor: '{anchor_text_original}'")
            continue
        
        # Quan trọng: Anchor text từ AI có thể không khớp chính xác 100% với text trong HTML.
        # Cần tìm một cách "fuzzy" hoặc đảm bảo AI trả về cụm từ y hệt.
        # Hiện tại, giả sử AI trả về cụm từ có trong plain_text_content.
        # Chúng ta cần tìm cụm từ này trong updated_html_content (có thể đã thay đổi).
        
        # Kiểm tra xem anchor_text_original có thực sự tồn tại trong nội dung HTML hiện tại không
        # (không phân biệt hoa thường và bỏ qua các tag HTML bên trong anchor tiềm năng)
        # Đây là một thách thức. Cách đơn giản là tìm text thuần.
        temp_soup = BeautifulSoup(updated_html_content, "html.parser")
        if anchor_text_original.lower() not in temp_soup.get_text().lower():
            logger.warning(f"Anchor text '{anchor_text_original}' (from AI) not found in current HTML content of section '{section_data.get('sectionName')}'. Skipping.")
            continue

        # --- BƯỚC 2: Tìm Context Sentence ---
        # Dùng plain_text_content (từ HTML gốc) để tìm context, vì nó ổn định hơn.
        context_sentence = _find_context_sentence(plain_text_content, anchor_text_original)
        logger.debug(f"Context for '{anchor_text_original}': {context_sentence[:100]}...")

        # --- BƯỚC 3: Tạo Keyword tìm kiếm Citation ---
        prompt_citation_keyword = external_link_prompts.GENERATE_CITATION_SEARCH_KEYWORD_PROMPT.format(
            article_title_main=article_title_main,
            anchor_text=anchor_text_original,
            full_context_sentence=context_sentence,
            chapter_name=section_data.get('sectionName')
        )
        citation_search_keyword = call_openai_chat(
            [{"role": "user", "content": prompt_citation_keyword}],
            config.get('DEFAULT_OPENAI_CHAT_MODEL'),
            openai_api_key
        )
        if not citation_search_keyword:
            logger.warning(f"Failed to generate search keyword for anchor '{anchor_text_original}'. Skipping.")
            continue
        logger.info(f"Search keyword for '{anchor_text_original}': '{citation_search_keyword}'")

        # --- BƯỚC 4: Google Search ---
        cx_id_shared = config.get('GOOGLE_CX_ID')
        if not cx_id_shared:
            logger.error("GOOGLE_CX_ID not configured for external links search.")
            # Xử lý lỗi
            continue # Bỏ qua anchor text này nếu không có CX_ID

        google_search_items = google_search(
            query=urllib.parse.quote_plus(citation_search_keyword),
            api_key=google_api_key,
            cx_id=cx_id_shared,
            cx_id=config.get('GOOGLE_CX_ID_EXTERNAL_LINKS'), # Cần CX_ID riêng cho tìm external links
            num_results=config.get('GOOGLE_SEARCH_NUM_RESULTS_EXT_LINKS', 10),
            # Thêm các excludeTerms từ workflow n8n của bạn
            excludeTerms="forum", # Ví dụ
            # siteSearch="", # Nếu muốn giới hạn trong site cụ thể (ít dùng cho external)
            # linkSite="", # Tìm các trang link đến site này
            # relatedSite="",
            # Bạn có thể thêm các tham số như -inurl:quora.com -inurl:reddit.com trực tiếp vào query
            # hoặc dùng các tham số API nếu có. Trong ví dụ này, thêm vào query:
            # query=f"{urllib.parse.quote_plus(citation_search_keyword)} -inurl:quora.com -inurl:reddit.com"
        )
        if not google_search_items:
            logger.warning(f"No Google search results for keyword '{citation_search_keyword}'. Skipping anchor '{anchor_text_original}'.")
            continue

        link_options_parts = []
        for i, item in enumerate(google_search_items):
            title = item.get('title', 'N/A')
            url = item.get('link', 'N/A')
            # snippet = item.get('snippet', '') # Có thể thêm snippet vào prompt chọn link
            link_options_parts.append(f"{i+1}. Link Title: {title}, linkURL: {url}")
        link_options_str = "\n".join(link_options_parts)
        if not link_options_str: link_options_str = "No links found in search results."


        # --- BƯỚC 5: Chọn Best External Link (OpenAI) ---
        prompt_choose_exlink = external_link_prompts.CHOOSE_BEST_EXTERNAL_LINK_PROMPT.format(
            article_title_main=article_title_main,
            chapter_name_context=section_data.get('sectionName'),
            anchor_text_context=anchor_text_original,
            sentence_context=context_sentence,
            link_options_string=link_options_str
        )
        selected_url_string = call_openai_chat(
            [{"role": "user", "content": prompt_choose_exlink}],
            config.get('DEFAULT_OPENAI_CHAT_MODEL'),
            openai_api_key
        ) # Hàm này trả về string URL hoặc "NO_SUITABLE_LINK_FOUND"

        if not selected_url_string or selected_url_string == "NO_SUITABLE_LINK_FOUND":
            logger.info(f"AI did not select a suitable external link for anchor '{anchor_text_original}'.")
            continue
        
        # --- BƯỚC 6: Regex URL và Kiểm tra Trùng lặp ---
        final_url_to_insert = _extract_first_valid_url_from_string(selected_url_string)
        if not final_url_to_insert:
            logger.warning(f"Selected string '{selected_url_string}' is not a valid URL or could not be extracted for anchor '{anchor_text_original}'.")
            continue
        
        logger.info(f"AI selected URL '{final_url_to_insert}' for anchor '{anchor_text_original}'.")

        # Kiểm tra trùng lặp với exlinksArray từ Redis
        current_exlinks_array = redis_handler.get_value(redis_exlinks_key) or []
        if not isinstance(current_exlinks_array, list): current_exlinks_array = [] # Đảm bảo là list

        # Chuẩn hóa URL để kiểm tra trùng (ví dụ: bỏ / ở cuối, http vs https, www) - Tùy chọn
        normalized_url_to_check = final_url_to_insert.lower().replace("www.", "").rstrip('/')
        is_duplicate = any(
            url_entry.lower().replace("www.", "").rstrip('/') == normalized_url_to_check
            for url_entry in current_exlinks_array
        )

        if is_duplicate:
            logger.info(f"URL '{final_url_to_insert}' is a duplicate or already used. Skipping for anchor '{anchor_text_original}'.")
            continue
        
        # --- BƯỚC 7: Chèn Link vào HTML và Cập nhật Redis ---
        # Đây là phần khó: thay thế anchor_text trong updated_html_content bằng link.
        # Regex cần cẩn thận để không phá vỡ HTML hoặc thay thế sai chỗ.
        # Phải tìm anchor_text_original trong updated_html_content (đã có thể bị thay đổi từ lần lặp trước)
        # Chỉ thay thế lần xuất hiện đầu tiên chưa được link.
        
        # Để tránh regex phức tạp trên HTML, một cách tiếp cận là tìm kiếm không phân biệt
        # và đảm bảo không nằm trong tag <a> khác.
        # Hoặc, nếu anchor_text_original đủ đặc biệt:
        # Chú ý: html.escape(anchor_text_original) nếu anchor_text có ký tự đặc biệt HTML
        # và bạn muốn tìm nó chính xác trong HTML.
        
        # Tạo link HTML
        escaped_anchor_text = html.escape(anchor_text_original) # Dùng cho phần text của link
        link_html = f'<a href="{html.escape(final_url_to_insert)}" target="_blank" rel="noopener noreferrer">{escaped_anchor_text}</a>'
        
        # Tìm và thay thế. Cần một cách thông minh hơn là str.replace đơn giản nếu anchor text có thể
        # xuất hiện nhiều lần hoặc là một phần của từ khác.
        # Ví dụ: Thay thế lần xuất hiện đầu tiên của anchor_text mà không phải là một phần của link đã có.
        # Regex để tìm anchor_text không nằm trong tag <a>:
        # (?<!<a[^>]*?>\s*)\b(Your Anchor Text)\b(?!\s*<\/a>)
        # Cần escape anchor_text cho regex: re.escape(anchor_text_original)
        
        # Phiên bản đơn giản hóa, có thể cần cải thiện:
        # Chỉ thay thế nếu updated_html_content vẫn còn chứa anchor_text_original nguyên bản
        # Điều này giả định anchor_text_original là một chuỗi text thuần.
        # Cần một cách tốt hơn nếu anchor_text có thể chứa HTML đơn giản hoặc nằm rải rác.
        
        # Sử dụng một cách tiếp cận an toàn hơn: thay thế trên text thuần rồi ghép lại (phức tạp)
        # Hoặc tìm lần xuất hiện đầu tiên của anchor_text chưa được link
        
        # Tạm thời dùng str.replace, chỉ thay 1 lần
        # Cần đảm bảo anchor_text_original là text thuần không chứa HTML
        # và nó khớp chính xác với text trong updated_html_content (phần text node).
        # Điều này rất khó làm đúng với string replace trên HTML.
        
        # Một cách tiếp cận an toàn hơn là không thay thế trực tiếp vào HTML đang xử lý
        # mà đánh dấu vị trí và loại anchor, rồi sau khi duyệt hết các anchor,
        # mới xây dựng lại HTML có các link.
        # Hoặc, nếu bạn có thể đảm bảo AI trả về anchor text chính xác như trong source text
        # và nó là duy nhất, bạn có thể thử:
        
        # Chỉ thay thế nếu anchor text đó có trong text thuần của HTML hiện tại
        current_soup = BeautifulSoup(updated_html_content, "html.parser")
        if anchor_text_original.lower() in current_soup.get_text().lower():
            # Cố gắng thay thế một cách an toàn. Regex này tìm anchor_text như một từ hoàn chỉnh,
            # không phải là một phần của URL hoặc trong một tag attribute.
            # (?<![=\/"'>\w]) an assertion lookbehind tiêu cực, đảm bảo ký tự trước không phải là một phần của URL hoặc tag attribute.
            # (?![=\/"'<\w]) an assertion lookahead tiêu cực, đảm bảo ký tự sau không phải là một phần của URL hoặc tag.
            # \b là word boundary.
            # Cần xử lý cả trường hợp anchor_text có ký tự đặc biệt cho regex.
            
            # Đơn giản nhất cho mục đích test là replace 1 lần:
            if anchor_text_original in updated_html_content: # Tìm chính xác chuỗi
                updated_html_content = updated_html_content.replace(anchor_text_original, link_html, 1)
                logger.info(f"Inserted link for anchor '{anchor_text_original}' in section '{section_data.get('sectionName')}'.")
                links_inserted_count += 1
                processed_anchors_in_section.add(anchor_text_original.lower())
                
                # Cập nhật Redis exlinksArray
                current_exlinks_array.append(final_url_to_insert)
                redis_handler.set_value(redis_exlinks_key, list(set(current_exlinks_array))) # Lưu list unique
            else:
                logger.warning(f"Could not precisely replace anchor '{anchor_text_original}' in HTML of section '{section_data.get('sectionName')}'. It might have been modified or is inside HTML tags.")
        else:
             logger.warning(f"Anchor text '{anchor_text_original}' no longer found in text content of section '{section_data.get('sectionName')}' after previous replacements. Skipping.")


    return updated_html_content


def process_external_links_for_article(sections_with_content_list, article_title_main, config, unique_run_id):
    """
    Hàm chính để xử lý external links cho tất cả các section trong một bài viết.
    sections_with_content_list: List các dict, mỗi dict là thông tin của một section 
                                và chứa 'current_html_content'.
    unique_run_id: ID duy nhất cho lần chạy xử lý bài viết này.
    Trả về list các section đã được cập nhật 'current_html_content'.
    """
    logger.info(f"Starting external links processing for article: '{article_title_main}' with run_id: {unique_run_id}")

    openai_api_key = config.get('OPENAI_API_KEY')
    google_api_key = config.get('GOOGLE_API_KEY')
    if not all([openai_api_key, google_api_key, config.get('GOOGLE_CX_ID_EXTERNAL_LINKS')]):
        logger.error("Missing critical API keys or Google CX ID for external links in config.")
        # Trả về nội dung gốc nếu thiếu config
        return sections_with_content_list 

    redis_handler = RedisHandler(config=config)
    if not redis_handler.is_connected():
        logger.error("Cannot connect to Redis. Aborting external links processing.")
        return sections_with_content_list

    # Khởi tạo key exlinksArray trong Redis cho lần chạy này
    redis_exlinks_key = _get_redis_exlinks_array_key(config, unique_run_id)
    redis_handler.initialize_array_if_not_exists(redis_exlinks_key, "[]")

    updated_sections_list = []
    for section_data in sections_with_content_list:
        # Tạo một bản copy để không thay đổi dict gốc trong list
        current_section_copy = dict(section_data) 
        
        updated_content = process_external_links_for_section(
            section_data=current_section_copy, # Truyền bản copy
            article_title_main=article_title_main,
            redis_handler=redis_handler,
            config=config,
            openai_api_key=openai_api_key,
            google_api_key=google_api_key,
            unique_run_id=unique_run_id
        )
        current_section_copy['current_html_content'] = updated_content # Cập nhật nội dung
        updated_sections_list.append(current_section_copy)

    logger.info(f"Finished external links processing for article '{article_title_main}'.")
    return updated_sections_list

# --- Example Usage (sẽ được gọi từ main_logic.py) ---
# if __name__ == "__main__":
#     # Cần mock APP_CONFIG, RedisHandler, và các hàm API
#     # from utils.config_loader import load_app_config
#     # from utils.logging_config import setup_logging
#     # APP_CONFIG = load_app_config()
#     # setup_logging(log_level_str="DEBUG")

#     # mock_config = { # ... điền config ... 
#     #    'EXTERNAL_LINKS_PER_SECTION_MIN': 1, 
#     #    'EXTERNAL_LINKS_PER_SECTION_MAX': 2,
#     #    'GOOGLE_CX_ID_EXTERNAL_LINKS': "YOUR_GOOGLE_CX_ID_FOR_EXT_LINKS",
#     #    # ... các key khác
#     # }

#     # sample_sections_content = [
#     #     {"sectionName": "Guitar History", "sectionType": "chapter", "sectionIndex": 2, 
#     #      "current_html_content": "<p>The guitar has a rich history. Early stringed instruments date back thousands of years. The modern six-string guitar became popular in Spain.</p><p>Many famous luthiers contributed to its design. For example, Antonio de Torres Jurado is a key figure.</p>"},
#     #     {"sectionName": "Introduction", "sectionType": "chapter", "sectionIndex": 1, "sectionNameTag": "Introduction",
#     #      "current_html_content": "<p>This is an intro, no links here.</p>"}
#     # ]
#     # article_title_test_ext = "The Amazing World of Guitars"
#     # run_id_test_ext = "testextlinks123"

#     # # Cần mock các hàm API calls
#     # import unittest.mock as mock
#     # def mock_openai_for_ext_links(*args, **kwargs):
#     #     prompt_messages_list = args[0]
#     #     prompt_content = prompt_messages_list[0]['content'].lower()
#     #     is_json = kwargs.get('is_json_output', False)

#     #     if "identify the" in prompt_content and "key phrases" in prompt_content and is_json:
#     #         if "guitar has a rich history" in prompt_content:
#     #             return [{"anchortext": "rich history"}, {"anchortext": "Antonio de Torres Jurado"}]
#     #         return []
#     #     elif "suggest a highly relevant keyword" in prompt_content: # generate citation search keyword
#     #         if "rich history" in prompt_content: return "history of guitars"
#     #         if "antonio de torres" in prompt_content: return "Antonio de Torres luthier"
#     #         return "general music facts"
#     #     elif "which of the following urls is the most relevant" in prompt_content: # choose best exlink
#     #         if "http://example.com/guitarhistory" in prompt_content: return "http://example.com/guitarhistory"
#     #         if "http://example.com/torresbio" in prompt_content: return "http://example.com/torresbio"
#     #         return "NO_SUITABLE_LINK_FOUND"
#     #     return None

#     # def mock_google_search_ext_links(*args, **kwargs):
#     #     query = kwargs.get('query', '').lower()
#     #     if "history of guitars" in query:
#     #         return [{'link': 'http://example.com/guitarhistory', 'title': 'Guitar History Site'}]
#     #     if "antonio de torres luthier" in query:
#     #         return [{'link': 'http://example.com/torresbio', 'title': 'Torres Biography'}]
#     #     return []

#     # with mock.patch('workflows.external_links_processor.call_openai_chat', side_effect=mock_openai_for_ext_links), \
#     #      mock.patch('workflows.external_links_processor.google_search', side_effect=mock_google_search_ext_links):
#     #
#     #    updated_sections = process_external_links_for_article(
#     #        sample_sections_content, 
#     #        article_title_test_ext, 
#     #        mock_config, 
#     #        run_id_test_ext
#     #    )
#     #    for section in updated_sections:
#     #        logger.info(f"Section: {section['sectionName']}")
#     #        logger.info(f"Updated Content:\n{section['current_html_content']}\n-----------------")
#            # Add assertions here