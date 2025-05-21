# delete_keywords_from_pinecone.py
import argparse
import logging
import os
import json
import time

# Import các module cần thiết từ dự án của bạn
from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from utils.google_sheets_handler import GoogleSheetsHandler
from utils.pinecone_handler import PineconeHandler
from workflows.main_logic import normalize_keyword_for_pinecone_id # Dùng lại hàm chuẩn hóa ID

# --- Global Variables / Setup ---
# APP_CONFIG will be loaded and used within main_delete or passed if necessary.
logger = None

def setup_script_logging(config_for_logging):
    """Initializes logging for this script based on the provided config."""
    global logger
    try:
        log_level = "DEBUG" if config_for_logging.get('DEBUG_MODE') else "INFO"
        setup_logging(log_level_str=log_level, log_to_console=True, log_to_file=False) # Chỉ log ra console
        logger = logging.getLogger(__name__)
        logger.info("Delete Script: Logging initialized.")
        return True
    except Exception as e:
        # Fallback print if logger setup fails
        print(f"CRITICAL: Error during logging setup for delete script: {e}")
        return False

# The load_site_config function is no longer needed as load_app_config(site_name=...) handles this.

def get_keywords_to_delete(gsheet_handler, spreadsheet_id, delete_sheet_name):
    """
    Lấy danh sách keyword cần xóa từ sheet "Delete".
    Giả sử keyword nằm ở cột đầu tiên.
    """
    if not gsheet_handler or not gsheet_handler.is_connected():
        logger.error("Delete Script: Google Sheets handler not available or not connected.")
        return []
    
    try:
        logger.info(f"Delete Script: Attempting to fetch keywords from Google Sheet: ID='{spreadsheet_id}', Sheet='{delete_sheet_name}'")
        # Lấy tất cả dữ liệu dạng list of lists, vì có thể chỉ có 1 cột
        all_rows = gsheet_handler.get_sheet_data(
            spreadsheet_id_or_url=spreadsheet_id,
            sheet_name_or_gid=delete_sheet_name,
            return_as_dicts=False # Lấy list of lists
        )

        if not all_rows:
            logger.info(f"Delete Script: No keywords found in sheet '{delete_sheet_name}'.")
            return []

        keywords = []
        # Bỏ qua hàng header nếu có, hoặc lấy từ hàng đầu tiên nếu không có header
        start_row = 0
        if all_rows and isinstance(all_rows[0], list) and \
           (all_rows[0][0].lower() == 'keyword' or all_rows[0][0].lower() == 'keywords to delete'): # Kiểm tra header
            start_row = 1
            logger.info("Delete Script: Header row detected and skipped.")

        for row_idx, row in enumerate(all_rows[start_row:], start=start_row):
            if row and isinstance(row, list) and row[0] and row[0].strip():
                keywords.append(row[0].strip())
            else:
                logger.warning(f"Delete Script: Empty or invalid keyword in row {row_idx + 1} of sheet '{delete_sheet_name}'.")
        
        logger.info(f"Delete Script: Found {len(keywords)} keywords to potentially delete.")
        return keywords

    except Exception as e:
        logger.error(f"Delete Script: Error fetching keywords from Google Sheet: {e}", exc_info=True)
        return []

