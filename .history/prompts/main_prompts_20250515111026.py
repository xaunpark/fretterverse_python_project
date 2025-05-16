# prompts/main_prompts.py

# Prompt để phân tích keyword, search intent, content format từ Google Search results
# {keyword} và {search_results_string} sẽ được fill bằng .format() hoặc f-string
ANALYZE_KEYWORD_INTENT_PROMPT = """
Analyze the list of 10 Google search results for the keyword '{keyword}', 
including URLs, titles, and snippets, to determine the user's likely search intent, 
the most suitable content format, the appropriate article type, the writing model 
for a blog post, and the semantic keywords. Here are the search results:

{search_results_string}

1. What is the most likely search intent of the user based on these results?
2. Choose one content format for the blog post, without additional explanation, from these options: Step-by-step guide, Listicle, Comparison, Review, or How-to guide.
3. Based on the previously determined search intent, select the article type as follows: Choose 'Type 1: Best Product List' only when the search intent explicitly and unmistakably indicates a desire for a list of products... In all other cases, opt for 'Type 2: Informational'.
4. Based on the search intent, select one writing model for the article...: 'FAB', 'AIDA', '5Ws', 'SWOT', 'USP', 'USM'.
5. Identify a comprehensive list of semantic keywords for the topic '{keyword}'...

Please provide the analysis in JSON format with keys: 'searchIntent', 'contentFormat', 'articleType', 'selectedModel', 'semanticKeyword' where each key's value is limited to the specified choices without further elaboration."

Output Structure:
{{
  "searchIntent": "[Your analysis on the likely search intent]",
  "contentFormat": "[Selected content format from the given options]",
  "articleType": "[Selected article type from the given options]",
  "selectedModel": "[Selected writing model from the given options]",
  "semanticKeyword": ["[list", "of", "semantic", "keywords]"] 
}}
"""

# Prompt để tạo outline cho bài viết Type 1 (Best Product List)
# {keyword}, {search_intent}, {content_format}, {article_type}, {selected_model}, {semantic_keywords_list}
OUTLINE_GENERATION_TYPE1_PROMPT = """
Given the keyword '{keyword}', create a structured article outline in a valid JSON format, 
considering the search intent '{search_intent}', content format '{content_format}', 
article type '{article_type}', and integrating the '{selected_model}' writing model.

The outline should start with an 'Introduction' and end with 'FAQs' and 'Conclusion'...
Immediately following the introduction, generate a section highlighting top-rated products...
For each sub-chapter in the "Top-Rated Products" section, the subchapterName must be the product's actual name...
For each chapter and subchapter, select appropriate semantic keywords from the following list: {semantic_keywords_list}...
Each product should have a unique headline that reflects a specific characteristic or benefit...

Structure the output as follows:
- 'title': Generate 01 engaging, experience-driven article titles based on the keyword: '{keyword}'...
- 'slug': Create a WordPress SEO slug...
- 'description': A concise 160-character SEO description...
- 'chapters': An array of chapter objects, each with 'chapterName', 'modelRole', 'separatedSemanticKeyword', and 'length'...

Note: Avoid adding detailed content descriptions... Exclude mentions of the year...
"""
# Bạn sẽ cần copy toàn bộ prompt từ file JSON n8n vào đây,
# và thay các placeholder của n8n ({{...}}) bằng placeholder của Python ({...})

# Prompt để tạo outline cho bài viết Type 2 (Informational)
OUTLINE_GENERATION_TYPE2_PROMPT = """
Given the keyword '{keyword}', create a structured article outline in a valid JSON format, 
considering the search intent '{search_intent}', content format '{content_format}', 
article type '{article_type}', and integrating the '{selected_model}' writing model.
The outline should start with an 'Introduction' and end with 'FAQs' and 'Conclusion'...

For each chapter and subchapter, select appropriate semantic keywords from the following list: {semantic_keywords_list}...

Structure the output as follows:
- 'title': Generate 01 engaging, experience-driven article titles...
- 'slug': Create a WordPress slug...
- 'description': A concise 160-character description...
- 'chapters': An array of chapter objects...

Note: Avoid adding detailed content descriptions... Do not mention the year...
"""

# Prompt để chọn Author
CHOOSE_AUTHOR_PROMPT = """
Given the specific areas of expertise of the authors, identify the most suitable author 
to write content on this specific topic: '{topic_title}'. 
The chosen author should have the most relevant background, experience, and knowledge...
Return the selected author's information in JSON format...

Here is the list of authors:
{authors_json_string} 
""" # authors_json_string sẽ là chuỗi JSON của danh sách author personas

# Prompt để thêm authorInfo và sectionHook vào outline
ENRICH_OUTLINE_PROMPT = """
Given the initial outline of an article focused on '{keyword}':

Here's the initial article outline:
{initial_outline_json_string}

And here's the information about {author_name} - the author:
"{author_bio}"

For each chapter and sub-chapter of the provided outline, develop an 'authorInfo' snippet 
that reflects a specific aspect of {author_name}'s expertise...
Additionally, please update the outline by adding a 'sectionHook' key to each chapter 
and every sub-chapter within...

1. Intriguing Questions...
2. Fascinating Facts...
3. Brief Anecdotes...
4. Bold Claims or Statements...

IMPORTANT:
- The output should be strictly in valid JSON format.
- Ensure the integrity of the original outline is maintained.
...
"""