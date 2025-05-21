# prompts/content_writing_prompts.py

# ==============================================================================
# PROMPT FOR WRITING INTRODUCTION SECTION
# ==============================================================================
WRITE_INTRODUCTION_PROMPT = """
Craft an engaging {length}-word first-person introduction for the informational article titled '{article_title}'. 
As {author_name}, draw from the expertise and lived experiences detailed in '{author_info}'. Your narrative should feel authentic, grounded in real-world encounters, extensive research, consultations with professionals, or testing of solutions, directly addressing common reader concerns.

**Your Voice and Approach (Crucial for Credibility):**
Speak directly using 'I' and 'my'. Your tone must be expert yet relatable, instilling confidence that the content is based on genuine experience. **Crucially, adopt a critically analytical and objective mindset:**
- When sharing initial insights or setting the stage, ensure a balanced perspective. If hinting at solutions or problems, acknowledge potential complexities or varied viewpoints.
- Avoid unsubstantiated claims or overly enthusiastic language. Your credibility stems from thoughtful consideration and a commitment to providing a comprehensive, honest overview.
- This balanced, objective approach is paramount and must be evident from the outset.

Incorporate these semantic keywords: '{semantic_keywords}' to ensure topical relevance.

The introduction must be concise, seamlessly transitioning to the article's main content.
Output strictly in HTML: use only <p>, <strong>, and <em> tags. No other HTML (like <div>, <span>, <html>, <head>, <body>) or Markdown. Ensure clean, readable formatting with paragraphs and line breaks; AVOID WALLS OF TEXT. Do not repeat the article title.

For context, refer to the article outline: {section_names_list}.
"""
# Lưu ý: Prompt gốc trong n8n cho Introduction có phần phức tạp hơn về các loại hook.
# Bạn có thể tích hợp logic chọn hook vào Python hoặc đơn giản hóa prompt như trên.
# Prompt gốc của bạn cho Introduction đã bao gồm các loại hook, tôi sẽ giữ lại ý đó:
WRITE_INTRODUCTION_PROMPT_WITH_HOOK_CHOICES = """
Craft a concise {length}-word first-person introduction for the article titled '{article_title}'.
As {author_name}, drawing from the expertise and lived experiences in '{author_info}', begin with a compelling hook related to '{keyword_for_hook}'. Choose ONE hook style:
1.  **Narrative:** Start a story of a significant change/event, withholding the end to build curiosity.
2.  **Research:** Tease an intriguing finding/statistic, revealing just enough to spark interest.
3.  **Argument:** Make a bold/unexpected claim, delaying explanation to create debate.
Ensure your chosen hook is relevant, engaging, and smoothly transitions into the article's theme, setting an authentic tone based on real experience.

**Your Voice and Critical Approach (Paramount for this Introduction):**
Speak directly using 'I' and 'my'. Your tone must be expert yet relatable. **Crucially, apply a critically analytical and objective mindset from the very first sentence, including the hook:**
-   Even when using a hook, ensure it's presented with intellectual honesty. If making a claim (Argument Hook) or sharing a narrative, avoid hyperbole. If presenting research (Research Hook), ensure it's contextually sound.
-   Your initial statements must reflect thoughtful consideration, aiming for a balanced and credible setup rather than uncritical enthusiasm.
-   This balanced, objective approach is fundamental to establish trust immediately.

Incorporate these semantic keywords for depth: '{semantic_keywords}'.

The introduction must be concise and transition seamlessly.
Output strictly in HTML: use only <p>, <strong>, and <em>. No other HTML or Markdown. Ensure clean, readable formatting; AVOID WALLS OF TEXT. Do not repeat the article title.

For context, refer to the article outline: {section_names_list}.
"""
# Bạn sẽ cần thêm placeholder {keyword_for_hook} khi format prompt này.

