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
    """
    Lấy keyword đầu tiên từ Google Sheet có cột "Used" = "0" (hoặc rỗng).
    Sử dụng sheet đã được filter sẵn (ví dụ: "Keyword Used = 0").
    """
    if not gsheet_handler or not gsheet_handler.is_connected():
        logger.error("Google Sheets handler not available or not connected.")
        return None

    sheet_id = config.get('GSHEET_SPREADSHEET_ID')
    # Sử dụng sheet đã filter "Used = 0" như trong n8n
    sheet_name = config.get('GSHEET_KEYWORD_SHEET_NAME_USED_0', 'Keyword Used = 0') 
    keyword_col_name = config.get('GSHEET_KEYWORD_COLUMN', 'Keyword')
    # used_col_name = config.get('GSHEET_USED_COLUMN', 'Used') # Không cần thiết nếu sheet đã filter

    try:
        logger.info(f"Attempting to fetch keywords from Google Sheet: ID='{sheet_id}', Sheet='{sheet_name}'")
        # Lấy tất cả dữ liệu dưới dạng dicts, hàng đầu tiên là header
        # Giả sử sheet "Keyword Used = 0" đã được query trong Google Sheet để chỉ hiển thị Used=0
        # và có thể có các cột khác như "Uniqe", "Suitable" từ các lần chạy trước.
        all_rows_as_dicts = gsheet_handler.get_sheet_data(
            spreadsheet_id_or_url=sheet_id,
            sheet_name_or_gid=sheet_name, # Lấy từ sheet đã query "Used=0"
            return_as_dicts=True
        )

        if not all_rows_as_dicts:
            logger.info(f"No keywords found in sheet '{sheet_name}'.")
            return None

        # Tìm keyword đầu tiên chưa được xử lý (trong sheet này, tất cả đều là Used=0)
        # Hoặc bạn có thể thêm logic lọc phức tạp hơn ở đây nếu sheet "Keyword Used =0"
        # có thể chứa các keyword đã được đánh dấu "Uniqe=no" hoặc "Suitable=no" từ lần chạy trước.
        # Ví dụ: chỉ lấy những keyword mà "Uniqe" và "Suitable" không phải là "no".
        for row_data in all_rows_as_dicts:
            keyword = row_data.get(keyword_col_name)
            is_suitable = str(row_data.get(config.get('GSHEET_SUITABLE_COLUMN'), '')).lower()
            is_unique_checked = str(row_data.get(config.get('GSHEET_UNIQUE_COLUMN'), '')).lower()

            if keyword and keyword.strip():
                # Bỏ qua nếu đã bị đánh dấu không phù hợp hoặc không unique từ lần trước
                if is_suitable == 'no':
                    logger.info(f"Skipping keyword '{keyword}' as it was previously marked Suitable=no.")
                    continue
                if is_unique_checked == 'no':
                    logger.info(f"Skipping keyword '{keyword}' as it was previously marked Uniqe=no.")
                    continue
                
                logger.info(f"Found keyword to process: '{keyword}'")
                # Trả về toàn bộ row_data để main_logic có thể kiểm tra các cột khác nếu cần
                return {"keyword_string": keyword.strip(), "sheet_row_data": row_data}
        
        logger.info(f"No suitable keywords left to process in sheet '{sheet_name}'.")
        return None

    except Exception as e:
        logger.error(f"Error fetching keyword from Google Sheet: {e}", exc_info=True)
        return None


def main():
    """Hàm chính điều phối toàn bộ quá trình."""
    if not initialize_app(): # Gọi initialize_app ở đây để logger và APP_CONFIG sẵn sàng
        return # Dừng nếu khởi tạo thất bại

    logger.info("=== FretterVerse Python Orchestrator Started ===")
    
    # Khởi tạo các handlers
    gsheet_handler = GoogleSheetsHandler(config=APP_CONFIG) # Cần file service_account.json hoặc OAuth
    pinecone_handler = PineconeHandler(config=APP_CONFIG)
    db_handler = MySQLHandler(config=APP_CONFIG) # Cho ILJ

    if not all([gsheet_handler.is_connected(), pinecone_handler.is_connected(), db_handler.connect()]):
        logger.critical("One or more critical handlers (GSheet, Pinecone, MySQL) failed to connect. Exiting.")
        if db_handler.connection: db_handler.disconnect() # Đảm bảo đóng MySQL nếu đã mở
        return

    # Lấy keyword để xử lý
    keyword_data_to_process = get_keyword_to_process(gsheet_handler, APP_CONFIG)

    if keyword_data_to_process and isinstance(keyword_data_to_process, dict):
        keyword_string = keyword_data_to_process.get("keyword_string")
        # sheet_row_data = keyword_data_to_process.get("sheet_row_data") # Có thể dùng sau này
        
        logger.info(f"Processing keyword: '{keyword_string}'")
        
        # Tạo unique_run_id cho lần xử lý này
        keyword_slug_for_id = normalize_keyword_for_pinecone_id(keyword_string) # Dùng hàm đã có
        unique_run_id = f"{keyword_slug_for_id}_{int(time.time())}"
        logger.info(f"Generated unique_run_id for this process: {unique_run_id}")

        try:
            orchestration_result = orchestrate_article_creation(
                keyword_to_process=keyword_string,
                config=APP_CONFIG,
                gsheet_handler_instance=gsheet_handler,
                pinecone_handler_instance=pinecone_handler,
                db_handler_instance=db_handler,
                unique_run_id_override=unique_run_id
            )

            if orchestration_result:
                logger.info(f"Orchestration completed for keyword '{keyword_string}'. Result: {orchestration_result.get('status', 'Unknown')}")
                if orchestration_result.get('post_url'):
                    logger.info(f"Article URL: {orchestration_result.get('post_url')}")
                # Thêm logic thông báo thành công (ví dụ: Slack) ở đây nếu muốn
            else:
                logger.error(f"Orchestration failed for keyword '{keyword_string}'. No detailed result returned from main_logic.")
                # GSheet có thể đã được cập nhật là Used=1, Suitable=no, hoặc Uniqe=no bởi các hàm con

        except Exception as e:
            logger.critical(f"CRITICAL ERROR during orchestration for keyword '{keyword_string}': {e}", exc_info=True)
            # Xử lý lỗi ở mức cao nhất, có thể thông báo admin
            # Cân nhắc việc cập nhật Google Sheet là có lỗi ở đây nếu chưa được xử lý ở tầng thấp hơn
    else:
        logger.info("No new keyword to process at this time.")

    # Đóng kết nối MySQL nếu nó được mở bởi db_handler.connect()
    if db_handler: db_handler.disconnect()
    logger.info("=== FretterVerse Python Orchestrator Finished ===")

if __name__ == "__main__":
    main()