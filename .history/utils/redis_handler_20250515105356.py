# utils/redis_handler.py
import redis
import json
import logging

# Lấy logger đã được cấu hình
logger = logging.getLogger(__name__)

class RedisHandler:
    def __init__(self, host='localhost', port=6379, db=0, password=None, config=None):
        """
        Initializes the Redis connection.
        'config' là một dict chứa các thông tin kết nối, sẽ override các tham số riêng lẻ.
        """
        if config:
            self.host = config.get('REDIS_HOST', host)
            self.port = int(config.get('REDIS_PORT', port))
            self.db = int(config.get('REDIS_DB', db))
            self.password = config.get('REDIS_PASSWORD', password)
        else:
            self.host = host
            self.port = port
            self.db = db
            self.password = password

        try:
            # decode_responses=True để các giá trị trả về từ Redis là string thay vì bytes
            self.r = redis.Redis(host=self.host, port=self.port, db=self.db, password=self.password, decode_responses=True)
            self.r.ping() # Kiểm tra kết nối
            logger.info(f"Successfully connected to Redis at {self.host}:{self.port}, DB: {self.db}")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis at {self.host}:{self.port}, DB: {self.db}. Error: {e}")
            # Có thể raise lỗi ở đây hoặc cho phép ứng dụng chạy mà không có Redis (nếu logic cho phép)
            # raise ConnectionError(f"Redis connection failed: {e}") from e
            self.r = None # Đặt là None nếu kết nối thất bại

    def is_connected(self):
        return self.r is not None

    def set_value(self, key, value, ex=None):
        """
        Sets a value in Redis.
        If value is a dict or list, it's automatically JSON serialized.
        'ex' is expiration time in seconds.
        """
        if not self.is_connected():
            logger.error(f"Cannot set value for key '{key}'. Redis is not connected.")
            return False
        try:
            if isinstance(value, (dict, list)):
                value_to_set = json.dumps(value)
            else:
                value_to_set = value # Giả sử là string hoặc type Redis hỗ trợ trực tiếp
            self.r.set(key, value_to_set, ex=ex)
            logger.debug(f"Set key '{key}' with value (type: {type(value)})") # Không log value vì có thể nhạy cảm/dài
            return True
        except Exception as e:
            logger.error(f"Error setting key '{key}' in Redis: {e}")
            return False

    def get_value(self, key):
        """
        Gets a value from Redis.
        Tries to JSON deserialize if the value looks like a JSON string.
        """
        if not self.is_connected():
            logger.error(f"Cannot get value for key '{key}'. Redis is not connected.")
            return None
        try:
            value = self.r.get(key)
            if value is None:
                logger.debug(f"Key '{key}' not found in Redis.")
                return None

            # Thử parse JSON
            try:
                # Chỉ parse nếu nó bắt đầu bằng { hoặc [ và kết thúc bằng } hoặc ]
                if (value.startswith('{') and value.endswith('}')) or \
                   (value.startswith('[') and value.endswith(']')):
                    deserialized_value = json.loads(value)
                    logger.debug(f"Got key '{key}', deserialized as JSON.")
                    return deserialized_value
            except json.JSONDecodeError:
                # Không phải JSON, trả về string
                logger.debug(f"Got key '{key}', returned as string (not valid JSON).")
                pass # Bỏ qua lỗi parse và trả về string gốc
            return value
        except Exception as e:
            logger.error(f"Error getting key '{key}' from Redis: {e}")
            return None

    def delete_key(self, key):
        """Deletes a key from Redis."""
        if not self.is_connected():
            logger.error(f"Cannot delete key '{key}'. Redis is not connected.")
            return False
        try:
            result = self.r.delete(key)
            if result > 0:
                logger.info(f"Deleted key '{key}' from Redis.")
            else:
                logger.debug(f"Key '{key}' not found for deletion or already deleted.")
            return result > 0
        except Exception as e:
            logger.error(f"Error deleting key '{key}' from Redis: {e}")
            return False

    def initialize_array_if_not_exists(self, key, default_value="[]"):
        """
        Initializes a key with a default array string "[]" if it doesn't exist.
        Returns True if initialized or already existed, False on error.
        """
        if not self.is_connected():
            logger.error(f"Cannot initialize key '{key}'. Redis is not connected.")
            return False
        try:
            # SETNX (SET if Not eXists)
            if self.r.setnx(key, default_value):
                logger.info(f"Initialized Redis key '{key}' with default value '{default_value}'.")
            else:
                logger.debug(f"Redis key '{key}' already exists. No initialization needed.")
            return True
        except Exception as e:
            logger.error(f"Error initializing key '{key}' in Redis: {e}")
            return False

    def append_to_list_value(self, key, item_to_append, create_if_not_exists=True):
        """
        Appends an item to a list stored in Redis (assumes the value is a JSON list).
        If key doesn't exist and create_if_not_exists is True, it creates an empty list first.
        """
        if not self.is_connected():
            logger.error(f"Cannot append to list for key '{key}'. Redis is not connected.")
            return False

        current_list = self.get_value(key) # get_value sẽ tự parse JSON
        if current_list is None:
            if create_if_not_exists:
                current_list = []
                logger.info(f"Key '{key}' not found. Creating new list for appending.")
            else:
                logger.warning(f"Key '{key}' not found and create_if_not_exists is False. Cannot append.")
                return False
        elif not isinstance(current_list, list):
            logger.error(f"Value for key '{key}' is not a list (type: {type(current_list)}). Cannot append.")
            return False

        current_list.append(item_to_append)
        return self.set_value(key, current_list) # set_value sẽ tự serialize lại thành JSON

# Cách sử dụng ví dụ:
# from utils.config_loader import load_app_config
# from utils.redis_handler import RedisHandler
# from utils.logging_config import setup_logging
#
# if __name__ == "__main__":
#     APP_CONFIG = load_app_config()
#     setup_logging() # Cấu hình logging trước
#
#     redis_client = RedisHandler(config=APP_CONFIG)
#
#     if redis_client.is_connected():
#         # Khởi tạo các key cần thiết cho một luồng xử lý mới
#         # (Ví dụ: mỗi khi bắt đầu xử lý một keyword mới)
#         unique_run_id = "keyword_abc_run1" # Tạo ID duy nhất cho mỗi lần chạy xử lý
#         image_array_key = f"{APP_CONFIG['REDIS_KEY_IMAGE_ARRAY_PREFIX']}{unique_run_id}"
#         redis_client.initialize_array_if_not_exists(image_array_key)
#
#         # Set và Get
#         redis_client.set_value("mykey", "hello_redis")
#         print(f"Value for mykey: {redis_client.get_value('mykey')}")
#
#         my_list_data = [{"id": 1, "name": "item1"}, {"id": 2, "name": "item2"}]
#         redis_client.set_value("mylistkey", my_list_data)
#         retrieved_list = redis_client.get_value("mylistkey")
#         print(f"Retrieved list: {retrieved_list}, type: {type(retrieved_list)}")
#
#         # Append
#         redis_client.append_to_list_value("mylistkey", {"id": 3, "name": "item3"})
#         updated_list = redis_client.get_value("mylistkey")
#         print(f"Updated list: {updated_list}")
#
#         # Xóa
#         # redis_client.delete_key("mykey")