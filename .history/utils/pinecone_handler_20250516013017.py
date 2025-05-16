# utils/pinecone_handler.py
import logging
import time
from pinecone import Pinecone, Index # Giữ lại import cơ bản này
# KHÔNG import PineconeException, NotFoundException, ApiException nữa

from pinecone import ServerlessSpec, PodSpec # Vẫn cần nếu có logic tạo index

logger = logging.getLogger(__name__)

class PineconeHandler:
    def __init__(self, api_key=None, index_name=None, config=None, environment_for_pod_spec=None):
        self.pinecone_client = None
        self.index = None
        self.index_name = None
        self.api_key = None
        self.environment_for_pod_spec = environment_for_pod_spec

        if config:
            self.api_key = config.get('PINECONE_API_KEY', api_key)
            self.environment_for_pod_spec = config.get('PINECONE_ENVIRONMENT', environment_for_pod_spec)
            self.index_name = config.get('PINECONE_INDEX_NAME', index_name)
        else:
            self.api_key = api_key
            self.index_name = index_name

        if not self.api_key or not self.index_name:
            logger.error("Pinecone API key or index name is missing in configuration.")
            return

        self._initialize_pinecone(config)

    def _initialize_pinecone(self, config=None):
        try:
            self.pinecone_client = Pinecone(api_key=self.api_key)
            logger.info("Pinecone client initialized.")

            existing_indexes = self.pinecone_client.list_indexes().names
            if self.index_name not in existing_indexes:
                logger.warning(f"Pinecone index '{self.index_name}' does not exist.")
                if config and config.get('PINECONE_AUTOCREATE_INDEX', False):
                    dimension = config.get('PINECONE_EMBEDDING_DIMENSION', 256)
                    metric = config.get('PINECONE_METRIC', 'cosine')
                    cloud_provider = config.get('PINECONE_CLOUD_PROVIDER', 'aws')
                    region = config.get('PINECONE_REGION', 'us-east-1')
                    
                    logger.info(f"Attempting to auto-create index '{self.index_name}'...")
                    try:
                        self.pinecone_client.create_index(
                            name=self.index_name, dimension=dimension, metric=metric,
                            spec=ServerlessSpec(cloud=cloud_provider, region=region)
                        )
                        logger.info(f"Index '{self.index_name}' creation initiated. Waiting...")
                        while not self.pinecone_client.describe_index(self.index_name).status['ready']:
                            time.sleep(5)
                        logger.info(f"Index '{self.index_name}' is now ready.")
                    except Exception as e_create: # Bắt Exception chung khi tạo index
                        logger.error(f"Error during index creation '{self.index_name}': {e}", exc_info=True)
                        self.index = None
                        return
                else:
                    self.index = None
                    return

            self.index = self.pinecone_client.Index(self.index_name)
            stats = self.index.describe_index_stats()
            logger.info(f"Successfully connected to Pinecone index '{self.index_name}'. Stats: {stats.get('total_vector_count', 'N/A')} vectors.")

        except Exception as e: # Bắt Exception chung cho toàn bộ quá trình khởi tạo
            logger.error(f"Failed to initialize Pinecone or connect to index '{self.index_name}': {e}", exc_info=True)
            # Kiểm tra xem có phải lỗi API không (nếu e có các thuộc tính đó)
            if hasattr(e, 'status') and hasattr(e, 'body'):
                 logger.error(f"It might be an API error. Status: {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
            self.index = None

    def is_connected(self):
        return self.index is not None

    def query_vectors(self, vector, top_k=1, namespace=None, filter_criteria=None, include_values=False, include_metadata=False):
        if not self.is_connected():
            logger.error("Cannot query Pinecone. Not connected to an index.")
            return None
        try:
            query_params = {
                "vector": vector, "top_k": top_k,
                "include_values": include_values, "include_metadata": include_metadata
            }
            if namespace: query_params["namespace"] = namespace
            if filter_criteria: query_params["filter"] = filter_criteria
            
            logger.debug(f"Querying Pinecone index '{self.index_name}'...")
            query_response = self.index.query(**query_params)
            
            if query_response and hasattr(query_response, 'matches'):
                 logger.info(f"Pinecone query successful. Found {len(query_response.matches)} matches.")
            else:
                logger.info("Pinecone query successful but no 'matches' or empty response.")
            return query_response
        except Exception as e: # Bắt Exception chung
            logger.error(f"Error querying Pinecone index '{self.index_name}': {e}", exc_info=True)
            if hasattr(e, 'status') and hasattr(e, 'body'):
                 logger.error(f"API Error details - Status: {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
        return None

    def upsert_vectors(self, vectors_data, namespace=None, batch_size=100):
        if not self.is_connected():
            logger.error("Cannot upsert to Pinecone. Not connected to an index.")
            return None
        # ... (logic chuẩn bị formatted_vectors như cũ) ...
        formatted_vectors = []
        if not vectors_data: # Thêm kiểm tra này
            logger.warning("No vectors provided for upserting.")
            return None
        
        if isinstance(vectors_data[0], tuple):
            for item in vectors_data:
                vec_id, values = item[0], item[1]
                metadata = item[2] if len(item) > 2 else None
                formatted_vec = {"id": str(vec_id), "values": values}
                if metadata: formatted_vec["metadata"] = metadata
                formatted_vectors.append(formatted_vec)
        else: 
            formatted_vectors = [{"id": str(v.get("id")), "values": v.get("values"), "metadata": v.get("metadata")} for v in vectors_data if v.get("id") and v.get("values")]
            formatted_vectors = [v for v in formatted_vectors if v["id"] and v["values"]]

        if not formatted_vectors:
            logger.warning("No valid formatted vectors for upserting after processing input.")
            return None
            
        try:
            logger.info(f"Upserting {len(formatted_vectors)} vectors to Pinecone index '{self.index_name}'...")
            upsert_params = {"vectors": formatted_vectors, "batch_size": batch_size}
            if namespace: upsert_params["namespace"] = namespace
            
            upsert_response = self.index.upsert(**upsert_params)
            logger.info(f"Pinecone upsert successful. Response: upserted_count={upsert_response.upserted_count if upsert_response else 'N/A'}")
            return upsert_response
        except Exception as e: # Bắt Exception chung
            logger.error(f"Error upserting to Pinecone index '{self.index_name}': {e}", exc_info=True)
            if hasattr(e, 'status') and hasattr(e, 'body'):
                 logger.error(f"API Error details - Status: {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
        return None

    def delete_vectors(self, ids=None, delete_all=False, namespace=None, filter_criteria=None):
        if not self.is_connected():
            logger.error("Cannot delete from Pinecone. Not connected to an index.")
            return None
        try:
            delete_params = {}
            if ids: delete_params["ids"] = [str(i) for i in ids]
            if delete_all: delete_params["delete_all"] = True
            if namespace: delete_params["namespace"] = namespace
            if filter_criteria: delete_params["filter"] = filter_criteria

            if not any([ids, delete_all, filter_criteria]):
                logger.warning("No specific deletion criteria provided for delete operation.")
                return None 
            
            logger.info(f"Deleting vectors from Pinecone index '{self.index_name}' with params: {delete_params}")
            delete_response = self.index.delete(**delete_params)
            logger.info(f"Pinecone delete operation successful. Response: {delete_response}")
            return delete_response
        except Exception as e: # Bắt Exception chung
            logger.error(f"Error deleting from Pinecone index '{self.index_name}': {e}", exc_info=True)
            if hasattr(e, 'status') and hasattr(e, 'body'):
                 logger.error(f"API Error details - Status: {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
        return None

    def describe_index_stats(self):
        if not self.is_connected():
            logger.error("Cannot describe index stats. Not connected to an index.")
            return None
        try:
            stats = self.index.describe_index_stats()
            logger.info(f"Pinecone index stats for '{self.index_name}': {stats}")
            return stats
        except Exception as e: # Bắt Exception chung
            logger.error(f"Error describing Pinecone index stats for '{self.index_name}': {e}", exc_info=True)
            if hasattr(e, 'status') and hasattr(e, 'body'):
                 logger.error(f"API Error details - Status: {getattr(e, 'status', 'N/A')}, Body: {getattr(e, 'body', 'N/A')}")
        return None