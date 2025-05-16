# prompts/main_prompts.py

# ==============================================================================
# PROMPT FOR KEYWORD ANALYSIS (Xac dinh searchIntent, contentFormat)
# ==============================================================================
# Placeholders:
#   {keyword}: The main keyword being analyzed.
#   {search_results_data}: A string representation of the Google SERP data (list of URLs, titles, snippets).
#                          You'll need to format your search_results_data (list of dicts) into a readable string.
ANALYZE_KEYWORD_FROM_SERP_PROMPT = """
Analyze the list of 10 Google search results for the keyword '{keyword}', 
including URLs, titles, and snippets, to determine the user's likely search intent, 
the most suitable content format, the appropriate article type, the writing model 
for a blog post, and the semantic keywords. Here are the search results:

{search_results_data}

1. What is the most likely search intent of the user based on these results?
2. Choose one content format for the blog post, without additional explanation, from these options: Step-by-step guide, Listicle, Comparison, Review, or How-to guide.
3. Based on the previously determined search intent, select the article type as follows: Choose 'Type 1: Best Product List' only when the search intent explicitly and unmistakably indicates a desire for a list of products, leaving no doubt that the searcher is specifically looking for a curated compilation of top products to purchase. In all other cases, opt for 'Type 2: Informational'.
4. Based on the search intent, select one writing model for the article, without additional explanation, from these options: 'FAB', 'AIDA', '5Ws', 'SWOT', 'USP', 'USM'.
5. Identify a comprehensive list of semantic keywords for the topic '{keyword}'. Consider the broad context of the subject, encompassing user intents, related concepts, industry jargon, and common queries. Focus on terms that are directly related and peripheral to the main keyword, offering a holistic view of the topic. Include variations, synonyms, and related phrases that users might use to search for information on this topic. Compile a concise yet diverse list of these keywords to effectively enhance content optimization and searchability across various platforms.

Please provide the analysis in JSON format with keys: 'searchIntent', 'contentFormat', 'articleType', 'selectedModel', 'semanticKeyword' where each key's value is limited to the specified choices without further elaboration.

Output Structure:
{{
  "searchIntent": "[Your analysis on the likely search intent]",
  "contentFormat": "[Selected content format from the given options]",
  "articleType": "[Selected article type from the given options]",
  "selectedModel": "[Selected writing model from the given options]",
  "semanticKeyword": ["[list", "of", "semantic", "keywords]"]
}}
"""

# ==============================================================================
# PROMPT FOR CHOOSING AUTHOR (Gemini - choose Author1 / Choose Author)
# ==============================================================================
# Placeholders:
#   {topic_title}: The title or main keyword of the article.
#   {authors_list_json_string}: A JSON string representing the list of author personas and their info.
#                               (e.g., json.dumps(AUTHOR_PERSONAS_from_settings))
CHOOSE_AUTHOR_PROMPT = """
Given the specific areas of expertise of the authors, identify the most suitable author 
to write content on this specific topic: '{topic_title}'. 
The chosen author should have the most relevant background, experience, and knowledge 
in relation to the topic. Return the selected author's information in JSON format 
with the following structure:

{{
  "name": "Author's Name",
  "info": "Author's Information", 
  "ID": "Author's ID"
}}

Here is the list of authors:
{authors_list_json_string}
"""

