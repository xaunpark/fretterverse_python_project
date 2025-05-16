# backup_pinecone_index.py
import logging
import json
import time
import os
import argparse # Để nhận tham số từ dòng lệnh

# Import các module cần thiết từ dự án của bạn
# Giả định rằng các file này nằm trong các thư mục con của thư mục gốc dự án
# và thư mục gốc dự án đã được thêm vào PYTHONPATH nếu cần,
# hoặc bạn chạy script này từ thư mục gốc.
try:
    from utils.config_loader import load_app_config
    from utils.logging_config import setup_logging
    from utils.pinecone_handler import PineconeHandler
    # Import hàm normalize_keyword_for_pinecone_id nếu bạn dùng nó để tạo ID
    # và bạn lưu trữ keyword gốc thay vì ID đã chuẩn hóa.
    # from workflows.main_logic import normalize_keyword_for_pinecone_id
except ImportError as e:
    print(f"Error importing project modules: {e}")
    print("Please ensure you are running this script from the root of your project directory,")
    print("or that the project modules are in your PYTHONPATH.")
    exit(1)

# --- Global Variables ---
APP_CONFIG = None
logger = None

def initialize_script():
    """Initializes configuration and logging for this script."""
    global APP_CONFIG, logger
    try:
        APP_CONFIG = load_app_config()
        # Ghi đè một số cài đặt log nếu cần cho script này
        log_level = APP_CONFIG.get('LOG_LEVEL_SCRIPT', "INFO") # Có thể thêm LOG_LEVEL_SCRIPT vào .env
        # Log ra file riêng cho backup hoặc chỉ console
        setup_logging(log_level_str=log_level, log_to_console=True, log_to_file=False) 
        logger = logging.getLogger(__name__) # Lấy logger cho file này
        logger.info("Backup Script: Application initialized successfully.")
        # In ra các config quan trọng cho Pinecone để kiểm tra
        logger.debug(f"Pinecone Config: API Key ends with ...{APP_CONFIG.get('PINECONE_API_KEY', '')[-4:]}, Index: {APP_CONFIG.get('PINECONE_INDEX_NAME')}")
        return True
    except Exception as e:
        print(f"CRITICAL: Error during application initialization for backup script: {e}")
        if logger: logger.critical("Initialization failed", exc_info=True)
        return False

