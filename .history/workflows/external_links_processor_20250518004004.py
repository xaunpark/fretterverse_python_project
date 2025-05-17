# workflows/external_links_processor.py
import logging
import random
import re 
import html 
import urllib.parse 
from bs4 import BeautifulSoup
from utils.api_clients import call_openai_chat, perform_search 
# from utils.redis_handler import RedisHandler # Sẽ được thay thế bởi RunContext
from prompts import external_link_prompts

logger = logging.getLogger(__name__)

def _get_redis_exlinks_array_key(config, unique_run_id):
    return f"{config.get('REDIS_KEY_EXLINKS_ARRAY_PREFIX', 'fvp_exlinks_array_')}{unique_run_id}"

def _should_skip_external_links(section_data):
    section_name = section_data.get('sectionName', '').lower()
    section_name_tag = section_data.get('sectionNameTag', '').lower()
    mother_chapter = section_data.get('motherChapter', 'no').lower()
    section_index = section_data.get('sectionIndex')
    skip_conditions = [
        section_name == "introduction", section_name == "faqs", section_name == "conclusion",
        section_name_tag == "introduction", section_name_tag == "conclusion", section_name_tag == "faqs",
        mother_chapter == "yes", "top rated" in section_name,
        (isinstance(section_index, int) and section_index == 2)
    ]
    if any(skip_conditions):
        logger.info(f"Skipping external links for section '{section_data.get('sectionName')}' due to skip conditions. Details: name='{section_name}', tag='{section_name_tag}', mother='{mother_chapter}', index='{section_index}'")
        return True
    return False

def _extract_text_from_html(html_content):
    if not html_content: return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        for script_or_style in soup(["script", "style"]): script_or_style.decompose()
        return soup.get_text(separator=" ", strip=True)
    except Exception: return html_content

def _find_context_sentence(full_text, anchor_text, sentences_around=1):
    if not full_text or not anchor_text: return anchor_text
    sentences = re.split(r'(?<=[.!?])\s+', full_text)
    cleaned_anchor = anchor_text.replace('.', '').strip().lower()
    for i, sentence in enumerate(sentences):
        if cleaned_anchor in sentence.lower():
            start_index = max(0, i - sentences_around)
            end_index = min(len(sentences), i + sentences_around + 1)
            return " ".join(sentences[start_index:end_index]).strip()
    return anchor_text

def _is_valid_url(url_string):
    if not url_string or not isinstance(url_string, str): return False
    regex = re.compile(r'^(?:http|ftp)s?://(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[?[A-F0-9]*:[A-F0-9:]+\]?)(?::\d+)?(?:/?|[/?]\S+)$', re.IGNORECASE)
    return re.match(regex, url_string) is not None

def _extract_first_valid_url_from_string(text_containing_url):
    if not text_containing_url: return None
    match = re.search(r'https?://[^\s]+', text_containing_url)
    if match:
        url = re.sub(r'[.,)\]!]$', '', match.group(0))
        if _is_valid_url(url): return url
    return None

