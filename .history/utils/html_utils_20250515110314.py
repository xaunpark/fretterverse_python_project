# utils/html_utils.py
import re
import html # Để escape HTML
import logging

# Tùy chọn: Import thư viện markdown nếu bạn muốn chuyển đổi đầy đủ hơn
try:
    import markdown as md_lib
    MARKDOWN_LIB_AVAILABLE = True
except ImportError:
    MARKDOWN_LIB_AVAILABLE = False
    pass

logger = logging.getLogger(__name__)

def basic_markdown_to_html(markdown_text):
    """
    Chuyển đổi Markdown cơ bản (bold, italic) sang HTML.
    Đây là phiên bản đơn giản, tương tự như code node n8n của bạn.
    """
    if not markdown_text:
        return ""
    
    # Xử lý bold: **text** hoặc __text__ -> <strong>text</strong>
    html_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', markdown_text)
    html_text = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html_text)
    
    # Xử lý italic: *text* hoặc _text_ -> <em>text</em>
    # Cần cẩn thận để không xung đột với bold nếu không xử lý đúng thứ tự hoặc regex quá tham lam
    # Regex này cố gắng khớp * không được theo sau bởi * và _ không được theo sau bởi _
    html_text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<em>\1</em>', html_text)
    html_text = re.sub(r'(?<!_)_{1}(?!_)(.*?)(?<!_)_{1}(?!_)', r'<em>\1</em>', html_text)
    
    # Xử lý xuống dòng đơn giản (chuyển \n thành <br> nếu không phải là giữa các block)
    # Điều này có thể cần tinh chỉnh tùy theo cách Markdown được tạo ra
    # html_text = html_text.replace('\n', '<br>\n')

    return html_text

def markdown_to_html_advanced(markdown_text, extensions=None):
    """
    Chuyển đổi Markdown sang HTML sử dụng thư viện 'markdown'.
    Cung cấp nhiều tính năng hơn (list, link, table, etc.).
    extensions: list các extension của thư viện markdown, ví dụ ['fenced_code', 'tables']
    """
    if not MARKDOWN_LIB_AVAILABLE:
        logger.warning("Markdown library is not available. Falling back to basic_markdown_to_html or returning raw text.")
        # return basic_markdown_to_html(markdown_text) # Hoặc
        return markdown_text # Trả về text gốc nếu thư viện không có
    
    if not markdown_text:
        return ""
        
    if extensions is None:
        extensions = ['fenced_code', 'tables', 'nl2br'] # nl2br chuyển newline thành <br>

    try:
        html_output = md_lib.markdown(markdown_text, extensions=extensions)
        return html_output
    except Exception as e:
        logger.error(f"Error converting markdown to HTML with library: {e}")
        return basic_markdown_to_html(markdown_text) # Fallback về basic

def generate_faq_schema_html(faq_list):
    """
    Tạo HTML cho FAQ theo schema.org/FAQPage.
    faq_list: list các dictionaries, mỗi dict có dạng {'question': '...', 'answer': '...'}
              Ví dụ: [{"question": "Q1?", "answer": "A1."}, {"question": "Q2?", "answer": "A2."}]
    """
    if not faq_list:
        logger.warning("FAQ list is empty. Returning empty string for FAQ schema.")
        return ""

    html_parts = ['<div itemscope itemtype="https://schema.org/FAQPage">']
    for item in faq_list:
        question = html.escape(item.get('question', ''))
        answer_html = item.get('answer', '') # Giả sử câu trả lời đã là HTML hoặc Markdown cần xử lý riêng

        # Nếu câu trả lời là Markdown, bạn có thể muốn chuyển đổi nó ở đây
        # answer_html = markdown_to_html_advanced(item.get('answer_markdown', ''))
        # Hoặc nếu câu trả lời đã là HTML (từ OpenAI), thì dùng trực tiếp
        # Cẩn thận XSS nếu answer_html đến từ nguồn không đáng tin cậy và bạn không sanitize

        html_parts.append('  <div itemscope itemprop="mainEntity" itemtype="https://schema.org/Question">')
        html_parts.append(f'    <h3 itemprop="name">{question}</h3>')
        html_parts.append('    <div itemscope itemprop="acceptedAnswer" itemtype="https://schema.org/Answer">')
        # Giả sử answer_html đã an toàn hoặc đã được sanitize trước đó
        html_parts.append(f'      <div itemprop="text">{answer_html}</div>')
        html_parts.append('    </div>')
        html_parts.append('  </div>')
    
    html_parts.append('</div>')
    return '\n'.join(html_parts)

