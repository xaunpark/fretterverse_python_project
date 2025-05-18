# main_orchestrator.py
import logging
import time
import json 
import argparse # Thêm argparse để đọc tham số dòng lệnh
import re 

from utils.config_loader import load_app_config
from utils.logging_config import setup_logging
from utils.google_sheets_handler import GoogleSheetsHandler
from utils.pinecone_handler import PineconeHandler
from utils.db_handler import MySQLHandler 
from workflows.main_logic import orchestrate_article_creation, normalize_keyword_for_pinecone_id

APP_CONFIG = None
logger = None 

def initialize_app(site_name_arg=None): # Thêm site_name_arg
    global APP_CONFIG, logger
    try:
        APP_CONFIG = load_app_config(site_name=site_name_arg) # Truyền site_name vào
        log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
        log_to_file_flag = APP_CONFIG.get('LOG_TO_FILE', True)
        log_file_path_from_config = APP_CONFIG.get('LOG_FILE_PATH', 'app.log')
        current_log_file_path = log_file_path_from_config if log_to_file_flag else None
        setup_logging(
            log_level_str=log_level, 
            log_to_console=APP_CONFIG.get('LOG_TO_CONSOLE', True),
            log_to_file=log_to_file_flag,
            log_file_path=current_log_file_path
        ) 
        logger = logging.getLogger(__name__) # Đảm bảo logger được gán sau setup_logging
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
    parser = argparse.ArgumentParser(description="FretterVerse Python Orchestrator")
    parser.add_argument("--site", type=str, help="The site name to process (must match a directory in site_profiles).")
    args = parser.parse_args()

    if not args.site:
        print("CRITICAL: No site specified. Use --site <site_name>. Application cannot start.")
        return
        
    if not initialize_app(site_name_arg=args.site): # Truyền site_name từ args
        return 
    logger.info("=== FretterVerse Python Orchestrator Started ===")
    
    gsheet_h = None
    pinecone_h = None
    db_h = None
    try:
        gsheet_h = GoogleSheetsHandler(config=APP_CONFIG)
        pinecone_h = PineconeHandler(config=APP_CONFIG) 
        db_h = MySQLHandler(config=APP_CONFIG) 
    except Exception as e:
        logger.critical(f"Failed to initialize one or more handlers: {e}", exc_info=True)
        return

    if not gsheet_h.is_connected():
        logger.critical("Google Sheets handler failed to initialize/connect. Exiting.")
        return
    if not pinecone_h.is_connected(): 
        logger.critical("Pinecone handler failed to initialize/connect. Exiting.")
        return
    # MySQLHandler sẽ tự kết nối khi cần

    keywords_processed_this_session = set() 
    max_failed_keywords_to_skip = APP_CONFIG.get('MAX_KEYWORDS_PER_RUN', 3) # Đổi tên biến cho rõ nghĩa hơn
    keywords_skipped_or_failed_count = 0
    article_successfully_published = False # Cờ để dừng sau khi publish thành công

    # Vòng lặp sẽ chạy cho đến khi một bài được publish thành công
    # HOẶC đã skip/fail quá số lượng max_failed_keywords_to_skip
    while not article_successfully_published and keywords_skipped_or_failed_count < max_failed_keywords_to_skip:
        logger.info(f"--- Attempting to process a keyword (attempt {keywords_skipped_or_failed_count + 1} for a failed/skipped keyword, target 1 successful publish) ---")
        
        keyword_info = get_keyword_to_process(gsheet_h, APP_CONFIG, keywords_processed_this_session)

        if not keyword_info: 
            logger.info("No new keyword to process from Google Sheet for this session.")
            break 

        keyword_str_to_process = keyword_info.get("keyword_string")
        sheet_data_for_keyword = keyword_info.get("sheet_row_data")
        
        keywords_processed_this_session.add(keyword_str_to_process.lower())
        # Không tăng keywords_skipped_or_failed_count ở đây vội
        
        logger.info(f"Processing keyword: '{keyword_str_to_process}'")
        
        keyword_slug_for_id = normalize_keyword_for_pinecone_id(keyword_str_to_process) 
        unique_run_id = f"{keyword_slug_for_id[:50]}_{int(time.time())}"
        logger.info(f"Generated unique_run_id for this keyword processing: {unique_run_id}")

        orchestration_status_dict = None
        try:
            if not pinecone_h.is_connected():
                logger.warning("Re-initializing Pinecone handler as it was not connected.")
                pinecone_h = PineconeHandler(config=APP_CONFIG)
                if not pinecone_h.is_connected():
                    logger.error(f"Failed to re-initialize Pinecone handler for '{keyword_str_to_process}'. Skipping this keyword.")
                    keywords_skipped_or_failed_count += 1
                    continue 
            
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
                logger.info(f"Successfully orchestrated and published article for '{keyword_str_to_process}'. URL: {orchestration_status_dict.get('post_url')}")
                article_successfully_published = True # Đặt cờ để thoát vòng lặp
                # Cột Used=1 đã được cập nhật trong finalize_and_publish_article_step
            else:
                # Keyword này bị lỗi ở một bước nào đó (Suitable=no, Uniqe=no, hoặc lỗi khác trong orchestrate)
                # GSheet đã được cập nhật Used=1 bởi các hàm con trong main_logic
                reason = orchestration_status_dict.get("reason", "Unknown error") if orchestration_status_dict else "Main logic returned None"
                logger.error(f"Orchestration failed or was stopped for '{keyword_str_to_process}'. Reason: {reason}. Will try next keyword if available.")
                keywords_skipped_or_failed_count += 1

        except Exception as e:
            keywords_skipped_or_failed_count += 1
            logger.critical(f"CRITICAL UNHANDLED ERROR during orchestration for '{keyword_str_to_process}': {e}", exc_info=True)
            if gsheet_h.is_connected(): # Cập nhật GSheet với lỗi nghiêm trọng
                status_col_name = APP_CONFIG.get('GSHEET_STATUS_COLUMN')
                update_payload_critical = {APP_CONFIG.get('GSHEET_USED_COLUMN'): "1"}
                if status_col_name:
                    update_payload_critical[status_col_name] = "critical_error_orchestration"
                
                gsheet_h.update_sheet_row_by_matching_column(
                    APP_CONFIG.get('GSHEET_SPREADSHEET_ID'), 
                    APP_CONFIG.get('GSHEET_KEYWORD_SHEET_NAME'), 
                    APP_CONFIG.get('GSHEET_KEYWORD_COLUMN'), 
                    keyword_str_to_process,
                    update_payload_critical
                )
        
        if not article_successfully_published and keywords_skipped_or_failed_count < max_failed_keywords_to_skip:
            delay = APP_CONFIG.get('DELAY_BETWEEN_KEYWORDS_SEC', 5)
            logger.info(f"Finished attempt for keyword: '{keyword_str_to_process}'. Waiting {delay}s before trying next keyword (if any)...")
            time.sleep(delay)
        elif article_successfully_published:
            logger.info(f"Article published successfully for '{keyword_str_to_process}'. Stopping orchestrator for this run.")
        elif keywords_skipped_or_failed_count >= max_failed_keywords_to_skip:
            logger.info(f"Reached max number of failed/skipped keywords ({max_failed_keywords_to_skip}). Stopping orchestrator for this run.")
            
    # Kết thúc vòng lặp while
    if not article_successfully_published and keywords_skipped_or_failed_count == 0 and not keyword_info: # Tức là không có keyword nào từ đầu
        logger.info("No keywords were found to process in this run.")
    elif not article_successfully_published:
        logger.info(f"Orchestrator finished. No article was successfully published in this run after {keywords_skipped_or_failed_count} attempts/skips.")

    if db_h and db_h.connection and db_h.connection.is_connected():
        db_h.disconnect()
    logger.info("=== FretterVerse Python Orchestrator Finished ===")

if __name__ == "__main__":
    main()