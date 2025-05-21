# prompts/image_prompts.py

# ==============================================================================
# PROMPT TO GENERATE IMAGE SEARCH KEYWORD FOR A SECTION/SUBSECTION
# (Tương ứng với node "Promt to find image Keyword" -> "find imageKeyword1" hoặc "Gemini - choose Author" trong v11)
# ==============================================================================
# Placeholders:
#   {section_type}: "chapter" hoặc "sub-section" (hoặc "subchapter" như trong code của bạn).
#   {section_name}: Tên của chapter hoặc sub-section.
#   {parent_section_name}: Tên của chapter cha (chỉ cần nếu section_type là "sub-section"/"subchapter").
#   {article_title}: Tiêu đề của toàn bộ bài viết.
GENERATE_IMAGE_SEARCH_KEYWORD_PROMPT = """
Consider the {section_type} titled "{section_name}" {parent_context_string}from the article "{article_title}".

Your task is to recommend a specific and visually descriptive keyword phrase (ideally 2-5 words) for an image search that would best illustrate the core subject or a key visual aspect of this section. 
Think about what a relevant photograph or illustration for this section might actually *show*.

Avoid abstract concepts or qualities (like "quality", "effectiveness", "importance") unless they are part of a more descriptive phrase that clearly implies a visual (e.g., "demonstrating software effectiveness on screen", "close-up of high-quality material weave", "historical importance illustrated via artifact").
Focus on tangible objects, specific scenes, actions, or visually distinct features relevant to "{section_name}".

For example:
- If article is about **Guitars** and section_name is "Anatomy of a Stratocaster Neck", good keywords: "Stratocaster guitar neck profile", "close-up Stratocaster headstock". Bad: "Neck Quality".
- If article is about **Software Development** and section_name is "Optimizing Database Queries", good keywords: "database query execution plan diagram", "flowchart of SQL optimization", "server room database racks". Bad: "Query Speed".
- If article is about **Gardening** and section_name is "Choosing the Right Soil for Tomatoes", good keywords: "hands holding rich potting soil", "tomato plants in raised garden bed", "soil pH test kit". Bad: "Soil Importance".
- If article is about **Travel** and section_name is "Exploring the Amalfi Coast", good keywords: "Positano cliffside village view", "Amalfi Coast lemon groves", "boat tour Capri grotto". Bad: "Coastal Beauty".
- If section_name is "Build Quality and Playability Insights" (for a physical product like a lap steel guitar), good keywords: "lap steel guitar construction detail", "close-up Rogue RLS-1 lap steel", "hand playing lap steel guitar". Bad: "Playability".
- If article is about **Cooking** and section_name is "Essential Kitchen Tools", good keywords: "chef's knife on cutting board", "kitchen utensils organized drawer", "mixing bowl set". Bad: "Kitchen Efficiency".
- If article is about **Firearms** and section_name is "Understanding Ballistics", good keywords: "ballistic gel test with bullet", "firearm ballistic trajectory diagram", "close-up of bullet impact". Bad: "Ballistic Performance".
- If article is about **Photography** and section_name is "Mastering Low Light Photography", good keywords: "camera settings for low light", "night cityscape with stars", "photographer using tripod at night". Bad: "Low Light Techniques".

Provide ONLY the keyword phrase, without quotation marks or any other explanatory text.
"""
# Lưu ý: {parent_context_string} sẽ được điền động trong Python.
# Ví dụ: nếu section_type là "sub-section", parent_context_string = f"from the section \"{parent_section_name}\" "
#        nếu section_type là "chapter", parent_context_string = ""

# ==============================================================================
# PROMPT TO CHOOSE THE BEST IMAGE FROM SEARCH RESULTS
# (Tương ứng với node "Promt to choose best imageURL")
# ==============================================================================
# Placeholders:
#   {article_title}: Tiêu đề của toàn bộ bài viết.
#   {section_type}: "section" (cho chapter) hoặc "sub-section" (cho subchapter).
#   {section_name}: Tên của chapter hoặc sub-section.
#   {parent_section_name}: Tên của chapter cha (nếu là sub-section).
#   {image_options_string}: Một chuỗi liệt kê các lựa chọn ảnh, mỗi lựa chọn bao gồm
#                           "Image Description", "imageURL".
#                           Ví dụ: "1. Image Description: ABC, imageURL: http://... \n
#                                   2. Image Description: XYZ, imageURL: http://..."
CHOOSE_BEST_IMAGE_URL_PROMPT = """
Given the article titled "{article_title}" {parent_context_string_for_selection}, 
which image best visually represents its content or theme based on the description provided? 

IMPORTANT: The image should ideally have a clear file format extension in its URL if visible (e.g., .jpg, .png, .gif), though this is not a strict requirement for selection if the description is highly relevant.
Return the response STRICTLY in a valid JSON format without any additional formatting characters. 
The JSON should have two keys: "imageURL" for the image URL and "imageDes" for the image description.

Here are the options:
{image_options_string}

If no images are suitable or available, return JSON with null values: 
{{"imageURL": null, "imageDes": null}}
"""
# Lưu ý: {parent_context_string_for_selection} sẽ được điền động trong Python.
# Ví dụ:
# if section_type == 'chapter':
#   parent_context_string_for_selection = f", the section \"{section_name}\""
# else: # subchapter
#   parent_context_string_for_selection = f", and its specific sub-section \"{section_name}\" (of chapter \"{parent_section_name}\")"


# ==============================================================================
# PROMPT FOR GENERATING DALL-E FEATURED IMAGE DESCRIPTION
# (Từ workflow chính [fretterverse]-v14-main, node "OpenAI" trước "OpenAI1" (DALL-E call))
# ==============================================================================
# Placeholders:
#   {article_title_raw}: Tiêu đề gốc của bài viết.
#   (Bạn có thể thêm các placeholder khác nếu muốn, ví dụ {main_keyword} để DALL-E tập trung hơn)
GENERATE_DALLE_FEATURED_IMAGE_DESCRIPTION_PROMPT = """
With the article title '{article_title_raw}', I am seeking a captivating featured image 
created by Dall-E 3. The image should creatively embody the theme of guitars, 
showcasing them in an environment or context that enhances their allure. 

Employ a photography style that complements the setting, possibly with a color scheme 
featuring neutral tones to evoke a warm, inviting atmosphere, or a style that matches 
the specific mood or genre of the article title. Aim for a composition that could be wide angle 
or a focused shot, ensuring strong contrast or harmony between elements to draw the 
viewer's attention and create visual intrigue.

The description you provide should vividly detail:
1.  **Main Focus:** What is the central subject of the image (e.g., a specific type of guitar, a person playing, a collection)?
2.  **Setting/Environment:** Where is the main focus situated (e.g., a cozy room, a stage, a workshop, an abstract background)?
3.  **Supporting Elements:** What other objects or details are present to enhance the theme (e.g., amplifier, sheet music, tools, atmospheric lighting)?
4.  **Artistic Style:** Specify the desired style (e.g., photorealistic, digital art, impressionistic, vintage photo, cinematic lighting, golden hour).
5.  **Color Palette & Mood:** Describe the dominant colors and the overall feeling the image should convey (e.g., warm and nostalgic, energetic and modern, mysterious and moody).
6.  **Composition Details:** (Optional) Any specific requests for camera angle, depth of field, etc.

Provide just a detailed description for Dall-E 3 only, no other information or introductory phrases are necessary. 
The description should be rich enough for Dall-E 3 to generate a compelling and relevant image.
"""