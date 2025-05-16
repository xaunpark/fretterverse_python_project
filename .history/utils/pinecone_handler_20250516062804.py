# utils/pinecone_handler.py
import logging
import time

# CỐ GẮNG IMPORT EXCEPTION CỤ THỂ
# Đây là cách phổ biến cho các phiên bản pinecone SDK gần đây (v3+)
# Nếu vẫn lỗi, bạn cần kiểm tra tài liệu của phiên_bản Pinecone SDK bạn đang dùng.
try:
    from pinecone import Pinecone, Index # Index có thể không cần thiết nếu luôn dùng client.Index()
    from pinecone.exceptions import ApiException, NotFoundException, PineconeException
    # Một số phiên bản có thể export trực tiếp:
    # from pinecone import ApiException, NotFoundException, PineconeException 
    PINECONE_EXCEPTIONS_AVAILABLE = True
except ImportError:
    # Fallback nếu không import được exception cụ thể
    # Điều này cho phép code vẫn chạy nhưng xử lý lỗi sẽ kém chi tiết hơn.
    # Tuy nhiên, mục tiêu là làm cho import cụ thể hoạt động.
    from pinecone import Pinecone # Ít nhất phải import được cái này
    ApiException = None # Đặt là None để có thể kiểm tra sự tồn tại
    NotFoundException = None
    PineconeException = None
    PINECONE_EXCEPTIONS_AVAILABLE = False
    logging.getLogger(__name__).warning(
        "Could not import specific Pinecone exceptions (ApiException, NotFoundException, PineconeException). "
        "Falling back to generic Exception handling for Pinecone operations. "
        "Please ensure you have the correct 'pinecone' package version and check its documentation for exception imports."
    )

from pinecone import ServerlessSpec, PodSpec # Vẫn cần nếu có logic tạo index

logger = logging.getLogger(__name__)