def delete_from_pinecone(pinecone_handler, keyword_list_to_delete):
    """
    Xóa các keyword đã được chuẩn hóa ID khỏi Pinecone.
    """
    if not pinecone_handler or not pinecone_handler.is_connected():
        logger.error("Delete Script: Pinecone handler not available or not connected. Cannot delete.")
        return 0

    if not keyword_list_to_delete:
        logger.info("Delete Script: No keywords provided to delete from Pinecone.")
        return 0

    pinecone_ids_to_delete = [normalize_keyword_for_pinecone_id(kw) for kw in keyword_list_to_delete]
    # Loại bỏ các ID rỗng có thể phát sinh nếu keyword rỗng
    pinecone_ids_to_delete = [pid for pid in pinecone_ids_to_delete if pid]

    if not pinecone_ids_to_delete:
        logger.info("Delete Script: No valid Pinecone IDs generated from keyword list.")
        return 0
        
    logger.info(f"Delete Script: Attempting to delete {len(pinecone_ids_to_delete)} IDs from Pinecone index '{pinecone_handler.index_name}'.")
    logger.debug(f"Delete Script: Pinecone IDs to delete: {pinecone_ids_to_delete}")

    # Pinecone delete có thể nhận list các ID
    # Chia thành các batch nhỏ nếu list quá lớn (ví dụ > 1000) để tránh lỗi API
    # Tuy nhiên, API delete thường chấp nhận list lớn.
    # Xem tài liệu Pinecone để biết giới hạn.
    
    # Hiện tại, API `delete` của Pinecone client có thể nhận một list các ID.
    # không có `batch_size` trực tiếp như upsert.
    # Nếu bạn có hàng ngàn ID, bạn có thể cần tự chia batch.
    # Ví dụ, xóa 100 ID mỗi lần:
    batch_size_delete = 100 # Hoặc một giá trị phù hợp
    deleted_count_total = 0
    
    for i in range(0, len(pinecone_ids_to_delete), batch_size_delete):
        batch_ids = pinecone_ids_to_delete[i:i + batch_size_delete]
        if not batch_ids:
            continue
        logger.info(f"Delete Script: Processing batch {i//batch_size_delete + 1} with {len(batch_ids)} IDs.")
        try:
            # Response của delete thường là {} nếu thành công hoặc raise lỗi.
            # Nó không trả về số lượng đã xóa.
            delete_response = pinecone_handler.delete_vectors(ids=batch_ids) 
            if delete_response is not None: # Kiểm tra response không phải là None (dấu hiệu lỗi từ handler)
                logger.info(f"Delete Script: Batch delete request sent for {len(batch_ids)} IDs. Response: {delete_response}")
                # Không có cách trực tiếp để biết bao nhiêu ID thực sự bị xóa từ response này,
                # chỉ biết request đã được chấp nhận.
                # Chúng ta giả định nếu không có lỗi, các ID hợp lệ sẽ bị xóa.
                deleted_count_total += len(batch_ids) # Tạm tính
            else:
                logger.error(f"Delete Script: Failed to send delete request for batch starting with ID '{batch_ids[0]}'.")

        except Exception as e:
            logger.error(f"Delete Script: Error during Pinecone delete operation for batch starting with ID '{batch_ids[0]}': {e}", exc_info=True)
            # Có thể dừng lại hoặc tiếp tục với batch tiếp theo tùy logic
    
    if deleted_count_total > 0:
        logger.info(f"Delete Script: Finished attempting to delete {deleted_count_total} (approx) IDs from Pinecone.")
    else:
        logger.info("Delete Script: No IDs were processed for deletion or all delete requests failed.")
        
    # Sau khi xóa, có thể gọi describe_index_stats để xem số vector thay đổi
    time.sleep(5) # Chờ một chút để Pinecone cập nhật
    if pinecone_handler.is_connected():
        pinecone_handler.describe_index_stats()
        
    return deleted_count_total