def process_external_links_for_section(
    section_data, article_title_main, 
    redis_handler, config, openai_api_key, google_api_key, 
    unique_run_id
):
    min_links = config.get('EXTERNAL_LINKS_PER_SECTION_MIN', 1) # Giảm min xuống 1 để dễ thấy kết quả
    max_links = config.get('EXTERNAL_LINKS_PER_SECTION_MAX', 2) # Giảm max xuống 2 để test nhanh hơn
    num_links_to_find = random.randint(min_links, max_links)

    original_html_content = section_data.get('current_html_content', '')
    updated_html_content = original_html_content

    if _should_skip_external_links(section_data) or not original_html_content.strip():
        logger.debug(f"ExtLinks: Skipped or no content for section '{section_data.get('sectionName')}'.")
        return original_html_content

    logger.info(f"ExtLinks: Processing section '{section_data.get('sectionName')}', aiming for ~{num_links_to_find} links.")
    plain_text_content = _extract_text_from_html(original_html_content)
    if not plain_text_content.strip() or len(plain_text_content.split()) < 15:
        logger.warning(f"ExtLinks: Not enough plain text in '{section_data.get('sectionName')}' for citations.")
        return original_html_content

    prompt_get_anchors = external_link_prompts.IDENTIFY_ANCHOR_TEXTS_FOR_CITATIONS_PROMPT.format(
        num_key_phrases=num_links_to_find, section_content_text=plain_text_content
    )
    anchor_texts_info_raw = call_openai_chat(
        [{"role": "user", "content": prompt_get_anchors}],
        model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'), 
        api_key=openai_api_key, # OpenAI API key gốc
        is_json_output=True,
        target_api="openrouter",
        openrouter_api_key=config.get('OPENROUTER_API_KEY'),
        openrouter_base_url=config.get('OPENROUTER_BASE_URL')
    )
    
    # Kiểm tra định dạng của anchor_texts_info_raw
    anchor_texts_info = []
    if isinstance(anchor_texts_info_raw, list):
        anchor_texts_info = anchor_texts_info_raw
    elif isinstance(anchor_texts_info_raw, dict):
        # Thêm các key bạn đã thấy trong log vào đây
        possible_keys = ["citations", "essential_citations", "citedPhrases", "key_phrases", "keyPhrases", "result"] 
        for key_option in possible_keys:
            if key_option in anchor_texts_info_raw and isinstance(anchor_texts_info_raw[key_option], list):
                anchor_texts_info = anchor_texts_info_raw[key_option]
                logger.debug(f"ExtLinks: Extracted anchor texts from key '{key_option}'.")
                break
        if not anchor_texts_info:
            logger.warning(f"ExtLinks: LLM returned a dict for anchor texts but no known/expected list key found for '{section_data.get('sectionName')}'. Response: {anchor_texts_info_raw}")
            # return original_html_content # Có thể dừng sớm nếu không có anchor
    else:
        logger.warning(f"ExtLinks: Failed to get valid anchor texts structure for '{section_data.get('sectionName')}'. Type: {type(anchor_texts_info_raw)}, Response: {anchor_texts_info_raw}")
        # return original_html_content # Có thể dừng sớm

    if not anchor_texts_info: # Nếu vẫn rỗng sau khi thử các key
        logger.info(f"ExtLinks: No anchor texts could be extracted for '{section_data.get('sectionName')}'.")
        return original_html_content # Dừng xử lý section này nếu không có anchor
    
    logger.debug(f"ExtLinks: Anchors for '{section_data.get('sectionName')}': {anchor_texts_info}")

    redis_exlinks_key = _get_redis_exlinks_array_key(config, unique_run_id)
    
    links_inserted_count = 0
    processed_anchors_in_section = set()

    for anchor_info in anchor_texts_info:
        if links_inserted_count >= num_links_to_find: break
        anchor_text_original = anchor_info.get('anchortext')
        if not anchor_text_original or not isinstance(anchor_text_original, str) or \
           anchor_text_original.lower() in processed_anchors_in_section:
            continue
        
        temp_soup = BeautifulSoup(updated_html_content, "html.parser")
        if anchor_text_original.lower() not in temp_soup.get_text(separator=" ").lower(): # Dùng separator=" "
            logger.warning(f"ExtLinks: Anchor '{anchor_text_original}' not found in HTML of '{section_data.get('sectionName')}'. Skipping.")
            continue

        context_sentence = _find_context_sentence(plain_text_content, anchor_text_original)
        prompt_citation_keyword = external_link_prompts.GENERATE_CITATION_SEARCH_KEYWORD_PROMPT.format(
            article_title_main=article_title_main, anchor_text=anchor_text_original,
            full_context_sentence=context_sentence, chapter_name=section_data.get('sectionName')
        )
        citation_search_keyword = call_openai_chat(
            [{"role": "user", "content": prompt_citation_keyword}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'), 
            api_key=openai_api_key, # OpenAI API key gốc
            target_api="openrouter",
            openrouter_api_key=config.get('OPENROUTER_API_KEY'),
            openrouter_base_url=config.get('OPENROUTER_BASE_URL')
        )
        if not citation_search_keyword: continue
        logger.info(f"ExtLinks: Search keyword for '{anchor_text_original}': '{citation_search_keyword}'")

        # Thay thế google_search bằng perform_search
        # google_api_key không cần truyền trực tiếp nữa, perform_search sẽ lấy từ config
        search_results_items = perform_search(
            query=urllib.parse.quote_plus(citation_search_keyword),
            search_type='web',
            config=config, # perform_search sẽ lấy API keys và provider từ đây
            num_results=config.get('GOOGLE_SEARCH_NUM_RESULTS_EXT_LINKS', 5) # Giảm số lượng kết quả cho test
        )
        if not search_results_items: continue

        link_options_parts = [f"{i+1}. Link Title: {item.get('title', 'N/A')}, linkURL: {item.get('link', 'N/A')}"
                              for i, item in enumerate(search_results_items)]
        link_options_str = "\n".join(link_options_parts) or "No links found."

        prompt_choose_exlink = external_link_prompts.CHOOSE_BEST_EXTERNAL_LINK_PROMPT.format(
            article_title_main=article_title_main, chapter_name_context=section_data.get('sectionName'),
            anchor_text_context=anchor_text_original, sentence_context=context_sentence,
            link_options_string=link_options_str
        )
        selected_url_string = call_openai_chat(
            [{"role": "user", "content": prompt_choose_exlink}],
            model_name=config.get('DEFAULT_OPENAI_CHAT_MODEL'), 
            api_key=openai_api_key, # OpenAI API key gốc
            target_api="openrouter",
            openrouter_api_key=config.get('OPENROUTER_API_KEY'),
            openrouter_base_url=config.get('OPENROUTER_BASE_URL')
        )
        if not selected_url_string or selected_url_string == "NO_SUITABLE_LINK_FOUND": continue
        
        final_url_to_insert = _extract_first_valid_url_from_string(selected_url_string)
        if not final_url_to_insert: continue
        logger.info(f"ExtLinks: AI selected URL '{final_url_to_insert}' for '{anchor_text_original}'.")

        current_exlinks_array = redis_handler.get_value(redis_exlinks_key) or []
        if not isinstance(current_exlinks_array, list): current_exlinks_array = []
        
        normalized_url_to_check = final_url_to_insert.lower().replace("www.", "").rstrip('/')
        is_duplicate = any(url_entry.lower().replace("www.", "").rstrip('/') == normalized_url_to_check 
                           for url_entry in current_exlinks_array)
        if is_duplicate: 
            logger.info(f"ExtLinks: URL '{final_url_to_insert}' is duplicate. Skipping.")
            continue
        
        # Chèn link: dùng regex để tìm anchor_text dưới dạng một từ/cụm từ hoàn chỉnh
        # và không nằm trong một tag <a> khác. Đây là một regex cải tiến hơn.
        # Nó tìm anchor_text mà không có > ngay trước và không có < ngay sau (để tránh nằm trong tag)
        # và cũng không phải là một phần của href="...anchor_text..."
        # Cần escape anchor_text cho regex.
        escaped_regex_anchor = re.escape(anchor_text_original)
        # Pattern: tìm anchor_text không phải là text của một link đã có (không nằm giữa > và </a>)
        # và không phải là giá trị của href.
        # ( Negative lookbehind: (?<! ... ) , Negative lookahead: (?! ... ) )
        # (?<!>) : không có > ngay trước
        # (?![^<]*<\/a>) : không có </a> theo sau mà không gặp < (nghĩa là không phải text của link)
        # (?!(?:(?!href=).)*?") : không nằm trong dấu nháy kép của một attribute không phải href
        # (?!(?:(?!>).)*<) : không nằm trong một tag html
        # Đây là một regex rất phức tạp và khó để đúng 100% cho mọi trường hợp HTML.
        # Cách tiếp cận đơn giản hơn nhưng kém chính xác hơn:
        # target_pattern = re.compile(r"\b" + re.escape(anchor_text_original) + r"\b", re.IGNORECASE)
        # if target_pattern.search(updated_html_content):
        #     updated_html_content = target_pattern.sub(link_html, updated_html_content, 1)

        # Cách tiếp cận an toàn hơn với BeautifulSoup để thay thế text node
        soup = BeautifulSoup(updated_html_content, 'html.parser')
        text_nodes_containing_anchor = soup.find_all(string=re.compile(re.escape(anchor_text_original), re.IGNORECASE))
        logger.debug(f"ExtLinks: Found {len(text_nodes_containing_anchor)} text nodes potentially containing anchor '{anchor_text_original}'.")

        replaced_in_soup = False
        for text_node_idx, text_node in enumerate(text_nodes_containing_anchor):
            logger.debug(f"ExtLinks: Checking text node {text_node_idx}: '{str(text_node)[:100]}...' Parent: {text_node.parent.name}")
            if text_node.parent.name == 'a': # Đã là link rồi, bỏ qua
                continue
            
            # Thay thế an toàn
            node_content = str(text_node)
            # Tìm vị trí chính xác, không phân biệt hoa thường
            match_obj = re.search(re.escape(anchor_text_original), node_content, re.IGNORECASE)
            if match_obj:
                start, end = match_obj.span()
                original_matched_text = node_content[start:end] # Lấy đúng text gốc đã khớp
                
                # Tạo link với text gốc đã khớp (để giữ nguyên case nếu có)
                linked_anchor_html = f'<a href="{html.escape(final_url_to_insert)}" target="_blank" rel="noopener noreferrer">{html.escape(original_matched_text)}</a>'
                
                # Tạo các phần mới
                before_text = node_content[:start]
                after_text = node_content[end:]
                
                new_tag_sequence = []
                if before_text: new_tag_sequence.append(BeautifulSoup(before_text, 'html.parser').contents[0] if len(BeautifulSoup(before_text, 'html.parser').contents)>0 else before_text)
                new_tag_sequence.append(BeautifulSoup(linked_anchor_html, 'html.parser'))
                if after_text: new_tag_sequence.append(BeautifulSoup(after_text, 'html.parser').contents[0] if len(BeautifulSoup(after_text, 'html.parser').contents)>0 else after_text)

                text_node.replace_with(*new_tag_sequence) # Giải nén list thành các arguments
                replaced_in_soup = True
                logger.debug(f"ExtLinks: Successfully prepared replacement for '{original_matched_text}'.")
                break # Chỉ thay thế lần đầu tiên tìm thấy
            else:
                logger.debug(f"ExtLinks: Regex did not match '{anchor_text_original}' in text node content '{node_content[:50]}...'")
                                    
        if replaced_in_soup:
            updated_html_content = str(soup)
            logger.info(f"ExtLinks: Inserted link for anchor '{anchor_text_original}' in section '{section_data.get('sectionName')}'.")
            links_inserted_count += 1
            processed_anchors_in_section.add(anchor_text_original.lower())
            current_exlinks_array.append(final_url_to_insert)
            redis_handler.set_value(redis_exlinks_key, list(set(current_exlinks_array)))
        else:
            logger.warning(f"ExtLinks: Could not replace anchor '{anchor_text_original}' in HTML (maybe already linked or complex structure) of section '{section_data.get('sectionName')}'.")

    return updated_html_content


def process_external_links_for_article(sections_with_content_list, article_title_main, run_context, config):
    logger.info(f"Starting external links processing for article: '{article_title_main}' with run_id: {run_context.unique_run_id}")

    openai_api_key = config.get('OPENAI_API_KEY')
    google_api_key = config.get('GOOGLE_API_KEY')
    # SỬ DỤNG GOOGLE_CX_ID CHUNG
    google_cx_id_shared = config.get('GOOGLE_CX_ID') 

    if not all([openai_api_key, google_api_key, google_cx_id_shared]): # google_api_key vẫn cần cho perform_search nếu provider là google
        logger.error("Missing critical API keys or Google CX ID for external links in config.")
        return sections_with_content_list 

    # redis_handler = RedisHandler(config=config) # Sẽ thay thế bằng run_context
    # if not redis_handler.is_connected():
    #     logger.error("Cannot connect to Redis. Aborting external links processing.")
    #     return sections_with_content_list

    # redis_exlinks_key = _get_redis_exlinks_array_key(config, run_context.unique_run_id) # Sẽ dùng run_context trực tiếp
    # run_context.used_external_links đã được khởi tạo là set rỗng

    updated_sections_list = []
    for section_data in sections_with_content_list:
        current_section_copy = dict(section_data) 
        updated_content = process_external_links_for_section(
            section_data=current_section_copy,
            article_title_main=article_title_main,
            # redis_handler=redis_handler, # Sẽ truyền run_context vào process_single_section_external_links
            run_context=run_context, # Tạm thời truyền vào đây
            config=config,
            openai_api_key=openai_api_key,
            google_api_key=google_api_key,
            unique_run_id=run_context.unique_run_id # Vẫn cần unique_run_id cho _get_redis_exlinks_array_key (sẽ sửa sau)
        )
        current_section_copy['current_html_content'] = updated_content
        updated_sections_list.append(current_section_copy)

    logger.info(f"Finished external links processing for article '{article_title_main}'.")
    return updated_sections_list