# ==============================================================================
# PROMPT FOR ARTICLE OUTLINE - TYPE 1 (BEST PRODUCT LIST)
# ==============================================================================
# Placeholders:
#   {keyword}: The main keyword.
#   {search_intent}: Determined from ANALYZE_KEYWORD_FROM_SERP_PROMPT.
#   {content_format}: Determined from ANALYZE_KEYWORD_FROM_SERP_PROMPT.
#   {article_type}: Should be "Type 1: Best Product List".
#   {selected_model}: Writing model (e.g., AIDA, FAB).
#   {semantic_keyword_list_string}: A string of semantic keywords, comma-separated.
OUTLINE_GENERATION_TYPE1_PROMPT = """
Given the keyword '{keyword}', create a structured article outline in a valid JSON format, 
considering the search intent '{search_intent}', content format '{content_format}', 
article type '{article_type}', and integrating the '{selected_model}' writing model.

The outline should start with an 'Introduction' and end with 'FAQs' and 'Conclusion', 
with chapters and sub-chapters structured according to the roles in the '{selected_model}' model. 

Immediately following the introduction, generate a section highlighting top-rated products 
with sub-chapters for each product related to '{keyword}'. 
Ensure that all product names and models mentioned in the outline correspond to real, 
existing products in the market. IMPORTANT: Do not include fictional or hypothetical products. 
The article should reflect accurate and current market offerings, using only genuine 
product names and models that are verifiable and relevant to the topic.

For each sub-chapter in the "Top-Rated Products" section, the subchapterName must be 
the product's actual name. In addition, each product should have a unique headline 
in the 'headline' key that reflects a specific characteristic or benefit. 
The headline must follow the format "best for [specific use or feature]", 
clearly indicating why each product is the top choice within a certain range or 
for a specific use case. Do not repeat the product name in the headline.

For each chapter and subchapter, select appropriate semantic keywords from the 
following list: {semantic_keyword_list_string}. These should be inserted into the 
'separatedSemanticKeyword' key for each chapter/subchapter, ensuring that the 
selected keywords are highly relevant and contribute meaningfully to the content 
of each section.

After the top-rated products section, produce additional relevant chapters/sub-chapters 
that explore different facets of the product based on the keyword. Each of these 
chapters/sub-chapters should also include a "modelRole" corresponding to its purpose 
in the {selected_model} model and a 'separatedSemanticKeyword' list of carefully 
selected semantic keywords.

Structure the output as follows:

- 'title': Generate 01 engaging, experience-driven article titles based on the keyword: '{keyword}'.
  The titles should feel authentic, professional, and written by an expert who has 
  personally tested, reviewed, or worked with the subject matter.
  Ensure the titles follow one (or a mix) of these styles:
  🔹 Hands-on Review & Firsthand Experience: Titles should imply the author has personally tested or worked with the product/issue (e.g., "I Tried X for 30 Days – Here’s What Happened").
  🔹 Expert Opinion & Deep Insights: Titles should sound like they come from an industry professional with inside knowledge (e.g., "As a Mechanic, Here’s My Take on X").
  🔹 Real-World Comparisons & Testing: Titles should highlight actual performance, comparisons, or evaluations (e.g., "We Tested 10 X – This One Stands Out").
  🔹 Mistakes & Lessons Learned: Titles should suggest learning from experience or revealing little-known facts (e.g., "X Mistakes Everyone Makes With Y – And How to Fix Them").
  🔹 Industry Secrets & Insider Knowledge: Titles should give off an exclusive, insider perspective (e.g., "What Experts Won’t Tell You About X – Until Now").
  Make sure the titles sound natural and compelling, not generic or robotic. Avoid vague or clickbait phrases. Instead, focus on creating a sense of credibility, authority, and hands-on experience.

- 'slug': Create a WordPress SEO slug related to the keyword without the current year.
- 'description': A concise 160-character SEO description that captures the essence of the article.
- 'chapters': An array of chapter objects, each with 'chapterName', 'modelRole', 
              'separatedSemanticKeyword', and 'length' key indicating the word count for the chapter. 
              Include subchapters as needed, reflecting the selected content format and article type. 
              Each subchapter is an object with 'subchapterName', 'modelRole', 
              'separatedSemanticKeyword', and 'length' key indicating the word count for the subchapter, 
              aligning with its parent chapter. For the sub-chapters that are products 
              belonging to top-rated products, there is an additional key 'headline'. 
              If a chapter does not have subchapters, set 'subchapters' to an empty array ('[]') or null.

Note: Avoid adding detailed content descriptions under each chapter or subchapter. 
Please maintain the exact spelling of variables as mentioned (subchapterName, chapterName, 
title, slug, description, chapters, modelRole, separatedSemanticKeyword, length, headline). 
Exclude mentions of the year for a timeless appeal.
"""

