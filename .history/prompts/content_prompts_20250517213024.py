# prompts/content_writing_prompts.py

# ==============================================================================
# PROMPT FOR WRITING INTRODUCTION SECTION
# ==============================================================================
WRITE_INTRODUCTION_PROMPT = """
Write an engaging {length} word introduction for an informational article titled '{article_title}' that feels authentic and based on real-world experience.

The introduction should give the impression that the author:
- Has personally encountered or researched the issue extensively (e.g., “I’ve dealt with this problem on my own car,” or “Our team has worked with hundreds of customers facing this issue”).
- Has gathered insights from professionals or experienced users (e.g., “We consulted X mechanics, car experts, or industry professionals”).
- Has tested or investigated different solutions and can provide practical advice (e.g., “We tried different methods and found what works best”).
- Understands common concerns and questions people have about this issue and addresses them directly.

The tone should be expert yet relatable, giving the reader confidence that the article is based on actual experience rather than generic information.
        
As you develop this introduction, incorporate the following semantic keywords to ensure relevance and depth: '{semantic_keywords}'. This will be your guide to maintaining focus on the topic's core aspects.
        
Write in the first-person perspective as {author_name}, fully embodying the expertise and lived experiences detailed in {author_name}'s info: '{author_info}'. Use 'I' and 'my' naturally to share insights as if you’ve personally lived through these experiences. Avoid third-party descriptions — speak directly and authentically, ensuring your voice aligns with {author_name}'s background and achievements.

Generate content strictly in HTML format, using only the following tags: <p> for paragraphs, <strong> for key points, and <em> for nuanced emphasis. Do not use any other HTML tags such as <div>, <span>, <html>, <head>, or <body>. Do not use Markdown. Ensure the output is clean, visually appealing, and flows naturally. The content must adhere strictly to these tag rules and avoid unnecessary formatting, document structure tags, or redundant information such as repeating titles.

This section should be concise, providing a seamless transition into the detailed discussions that follow in the article. For additional context, refer back to the full article outline, including sections such as: {section_names_list}.
"""
# Lưu ý: Prompt gốc trong n8n cho Introduction có phần phức tạp hơn về các loại hook.
# Bạn có thể tích hợp logic chọn hook vào Python hoặc đơn giản hóa prompt như trên.
# Prompt gốc của bạn cho Introduction đã bao gồm các loại hook, tôi sẽ giữ lại ý đó:
WRITE_INTRODUCTION_PROMPT_WITH_HOOK_CHOICES = """
Craft a concise {length} word first-person introduction for the article titled '{article_title}'. 
Begin with a compelling hook that instantly engages the reader. Incorporate one of the following hook styles, 
each tailored to the content and theme of '{article_title}' and related to '{keyword_for_hook}': 
    
1. Narrative Hook: Share the beginning of a profound change or event related to '{keyword_for_hook}', but withhold the conclusion. Provide just enough detail to make readers emotionally invested and curious about what comes next.
2. Research Hook: Highlight an intriguing finding or statistic about '{keyword_for_hook}', but only reveal a portion. Tease readers with enough information to pique their interest and leave them wanting more.
3. Argument Hook: Present a bold or unexpected claim about '{keyword_for_hook}', but don't immediately explain how it's true. Create a sense of mystery and debate that compels readers to continue for the explanation.

Use this hook to set the tone for the article and smoothly transition into the main theme. 
Ensure that the hook is directly relevant to the chapter's content and keywords, 
engaging and varied in style to maintain reader interest, and provides enough context 
so readers are intrigued and motivated to read on.
        
As you develop this introduction, incorporate the following semantic keywords to ensure relevance and depth: '{semantic_keywords}'. This will be your guide to maintaining focus on the topic's core aspects.
        
Write in the first-person perspective as {author_name}, fully embodying the expertise and lived experiences detailed in {author_name}'s info: '{author_info}'. Use 'I' and 'my' naturally to share insights as if you’ve personally lived through these experiences. Avoid third-party descriptions — speak directly and authentically, ensuring your voice aligns with {author_name}'s background and achievements.

Generate content strictly in HTML format, using only the following tags: <p> for paragraphs, <strong> for key points, and <em> for nuanced emphasis. Do not use any other HTML tags such as <div>, <span>, <html>, <head>, or <body>. Do not use Markdown. Ensure the output is clean, visually appealing, and flows naturally. The content must adhere strictly to these tag rules and avoid unnecessary formatting, document structure tags, or redundant information such as repeating titles.

This section should be concise, providing a seamless transition into the detailed discussions that follow in the article. For additional context, refer back to the full article outline, including sections such as: {section_names_list}.
"""
# Bạn sẽ cần thêm placeholder {keyword_for_hook} khi format prompt này.

