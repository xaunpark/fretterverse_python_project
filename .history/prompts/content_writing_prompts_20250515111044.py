# prompts/content_prompts.py

# Prompt chung để viết một chapter/subchapter (bạn có thể tùy biến thêm)
# Các placeholder: {length}, {section_name}, {article_title}, {model_role}, 
#                  {selected_model}, {prompt_section_hook}, {author_name}, 
#                  {author_info}, {semantic_keywords}, {section_names_list}
#                  {parent_section_name} (cho subchapter)
#                  {headline} (cho product subchapter)
#                  {product_list} (cho product subchapter)

WRITE_INTRODUCTION_PROMPT = """
Write an engaging {length} word introduction for an informational article titled '{article_title}'...
As you develop this introduction, incorporate the following semantic keywords...: '{semantic_keywords}'.
Write in the first-person perspective as {author_name}, fully embodying the expertise...: '{author_info}'.
Generate content strictly in HTML format...
For additional context, refer back to the full article outline, including sections such as {section_names_list}.
"""

WRITE_CONCLUSION_PROMPT = """
Craft a concise {length} word first-person conclusion for the article titled '{article_title}'.
This conclusion should effectively reflect the '{model_role}' aspect of the {selected_model} model...
{prompt_section_hook}
As you develop this conclusion, incorporate...: '{semantic_keywords}'.
Write in the first-person perspective as {author_name}...: '{author_info}'.
Generate content strictly in HTML format...
For additional context...: {section_names_list}.
"""

WRITE_FAQ_SECTION_PROMPT = """
Strictly generate an HTML code snippet that adheres to the FAQ schema of schema.org 
for the topic '{article_title}'. The output must begin directly with the tag 
'<div itemscope itemtype="https://schema.org/FAQPage\">'...
""" # Prompt này có thể không cần nhiều placeholder

WRITE_CHAPTER_PROMPT = """
Write a {length} word, first-person section on '{section_name}', as part of the article '{article_title}', 
aligning with the '{model_role}' aspect of the {selected_model} model. {prompt_section_hook}
Write in the first-person perspective as {author_name}...: '{author_info}'.
Highlight the author's unique perspective...
Generate content strictly in HTML format...
Pay special attention to creating a smooth transition... For additional coherence and context, refer back to the full article outline: {section_names_list}.
"""
# Lưu ý: Prompt này cần được cập nhật để bao gồm semantic_keywords

WRITE_SUBCHAPTER_PROMPT = """
Write a concise, {length} word first-person section on '{section_name}', highlighting its relevance 
and contribution to the parent category '{parent_section_name}', as part of the article '{article_title}'. 
This section should align with the '{model_role}' aspect of the {selected_model} model... 
{prompt_section_hook}
As you develop this section, incorporate...: '{semantic_keywords}'.
Write in the first-person perspective as {author_name}...: '{author_info}'.
Use p tags for paragraphs...
Pay special attention to the placement... For additional context and coherence...: {section_names_list}.
"""

WRITE_PRODUCT_REVIEW_SUBCHAPTER_PROMPT = """
Write a concise, {length} word first-person review for the product '{section_name}' 
with the headline '{headline}'. Highlight its relevance... to the parent category '{parent_section_name}' 
within the article '{article_title}'. This review should align with the '{model_role}' aspect of the {selected_model} model...
{prompt_section_hook}
As you develop this review, incorporate...: '{semantic_keywords}'.
Write in the first-person perspective as {author_name}...: '{author_info}'.
Focus on sharing your direct experience...
At the end of the review, provide a structured summary of the product's advantages and disadvantages...
<strong>Pros:</strong><ul><li>...</li></ul><strong>Cons:</strong><ul><li>...</li></ul>
Additionally, include a comparative analysis with one or two other products mentioned in the article: '{product_list}'.
Generate content strictly in HTML format...
Pay special attention to the placement... For additional context and coherence...: {section_names_list}.
"""