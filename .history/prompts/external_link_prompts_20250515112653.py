# prompts/external_link_prompts.py

# ==============================================================================
# PROMPT TO IDENTIFY ANCHOR TEXTS FOR CITATIONS
# (Tương ứng với node "get Citations")
# ==============================================================================
# Placeholders:
#   {num_key_phrases}: Số lượng cụm từ khóa cần xác định (ví dụ, 2-4).
#   {section_content_text}: Nội dung text của section (đã loại bỏ HTML nếu cần,
#                           hoặc LLM tự xử lý nếu có khả năng).
IDENTIFY_ANCHOR_TEXTS_FOR_CITATIONS_PROMPT = """
Please analyze my text and identify the {num_key_phrases} key phrases that most critically 
require direct citations to support specific facts or claims made in the article. 
Focus should be on phrases related to historical details, technical information, 
or important factual statements. 

Output the results STRICTLY in JSON format, with each essential citation need 
represented as an object containing 'anchortext' for the phrase. 
Leave the 'sourceURL' field empty for now (e.g., "sourceURL": ""). 
The aim is to enhance the article's credibility by pinpointing where direct 
citations from authoritative sources are most needed.

Here is my text:
{section_content_text}

Example JSON output format for 2 key phrases:
[
  {{"anchortext": "identified key phrase 1", "sourceURL": ""}},
  {{"anchortext": "identified key phrase 2", "sourceURL": ""}}
]
"""

# ==============================================================================
# PROMPT TO GENERATE SEARCH KEYWORD FOR A CITATION
# (Tương ứng với node "keyword for Citations")
# ==============================================================================
# Placeholders:
#   {article_title_main}: Tiêu đề của toàn bộ bài viết chính.
#   {anchor_text}: Cụm từ cần tìm nguồn trích dẫn.
#   {full_context_sentence}: Câu đầy đủ chứa anchor_text.
#   {chapter_name}: Tên của chapter/section chứa anchor_text.
GENERATE_CITATION_SEARCH_KEYWORD_PROMPT = """
Please analyze the provided details from my document to suggest a highly relevant keyword. 
This keyword should guide a Google search towards authoritative and educational sources 
for citations, such as academic research, official reports, or established news articles. 

Avoid suggesting keywords that lead to competitive commercial websites or other content 
that directly competes with my article's topic (Article Title: {article_title_main}). 
The goal is to find credible, non-competitive sources that enhance the article's 
informational value. 

Provide just the keyword without any quotation marks or introductory phrases.

Here are the details for context:
Anchor Text: {anchor_text}
Full Context Sentence: {full_context_sentence}
Chapter Name: {chapter_name}
"""

# ==============================================================================
# PROMPT TO CHOOSE THE BEST EXTERNAL LINK (CITATION URL) FROM SEARCH RESULTS
# (Tương ứng với node "Promt to find best exlink")
# ==============================================================================
# Placeholders:
#   {article_title_main}: Tiêu đề của toàn bộ bài viết chính.
#   {chapter_name_context}: Tên của chapter/section chứa anchor_text.
#   {anchor_text_context}: Cụm từ (anchor text) đang cần tìm nguồn.
#   {sentence_context}: Câu đầy đủ chứa anchor_text.
#   {link_options_string}: Một chuỗi liệt kê các lựa chọn link, mỗi lựa chọn bao gồm
#                           "Link Title", "linkURL".
#                           Ví dụ: "1. Link Title: ABC, linkURL: http://... \n
#                                   2. Link Title: XYZ, linkURL: http://..."
CHOOSE_BEST_EXTERNAL_LINK_PROMPT = """
Given the article titled "{article_title_main}" with the chapter named "{chapter_name_context}" 
and the specific anchor text "{anchor_text_context}" which appears in the following context sentence:

"{sentence_context}"

Which of the following URLs is the most relevant, authoritative, and non-competitive source 
to cite for the given anchor text and context? 
Please prioritize educational, research, official reports, or highly reputable informational sites. 
Avoid commercial product pages, direct competitor articles, forums, or user-generated content sites 
unless they are exceptionally authoritative for the specific claim.

Please provide only the exact URL as a plain string, without quotes, punctuation, or any other text.

Here are the options:
{link_options_string}

If no URL from the options is suitable, please return the exact string "NO_SUITABLE_LINK_FOUND".
"""