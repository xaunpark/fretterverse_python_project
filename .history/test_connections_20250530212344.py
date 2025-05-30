# i:\VS-Project\fretterverse_python_project\test_connections.py
import argparse
import logging
import sys
import os
import requests
import mysql.connector
from mysql.connector import errorcode

# Thêm project_root vào sys.path để import các module tùy chỉnh
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.config_loader import load_app_config
from utils.logging_config import setup_logging

# Biến toàn cục cho logger
logger = None

def initialize_test_logging(config_for_logging):
    """Khởi tạo logging cho script test."""
    global logger
    try:
        log_level = "DEBUG" if config_for_logging.get('DEBUG_MODE') else "INFO"
        # Sử dụng một tên file log cụ thể cho script test nếu muốn, hoặc chỉ log ra console
        logger = setup_logging(
            log_level_str=log_level,
            log_to_console=True, # Luôn log ra console cho script test
            log_to_file=config_for_logging.get('LOG_TEST_CONNECTIONS_TO_FILE', False), # Tùy chọn log ra file
            log_file_path=config_for_logging.get('TEST_CONNECTIONS_LOG_FILE_PATH', 'logs/test_connections.log')
        )
        logger.info("Test Connections: Logging initialized.")
        return True
    except Exception as e:
        print(f"CRITICAL: Error during logging setup for test script: {e}")
        return False

def test_wordpress_connection(config):
    """Kiểm tra kết nối đến WordPress bằng cách thử lấy thông tin site."""
    wp_base_url = config.get('WP_BASE_URL')
    wp_user = config.get('WP_USER')
    wp_password = config.get('WP_PASSWORD')

    if not wp_base_url:
        logger.error("WP_BASE_URL không được cấu hình. Không thể kiểm tra kết nối WordPress.")
        return False

    # Thử một endpoint đơn giản không cần xác thực trước (ví dụ: /wp-json/)
    # Hoặc một endpoint cần xác thực để kiểm tra cả thông tin đăng nhập
    # Ví dụ: thử lấy danh sách categories (cần auth)
    test_url = f"{wp_base_url.rstrip('/')}/wp-json/wp/v2/categories?per_page=1"
    
    logger.info(f"Đang kiểm tra kết nối WordPress đến: {wp_base_url}")
    logger.debug(f"URL kiểm tra WordPress: {test_url}")
    logger.debug(f"Sử dụng user: {wp_user}")

    try:
        # Sử dụng timeout để tránh chờ đợi vô hạn
        response = requests.get(test_url, auth=(wp_user, wp_password) if wp_user and wp_password else None, timeout=15)
        
        # Kiểm tra status code
        if response.status_code == 200:
            logger.info(f"Kết nối WordPress thành công! Status: {response.status_code}")
            try:
                categories = response.json()
                if isinstance(categories, list):
                    logger.info(f"Lấy được {len(categories)} category (kiểm tra).")
                else:
                    logger.warning(f"Phản hồi từ WordPress không phải là danh sách category mong đợi: {categories}")
            except requests.exceptions.JSONDecodeError:
                logger.warning("Kết nối WordPress thành công nhưng phản hồi không phải JSON hợp lệ.")
            return True
        elif response.status_code == 401:
            logger.error(f"Kết nối WordPress thất bại! Lỗi xác thực (401). Vui lòng kiểm tra WP_USER và WP_PASSWORD.")
            return False
        elif response.status_code == 403:
            logger.error(f"Kết nối WordPress thất bại! Lỗi phân quyền (403). User có thể không có quyền truy cập endpoint.")
            return False
        elif response.status_code == 404:
            logger.error(f"Kết nối WordPress thất bại! Endpoint không tìm thấy (404). Kiểm tra WP_BASE_URL và cấu trúc API.")
            return False
        else:
            logger.error(f"Kết nối WordPress thất bại! Status code: {response.status_code}. Phản hồi: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Lỗi kết nối đến WordPress: {wp_base_url}. Chi tiết: {e}")
        return False
    except requests.exceptions.Timeout:
        logger.error(f"Kết nối đến WordPress timed out (sau 15 giây): {wp_base_url}")
        return False
    except Exception as e:
        logger.error(f"Lỗi không xác định khi kiểm tra kết nối WordPress: {e}", exc_info=True)
        return False

