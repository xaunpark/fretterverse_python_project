# prompts/video_prompts.py

# ==============================================================================
# PROMPT TO GENERATE VIDEO SEARCH KEYWORD FOR A SECTION
# (Tương ứng với node "keyword for Citations1" trong _fretterverse__v9_video)
# ==============================================================================
# Placeholders:
#   {section_name}: Tên của section (chapter/subchapter).
#   {article_title}: Tiêu đề của toàn bộ bài viết.
#   {parent_section_name}: Tên chapter cha nếu section_name là subchapter (tùy chọn, thêm nếu cần)
#                          Trong prompt gốc của bạn, nó không phân biệt rõ ràng chapter/subchapter
#                          cho việc tạo keyword này, chỉ dùng sectionName.
GENERATE_VIDEO_SEARCH_KEYWORD_PROMPT = """
If you were to identify the central theme or the most defining moment of the section 
titled "{section_name}" from the article "{article_title}", 
what specific keyword or phrase would you recommend for a relevant video search? 
Give me just only one keyword or phrase without using quotation marks.
"""
# Nếu muốn phân biệt rõ hơn cho subchapter:
# GENERATE_VIDEO_SEARCH_KEYWORD_FOR_SUBCHAPTER_PROMPT = """
# If you were to identify the central theme or the most defining moment of the sub-section
# titled "{sub_section_name}" from the chapter "{parent_section_name}" of the article "{article_title}",
# what specific keyword or phrase would you recommend for a relevant video search?
# Give me just only one keyword or phrase without using quotation marks.
# """


# ==============================================================================
# PROMPT TO CHOOSE THE BEST VIDEO FROM YOUTUBE SEARCH RESULTS
# (Tương ứng với node "Promt to find Video" -> "choose best videoID")
# ==============================================================================
# Placeholders:
#   {article_title}: Tiêu đề của toàn bộ bài viết.
#   {section_type}: "section" (cho chapter) hoặc "sub-section" (cho subchapter).
#   {section_name}: Tên của chapter hoặc sub-section.
#   {parent_section_name}: Tên của chapter cha (nếu là sub-section, để làm rõ context).
#   {video_options_string}: Một chuỗi liệt kê các lựa chọn video, mỗi lựa chọn bao gồm
#                           "Video Title", "Video Description", "videoID".
#                           Ví dụ: "1. Video Title: ABC, Video Description: Desc1, videoID: id1 \n
#                                   2. Video Title: XYZ, Video Description: Desc2, videoID: id2"
CHOOSE_BEST_VIDEO_ID_PROMPT = """
Given the article titled "{article_title}"{section_context_string}, 
which video best represents its content or theme based on the description provided? 

IMPORTANT: Return the response STRICTLY in a valid JSON format without any 
additional formatting characters. The JSON should have keys for "videoID", 
"videoTitle", and "videoDescription". Choose the one that is most relevant.

Here are the options:
{video_options_string}

If no videos are suitable or available from the options, return JSON with null values for videoID, 
and appropriate messages for videoTitle and videoDescription, for example:
{{"videoID": null, "videoTitle": "No suitable video found", "videoDescription": "No video from the provided options was deemed relevant to the section."}}
"""
# Lưu ý: {section_context_string} sẽ được điền động trong Python.
# Ví dụ:
# if section_type == 'chapter':
#   section_context_string = f", the section \"{section_name}\""
# elif section_type == 'subchapter' and parent_section_name:
#   section_context_string = f", and its specific sub-section \"{section_name}\" (of chapter \"{parent_section_name}\")"
# else:
# section_context_string = f", the section/sub-section \"{section_name}\""