# ==============================================================================
# PROMPT FOR WRITING CONCLUSION SECTION
# ==============================================================================
WRITE_CONCLUSION_PROMPT = """
Craft a concise {length} word first-person conclusion for the article titled '{article_title}'. 
This conclusion should effectively reflect the '{model_role}' aspect of the {selected_model} model, 
encapsulating the article's main points and emphasizing the key message. 

{prompt_section_hook}

As you develop this conclusion, incorporate the following semantic keywords to ensure relevance and depth: '{semantic_keywords}'.

Write in the first-person perspective as {author_name}, fully embodying the expertise and lived experiences detailed in {author_name}'s info: '{author_info}'. Use 'I' and 'my' naturally to share insights as if you’ve personally lived through these experiences. Avoid third-party descriptions — speak directly and authentically, ensuring your voice aligns with {author_name}'s background and achievements.

Generate content strictly in HTML format, using only the following tags: <p> for paragraphs, <strong> for key points, and <em> for nuanced emphasis. Do not use any other HTML tags such as <div>, <span>, <html>, <head>, or <body>. Do not use Markdown. Ensure the output is clean, visually appealing, and flows naturally. The content must adhere strictly to these tag rules and avoid unnecessary formatting, document structure tags, or redundant information such as repeating titles.

This section should be concise yet powerful, providing a seamless integration into the broader context of the article. For additional context and to ensure a coherent wrap-up, refer back to the full article outline, including sections such as: {section_names_list}.
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
Write a {length} word, first-person section on '{section_name}', as part of the article '{article_title}', 
aligning with the '{model_role}' aspect of the {selected_model} model. 
{prompt_section_hook}
As you develop this section, incorporate the following semantic keywords to ensure relevance and depth: '{semantic_keywords}'.

Write in the first-person perspective as {author_name}, fully embodying the expertise and lived experiences detailed in {author_name}'s info: '{author_info}'. Use 'I' and 'my' naturally to share insights as if you’ve personally lived through these experiences. Avoid third-party descriptions — speak directly and authentically, ensuring your voice aligns with {author_name}'s background and achievements.

Highlight the author's unique perspective, experiences, and insights to enrich the content, 
making it both informative and personally engaging. Ensure the section not only conveys 
detailed knowledge but also resonates with the reader through the author's authentic 
voice and passion for the subject.
            
Generate content strictly in HTML format, using only the following tags: <p> for paragraphs, <strong> for key points, and <em> for nuanced emphasis. Do not use any other HTML tags such as <div>, <span>, <html>, <head>, or <body>. Do not use Markdown. Ensure the output is clean, visually appealing, and flows naturally. The content must adhere strictly to these tag rules and avoid unnecessary formatting, document structure tags, or redundant information such as repeating titles.

Pay special attention to creating a smooth transition at both the beginning and end of this section, 
ensuring it fits cohesively within the overall theme of the article. This chapter should be 
concise yet rich with insightful observations, seamlessly integrated into the broader context 
of the article. For additional coherence and context, refer back to the full article outline: {section_names_list}.
"""

# ==============================================================================
# PROMPT FOR WRITING A GENERAL SUBCHAPTER (Not Product Review)
# ==============================================================================
WRITE_SUBCHAPTER_PROMPT = """
Write a concise, {length} word first-person section on '{section_name}', highlighting its relevance 
and contribution to the parent category '{parent_section_name}', as part of the article '{article_title}'. 
This section should align with the '{model_role}' aspect of the {selected_model} model and 
effectively demonstrate the author's expertise and in-depth knowledge of the topic. 
              
{prompt_section_hook}
              
As you develop this section, incorporate the following semantic keywords to ensure relevance and depth: '{semantic_keywords}'.

Write in the first-person perspective as {author_name}, fully embodying the expertise and lived experiences detailed in {author_name}'s info: '{author_info}'. Use 'I' and 'my' naturally to share insights as if you’ve personally lived through these experiences. Avoid third-party descriptions — speak directly and authentically, ensuring your voice aligns with {author_name}'s background and achievements.

Use p tags for paragraphs. Apply strong tags for key points and em tags for nuanced emphasis. 
Ensure the text is visually appealing and maintains the natural flow of content. 
Avoid repeating the article title, creating a separate chapter title, or using unnecessary quotation marks.

Pay special attention to the placement of this section within the overall outline of the article. 
Create logical and enhancing transitions at both the beginning and the end of this section, 
ensuring it contributes cohesively to the overall theme of the article. This section should be 
concise and seamlessly integrated into the broader context of the article, providing insightful 
observations without unnecessary repetition. For additional context and coherence, refer back to 
the full article outline: {section_names_list}.
"""

