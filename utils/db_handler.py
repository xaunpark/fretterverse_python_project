# utils/db_handler.py
import mysql.connector
from mysql.connector import errorcode
import logging

# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG

# Khởi tạo logger
logger = logging.getLogger(__name__)

class MySQLHandler:
    def __init__(self, config=None, host=None, port=None, user=None, password=None, database=None):
        """
        Initializes the MySQL connection details.
        'config' là một dict chứa các thông tin kết nối, sẽ override các tham số riêng lẻ nếu chúng cũng được cung cấp.
        """
        if config:
            self.host = config.get('MYSQL_HOST', host or 'localhost')
            self.port = int(config.get('MYSQL_PORT', port or 3306))
            self.user = config.get('MYSQL_USER', user)
            self.password = config.get('MYSQL_PASSWORD', password)
            self.database = config.get('MYSQL_DATABASE', database)
        else: # Nếu không có config object, dùng các tham số riêng lẻ
            self.host = host or 'localhost'
            self.port = int(port or 3306)
            self.user = user
            self.password = password
            self.database = database
        
        # Kiểm tra xem các thông tin cần thiết có được cung cấp không
        if not all([self.host, self.port, self.user, self.database]): # Password có thể rỗng
            logger.error("MySQL connection details (host, port, user, database) are missing.")
            # raise ValueError("MySQL connection details are required.")
            self.connection = None
            self.cursor = None
            return

        self.connection = None
        self.cursor = None
        # self.connect() # Bạn có thể chọn tự động kết nối hoặc gọi connect() riêng

    def connect(self):
        """Establishes a connection to the MySQL database."""
        if self.connection and self.connection.is_connected():
            logger.debug("Already connected to MySQL.")
            return True
        try:
            self.connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database
            )
            if self.connection.is_connected():
                self.cursor = self.connection.cursor(dictionary=True) # dictionary=True để trả về kết quả dạng dict
                logger.info(f"Successfully connected to MySQL database '{self.database}' at {self.host}:{self.port}")
                return True
        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                logger.error("MySQL Error: Something is wrong with your user name or password.")
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                logger.error(f"MySQL Error: Database '{self.database}' does not exist.")
            else:
                logger.error(f"MySQL Error: {err}")
            self.connection = None
            self.cursor = None
        return False

    def disconnect(self):
        """Closes the database connection."""
        if self.connection and self.connection.is_connected():
            if self.cursor:
                self.cursor.close()
                self.cursor = None
            self.connection.close()
            logger.info("MySQL connection closed.")
        else:
            logger.debug("No active MySQL connection to close.")
        self.connection = None # Đảm bảo reset connection

    def execute_query(self, query, params=None, fetch_one=False, fetch_all=False, is_transaction=False):
        """
        Executes a SQL query.
        ... (docstring giữ nguyên) ...
        """
        if not (self.connection and self.connection.is_connected()):
            logger.warning("No active MySQL connection. Attempting to reconnect...")
            if not self.connect(): 
                logger.error("Failed to reconnect to MySQL. Cannot execute query.")
                return None
        
        # Kiểm tra xem self.cursor có tồn tại không. 
        # Nếu connection đã đóng rồi mở lại, self.cursor sẽ được tạo mới trong self.connect().
        # Nếu self.cursor là None (ví dụ, connect thất bại ban đầu), self.connect() ở trên sẽ cố gắng tạo lại.
        if self.cursor is None: # Nếu vẫn là None sau khi connect()
            logger.error("Cannot execute query: MySQL cursor is not available (connection might have failed).")
            return None
        
        # Không cần kiểm tra self.cursor.closed nữa, vì nếu cursor không hợp lệ, 
        # self.cursor.execute() sẽ raise lỗi và được bắt bởi khối try-except bên dưới.

        try:
            logger.debug(f"Executing SQL query: {query} with params: {params}")
            self.cursor.execute(query, params or ()) 

            query_upper = query.strip().upper()
            is_dml = query_upper.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))

            if not is_transaction and is_dml:
                self.connection.commit()
                logger.info(f"Query executed and committed. Rows affected: {self.cursor.rowcount}")
                return self.cursor.rowcount 

            if fetch_one:
                result = self.cursor.fetchone()
                # logger.debug(f"Fetched one row: {result is not None}") # Có thể log nhiều
                return result
            elif fetch_all:
                result = self.cursor.fetchall()
                # logger.debug(f"Fetched all rows: {len(result) if result else 0} rows.")
                return result
            
            if is_dml: 
                return self.cursor.rowcount
            
            logger.debug("Query executed (likely SELECT without fetch or DDL).")
            return True 

        except mysql.connector.Error as err: # Bắt lỗi cụ thể của mysql.connector trước
            logger.error(f"MySQL Connector Error executing query: {query} - Params: {params} - Error: {err.errno} {err.msg}", exc_info=True)
            if not is_transaction and self.connection and self.connection.is_connected():
                logger.warning("Attempting to rollback transaction due to MySQL Connector Error.")
                try:
                    self.connection.rollback()
                    logger.info("Transaction rolled back.")
                except mysql.connector.Error as rb_err:
                    logger.error(f"Error during rollback: {rb_err}")
            return None
        except Exception as e: # Bắt các lỗi không mong muốn khác
            logger.error(f"An unexpected error occurred during query execution: {query} - Params: {params} - Error: {e}", exc_info=True)
            # Tương tự, có thể thử rollback nếu connection còn
            if not is_transaction and self.connection and self.connection.is_connected():
                 logger.warning("Attempting to rollback transaction due to unexpected error.")
                 try:
                     self.connection.rollback()
                     logger.info("Transaction rolled back (unexpected error).")
                 except Exception as rb_e_unexpected:
                     logger.error(f"Error during rollback (unexpected error): {rb_e_unexpected}")
            return None

    def commit(self):
        """Commits the current transaction."""
        if self.connection and self.connection.is_connected():
            try:
                self.connection.commit()
                logger.info("MySQL transaction committed.")
                return True
            except mysql.connector.Error as err:
                logger.error(f"Error committing MySQL transaction: {err}")
                return False
        logger.warning("No active MySQL connection to commit.")
        return False

    def rollback(self):
        """Rolls back the current transaction."""
        if self.connection and self.connection.is_connected():
            try:
                self.connection.rollback()
                logger.info("MySQL transaction rolled back.")
                return True
            except mysql.connector.Error as err:
                logger.error(f"Error rolling back MySQL transaction: {err}")
                return False
        logger.warning("No active MySQL connection to roll back.")
        return False

    # Context manager methods để sử dụng với `with` statement
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

