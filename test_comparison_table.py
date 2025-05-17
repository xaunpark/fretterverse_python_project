# i:\VS-Project\fretterverse_python_project\test_comparison_table.py
import logging
import unittest
from unittest import mock
import html # Để unescape trong mock nếu cần, hoặc để test hàm unescape trong code chính

# Import các module cần thiết
from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
# Hàm cần test
from workflows.main_logic import _generate_comparison_table_if_needed
# Prompts (nếu cần tham chiếu trong mock)
from prompts import misc_prompts

# --- Global Variables / Setup ---
APP_CONFIG = None
logger = None

# --- Dữ liệu mẫu cho Test ---
SAMPLE_ARTICLE_META_TYPE1 = {
    "article_type": "Type 1: Best Product List",
    "title": "Best Acoustic Guitars 2025"
}

SAMPLE_ARTICLE_META_TYPE2 = {
    "article_type": "Type 2: Informational",
    "title": "How to Choose an Acoustic Guitar"
}

SAMPLE_PROCESSED_SECTIONS_TYPE1_WITH_PRODUCTS = [
    {"sectionName": "Introduction", "sectionType": "chapter", "sectionNameTag": "introduction", "motherChapter": "no", "sectionIndex": 1},
    {
        "sectionName": "Top Rated Acoustic Guitars", "sectionType": "chapter",
        "sectionNameTag": "top rated", "motherChapter": "yes", "sectionIndex": 2
    },
    {
        "sectionName": "Martin D-28", "sectionType": "subchapter",
        "sectionNameTag": "product", "motherChapter": "no", "sectionIndex": 3,
        "parentChapterName": "Top Rated Acoustic Guitars"
    },
    {
        "sectionName": "Taylor 814ce", "sectionType": "subchapter",
        "sectionNameTag": "product", "motherChapter": "no", "sectionIndex": 4,
        "parentChapterName": "Top Rated Acoustic Guitars"
    },
    {
        "sectionName": "Gibson J-45", "sectionType": "subchapter",
        "sectionNameTag": "product", "motherChapter": "no", "sectionIndex": 5,
        "parentChapterName": "Top Rated Acoustic Guitars"
    },
    {"sectionName": "Buying Guide", "sectionType": "chapter", "sectionNameTag": "", "motherChapter": "no", "sectionIndex": 6},
    {"sectionName": "Conclusion", "sectionType": "chapter", "sectionNameTag": "conclusion", "motherChapter": "no", "sectionIndex": 7},
]

SAMPLE_PROCESSED_SECTIONS_TYPE1_NO_PRODUCTS = [
    {"sectionName": "Introduction", "sectionType": "chapter", "sectionNameTag": "introduction", "motherChapter": "no", "sectionIndex": 1},
    {
        "sectionName": "Top Rated Items (General)", "sectionType": "chapter", # Không có subchapter product
        "sectionNameTag": "top rated", "motherChapter": "no", "sectionIndex": 2 # motherChapter=no để không trích xuất
    },
    {"sectionName": "Conclusion", "sectionType": "chapter", "sectionNameTag": "conclusion", "motherChapter": "no", "sectionIndex": 3},
]

# --- Mocking Functions ---
MOCK_LLM_TABLE_ALREADY_UNESCAPED = """
<table class="comparison-table">
  <thead>
    <tr>
      <th>Product</th>
      <th>Key Feature</th>
      <th>Price Range</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Martin D-28</td>
      <td>Rich Tone</td>
      <td>$3000-$4000</td>
    </tr>
    <tr>
      <td>Taylor 814ce</td>
      <td>Playability</td>
      <td>$4000-$5000</td>
    </tr>
    <tr>
      <td>Gibson J-45</td>
      <td>Iconic Sound</td>
      <td>$2500-$3500</td>
    </tr>
  </tbody>
</table>
"""

MOCK_LLM_TABLE_WITH_MARKDOWN_BUT_UNESCAPED_HTML = """
```html
&lt;table class="comparison-table"&gt;
  &lt;thead&gt;
    &lt;tr&gt;
      &lt;th&gt;Product&lt;/th&gt;
      &lt;th&gt;Unique Selling Point&lt;/th&gt;
    &lt;/tr&gt;
  &lt;/thead&gt;
  &lt;tbody&gt;
    &lt;tr&gt;
      &lt;td&gt;Martin D-28&lt;/td&gt;
      &lt;td&gt;Legendary Dreadnought&lt;/td&gt;
    &lt;/tr&gt;
    &lt;tr&gt;
      &lt;td&gt;Taylor 814ce&lt;/td&gt;
      &lt;td&gt;Modern Versatility&lt;/td&gt;
    &lt;/tr&gt;
  &lt;/tbody&gt;
&lt;/table&gt;
```
"""