def generate_comparison_table_html(products_data, comparison_factors, article_title="Comparison"):
    """
    Tạo HTML cho bảng so sánh sản phẩm.
    products_data: List các dictionaries, mỗi dict đại diện cho một sản phẩm và có các key
                   là các 'comparison_factors' và một key 'product_name'.
                   Ví dụ:
                   [
                       {"product_name": "Product A", "feature1": "Value A1", "feature2": "Value A2", "link_id": "product-a"},
                       {"product_name": "Product B", "feature1": "Value B1", "feature2": "Value B2", "link_id": "product-b"}
                   ]
    comparison_factors: List các strings là tên của các cột (tính năng) để so sánh,
                        ngoại trừ cột "Product Name" sẽ được thêm tự động.
                        Ví dụ: ["Feature 1", "Price", "Rating"]
    article_title: Dùng cho context, có thể không trực tiếp vào table.
    """
    if not products_data:
        logger.warning("Products data for comparison table is empty. Returning empty string.")
        return ""
    if not comparison_factors:
        logger.warning("Comparison factors for table are empty. Returning empty string.")
        return ""

    # Bắt đầu bảng
    html_output = '<div class="comparison-table-container">\n' # Optional container
    html_output += '  <table class="comparison-table styled-table">\n' # Thêm class để CSS styling

    # Hàng tiêu đề (Header row)
    html_output += '    <thead>\n'
    html_output += '      <tr>\n'
    html_output += '        <th>Product</th>\n' # Cột tên sản phẩm
    for factor in comparison_factors:
        html_output += f'        <th>{html.escape(factor)}</th>\n'
    html_output += '      </tr>\n'
    html_output += '    </thead>\n'

    # Nội dung bảng (Table body)
    html_output += '    <tbody>\n'
    for product in products_data:
        product_name = html.escape(product.get('product_name', 'N/A'))
        product_link_id = product.get('link_id') # ID để tạo anchor link (nếu có)

        html_output += '      <tr>\n'
        if product_link_id:
            # Tạo link neo đến phần review sản phẩm trong bài viết
            html_output += f'        <td data-label="Product"><a href="#{html.escape(product_link_id)}">{product_name}</a></td>\n'
        else:
            html_output += f'        <td data-label="Product">{product_name}</td>\n'
        
        for factor in comparison_factors:
            # Lấy giá trị, html escape nó, và xử lý nếu giá trị là list/dict
            value = product.get(factor)
            display_value = ""
            if value is None:
                display_value = "N/A"
            elif isinstance(value, list):
                # Nếu là list, có thể muốn hiển thị dưới dạng bullet points hoặc nối chuỗi
                display_value = "<ul>" + "".join(f"<li>{html.escape(str(item))}</li>" for item in value) + "</ul>"
            elif isinstance(value, dict):
                # Nếu là dict, có thể muốn hiển thị key-value hoặc một chuỗi mô tả
                display_value = "<br>".join(f"<strong>{html.escape(str(k))}:</strong> {html.escape(str(v))}" for k,v in value.items())
            else:
                display_value = html.escape(str(value))
            
            # data-label dùng cho responsive tables (CSS sẽ xử lý)
            html_output += f'        <td data-label="{html.escape(factor)}">{display_value}</td>\n'
        html_output += '      </tr>\n'
    html_output += '    </tbody>\n'

    # Kết thúc bảng
    html_output += '  </table>\n'
    html_output += '</div>\n'
    
    logger.info(f"Generated comparison table HTML for {len(products_data)} products.")
    return html_output

# --- Example Usage ---
# if __name__ == "__main__":
#     # from utils.logging_config import setup_logging
#     # setup_logging(log_level_str="DEBUG")

#     # Test markdown_to_html
#     md_text = "**Bold Text** and *Italic Text*. \nAnother line with __Strong__ and _Emphasis_."
#     print("--- Basic Markdown to HTML ---")
#     print(basic_markdown_to_html(md_text))
#     print("\n--- Advanced Markdown to HTML (if library available) ---")
#     print(markdown_to_html_advanced(md_text))

#     # Test generate_faq_schema_html
#     print("\n--- FAQ Schema HTML ---")
#     faqs = [
#         {"question": "What is Python?", "answer": "<p>Python is a versatile programming language.</p><p>It's known for its readability.</p>"},
#         {"question": "Why use schema.org for FAQs?", "answer": "It helps search engines understand your FAQ content, potentially leading to rich snippets."}
#     ]
#     print(generate_faq_schema_html(faqs))

#     # Test generate_comparison_table_html
#     print("\n--- Comparison Table HTML ---")
#     products = [
#         {
#             "product_name": "Acoustic Guitar X100", 
#             "link_id": "acoustic-guitar-x100-review", # Dùng để tạo anchor link
#             "Type": "Acoustic", 
#             "Wood": "Spruce Top, Mahogany Back", 
#             "Price": "$300",
#             "Rating": "4.5/5",
#             "Features": ["Good for beginners", "Warm tone"]
#         },
#         {
#             "product_name": "Electric Guitar Z2000", 
#             "link_id": "electric-guitar-z2000-review",
#             "Type": "Electric", 
#             "Wood": "Alder Body, Maple Neck", 
#             "Price": "$750",
#             "Rating": "4.8/5",
#             "Features": ["Versatile pickups", "Smooth playability", "Includes whammy bar"]
#         },
#         {
#             "product_name": "Classical Guitar C50", 
#             "Type": "Classical", 
#             "Wood": "Cedar Top, Rosewood Sides", 
#             "Price": "$200",
#             "Rating": "4.2/5",
#             "Features": ["Nylon strings", "Soft sound"]
#         }
#     ]
#     factors = ["Type", "Wood", "Price", "Rating", "Features"] # Các cột muốn so sánh
#     print(generate_comparison_table_html(products, factors))