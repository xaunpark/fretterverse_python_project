# utils/pinecone_handler.py
import logging
import time # For potential delays if creating an index

# Import từ thư viện Pinecone. Tên cụ thể có thể thay đổiเล็กน้อย giữa các phiên bản.
# Đây là cách import phổ biến cho các phiên bản gần đây (v3+).
from pinecone import Pinecone, Index
from pinecone.core.client.exceptions import PineconeApiException, NotFoundException, ForbiddenException, UnauthorizedException, ApiException as GenericPineconeApiException
from pinecone import ServerlessSpec, PodSpec # Import Spec để tạo index nếu cần

# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG

logger = logging.getLogger(__name__)

class PineconeHandler:
    def __init__(self, api_key=None, index_name=None, config=None, 
                 create_index_if_not_exists=False, 
                 index_dimension=None, index_metric="cosine"):
        """
        Initializes the Pinecone client and connects to a specific index.
        'config': A dict containing connection info, overrides individual params.
        'create_index_if_not_exists': Boolean, if True, attempts to create the index.
        'index_dimension': Required if create_index_if_not_exists is True.
        'index_metric': Metric for the index if created ('cosine', 'euclidean', 'dotproduct').
        """
        self.pinecone_client = None
        self.index_object = None # Đổi tên từ self.index để tránh nhầm lẫn với class Index
        self.index_name = None
        self.api_key = None
        self.environment = None # Có thể không cần cho client init ở v3+ nhưng cần cho PodSpec

        if config:
            self.api_key = config.get('PINECONE_API_KEY', api_key)
            self.environment = config.get('PINECONE_ENVIRONMENT', None) # Environment cho PodSpec
            self.index_name = config.get('PINECONE_INDEX_NAME', index_name)
            self.index_dimension = config.get('PINECONE_EMBEDDING_DIMENSION', index_dimension) # Lấy từ config nếu có
            self.index_metric = config.get('PINECONE_INDEX_METRIC', index_metric)
        else:
            self.api_key = api_key
            # self.environment = environment # Ít dùng trực tiếp ở client init nữa
            self.index_name = index_name
            self.index_dimension = index_dimension
            self.index_metric = index_metric


        if not self.api_key or not self.index_name:
            logger.error("Pinecone API key or index name is missing in configuration.")
            return

        self._initialize_pinecone(create_index_if_not_exists)

    def _initialize_pinecone(self, create_if_not_exists):
        """Initializes the Pinecone client and gets the index object."""
        try:
            self.pinecone_client = Pinecone(api_key=self.api_key)
            logger.info("Pinecone client initialized.")

            index_exists = False
            try:
                index_description = self.pinecone_client.describe_index(name=self.index_name)
                logger.info(f"Pinecone index '{self.index_name}' exists. Status: {index_description.status}")
                if index_description.status['ready']: # Kiểm tra xem index có sẵn sàng không
                    index_exists = True
                else:
                    logger.warning(f"Pinecone index '{self.index_name}' exists but is not ready. Current state: {index_description.status.get('state')}")
                    # Có thể cần đợi hoặc xử lý thêm ở đây
            except NotFoundException: # Lỗi cụ thể nếu index không tồn tại
                logger.warning(f"Pinecone index '{self.index_name}' does not exist.")
                if create_if_not_exists:
                    if not self.index_dimension:
                        logger.error("Index dimension is required to create a new index but was not provided.")
                        return # Không thể tạo index

                    logger.info(f"Attempting to create Pinecone index '{self.index_name}' with dimension {self.index_dimension} and metric '{self.index_metric}'.")
                    # Chọn Spec dựa trên cấu hình hoặc mặc định
                    # Ví dụ: dùng ServerlessSpec nếu environment không được cung cấp hoặc là 'serverless'
                    # Cần có region và cloud cho ServerlessSpec
                    # Cần environment cho PodSpec
                    # Đây là phần cần bạn tùy chỉnh dựa trên loại index Pinecone bạn dùng (Serverless/Pod-based)
                    
                    # Ví dụ đơn giản hóa, bạn cần cung cấp spec phù hợp trong config
                    cloud_provider = self.config.get('PINECONE_CLOUD_PROVIDER', 'aws') # Ví dụ: aws, gcp, azure
                    region = self.config.get('PINECONE_REGION', 'us-east-1') # Ví dụ

                    try:
                        # Giả sử Serverless nếu không có environment cụ thể cho PodSpec
                        # Bạn cần điều chỉnh logic này cho phù hợp với loại index của bạn
                        if not self.environment or self.environment.lower() == "serverless": # Cần check kỹ hơn
                             spec = ServerlessSpec(cloud=cloud_provider, region=region)
                             logger.info(f"Using ServerlessSpec: cloud='{cloud_provider}', region='{region}'")
                        else: # Giả sử là Pod-based
                             pod_type = self.config.get('PINECONE_POD_TYPE', 'p1.x1') # Ví dụ
                             logger.info(f"Using PodSpec: environment='{self.environment}', pod_type='{pod_type}'")
                             spec = PodSpec(environment=self.environment, pod_type=pod_type)

                        self.pinecone_client.create_index(
                            name=self.index_name,
                            dimension=int(self.index_dimension), # Đảm bảo là int
                            metric=self.index_metric,
                            spec=spec,
                            timeout=-1 # Chờ cho đến khi index sẵn sàng, hoặc đặt giá trị cụ thể (giây)
                        )
                        logger.info(f"Pinecone index '{self.index_name}' creation initiated. Waiting for it to be ready...")
                        # Vòng lặp kiểm tra trạng thái (tùy chọn, create_index với timeout=-1 đã làm việc này)
                        # while not self.pinecone_client.describe_index(name=self.index_name).status['ready']:
                        #     time.sleep(5)
                        #     logger.debug(f"Waiting for index '{self.index_name}' to be ready...")
                        index_exists = True # Giờ thì nó tồn tại và sẵn sàng
                    except PineconeApiException as create_e:
                        logger.error(f"Failed to create Pinecone index '{self.index_name}': {getattr(create_e, 'body', str(create_e))}")
                        return # Không thể tiếp tục
                else: # Không tạo index nếu không tồn tại và không được yêu cầu
                    return
            except (ForbiddenException, UnauthorizedException) as auth_e:
                logger.error(f"Pinecone authentication/authorization error: {getattr(auth_e, 'body', str(auth_e))}")
                return
            except PineconeApiException as api_e: # Các lỗi API khác khi describe_index
                logger.error(f"Pinecone API Exception during describe_index: {getattr(api_e, 'body', str(api_e))}")
                return

            if index_exists:
                self.index_object = self.pinecone_client.Index(self.index_name)
                logger.info(f"Successfully connected to Pinecone index object for '{self.index_name}'.")

        except Exception as e: # Bắt các lỗi chung khác khi khởi tạo Pinecone client
            logger.error(f"Failed to initialize Pinecone client: {e}", exc_info=True)
            self.pinecone_client = None # Đảm bảo client là None nếu lỗi

    def is_connected(self):
        """Checks if successfully connected to an index object."""
        return self.index_object is not None

    def query_vectors(self, vector, top_k=1, namespace=None, filter_criteria=None, include_values=False, include_metadata=False):
        if not self.is_connected():
            logger.error("Cannot query Pinecone. Not connected to an index.")
            return None
        try:
            query_params = {
                "vector": vector,
                "top_k": int(top_k), # Đảm bảo là int
                "include_values": include_values,
                "include_metadata": include_metadata
            }
            if namespace: query_params["namespace"] = namespace
            if filter_criteria: query_params["filter"] = filter_criteria
            
            logger.debug(f"Querying Pinecone index '{self.index_name}' with top_k={top_k}, namespace='{namespace}', filter='{filter_criteria}'")
            query_response = self.index_object.query(**query_params)
            
            if query_response and hasattr(query_response, 'matches'):
                 logger.info(f"Pinecone query successful. Found {len(query_response.matches)} matches.")
            else:
                logger.info("Pinecone query successful but no matches attribute or empty response.")
            return query_response

        except PineconeApiException as e:
            error_body = getattr(e, 'body', str(e))
            error_status = getattr(e, 'status', 'N/A')
            logger.error(f"Pinecone API Exception during query (Status: {error_status}): {error_body}")
        except Exception as e:
            logger.error(f"Error querying Pinecone index '{self.index_name}': {e}", exc_info=True)
        return None

    def upsert_vectors(self, vectors_with_ids, namespace=None, batch_size=100):
        if not self.is_connected():
            logger.error("Cannot upsert to Pinecone. Not connected to an index.")
            return None
        
        formatted_vectors = []
        if vectors_with_ids:
            # Chuyển đổi tuple sang dict nếu cần
            if isinstance(vectors_with_ids[0], tuple):
                for item in vectors_with_ids:
                    vec_id, values = item[0], item[1]
                    metadata = item[2] if len(item) > 2 else None
                    formatted_vec = {"id": str(vec_id), "values": values} # ID phải là string
                    if metadata: formatted_vec["metadata"] = metadata
                    formatted_vectors.append(formatted_vec)
            else: # Giả sử đã là list of dicts, chỉ cần đảm bảo ID là string
                for item in vectors_with_ids:
                    item_copy = dict(item)
                    item_copy["id"] = str(item_copy.get("id",""))
                    formatted_vectors.append(item_copy)


        if not formatted_vectors:
            logger.warning("No vectors provided or all vectors were invalid for upserting.")
            return None
            
        try:
            logger.info(f"Upserting {len(formatted_vectors)} vectors to Pinecone index '{self.index_name}', namespace='{namespace}', batch_size={batch_size}.")
            
            upsert_response = None
            # Chia thành các batch nếu số lượng vector lớn hơn batch_size
            for i in range(0, len(formatted_vectors), batch_size):
                batch = formatted_vectors[i:i + batch_size]
                if namespace:
                    current_response = self.index_object.upsert(vectors=batch, namespace=namespace)
                else:
                    current_response = self.index_object.upsert(vectors=batch)
                # Gộp response (ví dụ: đếm tổng số upserted_count)
                if upsert_response is None:
                    upsert_response = current_response
                elif hasattr(current_response, 'upserted_count') and hasattr(upsert_response, 'upserted_count'):
                    upsert_response.upserted_count += current_response.upserted_count
                logger.debug(f"Upserted batch {i//batch_size + 1}, response: {current_response}")

            logger.info(f"Pinecone upsert process completed. Final response: {upsert_response}")
            return upsert_response
        except PineconeApiException as e:
            error_body = getattr(e, 'body', str(e))
            error_status = getattr(e, 'status', 'N/A')
            logger.error(f"Pinecone API Exception during upsert (Status: {error_status}): {error_body}")
        except Exception as e:
            logger.error(f"Error upserting to Pinecone index '{self.index_name}': {e}", exc_info=True)
        return None

    def delete_vectors(self, ids=None, delete_all=False, namespace=None, filter_criteria=None):
        if not self.is_connected():
            logger.error("Cannot delete from Pinecone. Not connected to an index.")
            return None
        try:
            delete_params = {}
            if ids: delete_params["ids"] = [str(i) for i in ids] # Đảm bảo IDs là list of strings
            if delete_all: delete_params["delete_all"] = True
            if namespace: delete_params["namespace"] = namespace
            if filter_criteria: delete_params["filter"] = filter_criteria

            if not any([ids, delete_all, filter_criteria]): # Phải có ít nhất một điều kiện xóa
                logger.warning("No IDs, filter, or delete_all flag specified for delete operation.")
                return None
            
            logger.info(f"Deleting vectors from Pinecone index '{self.index_name}' with params: {delete_params}")
            delete_response = self.index_object.delete(**delete_params)
            logger.info(f"Pinecone delete operation successful. Response: {delete_response}") # Thường trả về {} rỗng khi thành công
            return delete_response
        except PineconeApiException as e:
            error_body = getattr(e, 'body', str(e))
            error_status = getattr(e, 'status', 'N/A')
            logger.error(f"Pinecone API Exception during delete (Status: {error_status}): {error_body}")
        except Exception as e:
            logger.error(f"Error deleting from Pinecone index '{self.index_name}': {e}", exc_info=True)
        return None

    def describe_index_stats(self):
        """Gets statistics about the index by calling describe_index on the client."""
        if not self.pinecone_client: # Kiểm tra client, không phải index_object
            logger.error("Pinecone client not initialized. Cannot describe index stats.")
            return None
        try:
            # describe_index_stats trên Index object có thể không còn là cách chính
            # Thay vào đó, dùng describe_index trên client, nó trả về IndexDescription
            index_description = self.pinecone_client.describe_index(name=self.index_name)
            
            # Trích xuất thông tin stats từ IndexDescription
            # Cấu trúc của index_description.status có thể thay đổi, cần kiểm tra docs
            stats_summary = {
                "name": index_description.name,
                "metric": index_description.metric,
                "dimension": index_description.dimension,
                "status": index_description.status, # Toàn bộ object status
                "host": index_description.host,
                # Trích xuất các thông tin cụ thể hơn nếu cần từ index_description.status
                "total_vector_count": index_description.status.get('total_vector_count', 0) if index_description.status else 0,
                "ready": index_description.status.get('ready', False) if index_description.status else False
            }
            logger.info(f"Pinecone index stats for '{self.index_name}': {stats_summary}")
            return stats_summary
        except PineconeApiException as e:
            error_body = getattr(e, 'body', str(e))
            error_status = getattr(e, 'status', 'N/A')
            logger.error(f"Pinecone API Exception describing index stats (Status: {error_status}): {error_body}")
        except Exception as e:
            logger.error(f"Error describing Pinecone index stats for '{self.index_name}': {e}", exc_info=True)
        return None