def get_all_vector_ids_from_source(config, source_type="mock", **kwargs):
    """
    Lấy danh sách tất cả các ID vector từ nguồn dữ liệu của bạn.
    :param config: APP_CONFIG object.
    :param source_type: "mock", "file", "database", "pinecone_list" (nếu dùng list_paginated).
    :param kwargs: Các tham số bổ sung tùy theo source_type.
                   Ví dụ: file_path cho source_type="file".
    :return: List các string ID.
    """
    logger.info(f"Fetching all vector IDs from source type: {source_type}")
    
    if source_type == "mock":
        # HÀM GIẢ LẬP: TRẢ VỀ ID GIẢ ĐỂ TEST SCRIPT
        # Trong thực tế, bạn sẽ không dùng cái này cho backup thật
        num_mock_ids = kwargs.get("num_ids", 1050)
        mock_ids = [f"mock_id_{i:04d}" for i in range(num_mock_ids)]
        logger.info(f"Generated {len(mock_ids)} mock IDs for testing.")
        return mock_ids
        
    elif source_type == "file":
        # Đọc ID từ một file text, mỗi ID một dòng
        file_path = kwargs.get("file_path")
        if not file_path or not os.path.exists(file_path):
            logger.error(f"ID source file not found: {file_path}")
            return []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                ids = [line.strip() for line in f if line.strip()]
            logger.info(f"Read {len(ids)} IDs from file: {file_path}")
            return ids
        except Exception as e:
            logger.error(f"Error reading IDs from file {file_path}: {e}")
            return []
            
    elif source_type == "pinecone_list":
        # Sử dụng list_paginated để lấy ID trực tiếp từ Pinecone
        # CẢNH BÁO: Có thể chậm và không hiệu quả cho index rất lớn.
        # Cần kiểm tra giới hạn của Pinecone cho việc list ID.
        pinecone_handler = PineconeHandler(config=config) # Kết nối đến index mặc định trong config
        if not pinecone_handler.is_connected():
            logger.error("Cannot connect to Pinecone to list IDs.")
            return []
        
        all_ids = []
        limit_per_page = 1000 # Giới hạn của Pinecone cho list_paginated
        namespace_to_list = kwargs.get("namespace") # Namespace cụ thể hoặc None
        
        logger.info(f"Listing IDs from Pinecone index '{pinecone_handler.index_name}' (namespace: {namespace_to_list or 'all'})...")
        try:
            # list_paginated trả về một generator
            # Cần Pinecone client v3.0.2 trở lên để có list_paginated
            # Hoặc dùng index.list(namespace=...) cho các phiên bản cũ hơn nếu có
            
            # Logic cho pinecone-client v3+ với list_paginated
            # for ids_batch_response in pinecone_handler.index.list_paginated(namespace=namespace_to_list, limit=limit_per_page):
            #     if ids_batch_response.vectors:
            #         all_ids.extend([v.id for v in ids_batch_response.vectors])
            # logger.info(f"Listed {len(all_ids)} IDs from Pinecone using list_paginated.")
            
            # Nếu phiên bản của bạn không có list_paginated hoặc muốn dùng cách khác:
            # Cách này có thể không lấy được hết nếu index quá lớn và không có pagination token tốt
            # describe_stats = pinecone_handler.describe_index_stats()
            # if describe_stats and describe_stats.namespaces and namespace_to_list:
            #     if namespace_to_list in describe_stats.namespaces:
            #         # Pinecone không có API dễ dàng để list tất cả ID mà không query.
            #         # Đây là một hạn chế.
            #         logger.warning("Directly listing all IDs from a large Pinecone index is often not feasible via API without specific querying strategies.")
            #         logger.warning("Consider maintaining your ID list externally for reliable full backups.")
            #         # Tạm thời trả về rỗng cho trường hợp này
            #         return [] 
            # else: # List toàn bộ index (rất không nên)
                 logger.warning("Attempting to list IDs from Pinecone without pagination might be incomplete or very slow for large indexes.")
                 # Thử một cách rất cơ bản (có thể không hoạt động tốt)
                 # Pinecone không thực sự cung cấp API "list all IDs" một cách đơn giản.
                 # Đây là lý do tại sao việc có nguồn ID bên ngoài là quan trọng.
                 # Ví dụ: Query tất cả với một filter trống (nếu API hỗ trợ) hoặc query với vector zero
                 # và hy vọng nó trả về một phần ID, nhưng không đảm bảo.
                 # Để đơn giản, nếu source_type là "pinecone_list", bạn cần tự implement logic phức tạp hơn
                 # hoặc dựa vào việc đã có sẵn list ID ở đâu đó.
                 logger.error("Source type 'pinecone_list' requires a robust implementation to list all IDs, which is non-trivial for large indexes. Please use 'mock' or 'file' or provide IDs externally.")
                 return []


        except Exception as e:
            logger.error(f"Error listing IDs from Pinecone: {e}", exc_info=True)
            return []
        return all_ids
        
    # TODO: Thêm source_type="database" nếu bạn lưu ID trong DB chính
    # elif source_type == "database":
    #     db_host = config.get('YOUR_DB_HOST')
    #     # ... (kết nối DB và query lấy tất cả ID) ...
    #     pass

    else:
        logger.error(f"Unsupported ID source type: {source_type}")
        return []