# ==============================================================================
# PROMPT FOR ARTICLE OUTLINE - TYPE 2 (INFORMATIONAL)
# ==============================================================================
# Placeholders:
#   {keyword}: The main keyword.
#   {search_intent}: Determined from ANALYZE_KEYWORD_FROM_SERP_PROMPT.
#   {content_format}: Determined from ANALYZE_KEYWORD_FROM_SERP_PROMPT.
#   {article_type}: Should be "Type 2: Informational".
#   {selected_model}: Writing model (e.g., AIDA, FAB).
#   {semantic_keyword_list_string}: A string of semantic keywords, comma-separated.
OUTLINE_GENERATION_TYPE2_PROMPT = """
Given the keyword '{keyword}', create a structured article outline in a valid JSON format, 
considering the search intent '{search_intent}', content format '{content_format}', 
article type '{article_type}', and integrating the '{selected_model}' writing model. 
The outline should start with an 'Introduction' and end with 'FAQs' and 'Conclusion', 
with chapters and sub-chapters structured according to the roles in the '{selected_model}' model.

For each chapter and subchapter, select appropriate semantic keywords from the 
following list: {semantic_keyword_list_string}. These should be inserted into the 
'separatedSemanticKeyword' key for each chapter/subchapter, ensuring that the 
selected keywords are highly relevant and contribute meaningfully to the content 
of each section.

Structure the output as follows:

- 'title': Generate 01 engaging, experience-driven article titles based on the keyword: '{keyword}'.
  The titles should feel authentic, professional, and written by an expert who has 
  personally tested, reviewed, or worked with the subject matter.
  Ensure the titles follow one (or a mix) of these styles:
  🔹 Hands-on Review & Firsthand Experience: Titles should imply the author has personally tested or worked with the product/issue (e.g., "I Tried X for 30 Days – Here’s What Happened").
  🔹 Expert Opinion & Deep Insights: Titles should sound like they come from an industry professional with inside knowledge (e.g., "As a Mechanic, Here’s My Take on X").
  🔹 Real-World Comparisons & Testing: Titles should highlight actual performance, comparisons, or evaluations (e.g., "We Tested 10 X – This One Stands Out").
  🔹 Mistakes & Lessons Learned: Titles should suggest learning from experience or revealing little-known facts (e.g., "X Mistakes Everyone Makes With Y – And How to Fix Them").
  🔹 Industry Secrets & Insider Knowledge: Titles should give off an exclusive, insider perspective (e.g., "What Experts Won’t Tell You About X – Until Now").
  Make sure the titles sound natural and compelling, not generic or robotic. Avoid vague or clickbait phrases. Instead, focus on creating a sense of credibility, authority, and hands-on experience.

- 'slug': Create a WordPress SEO slug related to the keyword without the current year.
- 'description': A concise 160-character SEO description that captures the essence of the article.
- 'chapters': An array of chapter objects, each with 'chapterName', 'modelRole', 
              'separatedSemanticKeyword', and 'length' key indicating the word count for the chapter. 
              Include subchapters as needed, reflecting the selected content format and article type. 
              Each subchapter is an object with 'subchapterName', 'modelRole', 
              'separatedSemanticKeyword', and 'length' key indicating the word count for the subchapter, 
              aligning with its parent chapter (around 100-200 words for each chapter/subchapter). 
              If a chapter does not have subchapters, set 'subchapters' to an empty array ('[]') or null. 

Note: Avoid adding detailed content descriptions under each chapter or subchapter. 
Please maintain the exact spelling of variables as mentioned (subchapterName, chapterName, 
title, slug, description, chapters, modelRole, separatedSemanticKeyword, length). 
Do not mention the year in the response.
"""

