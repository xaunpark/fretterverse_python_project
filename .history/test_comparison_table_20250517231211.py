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
MOCK_LLM_TABLE_CLEAN = """
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

MOCK_LLM_TABLE_NEEDS_CLEANING = """
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
