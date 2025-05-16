# utils/pinecone_handler.py
import logging

# from pinecone import Pinecone, Index, ApiException

from pinecone import Pinecone, Index # Giữ lại Pinecone và Index
try:
    from pinecone.exceptions import ApiException # Thử import từ đây
except ImportError:
    # Fallback cho trường hợp ApiException có thể được định nghĩa ở chỗ khác hoặc không còn dùng tên đó
    # Trong nhiều trường hợp, các lỗi API có thể là pinecone.core.client.exceptions.ApiException
    # Hoặc đơn giản là dùng requests.exceptions.HTTPError nếu lỗi là từ HTTP request
    # Để đơn giản, chúng ta có thể bắt Exception chung hơn và kiểm tra nội dung lỗi
    # Hoặc nếu bạn biết chắc chắn lỗi là HTTPError từ thư viện requests mà pinecone dùng ngầm:
    from requests.exceptions import HTTPError as ApiException_fallback # Đặt tên khác để tránh nhầm lẫn
    ApiException = ApiException_fallback # Gán lại nếu muốn dùng tên ApiException
    logger.warning("pinecone.exceptions.ApiException not found, consider adjusting exception handling.")

# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG

logger = logging.getLogger(__name__)

class PineconeHandler:
    def __init__(self, api_key=None, environment=None, index_name=None, config=None):
        """
        Initializes the Pinecone client and connects to a specific index.
        'config' là một dict chứa các thông tin kết nối, sẽ override các tham số riêng lẻ.
        """
        self.pinecone_client = None
        self.index = None
        self.index_name = None

        if config:
            self.api_key = config.get('PINECONE_API_KEY', api_key)
            self.environment = config.get('PINECONE_ENVIRONMENT', environment)
            self.index_name = config.get('PINECONE_INDEX_NAME', index_name)
        else:
            self.api_key = api_key
            self.environment = environment
            self.index_name = index_name

        if not self.api_key or not self.environment or not self.index_name:
            logger.error("Pinecone API key, environment, or index name is missing in configuration.")
            # raise ValueError("Pinecone API key, environment, and index name are required.")
            return # Không kết nối nếu thiếu config

        self._initialize_pinecone()

    def _initialize_pinecone(self):
        """Initializes the Pinecone client and gets the index object."""
        try:
            # --- Cách tiếp cận cho pinecone-client v3.x+ ---
            self.pinecone_client = Pinecone(api_key=self.api_key, environment=self.environment) # Một số phiên bản mới hơn có thể không cần environment ở đây
            
            # Kiểm tra xem index có tồn tại không
            if self.index_name not in self.pinecone_client.list_indexes().names:
                logger.error(f"Pinecone index '{self.index_name}' does not exist in environment '{self.environment}'.")
                # Bạn có thể muốn tạo index ở đây nếu logic cho phép, ví dụ:
                # from pinecone import ServerlessSpec, PodSpec
                # dimension = APP_CONFIG.get('PINECONE_EMBEDDING_DIMENSION', 256) # Lấy từ config
                # self.pinecone_client.create_index(
                #     name=self.index_name,
                #     dimension=dimension,
                #     metric="cosine", # Hoặc "euclidean", "dotproduct"
                #     spec=ServerlessSpec(cloud='aws', region='us-east-1') # Ví dụ cho serverless
                #     # Hoặc spec=PodSpec(environment=self.environment, pod_type="p1.x1") cho pod-based
                # )
                # logger.info(f"Pinecone index '{self.index_name}' created.")
                # time.sleep(60) # Đợi index sẵn sàng (có thể cần thời gian)
                self.index = None
                return

            self.index = self.pinecone_client.Index(self.index_name)
            logger.info(f"Successfully connected to Pinecone index '{self.index_name}' in environment '{self.environment}'.")
            # logger.debug(f"Index stats: {self.index.describe_index_stats()}")

            # --- Cách tiếp cận cho pinecone-client v2.x ---
            # pinecone.init(api_key=self.api_key, environment=self.environment)
            # if self.index_name not in pinecone.list_indexes():
            #     logger.error(f"Pinecone index '{self.index_name}' does not exist.")
            #     self.index = None
            #     return
            # self.index = pinecone.Index(self.index_name)
            # logger.info(f"Successfully connected to Pinecone index '{self.index_name}'.")
            # logger.debug(f"Index stats: {self.index.describe_index_stats()}")

        except ApiException as e:
            logger.error(f"Pinecone API Exception during initialization: {e.body if hasattr(e, 'body') else e}")
            self.index = None
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {e}")
            self.index = None

    def is_connected(self):
        """Checks if successfully connected to an index."""
        return self.index is not None

    def query_vectors(self, vector, top_k=1, namespace=None, filter_criteria=None, include_values=False, include_metadata=False):
        """
        Queries the Pinecone index for similar vectors.
        :param vector: The query vector (list of floats).
        :param top_k: The number of top similar vectors to return.
        :param namespace: (Optional) The namespace to query.
        :param filter_criteria: (Optional) Metadata filter dictionary.
        :param include_values: (Optional) Whether to include vector values in results.
        :param include_metadata: (Optional) Whether to include metadata in results.
        :return: Query response object from Pinecone or None on error.
        """
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
            if namespace:
                query_params["namespace"] = namespace
            if filter_criteria:
                query_params["filter"] = filter_criteria
            
            logger.debug(f"Querying Pinecone index '{self.index_name}' with top_k={top_k}, namespace='{namespace}', filter='{filter_criteria}'")
            query_response = self.index.query(**query_params)
            
            # logger.debug(f"Pinecone query response: {query_response}")
            if query_response and hasattr(query_response, 'matches'):
                 logger.info(f"Pinecone query successful. Found {len(query_response.matches)} matches.")
            else:
                logger.info("Pinecone query successful but no matches attribute or empty response.")
            return query_response

        except ApiException as e:
            logger.error(f"Pinecone API Exception during query: {e.body if hasattr(e, 'body') else e}")
        except Exception as e:
            logger.error(f"Error querying Pinecone index '{self.index_name}': {e}")
        return None

    def upsert_vectors(self, vectors_with_ids, namespace=None, batch_size=100):
        """
        Upserts (inserts or updates) vectors into the Pinecone index.
        :param vectors_with_ids: A list of tuples or dicts.
                                 If tuples: [(id1, vector1, metadata1), (id2, vector2, metadata2), ...]
                                 If dicts: [{"id": id1, "values": vector1, "metadata": metadata1}, ...]
                                 Metadata is optional.
        :param namespace: (Optional) The namespace to upsert into.
        :param batch_size: (Optional) Size of batches for upserting.
        :return: Upsert response object from Pinecone or None on error.
        """
        if not self.is_connected():
            logger.error("Cannot upsert to Pinecone. Not connected to an index.")
            return None

        # Chuẩn bị data cho API (đảm bảo đúng format list of dicts hoặc list of tuples)
        # Thư viện Pinecone v3 thường dùng list of dicts hoặc Pinecone Vector objects.
        # Ví dụ này giả sử vectors_with_ids là list các dicts:
        # [{"id": "vec1", "values": [0.1, 0.2], "metadata": {"genre": "drama"}}, ...]
        # Hoặc list các tuples: [("vec1", [0.1,0.2], {"genre": "drama"}), ...]
        # Hãy đảm bảo format đầu vào của bạn nhất quán.

        # Nếu đầu vào là list of tuples, chuyển đổi nó
        formatted_vectors = []
        if vectors_with_ids and isinstance(vectors_with_ids[0], tuple):
            for item in vectors_with_ids:
                vec_id = item[0]
                values = item[1]
                metadata = item[2] if len(item) > 2 else None
                formatted_vec = {"id": vec_id, "values": values}
                if metadata:
                    formatted_vec["metadata"] = metadata
                formatted_vectors.append(formatted_vec)
        else: # Giả sử đã là list of dicts
            formatted_vectors = vectors_with_ids

        if not formatted_vectors:
            logger.warning("No vectors provided for upserting.")
            return None

        try:
            logger.info(f"Upserting {len(formatted_vectors)} vectors to Pinecone index '{self.index_name}', namespace='{namespace}', batch_size={batch_size}.")
            
            upsert_response = None
            if namespace:
                upsert_response = self.index.upsert(vectors=formatted_vectors, namespace=namespace, batch_size=batch_size)
            else:
                upsert_response = self.index.upsert(vectors=formatted_vectors, batch_size=batch_size)
            
            logger.info(f"Pinecone upsert successful. Response: {upsert_response}")
            return upsert_response
        except ApiException as e:
            logger.error(f"Pinecone API Exception during upsert: {e.body if hasattr(e, 'body') else e}")
        except Exception as e:
            logger.error(f"Error upserting to Pinecone index '{self.index_name}': {e}")
        return None

    def delete_vectors(self, ids=None, delete_all=False, namespace=None, filter_criteria=None):
        """
        Deletes vectors from the Pinecone index by IDs, or all vectors in a namespace, or by filter.
        :param ids: A list of vector IDs to delete.
        :param delete_all: If True, deletes all vectors in the specified namespace.
        :param namespace: (Optional) The namespace to delete from.
        :param filter_criteria: (Optional) Metadata filter for deletion.
        :return: Delete response or None on error.
        """
        if not self.is_connected():
            logger.error("Cannot delete from Pinecone. Not connected to an index.")
            return None
        try:
            delete_params = {}
            if ids:
                delete_params["ids"] = ids
            if delete_all:
                delete_params["delete_all"] = True
            if namespace:
                delete_params["namespace"] = namespace
            if filter_criteria:
                delete_params["filter"] = filter_criteria

            if not delete_params:
                logger.warning("No parameters specified for delete operation.")
                return None
            
            logger.info(f"Deleting vectors from Pinecone index '{self.index_name}' with params: {delete_params}")
            delete_response = self.index.delete(**delete_params)
            logger.info(f"Pinecone delete operation successful. Response: {delete_response}")
            return delete_response
        except ApiException as e:
            logger.error(f"Pinecone API Exception during delete: {e.body if hasattr(e, 'body') else e}")
        except Exception as e:
            logger.error(f"Error deleting from Pinecone index '{self.index_name}': {e}")
        return None

    def describe_index_stats(self):
        """Gets statistics about the index."""
        if not self.is_connected():
            logger.error("Cannot describe index stats. Not connected to an index.")
            return None
        try:
            stats = self.index.describe_index_stats()
            logger.info(f"Pinecone index stats for '{self.index_name}': {stats}")
            return stats
        except Exception as e:
            logger.error(f"Error describing Pinecone index stats for '{self.index_name}': {e}")
            return None