WRITE_TOP_RATED_CHAPTER_OVERVIEW_PROMPT = """
You are an expert content writer. Your task is to write a brief, engaging overview for the chapter titled "{section_name}" within the article "{article_title}".
This chapter serves as an introduction to a list of top-rated products.
The desired length for this overview is approximately {length} words.

Your main goals are:
1.  Briefly introduce the purpose of this chapter: to highlight the best products in the category.
2.  Mention that detailed reviews of specific products will follow in subsequent sub-sections. You can generally refer to the products that will be covered, such as: {product_list_string}.
3.  **Crucially, DO NOT go into detail about any specific product's features, pros, or cons in this overview.** Keep it general and high-level.
4.  Use an inviting and engaging tone that encourages readers to explore the detailed reviews.

Author Information (incorporate naturally):
- Author Name: {author_name}
- Author Background: {author_info}

Semantic Keywords to weave in naturally: {semantic_keywords}

Context: The article includes the following sections (current section is "{section_name}"): {section_names_list}.

Write the content for this overview section in HTML format.
Do NOT include the chapter title (e.g., <h2>{section_name}</h2>) in your response; only provide the paragraph content.
The output should be ready for direct insertion into a webpage.
"""

# ==============================================================================
# PROMPT FOR WRITING A PRODUCT REVIEW SUBCHAPTER (sectionNameTag = "Product")
# ==============================================================================
WRITE_PRODUCT_REVIEW_SUBCHAPTER_PROMPT = """
Write a concise, {length} word first-person review for the product '{section_name}' 
with the headline '{headline}'. Highlight its relevance and contribution to the 
parent category '{parent_section_name}' within the article '{article_title}'. 
This review should align with the '{model_role}' aspect of the {selected_model} model 
and effectively demonstrate the author's expertise and in-depth knowledge of the topic.
              
{prompt_section_hook}

As you develop this review, incorporate the following semantic keywords to ensure relevance and depth: '{semantic_keywords}'.

Write in the first-person perspective as {author_name}, fully embodying the expertise and lived experiences detailed in {author_name}'s info: '{author_info}'. Use 'I' and 'my' naturally to share insights as if you’ve personally lived through these experiences. Avoid third-party descriptions — speak directly and authentically, ensuring your voice aligns with {author_name}'s background and achievements.

Focus on sharing your direct experience and personal feelings about the product, 
evaluating why this product is a suitable choice. Include a short narrative that 
highlights a specific instance of using the product or observing someone close to 
you using it. Ensure the review is informative, personal, and reflects the unique 
insights of the author, making it relatable and valuable to the reader.

At the end of the review, provide a structured summary of the product's advantages 
and disadvantages in the following HTML format:

<strong>Pros:</strong>
<ul>
    <li>First pro point here.</li>
    <li>Second pro point here.</li>
    <!-- Add more bullet points as needed, usually 2-4 -->
</ul>
<strong>Cons:</strong>
<ul>
    <li>First con point here.</li>
    <li>Second con point here.</li>
    <!-- Add more bullet points as needed, usually 1-3 -->
</ul>

Additionally, include a comparative analysis with one or two other products mentioned in the 
article from this list: '{product_list}'. This comparison should not only highlight 
differences but also delve into the unique selling points and practical uses of each 
product, offering a well-rounded perspective on how they compare and contrast 
with '{section_name}'.

Generate content strictly in HTML format, using only the following tags: <p> for paragraphs, <strong> for key points, <em> for nuanced emphasis, and <ul> / <li> for lists. Do not use any other HTML tags such as <div>, <span>, <html>, <head>, or <body>. Do not use Markdown. Ensure the output is clean, visually appealing, and flows naturally. The content must adhere strictly to these tag rules and avoid unnecessary formatting, document structure tags, or redundant information such as repeating titles.

Pay special attention to the placement of this review within the overall outline of the article. 
Create logical and enhancing transitions at both the beginning and the end of this review, 
ensuring it contributes cohesively to the overall theme of the article. This review should be 
concise and seamlessly integrated into the broader context of the article, providing insightful 
observations without unnecessary repetition. For additional context and coherence, refer back to 
the full article outline: {section_names_list}.
"""

# ==============================================================================
# PROMPT FOR "I LOVE YOU" (Placeholder for chapters that are just parent containers)
# ==============================================================================
SAY_I_LOVE_YOU_PROMPT = "Please respond with exactly three words expressing affection, specifically 'I love you'."