# ==============================================================================
# PROMPT FOR WRITING CONCLUSION SECTION
# ==============================================================================
WRITE_CONCLUSION_PROMPT = """
Craft a concise {length}-word first-person conclusion for the article titled '{article_title}'.
As {author_name}, drawing from your expertise and lived experiences ('{author_info}'), encapsulate the article's main points and emphasize its key message, reflecting the '{model_role}' aspect of the {selected_model} model. {prompt_section_hook}

**Your Concluding Voice and Critical Reflection (Paramount for Impact):**
Speak directly using 'I' and 'my'. Your tone should be authentic and align with your established expertise. **Crucially, maintain a critically analytical and objective mindset even in your final thoughts:**
-   When summarizing or offering final takeaways, ensure a balanced perspective. If reinforcing a solution or viewpoint, subtly acknowledge any remaining complexities or areas for further consideration, rather than presenting it as an absolute or overly simplistic final word.
-   Avoid conclusive statements that sound like unsupported hyperbole or mere personal opinion without the backing of the article's content. Your final words should resonate with credibility and thoughtful reflection.
-   This balanced, objective approach is essential for a powerful and trustworthy conclusion.

Incorporate these semantic keywords for relevance: '{semantic_keywords}'.

The conclusion must be concise yet powerful, providing a coherent wrap-up.
Output strictly in HTML: use only <p>, <strong>, and <em>. No other HTML or Markdown. Ensure clean, readable formatting; AVOID WALLS OF TEXT. Do not repeat the article title.

For context, refer to the full article outline: {section_names_list}.
"""

# ==============================================================================
# PROMPT FOR GENERATING FAQ SECTION (Schema.org compliant)
# ==============================================================================
# Placeholder:
#   {article_title}: Title of the article for context.
#   (LLM is expected to generate relevant Q&A based on the title and general knowledge)
WRITE_FAQ_SECTION_PROMPT = """
Strictly generate an HTML code snippet that adheres to the FAQ schema of schema.org 
for the topic '{article_title}'. The output must begin directly with the tag 
'<div itemscope itemtype="https://schema.org/FAQPage">' 
and end with its corresponding closing tag '</div>'. 
Each FAQ question should be enclosed within 
'<div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">', 
with questions using the <h3> tag (e.g., '<h3 itemprop="name">Your Question Here?</h3>') 
and answers nested within their respective FAQ schema using 
'<div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer"><div itemprop="text">Your Answer Here.</div></div>'. 
Do not introduce or end the output with any extraneous characters, notations, or line breaks. 
The aim is to receive a clean, deployment-ready HTML segment that accurately and 
professionally presents the topic's key information in an engaging manner. 
Generate between 3 to 5 relevant question-answer pairs for the given topic.
"""

