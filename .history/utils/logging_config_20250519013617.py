# utils/logging_config.py
import logging
import sys
from config import settings # Để lấy LOG_FILE_PATH và DEBUG_MODE

def setup_logging(log_level_str="INFO", 
                  log_to_console=True, 
                  log_to_file=True, 
                  log_file_path="app.log"): # THÊM THAM SỐ log_file_path VỚI GIÁ TRỊ MẶC ĐỊNH
    """
    Sets up logging for the application.
    :param log_level_str: Log level as a string (e.g., "DEBUG", "INFO").
    :param log_to_console: Boolean, whether to log to console.
    :param log_to_file: Boolean, whether to log to file.
    :param log_file_path: String, path to the log file. Used if log_to_file is True.
    """
    numeric_level = getattr(logging, log_level_str.upper(), None)
    if not isinstance(numeric_level, int):
        # Nếu logger chưa được cấu hình, print là cách tốt nhất để báo lỗi này
        print(f"ERROR: Invalid log level string provided to setup_logging: {log_level_str}")
        # Fallback to INFO or raise error
        numeric_level = logging.INFO 
        # raise ValueError(f'Invalid log level: {log_level_str}')

    logger = logging.getLogger() # Lấy root logger
    logger.setLevel(numeric_level) 

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Xóa các handler cũ để tránh log nhiều lần nếu hàm này được gọi lại
    if logger.hasHandlers():
        for handler in logger.handlers[:]: # Lặp trên bản copy của list handlers
            logger.removeHandler(handler)
            if hasattr(handler, 'close'): # Đảm bảo đóng file handler cũ nếu có
                handler.close()


    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_to_file: # Chỉ thêm file handler nếu log_to_file là True
        if not log_file_path: # Kiểm tra xem log_file_path có được cung cấp không
            # Không thể dùng logger ở đây nếu nó chưa được thiết lập
            print(f"WARNING: log_to_file is True but log_file_path is not provided or is empty. File logging disabled.")
        else:
            try:
                # Tạo thư mục cho file log nếu chưa tồn tại (nếu log_file_path có chứa thư mục)
                import os
                log_dir = os.path.dirname(log_file_path)
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir, exist_ok=True)

                file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8')
                file_handler.setLevel(numeric_level)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                print(f"ERROR: Could not set up file logging to '{log_file_path}': {e}")
                # Có thể muốn fallback về console logging nếu file logging thất bại


    # Thông báo logging đã được thiết lập (chỉ khi logger có handlers)
    if logger.handlers:
        logger.info(
            f"Logging initialized with level {logging.getLevelName(logger.level)}. "
            f"Console: {log_to_console}, File: {log_to_file} "
            f"(Path: {log_file_path if log_to_file and log_file_path else 'N/A'})"
        )
    else:
        # Thêm NullHandler nếu không có handler nào được cấu hình để tránh thông báo lỗi của thư viện logging
        logger.addHandler(logging.NullHandler())
        print("WARNING: No logging handlers (console or file) were configured. Logging output will be suppressed.")
    return logger