# --- Example Usage (cần được gọi từ nơi có APP_CONFIG) ---
# if __name__ == "__main__":
#     # from utils.config_loader import load_app_config
#     # from utils.logging_config import setup_logging
#     # APP_CONFIG = load_app_config() # Giả sử hàm này load PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME
#     # setup_logging(log_level_str="DEBUG")
#
#     # pinecone_handler = PineconeHandler(config=APP_CONFIG)
#     # # Hoặc truyền trực tiếp
#     # # pinecone_handler = PineconeHandler(
#     # #     api_key=APP_CONFIG.get('PINECONE_API_KEY'),
#     # #     environment=APP_CONFIG.get('PINECONE_ENVIRONMENT'),
#     # #     index_name=APP_CONFIG.get('PINECONE_INDEX_NAME')
#     # # )
#
#     # if pinecone_handler.is_connected():
#     #     # Lấy thông tin index
#     #     pinecone_handler.describe_index_stats()
#
#     #     # Ví dụ Upsert (kích thước vector phải khớp với dimension của index)
#     #     # Giả sử dimension là 3
#     #     vectors_to_add = [
#     #         {"id": "vec_keyword_1", "values": [0.1, 0.2, 0.3], "metadata": {"source": "keyword_checker"}},
#     #         {"id": "vec_keyword_2", "values": [0.4, 0.5, 0.6], "metadata": {"source": "keyword_checker", "language": "en"}}
#     #     ]
#     #     # Hoặc dạng tuple:
#     #     # vectors_to_add_tuples = [
#     #     #     ("vec_keyword_1_tuple", [0.1, 0.2, 0.3], {"source": "keyword_checker"}),
#     #     #     ("vec_keyword_2_tuple", [0.4, 0.5, 0.6], {"source": "keyword_checker", "language": "en"})
#     #     # ]
#     #     # upsert_resp = pinecone_handler.upsert_vectors(vectors_to_add_tuples) # Hàm sẽ tự chuyển đổi format
#     #     upsert_resp = pinecone_handler.upsert_vectors(vectors_to_add)
#     #     if upsert_resp:
#     #         logger.info(f"Upsert response: {upsert_resp.upserted_count} vectors upserted.")
#
#     #     # Chờ một chút để upsert được xử lý (quan trọng cho các index mới hoặc sau khi upsert nhiều)
#     #     import time
#     #     time.sleep(5) # Có thể cần nhiều hơn
#     #     pinecone_handler.describe_index_stats()
#
#     #     # Ví dụ Query
#     #     query_vec = [0.11, 0.21, 0.31] # Một vector gần giống với "vec_keyword_1"
#     #     query_results = pinecone_handler.query_vectors(vector=query_vec, top_k=2, include_metadata=True, include_values=False)
#
#     #     if query_results and query_results.matches:
#     #         logger.info("Query results:")
#     #         for match in query_results.matches:
#     #             logger.info(f"  ID: {match.id}, Score: {match.score}, Metadata: {match.metadata}")
#     #     else:
#     #         logger.info("No matches found or error in query.")
#
#         # Ví dụ Delete (cẩn thận khi chạy)
#         # delete_resp = pinecone_handler.delete_vectors(ids=["vec_keyword_1", "vec_keyword_2"])
#         # if delete_resp:
#         #      logger.info(f"Delete response: {delete_resp}") # Nội dung response có thể khác nhau giữa các phiên bản
#         # pinecone_handler.describe_index_stats()