# ==============================================================================
# PROMPT FOR ENRICHING OUTLINE WITH AUTHOR INFO AND SECTION HOOKS
# (OpenAI2 / OpenAI4 nodes - Best - Outline / Other - Outline output goes here)
# ==============================================================================
# Placeholders:
#   {keyword}: The main keyword of the article.
#   {initial_outline_json_string}: The JSON string of the outline generated by
#                                  OUTLINE_GENERATION_TYPE1_PROMPT or OUTLINE_GENERATION_TYPE2_PROMPT.
#   {author_name}: Name of the chosen author.
#   {author_bio}: The 'info' field of the chosen author.
ENRICH_OUTLINE_WITH_AUTHOR_AND_HOOKS_PROMPT = """
Given the initial outline of an article focused on '{keyword}':

Here's the initial article outline:
{initial_outline_json_string}

And here's the information about {author_name} - the author:
"{author_bio}"

For each chapter and sub-chapter of the provided outline, develop an 'authorInfo' snippet 
that reflects a specific aspect of {author_name}'s expertise or experience relevant 
to the chapter's focus. Ensure that the 'authorInfo' adds a personal touch and 
professional insights to each section, enhancing the overall guide with 
{author_name}'s unique perspective.

Additionally, please update the outline by adding a 'sectionHook' key to each chapter 
and every sub-chapter within. Consider the following types suitable for the content 
and purpose of the chapter and every sub-chapter within:

1. Intriguing Questions: Pose a question that reflects a key theme or dilemma in the chapter, provoking thought and interest.
2. Fascinating Facts: Use an interesting fact or statistic that sets the stage for the chapter's content.
3. Brief Anecdotes: Share a concise, relevant anecdote that ties into the chapter's main point.
4. Bold Claims or Statements: Make a strong claim related to the chapter's topic to spark curiosity and debate.

Ensure that each 'sectionHook' is:
- Directly relevant to the chapter/sub-chapter's content and keywords.
- Engaging and varied in style to maintain reader interest.
- Providing enough context so readers are intrigued and motivated to read on.

IMPORTANT:
- The output should be strictly in valid JSON format.
- Remove any trailing commas or formatting errors.
- Do not include comments or unrelated content in the JSON.
- Ensure the integrity of the original outline is maintained by including ALL original keys and values from the initial outline, and only adding 'authorInfo' and 'sectionHook' to each chapter and subchapter object.
- Validate that each generated JSON object adheres to the JSON standard before returning the response.
The final output must be a single JSON object representing the complete, enriched outline.
"""

# ==============================================================================
# PROMPT FOR GENERATING INTERNAL LINKING KEYWORDS (Get internalKeywords2)
# ==============================================================================
# Placeholders:
#   {base_keyword}: The main keyword of the article being written (from Import Keyword).
#   {article_title_for_backlinks}: The title of the article being written (to which links will point).
INTERNAL_LINKING_KEYWORDS_PROMPT = """
Given the base keyword "{base_keyword}", generate a list of related and 
contextually relevant keywords that can be used for internal linking within the site, 
specifically focusing on creating backlinks to the article with the title 
'{article_title_for_backlinks}'. 
Ensure the keywords reflect the content's main topics and themes, 
and include variations where relevant.

Provide gap values where necessary to maintain the context and meaning of the keywords. 
When suggesting keywords with gaps, adhere to the following formats:

For "Minimal" Type, use "word1 {{+integer}} word2".
For "Exact" Type, use "word1 {{integer}} word2".
For "Maximum" Type, use "word1 {{-integer}} word2".

When suggesting keywords and their variants, consider the following:

Include both singular and plural forms where applicable.
Consider synonyms and closely related terms that reflect the content.
Provide gap values where necessary to maintain the context and meaning of the phrases.
Exclude any variations related to capitalization to focus on substantive variations.

Output the keywords in the following JSON format: ["keyword 1", "keyword 1 variant", "keyword 2", "keyword 2 variant", ...]

IMPORTANT: Return the response STRICTLY in a valid JSON format without any additional 
formatting characters. Focus on the unique aspects of the subject matter to ensure 
relevance and precision.
"""

