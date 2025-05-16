# utils/pinecone_handler.py
import logging
import time # Để sleep nếu cần khi tạo index
# from pinecone import Pinecone, Index # Không cần import Index riêng nếu dùng pc.Index()
from pinecone import Pinecone

#from pinecone.core.client.exceptions import PineconeException, NotFoundException, ApiException as PineconeApiException # ApiException vẫn có thể dùng để bắt lỗi cụ thể từ client API
from pinecone import ServerlessSpec, PodSpec # Import Spec nếu bạn có logic tạo index
from pinecone import ApiException, NotFoundException, PineconeException

# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG

logger = logging.getLogger(__name__)

class PineconeHandler:
    def __init__(self, api_key=None, index_name=None, config=None, environment_for_pod_spec=None): # Thêm environment_for_pod_spec
        """
        Initializes the Pinecone client and connects to a specific index.
        'config': một dict chứa các thông tin kết nối, sẽ override các tham số riêng lẻ.
        'environment_for_pod_spec': Chỉ cần thiết nếu bạn tạo Pod-based index và phiên bản SDK của bạn
                                    đặt environment trong PodSpec thay vì constructor Pinecone().
        """
        self.pinecone_client = None
        self.index = None
        self.index_name = None
        self.api_key = None
        self.environment_for_pod_spec = environment_for_pod_spec # Lưu lại environment cho PodSpec

        if config:
            self.api_key = config.get('PINECONE_API_KEY', api_key)
            # Environment cho Pinecone() constructor có thể không cần thiết với SDK v3+
            # nhưng environment cho PodSpec có thể cần.
            self.environment_for_pod_spec = config.get('PINECONE_ENVIRONMENT', environment_for_pod_spec) # Dùng key PINECONE_ENVIRONMENT từ config
            self.index_name = config.get('PINECONE_INDEX_NAME', index_name)
        else:
            self.api_key = api_key
            self.index_name = index_name
            # self.environment_for_pod_spec đã được gán từ tham số

        if not self.api_key or not self.index_name:
            logger.error("Pinecone API key or index name is missing in configuration.")
            return

        self._initialize_pinecone(config) # Truyền config vào để lấy dimension nếu tạo index

    def _initialize_pinecone(self, config=None): # Thêm config
        """Initializes the Pinecone client and gets the index object."""
        try:
            self.pinecone_client = Pinecone(api_key=self.api_key)
            logger.info("Pinecone client initialized.")

            # Kiểm tra xem index có tồn tại không
            existing_indexes = self.pinecone_client.list_indexes().names
            if self.index_name not in existing_indexes:
                logger.warning(f"Pinecone index '{self.index_name}' does not exist.")
                # Tùy chọn: Logic tự động tạo index nếu nó không tồn tại
                # Điều này cần được xem xét cẩn thận cho môi trường production
                if config and config.get('PINECONE_AUTOCREATE_INDEX', False): # Thêm config này
                    dimension = config.get('PINECONE_EMBEDDING_DIMENSION', 256)
                    metric = config.get('PINECONE_METRIC', 'cosine')
                    cloud_provider = config.get('PINECONE_CLOUD_PROVIDER', 'aws')
                    region = config.get('PINECONE_REGION', 'us-east-1') # Ví dụ cho serverless
                    
                    logger.info(f"Attempting to auto-create index '{self.index_name}' with dimension {dimension}, metric {metric}.")
                    try:
                        # Ví dụ cho Serverless Index (phổ biến hơn cho các trường hợp mới)
                        self.pinecone_client.create_index(
                            name=self.index_name,
                            dimension=dimension,
                            metric=metric,
                            spec=ServerlessSpec(cloud=cloud_provider, region=region)
                            # Hoặc cho Pod-based:
                            # spec=PodSpec(environment=self.environment_for_pod_spec, pod_type=config.get('PINECONE_POD_TYPE', 'p1.x1'))
                        )
                        logger.info(f"Pinecone index '{self.index_name}' creation initiated. Waiting for it to be ready...")
                        # Đợi index sẵn sàng - điều này có thể mất vài phút
                        while not self.pinecone_client.describe_index(self.index_name).status['ready']:
                            time.sleep(5)
                        logger.info(f"Pinecone index '{self.index_name}' is now ready.")
                    except PineconeApiException as api_e: # Bắt lỗi API cụ thể khi tạo index
                        logger.error(f"Pinecone API error during index creation '{self.index_name}': {api_e}")
                        self.index = None
                        return
                    except Exception as e_create:
                        logger.error(f"Unexpected error during index creation '{self.index_name}': {e_create}")
                        self.index = None
                        return
                else:
                    self.index = None
                    return # Không tạo index nếu không được cấu hình

            # Lấy đối tượng Index
            self.index = self.pinecone_client.Index(self.index_name)
            # Kiểm tra kết nối bằng cách lấy stats (nếu thành công thì index object hợp lệ)
            stats = self.index.describe_index_stats()
            logger.info(f"Successfully connected to Pinecone index '{self.index_name}'. Stats: {stats.get('total_vector_count', 'N/A')} vectors.")

        except NotFoundException: # Bắt cụ thể nếu index không tìm thấy sau khi list_indexes (hiếm khi xảy ra nếu logic trên đúng)
            logger.error(f"Pinecone index '{self.index_name}' confirmed not found after attempting to connect.")
            self.index = None
        except PineconeException as e: # Bắt lỗi chung của Pinecone
            logger.error(f"Pinecone Exception during initialization or connection to index '{self.index_name}': {e}")
            self.index = None
        except Exception as e: # Bắt các lỗi không mong muốn khác
            logger.error(f"Failed to initialize Pinecone or connect to index '{self.index_name}' (non-API error): {e}", exc_info=True)
            self.index = None

    def is_connected(self):
        """Checks if successfully connected to an index."""
        return self.index is not None

    def query_vectors(self, vector, top_k=1, namespace=None, filter_criteria=None, include_values=False, include_metadata=False):
        if not self.is_connected():
            logger.error("Cannot query Pinecone. Not connected to an index.")
            return None
        try:
            query_params = {
                "vector": vector,
                "top_k": top_k,
                "include_values": include_values,
                "include_metadata": include_metadata
            }
            if namespace: query_params["namespace"] = namespace
            if filter_criteria: query_params["filter"] = filter_criteria
            
            logger.debug(f"Querying Pinecone index '{self.index_name}' with top_k={top_k}, namespace='{namespace}', filter='{filter_criteria}'")
            query_response = self.index.query(**query_params)
            
            if query_response and hasattr(query_response, 'matches'):
                 logger.info(f"Pinecone query successful. Found {len(query_response.matches)} matches.")
            else:
                logger.info("Pinecone query successful but no 'matches' attribute or empty response.")
            return query_response

        except PineconeApiException as api_e: # Lỗi từ API của Pinecone (ví dụ: sai định dạng query)
            logger.error(f"Pinecone API Exception during query on index '{self.index_name}': Status {api_e.status}, Body: {api_e.body}")
        except PineconeException as e: # Các lỗi khác từ thư viện Pinecone
            logger.error(f"Pinecone library exception during query on index '{self.index_name}': {e}")
        except Exception as e: # Các lỗi không mong muốn
            logger.error(f"Unexpected error querying Pinecone index '{self.index_name}': {e}", exc_info=True)
        return None

    def upsert_vectors(self, vectors_data, namespace=None, batch_size=100):
        if not self.is_connected():
            logger.error("Cannot upsert to Pinecone. Not connected to an index.")
            return None

        formatted_vectors = []
        if not vectors_data:
            logger.warning("No vectors provided for upserting.")
            return None
        
        # Chuyển đổi nếu đầu vào là list of tuples (id, values, metadata)
        if isinstance(vectors_data[0], tuple):
            for item in vectors_data:
                vec_id, values = item[0], item[1]
                metadata = item[2] if len(item) > 2 else None
                formatted_vec = {"id": str(vec_id), "values": values} # Đảm bảo ID là string
                if metadata: formatted_vec["metadata"] = metadata
                formatted_vectors.append(formatted_vec)
        else: # Giả sử đã là list of dicts
            formatted_vectors = [{"id": str(v.get("id")), "values": v.get("values"), "metadata": v.get("metadata")} for v in vectors_data if v.get("id") and v.get("values")]
            formatted_vectors = [v for v in formatted_vectors if v["id"] and v["values"]] # Lọc bỏ entry thiếu id hoặc values

        if not formatted_vectors:
            logger.warning("No valid formatted vectors for upserting after processing input.")
            return None

        try:
            logger.info(f"Upserting {len(formatted_vectors)} vectors to Pinecone index '{self.index_name}', namespace='{namespace}', batch_size={batch_size}.")
            
            upsert_response = None
            upsert_params = {"vectors": formatted_vectors, "batch_size": batch_size}
            if namespace: upsert_params["namespace"] = namespace
            
            upsert_response = self.index.upsert(**upsert_params)
            
            logger.info(f"Pinecone upsert successful. Response: upserted_count={upsert_response.upserted_count if upsert_response else 'N/A'}")
            return upsert_response
        except PineconeApiException as api_e:
            logger.error(f"Pinecone API Exception during upsert to index '{self.index_name}': Status {api_e.status}, Body: {api_e.body}")
        except PineconeException as e:
            logger.error(f"Pinecone library exception during upsert to index '{self.index_name}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error upserting to Pinecone index '{self.index_name}': {e}", exc_info=True)
        return None

    def delete_vectors(self, ids=None, delete_all=False, namespace=None, filter_criteria=None):
        if not self.is_connected():
            logger.error("Cannot delete from Pinecone. Not connected to an index.")
            return None
        try:
            delete_params = {}
            if ids: delete_params["ids"] = [str(i) for i in ids] # Đảm bảo IDs là string
            if delete_all: delete_params["delete_all"] = True
            if namespace: delete_params["namespace"] = namespace
            if filter_criteria: delete_params["filter"] = filter_criteria

            if not any([ids, delete_all, filter_criteria]): # Cần ít nhất một điều kiện xóa
                logger.warning("No specific deletion criteria (ids, delete_all, filter) provided for delete operation.")
                return None # Trả về gì đó để biết không có gì được thực hiện
            
            logger.info(f"Deleting vectors from Pinecone index '{self.index_name}' with params: {delete_params}")
            delete_response = self.index.delete(**delete_params) # Response thường là {} hoặc một object rỗng khi thành công
            logger.info(f"Pinecone delete operation successful. Response: {delete_response}")
            return delete_response
        except PineconeApiException as api_e:
            logger.error(f"Pinecone API Exception during delete on index '{self.index_name}': Status {api_e.status}, Body: {api_e.body}")
        except PineconeException as e:
            logger.error(f"Pinecone library exception during delete on index '{self.index_name}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error deleting from Pinecone index '{self.index_name}': {e}", exc_info=True)
        return None

    def describe_index_stats(self):
        if not self.is_connected():
            logger.error("Cannot describe index stats. Not connected to an index.")
            return None
        try:
            stats = self.index.describe_index_stats()
            logger.info(f"Pinecone index stats for '{self.index_name}': {stats}")
            return stats
        except PineconeException as e:
            logger.error(f"Pinecone library exception describing index stats for '{self.index_name}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error describing Pinecone index stats for '{self.index_name}': {e}", exc_info=True)
        return None