MOCK_LLM_NO_TABLE_RESPONSE = "I am unable to generate a table at this moment."

def mock_call_openai_chat_for_table_test(prompt_messages, model_name, api_key, is_json_output=False, *args, **kwargs):
    global logger # Sử dụng logger toàn cục đã setup
    prompt_content = prompt_messages[0]['content']
    logger.debug(f"Mock call_openai_chat_for_table_test called. JSON: {is_json_output}. Prompt starts with: {prompt_content[:100]}")

    if misc_prompts.GENERATE_HTML_COMPARISON_TABLE_PROMPT.splitlines()[0] in prompt_content: # Kiểm tra dòng đầu của prompt
        # Dựa vào một phần của prompt để quyết định trả về gì (để test các kịch bản)
        if "Martin D-28, Taylor 814ce, Gibson J-45" in prompt_content: # Giả sử đây là list sản phẩm đầy đủ
            if "CleanHTMLTest" in prompt_content: # Thêm một marker vào prompt nếu muốn test clean HTML
                 return MOCK_LLM_TABLE_ALREADY_UNESCAPED
            elif "NeedsCleaningTest" in prompt_content:
                 return MOCK_LLM_TABLE_WITH_MARKDOWN_BUT_UNESCAPED_HTML
            elif "NoTableResponseTest" in prompt_content:
                 return MOCK_LLM_NO_TABLE_RESPONSE
            elif "LLMReturnsNoneTest" in prompt_content:
                 return None
            return MOCK_LLM_TABLE_ALREADY_UNESCAPED # Mặc định trả về clean
        else: # Trường hợp không có product nào được truyền vào (ví dụ)
            return MOCK_LLM_NO_TABLE_RESPONSE
    return "Error: Mock did not recognize the prompt for table generation."