def backup_pinecone_index(config, output_file_path, id_source_type="mock", **id_source_kwargs):
    """
    Backs up a Pinecone index.
    """
    pinecone_handler = PineconeHandler(config=config)
    if not pinecone_handler.is_connected():
        logger.error("Cannot connect to Pinecone. Backup aborted.")
        return False

    index_name = config.get('PINECONE_INDEX_NAME')
    logger.info(f"Starting backup for Pinecone index: {index_name}")

    all_vector_ids = get_all_vector_ids_from_source(config, source_type=id_source_type, **id_source_kwargs)
    if not all_vector_ids:
        logger.warning("No vector IDs found from source. Nothing to backup.")
        return True
    
    logger.info(f"Total vector IDs to fetch for backup: {len(all_vector_ids)}")

    batch_size = config.get('PINECONE_FETCH_BATCH_SIZE', 1000) 
    total_fetched_count = 0
    error_count = 0

    # Tạo thư mục cho file backup nếu chưa có
    output_dir = os.path.dirname(output_file_path)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            logger.info(f"Created directory for backup file: {output_dir}")
        except OSError as e_dir:
            logger.error(f"Could not create directory {output_dir}: {e_dir}")
            return False
            
    try:
        with open(output_file_path, 'w', encoding='utf-8') as f_out:
            for i in range(0, len(all_vector_ids), batch_size):
                batch_ids = all_vector_ids[i : i + batch_size]
                if not batch_ids: continue # Bỏ qua batch rỗng

                logger.info(f"Fetching batch {i//batch_size + 1}/{ (len(all_vector_ids) + batch_size - 1)//batch_size }: "
                            f"{len(batch_ids)} IDs (starting with {batch_ids[0]})...")
                
                try:
                    if not pinecone_handler.index: # Double check
                        logger.error("Pinecone index object is not available in handler. Cannot fetch.")
                        error_count += len(batch_ids)
                        continue
                    
                    # Hàm fetch của pinecone-client v3+
                    fetch_response = pinecone_handler.index.fetch(ids=batch_ids)

                    if fetch_response and fetch_response.vectors:
                        fetched_vectors_in_this_batch = 0
                        for vec_id, vector_obj in fetch_response.vectors.items():
                            backup_item = {
                                "id": str(vector_obj.id), # Đảm bảo ID là string
                                "values": vector_obj.values,
                                "metadata": vector_obj.metadata if vector_obj.metadata else {}
                            }
                            f_out.write(json.dumps(backup_item) + '\n')
                            fetched_vectors_in_this_batch += 1
                        
                        total_fetched_count += fetched_vectors_in_this_batch
                        logger.info(f"Fetched and wrote {fetched_vectors_in_this_batch} vectors in this batch.")
                        if fetched_vectors_in_this_batch < len(batch_ids):
                            logger.warning(f"Expected {len(batch_ids)} vectors but received {fetched_vectors_in_this_batch} for this batch. Some IDs might not exist.")
                            # Tìm các ID không được trả về
                            returned_ids = set(fetch_response.vectors.keys())
                            missing_ids_in_batch = [bid for bid in batch_ids if bid not in returned_ids]
                            if missing_ids_in_batch:
                                logger.warning(f"Missing IDs in current batch fetch: {missing_ids_in_batch[:10]}...") # Log một vài ID bị thiếu
                    
                    elif fetch_response and not fetch_response.vectors:
                        logger.warning(f"No vectors returned in fetch response for batch (IDs might not exist or other issue). Batch starts with {batch_ids[0]}.")
                    else: # fetch_response là None hoặc không có attribute vectors
                        logger.error(f"Unexpected fetch response for batch (IDs might not exist or API error). Batch starts with {batch_ids[0]}. Response: {fetch_response}")
                        error_count += len(batch_ids)

                except Exception as e_fetch: 
                    logger.error(f"Error fetching batch starting with ID {batch_ids[0]}: {e_fetch}", exc_info=True)
                    error_count += len(batch_ids)
                
                time.sleep(float(config.get('PINECONE_FETCH_DELAY_SECONDS', 0.2))) # Delay nhỏ

        logger.info(f"Backup process completed. Total vectors fetched and written: {total_fetched_count} to {output_file_path}")
        if error_count > 0:
            logger.warning(f"There were errors fetching approximately {error_count} vectors during backup.")
        return True

    except IOError as e_io:
        logger.error(f"IOError writing backup file {output_file_path}: {e_io}", exc_info=True)
    except Exception as e_main:
        logger.error(f"An unexpected error occurred during backup: {e_main}", exc_info=True)
    return False