def test_mysql_connection(config):
    """Kiểm tra kết nối đến MySQL."""
    db_host = config.get('MYSQL_HOST')
    db_port = config.get('MYSQL_PORT', 3306) # Mặc định cổng 3306
    db_user = config.get('MYSQL_USER')
    db_password = config.get('MYSQL_PASSWORD')
    db_name = config.get('MYSQL_DATABASE')

    if not all([db_host, db_user, db_password, db_name]):
        logger.error("Thông tin cấu hình MySQL (HOST, USER, PASSWORD, DATABASE) không đầy đủ. Không thể kiểm tra.")
        return False

    logger.info(f"Đang kiểm tra kết nối MySQL đến: {db_host}:{db_port}, Database: {db_name}")
    logger.debug(f"Sử dụng user MySQL: {db_user}")

    connection_config = {
        'host': db_host,
        'port': int(db_port), # Đảm bảo port là integer
        'user': db_user,
        'password': db_password,
        'database': db_name,
        'connection_timeout': 10 # Thêm timeout cho kết nối
    }

    try:
        # Cố gắng thiết lập kết nối
        cnx = mysql.connector.connect(**connection_config)
        if cnx.is_connected():
            logger.info("Kết nối MySQL thành công!")
            # Có thể thực hiện một query đơn giản để chắc chắn
            cursor = cnx.cursor()
            cursor.execute("SELECT VERSION();")
            db_version = cursor.fetchone()
            logger.info(f"Phiên bản MySQL Server: {db_version[0]}")
            cursor.close()
            cnx.close()
            return True
        else:
            logger.error("Không thể thiết lập kết nối MySQL (is_connected() trả về False).")
            return False
            
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logger.error("Lỗi kết nối MySQL: Sai tên đăng nhập hoặc mật khẩu.")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logger.error(f"Lỗi kết nối MySQL: Database '{db_name}' không tồn tại.")
        else:
            logger.error(f"Lỗi kết nối MySQL: {err}")
        return False
    except Exception as e:
        logger.error(f"Lỗi không xác định khi kiểm tra kết nối MySQL: {e}", exc_info=True)
        return False

def main():
    parser = argparse.ArgumentParser(description="Kiểm tra kết nối WordPress và MySQL cho một site profile.")
    parser.add_argument("--site", type=str, required=True, help="Tên site profile để kiểm tra (phải khớp với một thư mục trong site_profiles).")
    args = parser.parse_args()

    try:
        app_config = load_app_config(site_name=args.site)
    except ValueError as e:
        print(f"CRITICAL: Lỗi tải cấu hình cho site '{args.site}': {e}. Script không thể tiếp tục.")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"CRITICAL: Không tìm thấy file cấu hình cho site '{args.site}': {e}. Script không thể tiếp tục.")
        sys.exit(1)


    if not initialize_test_logging(app_config):
        print(f"CRITICAL: Khởi tạo logging thất bại. Script không thể tiếp tục an toàn.")
        sys.exit(1)

    logger.info(f"=== Bắt đầu kiểm tra kết nối cho site: {args.site} ===")

    # Kiểm tra WordPress
    logger.info("\n--- Kiểm tra WordPress ---")
    wp_success = test_wordpress_connection(app_config)
    if wp_success:
        logger.info(">>> Kết quả WordPress: THÀNH CÔNG")
    else:
        logger.error(">>> Kết quả WordPress: THẤT BẠI")

    # Kiểm tra MySQL
    logger.info("\n--- Kiểm tra MySQL ---")
    mysql_success = test_mysql_connection(app_config)
    if mysql_success:
        logger.info(">>> Kết quả MySQL: THÀNH CÔNG")
    else:
        logger.error(">>> Kết quả MySQL: THẤT BẠI")

    logger.info(f"\n=== Hoàn tất kiểm tra kết nối cho site: {args.site} ===")

    if not wp_success or not mysql_success:
        sys.exit(1) # Thoát với mã lỗi nếu có ít nhất một kiểm tra thất bại

if __name__ == "__main__":
    main()