# --- Example Usage (Cần APP_CONFIG để chạy) ---
# if __name__ == "__main__":
#     from utils.config_loader import load_app_config
#     from utils.logging_config import setup_logging
#     APP_CONFIG = load_app_config()
#     setup_logging(log_level_str="DEBUG")

#     # Thêm các giá trị này vào .env hoặc settings.py nếu chưa có
#     # APP_CONFIG['PINECONE_AUTOCREATE_INDEX'] = True # Đặt là True để thử tự tạo index
#     # APP_CONFIG['PINECONE_EMBEDDING_DIMENSION'] = 256
#     # APP_CONFIG['PINECONE_METRIC'] = 'cosine'
#     # APP_CONFIG['PINECONE_CLOUD_PROVIDER'] = 'aws' # Hoặc 'gcp', 'azure'
#     # APP_CONFIG['PINECONE_REGION'] = 'us-east-1'  # Chọn region phù hợp
#     # APP_CONFIG['PINECONE_POD_TYPE'] = 's1.x1' # Nếu dùng pod-based

#     pinecone_handler = PineconeHandler(config=APP_CONFIG)

#     if pinecone_handler.is_connected():
#         pinecone_handler.describe_index_stats()

#         # Test Upsert
#         dim = APP_CONFIG.get('PINECONE_EMBEDDING_DIMENSION', 256)
#         vectors_to_upsert = [
#             {"id": "test_vec_001", "values": [0.1] * dim, "metadata": {"genre": "test", "source": "script"}},
#             {"id": "test_vec_002", "values": [0.2] * dim, "metadata": {"genre": "example", "source": "script"}}
#         ]
#         upsert_resp = pinecone_handler.upsert_vectors(vectors_to_upsert)
#         if upsert_resp:
#             logger.info(f"Upsert count: {upsert_resp.upserted_count}")
        
#         time.sleep(2) # Đợi một chút cho vector được index
#         pinecone_handler.describe_index_stats()

#         # Test Query
#         query_vector = [0.11] * dim
#         results = pinecone_handler.query_vectors(vector=query_vector, top_k=2, include_metadata=True)
#         if results and results.matches:
#             logger.info("Query results:")
#             for match in results.matches:
#                 logger.info(f"  ID: {match.id}, Score: {match.score}, Metadata: {match.metadata}")
        
#         # Test Delete
#         # delete_resp = pinecone_handler.delete_vectors(ids=["test_vec_001", "test_vec_002"])
#         # if delete_resp is not None: # Delete thành công thường trả về {}
#         #    logger.info("Delete operation completed (check logs for details).")
#         # pinecone_handler.describe_index_stats()
#     else:
#         logger.error("Failed to connect to Pinecone index for testing.")