# main_orchestrator.py
import logging
import time
import json # Để có thể in dict đẹp hơn nếu cần
import re # Cho normalize_keyword_for_pinecone_id (nếu bạn muốn nó ở đây)

from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from utils.google_sheets_handler import GoogleSheetsHandler
from utils.pinecone_handler import PineconeHandler
from utils.db_handler import MySQLHandler 
from workflows.main_logic import orchestrate_article_creation, normalize_keyword_for_pinecone_id

# --- Global Variables / Setup ---
APP_CONFIG = None
logger = None # Sẽ được khởi tạo trong initialize_app

def initialize_app():
    """Initializes configuration and logging."""
    global APP_CONFIG, logger
    try:
        APP_CONFIG = load_app_config()
        # Cấu hình logging ngay sau khi có APP_CONFIG
        log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
        log_to_file_flag = APP_CONFIG.get('LOG_TO_FILE', True) # Lấy từ config, mặc định True
        log_file_path_from_config = APP_CONFIG.get('LOG_FILE_PATH', 'app.log')

        # Truyền log_file_path vào setup_logging nếu log_to_file là True
        current_log_file_path = log_file_path_from_config if log_to_file_flag else None
        setup_logging(
            log_level_str=log_level, 
            log_to_console=APP_CONFIG.get('LOG_TO_CONSOLE', True), # Mặc định True
            log_to_file=log_to_file_flag,
            log_file_path=current_log_file_path
        ) 
        logger = logging.getLogger(__name__) 
        logger.info("Application initialized successfully.")
        return True
    except ValueError as e: 
        print(f"CRITICAL: Configuration Error - {e}. Application cannot start.")
        if logger: logger.critical(f"Configuration Error - {e}. Application cannot start.", exc_info=True)
        return False
    except Exception as e:
        print(f"CRITICAL: Unexpected error during application initialization: {e}")
        if logger: logger.critical(f"Unexpected error during application initialization: {e}", exc_info=True)
        return False

def get_keyword_to_process(gsheet_handler: GoogleSheetsHandler, config: dict, processed_keywords_in_this_run: set):
    """
    Lấy keyword tiếp theo từ Google Sheet (từ sheet "Keyword Used = 0").
    Bỏ qua các keyword đã có trong processed_keywords_in_this_run.
    """
    if not gsheet_handler or not gsheet_handler.is_connected():
        if logger: logger.error("Google Sheets handler not available or not connected.")
        else: print("Error: Google Sheets handler not available for get_keyword_to_process.")
        return None

    sheet_id = config.get('GSHEET_SPREADSHEET_ID')
    sheet_name_used_0 = config.get('GSHEET_KEYWORD_SHEET_NAME_USED_0', 'Keyword Used = 0') 
    keyword_col_name = config.get('GSHEET_KEYWORD_COLUMN', 'Keyword')
    
    try:
        logger.info(f"Fetching next keyword from GSheet: ID='{sheet_id}', Sheet='{sheet_name_used_0}'")
        potential_keywords_data = gsheet_handler.get_sheet_data(
            spreadsheet_id_or_url=sheet_id,
            sheet_name_or_gid=sheet_name_used_0,
            return_as_dicts=True 
        )

        if not potential_keywords_data:
            logger.info(f"No keywords found in sheet '{sheet_name_used_0}'.")
            return None

        for row_data in potential_keywords_data:
            keyword_str = row_data.get(keyword_col_name)
            if keyword_str and keyword_str.strip():
                normalized_kw = keyword_str.strip().lower() 
                if normalized_kw not in processed_keywords_in_this_run:
                    logger.info(f"Found keyword to process: '{keyword_str.strip()}' with row data: {row_data}")
                    return {"keyword_string": keyword_str.strip(), "sheet_row_data": row_data}
        
        logger.info(f"No new, unprocessed keywords found in sheet '{sheet_name_used_0}' for this run after checking {len(potential_keywords_data)} rows.")
        return None

    except Exception as e:
        logger.error(f"Error fetching keyword from GSheet: {e}", exc_info=True)
        return None