# ==============================================================================
# PROMPT FOR CATEGORY RECOMMENDATION (Xac dinh Category1)
# ==============================================================================
# Placeholders:
#   {category_list_string}: A string describing the existing category structure (Parent: Sub1, Sub2\n...).
#   {keyword}: The keyword for which to recommend a category.
#   {search_intent}: The search intent for the keyword.
RECOMMEND_CATEGORY_PROMPT = """
I am organizing a database of articles and need to efficiently categorize them 
based on keywords and search intents. Below is a list of existing categories 
and sub-categories. Please analyze each provided keyword and its search intent, 
then recommend the most appropriate and specific category or sub-category for it. 
Provide only the most relevant and direct recommendation.

Task Instructions:

1. Understand the Keyword and Search Intent: Reflect on the meaning and the likely 
   context of the keyword. How might a user think about this item or topic?
2. Recommend a Category/Sub-Category: Choose the most relevant and specific 
   sub-category from the existing list. If a keyword fits well within a sub-category, 
   recommend only that sub-category. Consider where a user would most directly find 
   information about the keyword. When selecting a category from the list, ensure 
   the name is used exactly as it appears, without alterations or spelling variations.
3. New Category Consideration: Only suggest a new category/sub-category if no 
   existing one is a good fit. Ensure the new category is broad enough to include 
   a range of related articles.

Existing Categories/Sub-Categories:
{category_list_string}

For Each Keyword:

Keyword: "{keyword}"
Search Intent: "{search_intent}"
Consideration: "Evaluate whether the keyword fits more specifically within a sub-category. 
Recommend only the sub-category if it provides a clear and direct match for the 
keyword's intent."

Provide Your Recommendation:
Output as JSON with the following structure:
{{
  "recommendation": {{
    "category": "The most relevant and specific Sub-Category name. If there is no matching option, let it be null"
  }},
  "isNew": "yes/no - Indicate if this is a new category/sub-category suggestion. Only 'yes' when the appropriate category/sub-category cannot be found from the list.",
  "suggestedName": "Name of the proposed new category/sub-category, if applicable. Should be null if isNew is 'no'."
}}

Note: Emphasize precision and the need for direct categorization. The goal is to 
place each keyword in the most specific and relevant spot, enhancing the overall 
navigability of the database. Ensure that the category names are used exactly as 
they appear in the list, maintaining accuracy in spelling and formatting. 
If recommending an existing category, "suggestedName" should be null.
If suggesting a new category ("isNew": "yes"), "recommendation.category" should be null.
"""

# ==============================================================================
# PROMPT FOR CHECKING KEYWORD SUITABILITY (Check Suitable)
# ==============================================================================
# Placeholders:
#   {keyword}: The keyword to check.
CHECK_KEYWORD_SUITABILITY_PROMPT = """
Given that I have a website about music and musical instruments and need to write blog posts, 
evaluate whether the keyword '{keyword}' is suitable for the blog post. 
A keyword is suitable ('yes') if it meets the following criteria:

Relates to general music knowledge, technical guidance, or musical instruments.
Excludes overly specific keywords about tabs, chords, charts, or individual song titles.
Avoids biographical trivia, personal gossip, or pop culture unless directly tied to music, instruments, or their impact.
Avoids keywords about artist deaths, health, or unrelated locations unless relevant to their musical legacy.

Respond in JSON format with a single key "suitable" and a value of "yes" or "no".
Example: {{"suitable": "yes"}}
"""