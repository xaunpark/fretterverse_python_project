# prompts/misc_prompts.py

# ==============================================================================
# PROMPT TO GENERATE HTML COMPARISON TABLE FOR PRODUCTS
# (Tương ứng với node "Create Comparison Table" trong [fretterverse]-v14-main)
# ==============================================================================
# Placeholders:
#   {article_title_for_table}: Tiêu đề của bài viết (để LLM có context).
#   {product_list_string}: Một chuỗi liệt kê tên các sản phẩm cần đưa vào bảng so sánh.
#                          Ví dụ: "Product A, Product B, Product C"
#                          LLM sẽ phải tự tìm/suy luận các tính năng của những sản phẩm này.
#                          Hoặc, bạn có thể cung cấp thông tin chi tiết hơn cho từng sản phẩm nếu có.
GENERATE_HTML_COMPARISON_TABLE_PROMPT = """
Generate an HTML formatted comparison table for the article titled '{article_title_for_table}'. 
The table should include the products listed here: {product_list_string}.

Based on the unique features and market positioning of each product (which you should infer or research if necessary), 
identify and select the most relevant factors for comparison. These factors should be useful for a reader 
trying to decide between these products.

Instructions for the HTML table:
1.  Begin the table with the `<table>` tag and conclude with the `</table>` tag.
2.  Include `<thead>` for the header row and `<tbody>` for the product rows.
3.  The header row (`<tr>` within `<thead>`) should use `<th>` tags to label the columns:
    *   The first column should always be "Product".
    *   Subsequent columns should be the comparison factors you've identified (e.g., "Key Feature", "Price Range", "Best Suited For").
4.  Create a table row (`<tr>` within `<tbody>`) for each product.
    *   The first cell (`<td>`) in each product row should contain the product name. You can make this a link if you have a corresponding anchor ID for a review section later in the article (e.g., `<a href="#product-a-review">Product A</a>`), but this is optional for this generation step.
    *   Subsequent cells (`<td>`) should contain the information for each comparison factor for that product. Use "N/A" if a factor is not applicable or information is unavailable.
    *   For features or benefits that are lists, you can use a simple comma-separated string or basic HTML like `<br>` for line breaks within a cell if appropriate. Avoid complex nested HTML structures like `<ul>` within `<td>` unless specifically instructed otherwise for a particular factor.

The final output must be a clean, ready-to-deploy HTML table segment WITHOUT any placeholder text like "[Product Name Here]", extraneous characters, comments, or unnecessary line breaks. 
Ensure that the comparison factors chosen provide a clear, comprehensive, and relevant evaluation of each product. 
The table should be immediately usable on a webpage and should be well-formatted and validated HTML. 
Do not include any CSS styling directly in the HTML tags; assume styling will be handled by an external CSS file (e.g., you can add a class like `class="comparison-table"` to the `<table>` tag).

Example of a single product row structure (for guidance, not literal output):
<tr>
  <td>Product Name X</td>
  <td>Factor Value X1</td>
  <td>Factor Value X2</td>
  <td>Factor Value X3</td>
</tr>

Please proceed with generating the HTML table.
"""

# ==============================================================================
# (OPTIONAL) PROMPT FOR A VERY GENERIC SYSTEM MESSAGE (if needed for some OpenAI calls)
# ==============================================================================
# SYSTEM_MESSAGE_ASSISTANT_BEHAVIOR = """
# You are a helpful assistant, skilled in content creation and data structuring. 
# You follow instructions precisely and aim for accuracy and clarity in your responses.
# When asked for JSON, you provide only valid JSON.
# """

# Bạn có thể thêm các prompt nhỏ khác ở đây nếu chúng không phù hợp với các file khác.
# Ví dụ:
# - Prompt để tóm tắt một đoạn văn bản.
# - Prompt để kiểm tra ngữ pháp nhanh.
# - Prompt để chuyển đổi một định dạng dữ liệu đơn giản sang định dạng khác.