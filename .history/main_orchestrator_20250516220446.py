# main_orchestrator.py
import logging
import time
import json # Để có thể in dict đẹp hơn nếu cần

from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from utils.google_sheets_handler import GoogleSheetsHandler
from utils.pinecone_handler import PineconeHandler
from utils.db_handler import MySQLHandler # Cho Internal Link Juicer
from workflows.main_logic import orchestrate_article_creation, normalize_keyword_for_pinecone_id # Import hàm chính

# --- Global Variables / Setup ---
APP_CONFIG = None
logger = None

def initialize_app():
    """Initializes configuration and logging."""
    global APP_CONFIG, logger
    try:
        APP_CONFIG = load_app_config()
        log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
        # Log ra file và console
        setup_logging(log_level_str=log_level, log_to_console=True, log_to_file=True) 
        logger = logging.getLogger(__name__) # Lấy logger cho file này
        logger.info("Application initialized successfully.")
        return True
    except ValueError as e: # Lỗi thiếu config key
        # Không thể dùng logger ở đây nếu setup_logging thất bại hoặc APP_CONFIG chưa có
        print(f"CRITICAL: Configuration Error - {e}. Application cannot start.")
        # Nếu logger đã init, có thể log:
        # if logger: logger.critical(f"Configuration Error - {e}. Application cannot start.", exc_info=True)
        return False
    except Exception as e:
        print(f"CRITICAL: Unexpected error during application initialization: {e}")
        # if logger: logger.critical(f"Unexpected error during application initialization: {e}", exc_info=True)
        return False

def get_keyword_to_process(gsheet_handler, config):
    if not gsheet_handler or not gsheet_handler.is_connected():
        logger.error("GSheets handler not available.")
        return None

    sheet_id = config.get('GSHEET_SPREADSHEET_ID')
    sheet_name_used_0 = config.get('GSHEET_KEYWORD_SHEET_NAME_USED_0', 'Keyword Used = 0') 
    keyword_col_name = config.get('GSHEET_KEYWORD_COLUMN', 'Keyword')
    # Không cần đọc cột "Used" ở đây nữa vì sheet đã được filter

    try:
        logger.info(f"Fetching keywords from GSheet: ID='{sheet_id}', Sheet='{sheet_name_used_0}'")
        # Lấy toàn bộ dữ liệu của sheet "Keyword Used = 0"
        # Hàm get_sheet_data đã trả về list of dicts nếu return_as_dicts=True
        potential_keywords_data = gsheet_handler.get_sheet_data(
            spreadsheet_id_or_url=sheet_id,
            sheet_name_or_gid=sheet_name_used_0,
            return_as_dicts=True 
        )

        if not potential_keywords_data:
            logger.info(f"No keywords found in sheet '{sheet_name_used_0}'.")
            return None

        # Lấy keyword đầu tiên từ danh sách này.
        # Sheet "Keyword Used = 0" chỉ chứa các keyword có Used=0 (hoặc rỗng)
        # Logic lọc thêm (Suitable=no, Uniqe=no) sẽ được xử lý trong analyze_and_prepare_keyword
        for row_data in potential_keywords_data:
            keyword_str = row_data.get(keyword_col_name)
            if keyword_str and keyword_str.strip():
                logger.info(f"Found keyword to process: '{keyword_str}' with row data: {row_data}")
                return {"keyword_string": keyword_str.strip(), "sheet_row_data": row_data}
        
        logger.info(f"No processable keywords found in sheet '{sheet_name_used_0}' after initial check.")
        return None

    except Exception as e:
        logger.error(f"Error fetching keyword from GSheet: {e}", exc_info=True)
        return None

def main():
    if not initialize_app():
        return 

    logger.info("=== FretterVerse Python Orchestrator Started ===")
    
    gsheet_h = GoogleSheetsHandler(config=APP_CONFIG)
    pinecone_h = PineconeHandler(config=APP_CONFIG)
    db_h = MySQLHandler(config=APP_CONFIG) # Khởi tạo nhưng chỉ connect khi cần

    if not gsheet_h.is_connected(): # Pinecone và MySQL sẽ tự kết nối khi dùng
        logger.critical("GSheet handler failed to init. Exiting.")
        return
    # Không cần kiểm tra is_connected cho Pinecone/MySQL ở đây nữa

    # --- VÒNG LẶP XỬ LÝ NHIỀU KEYWORD (VÍ DỤ XỬ LÝ 1 KEYWORD MỖI LẦN CHẠY SCRIPT) ---
    # Nếu muốn xử lý nhiều keyword trong một lần chạy, bạn cần một vòng lặp ở đây
    # Ví dụ: while True:
    #            keyword_data = get_keyword_to_process(...)
    #            if not keyword_data: break
    #            ... xử lý ...
    # Hiện tại, script chỉ chạy 1 keyword mỗi lần thực thi.

    keyword_info = get_keyword_to_process(gsheet_h, APP_CONFIG)

    if keyword_info and isinstance(keyword_info, dict):
        keyword_str_to_process = keyword_info.get("keyword_string")
        sheet_data_for_keyword = keyword_info.get("sheet_row_data")
        
        logger.info(f"Processing keyword: '{keyword_str_to_process}'")
        
        keyword_slug = normalize_keyword_for_pinecone_id(keyword_str_to_process)
        unique_run_id = f"{keyword_slug[:50]}_{int(time.time())}"
        logger.info(f"Generated unique_run_id: {unique_run_id}")

        try:
            orchestration_status = orchestrate_article_creation(
                keyword_to_process=keyword_str_to_process,
                sheet_row_data_from_orchestrator=sheet_data_for_keyword, # Truyền sheet_row_data
                config=APP_CONFIG,
                gsheet_handler_instance=gsheet_h,
                pinecone_handler_instance=pinecone_h,
                db_handler_instance=db_h,
                unique_run_id_override=unique_run_id
            )

            if orchestration_status and orchestration_status.get("status") == "success":
                logger.info(f"Successfully orchestrated article for '{keyword_str_to_process}'. URL: {orchestration_status.get('post_url')}")
            else:
                reason = orchestration_status.get("reason", "Unknown error in orchestration") if orchestration_status else "Main logic did not return status"
                logger.error(f"Orchestration failed for '{keyword_str_to_process}'. Reason: {reason}")
                # GSheet đã được cập nhật bởi các hàm con nếu keyword bị dừng (Suitable=no, Uniqe=no, lỗi...)

        except Exception as e:
            logger.critical(f"CRITICAL ERROR during orchestration for '{keyword_str_to_process}': {e}", exc_info=True)
            # Cân nhắc cập nhật GSheet thủ công ở đây với trạng thái lỗi nghiêm trọng nếu cần
            if gsheet_h.is_connected():
                gsheet_h.update_sheet_row_by_matching_column(
                    APP_CONFIG.get('GSHEET_SPREADSHEET_ID'), APP_CONFIG.get('GSHEET_KEYWORD_SHEET_NAME'),
                    APP_CONFIG.get('GSHEET_KEYWORD_COLUMN'), keyword_str_to_process,
                    {APP_CONFIG.get('GSHEET_USED_COLUMN'): "1", 
                     APP_CONFIG.get('GSHEET_STATUS_COLUMN', 'Status'): f"critical_error_orchestration"}
                )
    else:
        logger.info("No new keyword to process at this time.")

    if db_h and db_h.connection and db_h.connection.is_connected(): # Chỉ disconnect nếu đã connect
        db_h.disconnect()
    logger.info("=== FretterVerse Python Orchestrator Finished ===")

if __name__ == "__main__":
    main()