def main():
    parser = argparse.ArgumentParser(description="Backup a Pinecone index.")
    parser.add_argument(
        "--output_file", 
        type=str, 
        help="Path to save the backup file (e.g., ./backups/my_index_backup.jsonl)."
    )
    parser.add_argument(
        "--id_source", 
        type=str, 
        default="mock", # Mặc định là mock để an toàn khi chạy thử
        choices=["mock", "file", "pinecone_list"], # Thêm "database" nếu bạn implement
        help="Source of vector IDs ('mock', 'file', 'pinecone_list')."
    )
    parser.add_argument(
        "--id_file_path", 
        type=str, 
        help="Path to the file containing vector IDs (required if id_source is 'file')."
    )
    parser.add_argument(
        "--mock_num_ids",
        type=int,
        default=100, # Số lượng ID mock nhỏ hơn để test nhanh
        help="Number of mock IDs to generate if id_source is 'mock'."
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=None,
        help="Specify a namespace if using id_source 'pinecone_list' or if your IDs are namespaced."
    )
    parser.add_argument(
        "--index_name_override",
        type=str,
        default=None,
        help="Override the PINECONE_INDEX_NAME from config for this backup run."
    )


    args = parser.parse_args()

    if not initialize_script():
        exit(1)

    # Lấy tên index
    pinecone_index_to_backup = args.index_name_override if args.index_name_override else APP_CONFIG.get('PINECONE_INDEX_NAME')
    if not pinecone_index_to_backup:
        logger.critical("Pinecone index name is not configured or provided. Cannot proceed.")
        exit(1)
    
    # Tạo tên file output mặc định nếu không được cung cấp
    output_file = args.output_file
    if not output_file:
        timestamp = int(time.time())
        output_file = f"./pinecone_backup_{pinecone_index_to_backup.replace('-', '_')}_{timestamp}.jsonl"
        logger.info(f"No output file specified, using default: {output_file}")

    # Tạo một bản copy của APP_CONFIG để có thể override index_name nếu cần
    current_config = APP_CONFIG.copy()
    current_config['PINECONE_INDEX_NAME'] = pinecone_index_to_backup


    id_source_kwargs = {}
    if args.id_source == "file":
        if not args.id_file_path:
            logger.error("--id_file_path is required when --id_source is 'file'.")
            exit(1)
        id_source_kwargs["file_path"] = args.id_file_path
    elif args.id_source == "mock":
        id_source_kwargs["num_ids"] = args.mock_num_ids
    elif args.id_source == "pinecone_list":
        if args.namespace:
            id_source_kwargs["namespace"] = args.namespace
        logger.warning("Using id_source 'pinecone_list' can be inefficient for very large indexes "
                       "as Pinecone's direct ID listing capabilities are limited. "
                       "Ensure your implementation of get_all_vector_ids_from_source for 'pinecone_list' is robust "
                       "or consider using an external ID list.")


    logger.info(f"Preparing to backup index '{pinecone_index_to_backup}' from source '{args.id_source}' to '{output_file}'.")
    
    # Xác nhận người dùng
    if args.id_source != "mock": # Không cần xác nhận cho mock
        confirm = input(f"This will fetch data from Pinecone. Do you want to continue? (yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("Backup aborted by user.")
            exit(0)

    success = backup_pinecone_index(
        config=current_config, 
        output_file_path=output_file, 
        id_source_type=args.id_source, 
        **id_source_kwargs
    )

    if success:
        logger.info("Backup script finished successfully.")
    else:
        logger.error("Backup script encountered errors.")

if __name__ == "__main__":
    main()