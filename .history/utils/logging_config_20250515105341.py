# utils/logging_config.py
import logging
import sys
from config import settings # Để lấy LOG_FILE_PATH và DEBUG_MODE

def setup_logging(log_level_str="INFO", log_to_console=True, log_to_file=True):
    """
    Sets up logging for the application.
    """
    # Chuyển đổi log_level_str sang logging level
    numeric_level = getattr(logging, log_level_str.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level_str}')

    # Lấy root logger
    logger = logging.getLogger()
    logger.setLevel(numeric_level) # Đặt level chung cho root logger

    # Định dạng log message
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Xóa các handler cũ (nếu có) để tránh log nhiều lần
    if logger.hasHandlers():
        logger.handlers.clear()

    if log_to_console:
        # Tạo console handler và đặt level
        console_handler = logging.StreamHandler(sys.stdout) # Hoặc sys.stderr
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_to_file and settings.LOG_FILE_PATH:
        # Tạo file handler và đặt level
        # 'a' for append mode
        file_handler = logging.FileHandler(settings.LOG_FILE_PATH, mode='a', encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Nếu không có handler nào được thêm (ví dụ cả console và file đều False)
    if not logger.handlers:
        # Thêm một NullHandler để tránh lỗi "No handlers could be found for logger..."
        logger.addHandler(logging.NullHandler())
        if settings.DEBUG_MODE:
            print("Warning: No logging handlers configured. Logging output will be suppressed.")

    # Thông báo logging đã được thiết lập (có thể log ra chính nó)
    logger.info(f"Logging initialized with level {log_level_str}. Console: {log_to_console}, File: {log_to_file} (Path: {settings.LOG_FILE_PATH if log_to_file else 'N/A'})")

# Ví dụ cách gọi ở đầu main_orchestrator.py:
# from utils.logging_config import setup_logging
# from utils.config_loader import load_app_config
#
# if __name__ == "__main__":
#     APP_CONFIG = load_app_config()
#     log_level = "DEBUG" if APP_CONFIG.get('DEBUG_MODE') else "INFO"
#     setup_logging(log_level_str=log_level)
#
#     # Sau đó trong các module khác, bạn có thể lấy logger như sau:
#     # import logging
#     # logger = logging.getLogger(__name__)
#     # logger.info("This is an info message.")
#     # logger.error("This is an error message.")