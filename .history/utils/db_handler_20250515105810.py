# utils/db_handler.py
import mysql.connector
from mysql.connector import errorcode
import logging

# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG

# Khởi tạo logger
logger = logging.getLogger(__name__)

class MySQLHandler:
    def __init__(self, host, port, user, password, database, config=None):
        """
        Initializes the MySQL connection details.
        'config' là một dict chứa các thông tin kết nối, sẽ override các tham số riêng lẻ.
        """
        if config:
            self.host = config.get('MYSQL_HOST', host)
            self.port = int(config.get('MYSQL_PORT', port))
            self.user = config.get('MYSQL_USER', user)
            self.password = config.get('MYSQL_PASSWORD', password)
            self.database = config.get('MYSQL_DATABASE', database)
        else:
            self.host = host
            self.port = port
            self.user = user
            self.password = password
            self.database = database
        
        self.connection = None
        self.cursor = None
        # Tự động kết nối khi khởi tạo instance
        # self.connect() # Bỏ comment nếu muốn tự động kết nối

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
        :param query: The SQL query string.
        :param params: A tuple of parameters to pass to the query (for %s placeholders).
        :param fetch_one: If True, fetches one row.
        :param fetch_all: If True, fetches all rows.
        :param is_transaction: If True, implies this query is part of a larger transaction
                               and commit/rollback might be handled externally or after multiple queries.
                               If False and it's a DML (INSERT, UPDATE, DELETE), it will try to commit.
        :return: Result of fetch_one/fetch_all, or rowcount for DML, or None on error.
        """
        if not (self.connection and self.connection.is_connected()):
            logger.warning("No active MySQL connection. Attempting to reconnect...")
            if not self.connect(): # Thử kết nối lại
                logger.error("Failed to reconnect to MySQL. Cannot execute query.")
                return None
        
        # Nếu cursor bị đóng vì lý do nào đó, tạo lại
        if not self.cursor or self.cursor.closed:
            if self.connection and self.connection.is_connected():
                self.cursor = self.connection.cursor(dictionary=True)
            else:
                logger.error("Cannot create cursor, connection is not available.")
                return None

        try:
            logger.debug(f"Executing SQL query: {query} with params: {params}")
            self.cursor.execute(query, params or ()) # params phải là tuple, () nếu không có params

            # Xử lý commit cho các câu lệnh INSERT, UPDATE, DELETE
            # Trừ khi nó là một phần của transaction lớn hơn
            if not is_transaction:
                # Heuristic để xác định DML (có thể không hoàn hảo)
                query_upper = query.strip().upper()
                if query_upper.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                    self.connection.commit()
                    logger.info(f"Query executed and committed. Rows affected: {self.cursor.rowcount}")
                    return self.cursor.rowcount # Trả về số hàng bị ảnh hưởng

            if fetch_one:
                result = self.cursor.fetchone()
                logger.debug(f"Fetched one row: {result is not None}")
                return result
            elif fetch_all:
                result = self.cursor.fetchall()
                logger.debug(f"Fetched all rows: {len(result) if result else 0} rows.")
                return result
            
            # Nếu không fetch và không phải DML đã commit ở trên (ví dụ SELECT không fetch)
            # hoặc là DML trong một transaction
            logger.debug("Query executed (no fetch specified or part of transaction).")
            return self.cursor.rowcount # Có thể hữu ích cho DDL hoặc DML trong transaction

        except mysql.connector.Error as err:
            logger.error(f"Error executing MySQL query: {query} - Params: {params} - Error: {err}")
            if not is_transaction and self.connection and self.connection.is_connected():
                logger.warning("Attempting to rollback transaction due to error.")
                try:
                    self.connection.rollback()
                    logger.info("Transaction rolled back.")
                except mysql.connector.Error as rb_err:
                    logger.error(f"Error during rollback: {rb_err}")
            return None
        except Exception as e:
            logger.error(f"An unexpected error occurred during query execution: {e}")
            # Xử lý rollback tương tự nếu cần
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