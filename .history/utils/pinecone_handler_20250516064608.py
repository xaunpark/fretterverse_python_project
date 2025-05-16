# utils/pinecone_handler.py
import logging
import time

# Import các exception cụ thể từ submodule pinecone.exceptions
from pinecone.exceptions import PineconeException, PineconeApiException, NotFoundException 

# Import các lớp chính khác từ package cấp cao nhất
from pinecone import Pinecone, ServerlessSpec, PodSpec 

logger = logging.getLogger(__name__)

class PineconeHandler:
    def __init__(self, api_key=None, index_name=None, config=None):
        self.pinecone_client = None
        self.index = None # Đối tượng Index sẽ được lấy từ client
        self.index_name = None
        self.api_key = None

        if config:
            self.api_key = config.get('PINECONE_API_KEY', api_key)
            self.index_name = config.get('PINECONE_INDEX_NAME', index_name)
        else:
            self.api_key = api_key
            self.index_name = index_name

        if not self.api_key or not self.index_name:
            logger.error("Pinecone API key or index name is missing in configuration.")
            # raise ValueError("Pinecone API key and index name are required.") # Có thể raise lỗi để dừng sớm
            return 

        self._initialize_pinecone(config)

    def _initialize_pinecone(self, config=None):
        """Initializes the Pinecone client and gets the index object."""
        try:
            self.pinecone_client = Pinecone(api_key=self.api_key)
            logger.info(f"Pinecone client initialized (API key ending with ...{self.api_key[-4:] if self.api_key else 'N/A'}).")

            existing_indexes = [idx_spec.name for idx_spec in self.pinecone_client.list_indexes()] # list_indexes trả về list các IndexDescription
            if self.index_name not in existing_indexes:
                logger.warning(f"Pinecone index '{self.index_name}' does not exist.")
                if config and config.get('PINECONE_AUTOCREATE_INDEX', False):
                    dimension = config.get('PINECONE_EMBEDDING_DIMENSION', 256)
                    metric = config.get('PINECONE_METRIC', 'cosine')
                    cloud_provider = config.get('PINECONE_CLOUD_PROVIDER', 'aws').lower()
                    region = config.get('PINECONE_REGION', 'us-west-2') # Ví dụ region cho AWS
                    
                    logger.info(f"Attempting to auto-create index '{self.index_name}' with dim={dimension}, metric={metric}, cloud={cloud_provider}, region={region}...")
                    try:
                        self.pinecone_client.create_index(
                            name=self.index_name, 
                            dimension=dimension, 
                            metric=metric,
                            spec=ServerlessSpec(cloud=cloud_provider, region=region)
                            # Hoặc PodSpec nếu bạn dùng pod-based index:
                            # environment_for_pod = config.get('PINECONE_ENVIRONMENT') # Cần environment cho PodSpec
                            # if not environment_for_pod:
                            #    logger.error("PINECONE_ENVIRONMENT config missing for PodSpec auto-creation.")
                            #    raise ValueError("PINECONE_ENVIRONMENT needed for PodSpec.")
                            # spec=PodSpec(environment=environment_for_pod, pod_type=config.get('PINECONE_POD_TYPE', "p1.x1"))
                        )
                        logger.info(f"Index '{self.index_name}' creation initiated. Waiting for it to be ready...")
                        while True:
                            index_description = self.pinecone_client.describe_index(self.index_name)
                            if index_description.status['ready']:
                                logger.info(f"Index '{self.index_name}' is now ready.")
                                break
                            logger.info(f"Index '{self.index_name}' not ready yet, state: {index_description.status['state']}. Waiting...")
                            time.sleep(10) 
                    except PineconeApiException as e_create_api:
                        logger.error(f"Pinecone API Exception during index auto-creation '{self.index_name}': Status {e_create_api.status}, Body: {e_create_api.body}", exc_info=False)
                        self.index = None
                        return
                    except PineconeException as e_create_general: # Bắt lỗi Pinecone chung hơn
                        logger.error(f"Pinecone general error during index auto-creation '{self.index_name}': {e_create_general}", exc_info=True)
                        self.index = None
                        return
                    except Exception as e_create_unknown: # Lỗi không mong muốn
                        logger.error(f"Unexpected error during index auto-creation '{self.index_name}': {e_create_unknown}", exc_info=True)
                        self.index = None
                        return
                else: # Không auto-create
                    self.index = None
                    return

            # Lấy đối tượng Index từ client
            self.index = self.pinecone_client.Index(self.index_name)
            # Kiểm tra kết nối bằng cách lấy stats
            stats = self.index.describe_index_stats() # Sẽ raise lỗi nếu index không truy cập được
            logger.info(f"Successfully connected to Pinecone index '{self.index_name}'. Stats: {stats.total_vector_count} vectors.")

        except PineconeApiException as e_init_api:
            logger.error(f"Pinecone API Exception during initialization for index '{self.index_name}': Status {e_init_api.status}, Body: {e_init_api.body}", exc_info=False)
            self.index = None
        except PineconeException as e_init_general: # Bắt lỗi Pinecone chung hơn
             logger.error(f"Pinecone general exception during initialization for index '{self.index_name}': {e_init_general}", exc_info=True)
             self.index = None
        except Exception as e_init_unknown: # Lỗi không mong muốn khác
            logger.error(f"Unexpected error during Pinecone initialization for index '{self.index_name}': {e_init_unknown}", exc_info=True)
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
            
            logger.debug(f"Querying Pinecone index '{self.index_name}' with top_k={top_k}...")
            query_response = self.index.query(**query_params)
            
            if query_response and hasattr(query_response, 'matches'):
                 logger.info(f"Pinecone query successful. Found {len(query_response.matches)} matches.")
            else:
                logger.info("Pinecone query successful but no 'matches' attribute or empty response.")
            return query_response
        except NotFoundException as e_nf: # Index hoặc namespace không tồn tại khi query
            logger.error(f"Pinecone NotFoundException during query on index '{self.index_name}': {e_nf}", exc_info=True)
        except PineconeApiException as e_api:
            logger.error(f"Pinecone API Exception during query on index '{self.index_name}': Status {e_api.status}, Body: {e_api.body}", exc_info=False)
        except PineconeException as e_general:
             logger.error(f"Pinecone general exception during query on index '{self.index_name}': {e_general}", exc_info=True)
        except Exception as e_unknown:
            logger.error(f"Unexpected error querying Pinecone index '{self.index_name}': {e_unknown}", exc_info=True)
        return None

    def upsert_vectors(self, vectors_data, namespace=None, batch_size=100):
        if not self.is_connected():
            logger.error("Cannot upsert to Pinecone. Not connected to an index.")
            return None
        
        formatted_vectors = []
        if not vectors_data: 
            logger.warning("No vectors provided for upserting.")
            return None
        
        # Chuẩn hóa ID thành string và đảm bảo format đúng
        if isinstance(vectors_data, list) and vectors_data:
            if isinstance(vectors_data[0], tuple):
                for item in vectors_data:
                    vec_id, values = str(item[0]), item[1]
                    metadata = item[2] if len(item) > 2 else None
                    formatted_vec = {"id": vec_id, "values": values}
                    if metadata: formatted_vec["metadata"] = metadata
                    formatted_vectors.append(formatted_vec)
            elif isinstance(vectors_data[0], dict):
                for v_dict in vectors_data:
                    if v_dict.get("id") and v_dict.get("values"):
                        formatted_vectors.append({
                            "id": str(v_dict.get("id")), 
                            "values": v_dict.get("values"), 
                            "metadata": v_dict.get("metadata") # Sẽ là None nếu không có
                        })
            else:
                logger.error(f"Unsupported format for vectors_data items: {type(vectors_data[0])}")
                return None
        else:
            logger.error(f"vectors_data is not a list or is empty: {vectors_data}")
            return None


        if not formatted_vectors:
            logger.warning("No valid formatted vectors for upserting after processing input.")
            return None
            
        try:
            logger.info(f"Upserting {len(formatted_vectors)} vectors to Pinecone index '{self.index_name}'...")
            upsert_params = {"vectors": formatted_vectors}
            if namespace: upsert_params["namespace"] = namespace
            
            upsert_response = self.index.upsert(**upsert_params, batch_size=batch_size)
            upserted_c = upsert_response.upserted_count if upsert_response else 'N/A'
            logger.info(f"Pinecone upsert successful. Response: upserted_count={upserted_c}")
            return upsert_response
        except PineconeApiException as e_api:
            logger.error(f"Pinecone API Exception during upsert to index '{self.index_name}': Status {e_api.status}, Body: {e_api.body}", exc_info=False)
        except PineconeException as e_general:
             logger.error(f"Pinecone general exception during upsert to index '{self.index_name}': {e_general}", exc_info=True)
        except Exception as e_unknown:
            logger.error(f"Unexpected error upserting to Pinecone index '{self.index_name}': {e_unknown}", exc_info=True)
        return None

    def delete_vectors(self, ids=None, delete_all=False, namespace=None, filter_criteria=None):
        if not self.is_connected():
            logger.error("Cannot delete from Pinecone. Not connected to an index.")
            return None
        try:
            delete_params = {}
            if ids: delete_params["ids"] = [str(i) for i in ids]
            if delete_all: delete_params["delete_all"] = True # Phải boolean
            if namespace: delete_params["namespace"] = namespace
            if filter_criteria: delete_params["filter"] = filter_criteria

            if not any(k in delete_params for k in ["ids", "delete_all", "filter"]):
                logger.warning("No parameters specified for delete operation (ids, delete_all, or filter).")
                return None 
            
            logger.info(f"Deleting vectors from Pinecone index '{self.index_name}' with params: {delete_params}")
            delete_response = self.index.delete(**delete_params) 
            logger.info(f"Pinecone delete operation successful. Response: {delete_response}") # Thường trả về {}
            return delete_response
        except NotFoundException as e_nf:
            logger.error(f"Pinecone NotFoundException during delete on index '{self.index_name}': {e_nf}", exc_info=True)
        except PineconeApiException as e_api:
            logger.error(f"Pinecone API Exception during delete on index '{self.index_name}': Status {e_api.status}, Body: {e_api.body}", exc_info=False)
        except PineconeException as e_general:
             logger.error(f"Pinecone general exception during delete on index '{self.index_name}': {e_general}", exc_info=True)
        except Exception as e_unknown:
            logger.error(f"Unexpected error deleting from Pinecone index '{self.index_name}': {e_unknown}", exc_info=True)
        return None

    def describe_index_stats(self):
        if not self.is_connected():
            logger.error("Cannot describe index stats. Not connected to an index.")
            return None
        try:
            stats = self.index.describe_index_stats()
            logger.info(f"Pinecone index stats for '{self.index_name}': Total vectors: {stats.total_vector_count}, Namespaces: {stats.namespaces}")
            return stats
        except PineconeApiException as e_api:
            logger.error(f"Pinecone API Exception during describe_index_stats for '{self.index_name}': Status {e_api.status}, Body: {e_api.body}", exc_info=False)
        except PineconeException as e_general:
             logger.error(f"Pinecone general exception during describe_index_stats for '{self.index_name}': {e_general}", exc_info=True)
        except Exception as e_unknown:
            logger.error(f"Unexpected error describing Pinecone index stats for '{self.index_name}': {e_unknown}", exc_info=True)
        return None