# ==============================================================================
# PROMPT FOR WRITING A GENERAL CHAPTER (Not Intro, Conclusion, FAQ, or Product Review)
# ==============================================================================
WRITE_CHAPTER_PROMPT = """
Write a {length}-word, first-person section on '{section_name}' for the article '{article_title}', aligning with the '{model_role}' aspect of the {selected_model} model. {prompt_section_hook}
As {author_name}, draw from your expertise and lived experiences ('{author_info}') to share unique insights and detailed knowledge.

**Authorial Voice, Perspective, and Critical Analysis (Paramount for this Section):**
Speak directly using 'I' and 'my'. Your voice must be authentic, expert, and personally engaging, reflecting your passion for the subject. **Crucially, all insights, experiences, and evaluations shared must be presented through a critically analytical and objective lens:**
-   When detailing your perspective or experiences, ensure a balanced discussion. Objectively analyze all facets, including not only positive aspects or successes but also potential limitations, drawbacks, challenges encountered, or alternative viewpoints.
-   Ground all statements, especially those conveying strong opinions or conclusions, in reasoned logic or clearly articulated experience. Avoid unsubstantiated claims, emotional bias, or hyperbole.
-   The goal is to provide a balanced, credible, and insightful perspective that reflects deep, thoughtful consideration, rather than mere promotion, uncritical enthusiasm, or undue criticism. This approach is vital for enriching the content informatively.

Incorporate these semantic keywords for relevance and depth: '{semantic_keywords}'.

This section must be concise yet rich with insightful observations, transitioning smoothly and fitting cohesively within the article.
Output strictly in HTML: use only <p>, <strong>, and <em>. No other HTML or Markdown. Ensure clean, readable formatting with paragraphs; AVOID WALLS OF TEXT. Do not repeat titles.

For context, refer to the full article outline: {section_names_list}.
"""
# ==============================================================================
# PROMPT FOR WRITING A GENERAL SUBCHAPTER (Not Product Review)
# ==============================================================================
WRITE_SUBCHAPTER_PROMPT = """
Write a concise, {length}-word first-person subchapter on '{section_name}' for the article '{article_title}'. 
As {author_name}, drawing from your expertise ('{author_info}'), clearly highlight this subchapter's relevance and contribution to its parent category, '{parent_section_name}'. This section must align with the '{model_role}' aspect of the {selected_model} model. {prompt_section_hook}

**Authorial Voice and Critical Analysis for Subchapter (Paramount for Cohesion and Credibility):**
Speak directly using 'I' and 'my'. Your voice must be authentic and demonstrate in-depth knowledge. **Crucially, all insights, explanations, or evaluations within this subchapter must be presented through a critically analytical and objective lens:**
-   When explaining concepts or detailing information specific to this subchapter, ensure a balanced presentation. If discussing benefits or applications, also consider potential limitations, prerequisites, or alternative perspectives relevant to this specific scope.
-   Ground all statements in reasoned logic or clearly articulated experience. Avoid unsubstantiated claims or hyperbole, especially when emphasizing the subchapter's importance or a particular point within it.
-   The aim is a balanced, credible, and insightful subchapter that reflects thoughtful consideration, contributing cohesively to the parent category with well-supported observations rather than mere assertion or uncritical enthusiasm.

Incorporate these semantic keywords for relevance: '{semantic_keywords}'.

This subchapter must be concise, providing insightful observations and seamlessly integrating with logical transitions.
Output strictly in HTML: use only <p>, <strong>, and <em>. No other HTML or Markdown. Ensure clean, readable formatting with paragraphs and line breaks; AVOID WALLS OF TEXT. Do not repeat titles or use unnecessary quotes.

For context and coherence with the overall outline, refer to: {section_names_list}.
"""

# ==============================================================================
# PROMPT FOR WRITING A PRODUCT REVIEW SUBCHAPTER (sectionNameTag = "Product")
# ==============================================================================
WRITE_PRODUCT_REVIEW_SUBCHAPTER_PROMPT = """
Write a concise, {length}-word first-person review for the product '{section_name}' (headline: '{headline}'), as part of the article '{article_title}'.
As {author_name}, drawing from your expertise and lived experiences ('{author_info}'), highlight this product's relevance to '{parent_section_name}' and align with the '{model_role}' of the {selected_model} model. {prompt_section_hook}

**Product Review Approach: Balanced, Authentic, and Insightful (Adherence is Paramount):**
Speak directly using 'I' and 'my'. Your review must be informative, personal, and relatable, reflecting your authentic experiences and unique insights. **Crucially, your evaluation of '{section_name}' must be critically analytical and objective throughout:**
-   **Share Direct Experience & Feelings:** Discuss your personal use or observation of the product. Include a brief, realistic narrative.
-   **Balanced Evaluation:** Objectively analyze all facets. When discussing why it's a suitable choice (or not), present both strengths and weaknesses. Avoid hyperbole, emotional bias, or uncritical praise. Ground your assessment in reasoned logic and clearly articulated experience.
-   **Goal:** Provide a credible, insightful, and well-rounded perspective that genuinely helps the reader, reflecting thoughtful consideration rather than mere promotion or undue criticism.

Incorporate these semantic keywords for relevance: '{semantic_keywords}'.

**Review Structure and Content:**
1.  **Main Review Body:** Your personal experience, evaluation, and narrative.
2.  **Pros and Cons Summary:** At the end, provide a structured summary:
    <strong>Pros:</strong>
    <ul><li>Pro point 1 (2-4 total).</li></ul>
    <strong>Cons:</strong>
    <ul><li>Con point 1 (1-3 total, representing genuine drawbacks).</li></ul>
3.  **Comparative Analysis:** Briefly compare '{section_name}' with 1-2 other products from '{product_list}'. Objectively highlight differences, unique selling points, practical uses, and potential trade-offs.

This review must be concise, seamlessly integrated with logical transitions.
Output strictly in HTML: use only <p>, <strong>, <em>, <ul>, and <li>. No other HTML or Markdown. Ensure clean, readable formatting with paragraphs; AVOID WALLS OF TEXT. Do not repeat titles.

For context and coherence, refer to the full article outline: {section_names_list}.
"""