def main_delete():
    """Hàm chính để chạy script xóa."""
    parser = argparse.ArgumentParser(description="Delete keywords from Pinecone for a specific site profile.")
    parser.add_argument("site_profile", help="The name of the site profile (e.g., 'my_site_com') whose config contains the Google Sheet ID.")
    args = parser.parse_args()
    site_profile_name = args.site_profile

    # Load the comprehensive APP_CONFIG using the site_profile_name.
    # This will include settings.py, global .env, site_config.json, and site .env.
    try:
        app_config = load_app_config(site_name=site_profile_name)
    except Exception as e:
        # Basic print if config load fails before full logger setup
        print(f"CRITICAL: Error loading application configuration for site '{site_profile_name}': {e}")
        return

    # Setup logging using the loaded configuration
    if not setup_script_logging(app_config):
        print(f"CRITICAL: Failed to initialize logging. Exiting.")
        return

    logger.info(f"=== Pinecone Keyword Deletion Script Started for site: {site_profile_name} ===")

    # Get GSheet Spreadsheet ID from the merged app_config
    gsheet_spreadsheet_id = app_config.get('GSHEET_SPREADSHEET_ID')
    if not gsheet_spreadsheet_id:
        logger.critical(f"Delete Script: 'GSHEET_SPREADSHEET_ID' not found in the effective configuration for '{site_profile_name}'. Exiting.")
        return
    
    # Get GSheet Delete Sheet Name from merged app_config, with a fallback.
    # settings.py can define a default for GSHEET_DELETE_SHEET_NAME,
    # site_config.json or site .env can override it.
    gsheet_delete_sheet_name = app_config.get('GSHEET_DELETE_SHEET_NAME', 'Delete')

    # Get Pinecone Index Name from merged app_config.
    pinecone_index_name = app_config.get('PINECONE_INDEX_NAME')
    if not pinecone_index_name:
        logger.critical(f"Delete Script: 'PINECONE_INDEX_NAME' not found in the effective configuration for '{site_profile_name}'. Exiting.")
        return

    # Ensure Pinecone API Key is present in the merged app_config.
    if not app_config.get('PINECONE_API_KEY'):
        logger.critical(f"Delete Script: 'PINECONE_API_KEY' not found in the effective configuration. Ensure it's in a .env file or settings.py. Exiting.")
        return

    # Initialize handlers with the comprehensive app_config
    gsheet_handler = GoogleSheetsHandler(config=app_config)
    # PineconeHandler will use PINECONE_API_KEY from app_config.
    # It will use the passed pinecone_index_name.
    pinecone_handler = PineconeHandler(config=app_config, index_name=pinecone_index_name)

    if not gsheet_handler.is_connected():
        logger.critical("Delete Script: Could not connect to Google Sheets. Exiting.")
        return
    if not pinecone_handler.is_connected():
        logger.critical(f"Delete Script: Could not connect to Pinecone (index: '{pinecone_handler.index_name}'). Exiting.")
        return
    logger.info(f"Delete Script: Successfully connected to Pinecone index: {pinecone_handler.index_name}")

    keywords_to_remove = get_keywords_to_delete(gsheet_handler, gsheet_spreadsheet_id, gsheet_delete_sheet_name)

    if keywords_to_remove:
        user_confirmation = input(f"Found {len(keywords_to_remove)} keywords to delete from Pinecone index '{pinecone_handler.index_name}' (source: GSheet ID '{gsheet_spreadsheet_id}', Sheet '{gsheet_delete_sheet_name}'). "
                                  f"First few: {keywords_to_remove[:5]}. \nARE YOU SURE you want to proceed? (yes/no): ")
        if user_confirmation.lower() == 'yes':
            logger.info(f"User confirmed. Proceeding with deletion from Pinecone index: {pinecone_handler.index_name} using keywords from GSheet ID: {gsheet_spreadsheet_id}, Sheet: {gsheet_delete_sheet_name}")
            delete_from_pinecone(pinecone_handler, keywords_to_remove)
            logger.info("Deletion process completed. Please check Pinecone console for final vector count.")
            # Cân nhắc: Có nên xóa các keyword đã xử lý khỏi sheet "Delete" không?
            # Hoặc thêm một cột "Deleted_Status" vào sheet đó.
        else:
            logger.info("Deletion aborted by user.")
    else:
        logger.info("No keywords to delete found in the specified Google Sheet.")

    logger.info("=== Pinecone Keyword Deletion Script Finished ===")

if __name__ == "__main__":
    main_delete()