class TestComparisonTableGeneration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        global APP_CONFIG, logger
        try:
            APP_CONFIG = load_app_config()
            APP_CONFIG['DEBUG_MODE'] = True
            # Các config khác nếu cần cho test, ví dụ:
            # APP_CONFIG['DEFAULT_OPENAI_CHAT_MODEL_FOR_TABLE'] = 'test-model'
            log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
            setup_logging(log_level_str=log_level, log_to_file=False, log_to_console=True)
            logger = logging.getLogger(__name__)
            logger.info("TestComparisonTableGeneration initialized.")
        except Exception as e:
            print(f"Critical error during test setup: {e}")
            raise

    @mock.patch('workflows.main_logic.call_openai_chat', side_effect=mock_call_openai_chat_for_table_test)
    def test_generate_table_type1_clean_html(self, mock_llm_call):
        logger.info("Running test_generate_table_type1_clean_html...")
        # Thêm marker vào article_title để mock_llm_call biết trả về gì
        article_meta_test = {**SAMPLE_ARTICLE_META_TYPE1, "title": SAMPLE_ARTICLE_META_TYPE1["title"] + " CleanHTMLTest"}
        
        table_html = _generate_comparison_table_if_needed(
            article_meta_test,
            SAMPLE_PROCESSED_SECTIONS_TYPE1_WITH_PRODUCTS,
            APP_CONFIG
        )
        self.assertIsNotNone(table_html, "Table HTML should not be None for clean LLM response.")
        self.assertIn("<table>", table_html, "HTML should contain <table> tag.")
        self.assertIn("Martin D-28", table_html, "Product 'Martin D-28' should be in the table.") # This assertion is fine
        self.assertIn("Taylor 814ce", table_html, "Product 'Taylor 814ce' should be in the table.") # This assertion is fine
        self.assertNotIn("```html", table_html, "Markdown code block should have been removed.")
        self.assertNotIn("&lt;table", table_html, "HTML entities should have been unescaped.")
        logger.info("test_generate_table_type1_clean_html PASSED.")

    @mock.patch('workflows.main_logic.call_openai_chat', side_effect=mock_call_openai_chat_for_table_test)
    def test_generate_table_type1_needs_cleaning(self, mock_llm_call):
        logger.info("Running test_generate_table_type1_needs_cleaning...")
        article_meta_test = {**SAMPLE_ARTICLE_META_TYPE1, "title": SAMPLE_ARTICLE_META_TYPE1["title"] + " NeedsCleaningTest"}
 
        table_html = _generate_comparison_table_if_needed(
            article_meta_test,
            SAMPLE_PROCESSED_SECTIONS_TYPE1_WITH_PRODUCTS, # Dùng list có 2 sản phẩm để khớp với MOCK_LLM_TABLE_NEEDS_CLEANING
            APP_CONFIG
        )
        self.assertIsNotNone(table_html, "Table HTML should not be None for response needing cleaning.")
        self.assertIn("<table>", table_html, "HTML should contain <table> tag after cleaning.")
        self.assertIn("Martin D-28", table_html, "Product 'Martin D-28' should be in the cleaned table.") # This assertion is fine
        self.assertNotIn("```html", table_html, "Markdown code block should have been removed.")
        self.assertNotIn("&lt;table", table_html, "HTML entities should have been unescaped.")
        logger.info("test_generate_table_type1_needs_cleaning PASSED.")

    @mock.patch('workflows.main_logic.call_openai_chat', side_effect=mock_call_openai_chat_for_table_test)
    def test_generate_table_not_type1(self, mock_llm_call):
        logger.info("Running test_generate_table_not_type1...")
        table_html = _generate_comparison_table_if_needed(
            SAMPLE_ARTICLE_META_TYPE2, # Article Type 2
            SAMPLE_PROCESSED_SECTIONS_TYPE1_WITH_PRODUCTS,
            APP_CONFIG
        )
        self.assertIsNone(table_html, "Table HTML should be None for non-Type 1 articles.")
        mock_llm_call.assert_not_called() # LLM không nên được gọi
        logger.info("test_generate_table_not_type1 PASSED.")

    @mock.patch('workflows.main_logic.call_openai_chat', side_effect=mock_call_openai_chat_for_table_test)
    def test_generate_table_type1_no_products_in_outline(self, mock_llm_call):
        logger.info("Running test_generate_table_type1_no_products_in_outline...")
        table_html = _generate_comparison_table_if_needed(
            SAMPLE_ARTICLE_META_TYPE1,
            SAMPLE_PROCESSED_SECTIONS_TYPE1_NO_PRODUCTS, # Outline không có product subchapters
            APP_CONFIG
        )
        self.assertIsNone(table_html, "Table HTML should be None if no products are found in outline.")
        mock_llm_call.assert_not_called() # LLM không nên được gọi nếu không có product
        logger.info("test_generate_table_type1_no_products_in_outline PASSED.")

    @mock.patch('workflows.main_logic.call_openai_chat', side_effect=mock_call_openai_chat_for_table_test)
    def test_generate_table_llm_returns_no_table_string(self, mock_llm_call):
        logger.info("Running test_generate_table_llm_returns_no_table_string...")
        article_meta_test = {**SAMPLE_ARTICLE_META_TYPE1, "title": SAMPLE_ARTICLE_META_TYPE1["title"] + " NoTableResponseTest"}
        table_html = _generate_comparison_table_if_needed(
            article_meta_test,
            SAMPLE_PROCESSED_SECTIONS_TYPE1_WITH_PRODUCTS,
            APP_CONFIG
        )
        self.assertIsNone(table_html, "Table HTML should be None if LLM returns a non-table string.")
        logger.info("test_generate_table_llm_returns_no_table_string PASSED.")

    @mock.patch('workflows.main_logic.call_openai_chat', side_effect=mock_call_openai_chat_for_table_test)
    def test_generate_table_llm_returns_none(self, mock_llm_call):
        logger.info("Running test_generate_table_llm_returns_none...")
        article_meta_test = {**SAMPLE_ARTICLE_META_TYPE1, "title": SAMPLE_ARTICLE_META_TYPE1["title"] + " LLMReturnsNoneTest"}
        table_html = _generate_comparison_table_if_needed(
            article_meta_test,
            SAMPLE_PROCESSED_SECTIONS_TYPE1_WITH_PRODUCTS,
            APP_CONFIG
        )
        self.assertIsNone(table_html, "Table HTML should be None if LLM returns None.")
        logger.info("test_generate_table_llm_returns_none PASSED.")

if __name__ == '__main__':
    unittest.main()