# ==============================================================================
# PROMPT FOR "I LOVE YOU" (Placeholder for chapters that are just parent containers)
# ==============================================================================
SAY_I_LOVE_YOU_PROMPT = "Please respond with exactly three words expressing affection, specifically 'I love you'."

# ==============================================================================
# PROMPT FOR REFINE AND FINALIZE ARTICLE
# ==============================================================================
REFINE_AND_FINALIZE_ARTICLE_PROMPT = """
You are an expert editor tasked with refining and finalizing a draft article.
The article's main topic is: "{article_topic}"
The desired tone is: "{desired_tone}"
The content provided is structured into sections, and each section was initially intended to have a certain length. While refining, focus on quality and coherence rather than drastically altering the overall length from the sum of its original section lengths.

Please perform the following actions on the draft:

1.  **Enhance and Deepen Content:**
    *   Actively incorporate verifiable data, statistics, research-backed examples, or illustrative quotes to substantiate claims.
    *   Expand on generic statements with detailed explanations, context, or varied perspectives.
    *   Ensure all arguments are well-supported and logical. Improve transitions between ideas, paragraphs, and sections for a cohesive narrative.
    *   Make content more insightful and practically valuable, removing any superficial or redundant information.

2.  **Preserve Media Tags:**
    *   **Images (`<figure><img ...>`)**: MUST be preserved perfectly (src, alt, placement). DO NOT alter or remove.
    *   **Videos (`<iframe>`):** MUST be preserved perfectly (src, attributes, placement). DO NOT alter or remove.

3.  **Preserve and Adapt External Links (`<a>` tags):**
    *   All existing `<a>` tags (external links) MUST be preserved in terms of their **count and their `href`, `target`, and `rel` attributes**. The destination URL (`href`) MUST NOT BE CHANGED.
    *   You MAY CAREFULLY rephrase the **anchor text** (the visible text of the `<a>` tag) ONLY IF the surrounding edited text makes the original anchor awkward or grammatically incorrect. The new anchor text MUST remain highly relevant to the link's `href`.
    *   Ensure the `<a>` tag structure is maintained if anchor text is modified.
    *   DO NOT remove existing external links. Keep them contextually relevant to their original placement.

4. Adopt a critically analytical and objective mindset. (**CORE GUIDELINE FOR CONTENT TONE AND SUBSTANCE (Adherence is paramount):**)
When sharing insights, experiences, or evaluations:
- Objectively analyze all facets: Discuss not only positive aspects but also potential limitations, drawbacks, or alternative viewpoints.
- Ground your statements in reasoned logic or clearly articulated experience, avoiding unsubstantiated claims, emotional bias, or hyperbole.
- Strive for a balanced, credible, and insightful perspective that reflects thoughtful consideration rather than mere promotion or undue criticism.

5.  **Formatting and Output:**
    *   It MUST also correctly include existing `<a>` tags (for external links), `<img>` tags (within `<figure>`), and `<iframe>` tags (for videos) from the draft without altering their `src` or `href` attributes unless it's to fix a clear formatting error around them.
    *   Do NOT add any introductory or concluding remarks outside of the article content itself (e.g., no "Here is the revised article:", "I have made the following changes:", etc.).
    *   Do NOT add or change any HTML `id` attributes on existing header tags (h2, h3).
    *   Ensure there are no weird characters, uninterpreted Markdown, or extraneous lines.
    *   AVOID WALLS OF TEXT. Use paragraphs and line breaks to enhance readability.

Please provide the fully refined and finalized HTML content of the article, respecting the original intended structure and flow as much as possible while enhancing its quality.

Here is the draft HTML content of the article:
--------------------------------------------------
{draft_html_content}
--------------------------------------------------
"""