# --- Example Usage (cần được gọi từ nơi có APP_CONFIG) ---
# if __name__ == "__main__":
#     # Load APP_CONFIG
#     # from utils.config_loader import load_app_config # Giả sử APP_CONFIG đã được load
#     # from utils.logging_config import setup_logging
#     # APP_CONFIG = load_app_config()
#     # setup_logging()
#
#     # Khởi tạo handler với config
#     # db_handler = MySQLHandler(config=APP_CONFIG)
#     # Hoặc truyền trực tiếp:
#     # db_handler = MySQLHandler(
#     #     host=APP_CONFIG['MYSQL_HOST'],
#     #     port=APP_CONFIG['MYSQL_PORT'],
#     #     user=APP_CONFIG['MYSQL_USER'],
#     #     password=APP_CONFIG['MYSQL_PASSWORD'],
#     #     database=APP_CONFIG['MYSQL_DATABASE']
#     # )
#
#     # Sử dụng với context manager (khuyến khích để đảm bảo đóng kết nối)
#     # with MySQLHandler(config=APP_CONFIG) as db_handler:
#     #     if db_handler.connection: # Kiểm tra kết nối thành công
#     #         # Ví dụ SELECT
#     #         # Thay 'your_table' và 'your_column' bằng tên thực tế
#     #         # items = db_handler.execute_query("SELECT * FROM wp_users WHERE user_login = %s", params=("admin_user",), fetch_all=True)
#     #         # if items:
#     #         #     for item in items:
#     #         #         logger.info(f"Item: {item}")
#     #         # else:
#     #         #     logger.info("No items found or error occurred.")
#
#     #         # Ví dụ INSERT (cho Internal Link Juicer)
#     #         # post_id_example = 123
#     #         # meta_key_example = 'ilj_linkdefinition'
#     #         # meta_value_example = 'a:1:{i:0;s:7:"keyword";}' # Chuỗi PHP serialized
#
#     #         # # Query cho ON DUPLICATE KEY UPDATE
#     #         # insert_query = """
#     #         # INSERT INTO wp_postmeta (post_id, meta_key, meta_value)
#     #         # VALUES (%s, %s, %s)
#     #         # ON DUPLICATE KEY UPDATE meta_value = VALUES(meta_value);
#     #         # """
#     #         # params_insert = (post_id_example, meta_key_example, meta_value_example)
#     #         # result_count = db_handler.execute_query(insert_query, params=params_insert)
#     #         # if result_count is not None:
#     #         #      # Với INSERT ... ON DUPLICATE KEY UPDATE, rowcount là 1 nếu insert, 2 nếu update
#     #         #      logger.info(f"ILJ data inserted/updated for post_id {post_id_example}. Rowcount: {result_count}")
#     #         # else:
#     #         #      logger.error(f"Failed to insert/update ILJ data for post_id {post_id_example}")
#
#             # # Ví dụ DELETE (cho Internal Link Juicer - xóa meta_key trùng lặp)
#             # delete_query = """
#             # DELETE FROM wp_postmeta
#             # WHERE post_id = %s
#             # AND meta_key = %s
#             # AND meta_id NOT IN (
#             #     SELECT meta_id_to_keep FROM ( -- Cần subquery để MySQL cho phép delete từ cùng table
#             #         SELECT MAX(meta_id) as meta_id_to_keep
#             #         FROM wp_postmeta
#             #         WHERE post_id = %s
#             #         AND meta_key = %s
#             #     ) AS temp_table
#             # );
#             # """
#             # # Cần truyền post_id và meta_key hai lần cho query trên
#             # params_delete = (post_id_example, meta_key_example, post_id_example, meta_key_example)
#             # deleted_rows = db_handler.execute_query(delete_query, params=params_delete)
#             # if deleted_rows is not None:
#             #     logger.info(f"Duplicate ILJ meta_keys cleaned for post_id {post_id_example}. Rows deleted: {deleted_rows}")
#
#     # Hoặc sử dụng không có context manager (nhớ gọi disconnect)
#     # if db_handler.connect():
#     #     # ... thực hiện query ...
#     #     db_handler.disconnect()