def main():
    """Hàm chính điều phối toàn bộ quá trình."""
    if not initialize_app(): # Khởi tạo config và logger trước tiên
        return 

    logger.info("=== FretterVerse Python Orchestrator Started ===")
    
    # Khởi tạo các handlers
    # Các handler này nên được thiết kế để có thể tái sử dụng kết nối nếu có thể,
    # hoặc tự quản lý việc mở/đóng kết nối.
    try:
        gsheet_h = GoogleSheetsHandler(config=APP_CONFIG)
        pinecone_h = PineconeHandler(config=APP_CONFIG) # PineconeHandler có thể cần config để lấy PINECONE_ENVIRONMENT cho PodSpec
        db_h = MySQLHandler(config=APP_CONFIG) 
    except Exception as e:
        logger.critical(f"Failed to initialize one or more handlers: {e}", exc_info=True)
        return

    if not gsheet_h.is_connected():
        logger.critical("Google Sheets handler failed to initialize/connect. Exiting.")
        return
    if not pinecone_h.is_connected(): # PineconeHandler nên có is_connected()
        logger.critical("Pinecone handler failed to initialize/connect. Exiting.")
        return
    # MySQLHandler sẽ tự kết nối khi cần, nhưng có thể thêm is_connected() cho nó nếu muốn

    keywords_processed_this_session = set() 
    max_keywords_per_run = APP_CONFIG.get('MAX_KEYWORDS_PER_RUN', 1) 
    keywords_attempted_count = 0
    successful_orchestrations = 0
    failed_orchestrations = 0

    while keywords_attempted_count < max_keywords_per_run:
        logger.info(f"--- Attempting to process keyword #{keywords_attempted_count + 1} (max {max_keywords_per_run} for this run) ---")
        
        keyword_info = get_keyword_to_process(gsheet_h, APP_CONFIG, keywords_processed_this_session)

        if not keyword_info: 
            logger.info("No new keyword to process from Google Sheet for this session, or max attempts reached.")
            break 

        keyword_str_to_process = keyword_info.get("keyword_string")
        sheet_data_for_keyword = keyword_info.get("sheet_row_data")
        
        keywords_processed_this_session.add(keyword_str_to_process.lower())
        keywords_attempted_count += 1
        
        logger.info(f"Processing keyword: '{keyword_str_to_process}'")
        
        # Tạo unique_run_id cho mỗi lần gọi orchestrate_article_creation
        # Hàm normalize_keyword_for_pinecone_id đã được import từ main_logic
        keyword_slug_for_id = normalize_keyword_for_pinecone_id(keyword_str_to_process) 
        unique_run_id = f"{keyword_slug_for_id[:50]}_{int(time.time())}" # Giới hạn độ dài slug
        logger.info(f"Generated unique_run_id for this keyword processing: {unique_run_id}")

        orchestration_status_dict = None
        try:
            # Đảm bảo các handler vẫn hợp lệ (ví dụ, kết nối không bị timeout)
            # MySQLHandler và PineconeHandler của bạn nên có khả năng tự kết nối lại nếu cần.
            if not pinecone_h.is_connected(): # Kiểm tra lại Pinecone trước mỗi keyword
                logger.warning("Re-initializing Pinecone handler as it was not connected.")
                pinecone_h = PineconeHandler(config=APP_CONFIG)
                if not pinecone_h.is_connected():
                    logger.error(f"Failed to re-initialize Pinecone handler for keyword '{keyword_str_to_process}'. Skipping.")
                    failed_orchestrations += 1
                    continue # Bỏ qua keyword này, thử keyword tiếp theo
            
            # db_h sẽ tự kết nối khi execute_query được gọi

            orchestration_status_dict = orchestrate_article_creation(
                keyword_to_process=keyword_str_to_process,
                sheet_row_data_from_orchestrator=sheet_data_for_keyword,
                config=APP_CONFIG,
                gsheet_handler_instance=gsheet_h,
                pinecone_handler_instance=pinecone_h,
                db_handler_instance=db_h,
                unique_run_id_override=unique_run_id
            )

            if orchestration_status_dict and orchestration_status_dict.get("status") == "success":
                logger.info(f"Successfully orchestrated article for '{keyword_str_to_process}'. URL: {orchestration_status_dict.get('post_url')}")
                successful_orchestrations += 1
            else:
                reason = orchestration_status_dict.get("reason", "Unknown error") if orchestration_status_dict else "Main logic returned None"
                logger.error(f"Orchestration failed for '{keyword_str_to_process}'. Reason: {reason}")
                failed_orchestrations += 1
                # GSheet đã được cập nhật bởi các hàm con trong main_logic nếu keyword bị dừng (Suitable=no, Uniqe=no, lỗi...)

        except Exception as e:
            failed_orchestrations += 1
            logger.critical(f"CRITICAL UNHANDLED ERROR during orchestration for keyword '{keyword_str_to_process}': {e}", exc_info=True)
            if gsheet_h.is_connected():
                status_col_name = APP_CONFIG.get('GSHEET_STATUS_COLUMN') # Tên cột Status từ config
                update_payload_critical = {APP_CONFIG.get('GSHEET_USED_COLUMN'): "1"}
                if status_col_name: # Chỉ thêm key này nếu status_col_name được định nghĩa
                    update_payload_critical[status_col_name] = "critical_error_orchestration"
                
                gsheet_h.update_sheet_row_by_matching_column(
                    APP_CONFIG.get('GSHEET_SPREADSHEET_ID'), 
                    APP_CONFIG.get('GSHEET_KEYWORD_SHEET_NAME'), # Cập nhật sheet gốc
                    APP_CONFIG.get('GSHEET_KEYWORD_COLUMN'), 
                    keyword_str_to_process,
                    update_payload_critical
                )
        
        if keywords_attempted_count < max_keywords_per_run:
            delay = APP_CONFIG.get('DELAY_BETWEEN_KEYWORDS_SEC', 5)
            logger.info(f"Finished processing for keyword: '{keyword_str_to_process}'. Waiting {delay}s before next keyword (if any)...")
            time.sleep(delay)
        else:
            logger.info(f"Finished processing for keyword: '{keyword_str_to_process}'. Max keywords per run reached.")

    # Kết thúc vòng lặp while
    if keywords_attempted_count == 0 :
        logger.info("No keywords were attempted in this run.")
    else:
        logger.info(f"Attempted to process {keywords_attempted_count} keyword(s) in this run. Successful: {successful_orchestrations}, Failed: {failed_orchestrations}.")

    # Đóng kết nối MySQL một lần cuối nếu db_h đã từng được kết nối
    if db_h and db_h.connection and db_h.connection.is_connected():
        db_h.disconnect()
    logger.info("=== FretterVerse Python Orchestrator Finished ===")

if __name__ == "__main__":
    main()