class PineconeHandler:
    def __init__(self, api_key=None, index_name=None, config=None): # Bỏ environment_for_pod_spec vì Pinecone client v3 quản lý khác
        self.pinecone_client = None
        self.index = None
        self.index_name = None
        self.api_key = None
        # self.environment = None # Pinecone client v3 không cần environment khi init Pinecone()

        if config:
            self.api_key = config.get('PINECONE_API_KEY', api_key)
            # self.environment = config.get('PINECONE_ENVIRONMENT', environment) # Không cần cho Pinecone() v3
            self.index_name = config.get('PINECONE_INDEX_NAME', index_name)
        else:
            self.api_key = api_key
            # self.environment = environment
            self.index_name = index_name

        if not self.api_key or not self.index_name: # environment không còn là điều kiện bắt buộc cho Pinecone()
            logger.error("Pinecone API key or index name is missing in configuration.")
            return

        self._initialize_pinecone(config)

    def _initialize_pinecone(self, config=None):
        try:
            self.pinecone_client = Pinecone(api_key=self.api_key) # Pinecone() v3 không cần environment
            logger.info("Pinecone client initialized.")

            existing_indexes = self.pinecone_client.list_indexes().names
            if self.index_name not in existing_indexes:
                logger.warning(f"Pinecone index '{self.index_name}' does not exist.")
                if config and config.get('PINECONE_AUTOCREATE_INDEX', False):
                    dimension = config.get('PINECONE_EMBEDDING_DIMENSION', 256)
                    metric = config.get('PINECONE_METRIC', 'cosine')
                    cloud_provider = config.get('PINECONE_CLOUD_PROVIDER', 'aws') # 'aws', 'gcp', 'azure'
                    region = config.get('PINECONE_REGION', 'us-east-1') # Ví dụ cho AWS
                    
                    logger.info(f"Attempting to auto-create index '{self.index_name}' with dim {dimension}, metric {metric}, cloud {cloud_provider}, region {region}...")
                    try:
                        self.pinecone_client.create_index(
                            name=self.index_name, dimension=dimension, metric=metric,
                            spec=ServerlessSpec(cloud=cloud_provider, region=region)
                            # Hoặc PodSpec nếu bạn dùng pod-based index:
                            # spec=PodSpec(environment=config.get('PINECONE_ENVIRONMENT'), pod_type="p1.x1")
                        )
                        logger.info(f"Index '{self.index_name}' creation initiated. Waiting for it to be ready...")
                        # Đợi index sẵn sàng
                        while True:
                            index_description = self.pinecone_client.describe_index(self.index_name)
                            if index_description.status['ready']:
                                logger.info(f"Index '{self.index_name}' is now ready.")
                                break
                            logger.info(f"Index '{self.index_name}' not ready yet, current state: {index_description.status['state']}. Waiting...")
                            time.sleep(10) # Chờ 10 giây rồi kiểm tra lại
                    except Exception as e_create:
                        logger.error(f"Error during Pinecone index auto-creation '{self.index_name}': {e_create}", exc_info=True)
                        if PINECONE_EXCEPTIONS_AVAILABLE and ApiException and isinstance(e_create, ApiException):
                            logger.error(f"Pinecone API Exception (Create): Status {e_create.status}, Body: {e_create.body}")
                        self.index = None
                        return
                else: # Không auto-create
                    self.index = None
                    return

            self.index = self.pinecone_client.Index(self.index_name)
            stats = self.index.describe_index_stats()
            logger.info(f"Successfully connected to Pinecone index '{self.index_name}'. Stats: {stats.get('total_vector_count', 'N/A')} vectors.")

        except Exception as e: # Bắt lỗi chung cho khởi tạo
            logger.error(f"Failed to initialize Pinecone or connect to index '{self.index_name}': {e}", exc_info=True)
            if PINECONE_EXCEPTIONS_AVAILABLE and ApiException and isinstance(e, ApiException):
                logger.error(f"Pinecone API Exception (Init): Status {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
            elif PINECONE_EXCEPTIONS_AVAILABLE and PineconeException and isinstance(e, PineconeException): # Bắt PineconeException chung hơn
                 logger.error(f"Pinecone general exception (Init): {e}")
            self.index = None


    def is_connected(self):
        return self.index is not None

    def query_vectors(self, vector, top_k=1, namespace=None, filter_criteria=None, include_values=False, include_metadata=False):
        if not self.is_connected():
            logger.error("Cannot query Pinecone. Not connected to an index.")
            return None
        try:
            query_params = {"vector": vector, "top_k": top_k, "include_values": include_values, "include_metadata": include_metadata}
            if namespace: query_params["namespace"] = namespace
            if filter_criteria: query_params["filter"] = filter_criteria
            
            logger.debug(f"Querying Pinecone index '{self.index_name}'...")
            query_response = self.index.query(**query_params)
            
            if query_response and hasattr(query_response, 'matches'):
                 logger.info(f"Pinecone query successful. Found {len(query_response.matches)} matches.")
            else:
                logger.info("Pinecone query successful but no 'matches' or empty response.")
            return query_response
        except Exception as e: # Bắt lỗi chung, sau đó kiểm tra type nếu có thể
            logger.error(f"Error querying Pinecone index '{self.index_name}': {e}", exc_info=True)
            if PINECONE_EXCEPTIONS_AVAILABLE and ApiException and isinstance(e, ApiException):
                logger.error(f"Pinecone API Exception (Query): Status {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
            elif PINECONE_EXCEPTIONS_AVAILABLE and PineconeException and isinstance(e, PineconeException):
                 logger.error(f"Pinecone general exception (Query): {e}")
        return None

    def upsert_vectors(self, vectors_data, namespace=None, batch_size=100):
        if not self.is_connected():
            logger.error("Cannot upsert to Pinecone. Not connected to an index.")
            return None
        
        formatted_vectors = []
        if not vectors_data:
            logger.warning("No vectors provided for upserting.")
            return None
        
        # Chuẩn hóa ID thành string
        if isinstance(vectors_data[0], tuple):
            for item in vectors_data:
                vec_id, values = str(item[0]), item[1] # Đảm bảo ID là string
                metadata = item[2] if len(item) > 2 else None
                formatted_vec = {"id": vec_id, "values": values}
                if metadata: formatted_vec["metadata"] = metadata
                formatted_vectors.append(formatted_vec)
        else: 
            formatted_vectors = [
                {"id": str(v.get("id")), "values": v.get("values"), "metadata": v.get("metadata")}
                for v in vectors_data if v.get("id") and v.get("values")
            ]
            formatted_vectors = [v for v in formatted_vectors if v["id"] and v["values"]]

        if not formatted_vectors:
            logger.warning("No valid formatted vectors for upserting after processing input.")
            return None
            
        try:
            logger.info(f"Upserting {len(formatted_vectors)} vectors to Pinecone index '{self.index_name}'...")
            upsert_params = {"vectors": formatted_vectors} # batch_size là tham số của method, không phải của dict
            if namespace: upsert_params["namespace"] = namespace
            
            upsert_response = self.index.upsert(**upsert_params, batch_size=batch_size) # Truyền batch_size ở đây
            logger.info(f"Pinecone upsert successful. Response: upserted_count={upsert_response.upserted_count if upsert_response else 'N/A'}")
            return upsert_response
        except Exception as e: # Bắt lỗi chung
            logger.error(f"Error upserting to Pinecone index '{self.index_name}': {e}", exc_info=True)
            if PINECONE_EXCEPTIONS_AVAILABLE and ApiException and isinstance(e, ApiException):
                logger.error(f"Pinecone API Exception (Upsert): Status {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
            elif PINECONE_EXCEPTIONS_AVAILABLE and PineconeException and isinstance(e, PineconeException):
                 logger.error(f"Pinecone general exception (Upsert): {e}")
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

            if not any(delete_params.values()): # Kiểm tra xem có tiêu chí nào được đặt không
                logger.warning("No parameters specified for delete operation (ids, delete_all, or filter).")
                return None 
            
            logger.info(f"Deleting vectors from Pinecone index '{self.index_name}' with params: {delete_params}")
            delete_response = self.index.delete(**delete_params)
            logger.info(f"Pinecone delete operation successful. Response: {delete_response}") # Response có thể là {}
            return delete_response
        except Exception as e: # Bắt lỗi chung
            logger.error(f"Error deleting from Pinecone index '{self.index_name}': {e}", exc_info=True)
            if PINECONE_EXCEPTIONS_AVAILABLE and ApiException and isinstance(e, ApiException):
                logger.error(f"Pinecone API Exception (Delete): Status {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
            elif PINECONE_EXCEPTIONS_AVAILABLE and PineconeException and isinstance(e, PineconeException):
                 logger.error(f"Pinecone general exception (Delete): {e}")
        return None

    def describe_index_stats(self):
        if not self.is_connected():
            logger.error("Cannot describe index stats. Not connected to an index.")
            return None
        try:
            stats = self.index.describe_index_stats()
            logger.info(f"Pinecone index stats for '{self.index_name}': {stats}")
            return stats
        except Exception as e: # Bắt lỗi chung
            logger.error(f"Error describing Pinecone index stats for '{self.index_name}': {e}", exc_info=True)
            if PINECONE_EXCEPTIONS_AVAILABLE and ApiException and isinstance(e, ApiException):
                logger.error(f"Pinecone API Exception (Describe): Status {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
            elif PINECONE_EXCEPTIONS_AVAILABLE and PineconeException and isinstance(e, PineconeException):
                 logger.error(f"Pinecone general exception (Describe): {e}")
        return None