# --- Example Usage (cần được gọi từ nơi có APP_CONFIG) ---
# if __name__ == "__main__":
#     # Load APP_CONFIG
#     # from utils.config_loader import load_app_config
#     # from utils.logging_config import setup_logging
#     # APP_CONFIG = load_app_config()
#     # setup_logging(log_level_str="DEBUG")

#     # pinecone_handler = PineconeHandler(
#     #     config=APP_CONFIG,
#     #     create_index_if_not_exists=True, # Đặt True nếu muốn tự tạo index
#     #     # index_dimension đã được lấy từ APP_CONFIG['PINECONE_EMBEDDING_DIMENSION']
#     # )

#     # if pinecone_handler.is_connected():
#     #     stats = pinecone_handler.describe_index_stats()
#     #     if stats:
#     #          logger.info(f"Initial Total vectors: {stats.get('total_vector_count')}")

#     #     # Ví dụ Upsert
#     #     dimension = APP_CONFIG.get('PINECONE_EMBEDDING_DIMENSION', 256)
#     #     vectors_to_add = [
#     #         {"id": "test_vec_1", "values": [0.1] * dimension, "metadata": {"genre": "test"}},
#     #         {"id": "test_vec_2", "values": [0.2] * dimension, "metadata": {"genre": "sample"}}
#     #     ]
#     #     upsert_resp = pinecone_handler.upsert_vectors(vectors_to_add)
#     #     if upsert_resp and hasattr(upsert_resp, 'upserted_count'):
#     #         logger.info(f"Upsert response: {upsert_resp.upserted_count} vectors upserted.")
#     #     
#     #     time.sleep(2) # Đợi Pinecone cập nhật
#     #     stats_after_upsert = pinecone_handler.describe_index_stats()
#     #     if stats_after_upsert:
#     #          logger.info(f"Total vectors after upsert: {stats_after_upsert.get('total_vector_count')}")


#     #     # Ví dụ Query
#     #     query_vec = [0.11] * dimension
#     #     query_results = pinecone_handler.query_vectors(vector=query_vec, top_k=1, include_metadata=True)
#     #     if query_results and query_results.matches:
#     #         logger.info("Query results:")
#     #         for match in query_results.matches:
#     #             logger.info(f"  ID: {match.id}, Score: {match.score}, Metadata: {match.metadata}")

#     #     # Ví dụ Delete
#     #     delete_resp = pinecone_handler.delete_vectors(ids=["test_vec_1", "test_vec_2"])
#     #     if delete_resp is not None : # Delete thành công thường trả về {} hoặc một object trống
#     #          logger.info(f"Delete response: {delete_resp}")
#     #     
#     #     time.sleep(2)
#     #     stats_after_delete = pinecone_handler.describe_index_stats()
#     #     if stats_after_delete:
#     #          logger.info(f"Total vectors after delete: {stats_after_delete.get('total_vector_count')}")
#     else:
#         logger.error("Failed to connect to Pinecone index.")