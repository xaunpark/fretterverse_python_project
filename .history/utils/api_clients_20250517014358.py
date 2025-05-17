# utils/api_clients.py
import requests
import time
import json
from openai import OpenAI # Thư viện OpenAI chính thức
import logging
from googleapiclient.discovery import build # Thư viện Google API
# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG
# Hoặc bạn có thể truyền config vào từng hàm/class

# Khởi tạo logger
logger = logging.getLogger(__name__)

# --- OpenAI Client Functions ---

def get_openai_client(api_key):
    """Helper function to get an OpenAI client instance."""
    if not api_key:
        logger.error("OpenAI API key is not configured.")
        raise ValueError("OpenAI API key is missing.")
    return OpenAI(api_key=api_key)

def call_openrouter_chat(prompt_messages, model_name, openrouter_api_key, openrouter_base_url, user_agent, is_json_output=False, max_retries=3, retry_delay=5):
    """
    Gửi request đến API chat của OpenRouter.
    prompt_messages: list of message objects, e.g., [{"role": "user", "content": "Hello"}]
    is_json_output: Nếu True, yêu cầu OpenAI trả về JSON và cố gắng parse.
    openrouter_api_key: API key dành riêng cho OpenRouter.
    """
    attempt = 0
    endpoint_url = f"{openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "User-Agent": user_agent
        # "HTTP-Referer": "YOUR_SITE_URL", # Tùy chọn: Thêm URL website của bạn
        # "X-Title": "YOUR_APP_NAME" # Tùy chọn: Thêm tên ứng dụng của bạn
    }
    payload = {
        "model": model_name,
        "messages": prompt_messages
    }
    if is_json_output:
        payload["response_format"] = {"type": "json_object"}

    while attempt < max_retries:
        try:
            logger.info(f"Calling OpenRouter Chat API. Model: {model_name}. JSON output: {is_json_output}. Attempt: {attempt + 1}")
            # logger.debug(f"Prompt messages: {prompt_messages}") # Có thể quá dài để log

            response = requests.post(endpoint_url, headers=headers, json=payload, timeout=180) # Tăng timeout nếu cần
            response.raise_for_status()
            
            response_data = response.json()
            content = response_data.get("choices", [{}])[0].get("message", {}).get("content")
            
            if content is None:
                logger.error(f"OpenRouter Chat API call did not return content. Response: {response_data}")
                raise Exception("No content in OpenRouter response")

            logger.info("OpenRouter Chat API call successful.")

            if is_json_output:
                try:
                    parsed_json = json.loads(content)
                    logger.debug("Successfully parsed JSON response from OpenAI.")
                    return parsed_json
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response from OpenAI: {e}. Raw content: {content}")
                    # Có thể thử lại hoặc trả về raw content tùy theo logic
                    # Nếu lỗi parse JSON là nghiêm trọng, có thể muốn retry
                    if attempt + 1 >= max_retries:
                        logger.warning("Max retries reached for JSON parsing. Returning raw content.")
                        return {"error": "JSONDecodeError", "raw_content": content}
                    # Fall through to retry logic
            else:
                return content # Trả về string nếu không yêu cầu JSON

        except Exception as e:
            logger.error(f"Error calling OpenRouter Chat API (attempt {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            if attempt >= max_retries:
                logger.error("Max retries reached for OpenRouter Chat API call. Raising exception.")
                # raise # Hoặc trả về một giá trị lỗi cụ thể
                return None # Hoặc một dict lỗi
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    return None # Nếu tất cả các lần thử đều thất bại

def call_openrouter_dalle(prompt, size, openrouter_api_key, openrouter_base_url, user_agent, model="openai/dall-e-3", n=1, max_retries=3, retry_delay=5):
    """Tạo ảnh với DALL-E (thông qua OpenRouter)."""
    attempt = 0
    endpoint_url = f"{openrouter_base_url}/images/generations"
    headers = {
        "Authorization": f"Bearer {openrouter_api_key}",
        "Content-Type": "application/json",
        "User-Agent": user_agent
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": size,
        "response_format": "url" # OpenRouter thường trả về URL
    }

    while attempt < max_retries:
        try:
            logger.info(f"Calling OpenRouter DALL-E API. Model: {model}. Prompt: '{prompt[:50]}...'. Attempt: {attempt + 1}")
            response = requests.post(endpoint_url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            
            response_data = response.json()
            # OpenRouter có thể trả về response hơi khác OpenAI một chút
            # Kiểm tra cấu trúc response của OpenRouter cho image generation
            image_url = response_data.get("data", [{}])[0].get("url")
            
            if not image_url:
                logger.error(f"OpenRouter DALL-E API call did not return image URL. Response: {response_data}")
                raise Exception("No image URL in OpenRouter DALL-E response")

            logger.info(f"OpenRouter DALL-E API call successful. Image URL: {image_url}")
            return image_url
        except Exception as e:
            logger.error(f"Error calling OpenRouter DALL-E API (attempt {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            if attempt >= max_retries:
                logger.error("Max retries reached for DALL-E API call.")
                return None
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    return None

def call_openai_embeddings(text_input, model_name, openai_api_key, max_retries=3, retry_delay=5):
    """Lấy embeddings trực tiếp từ OpenAI."""
    client = get_openai_client(openai_api_key)
    attempt = 0
    while attempt < max_retries:
        try:
            logger.info(f"Calling OpenAI Embeddings API. Model: {model_name}. Input text length: {len(text_input)}. Attempt: {attempt + 1}")
            response = client.embeddings.create(
                input=text_input,
                model=model_name
            )
            embedding = response.data[0].embedding
            logger.info("OpenAI Embeddings API call successful.")
            return embedding
        except Exception as e: # Bắt các lỗi chung từ thư viện OpenAI hoặc các lỗi khác
            logger.error(f"Error calling OpenAI Embeddings API (attempt {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            if attempt >= max_retries:
                logger.error("Max retries reached for Embeddings API call.")
                return None
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    return None # Nếu tất cả các lần thử đều thất bại

# --- Google API Client Functions ---

def get_google_service(service_name, version, api_key):
    """Helper function to build a Google API service."""
    if not api_key:
        logger.error(f"Google API key for {service_name} is not configured.")
        raise ValueError(f"Google API key for {service_name} is missing.")
    try:
        service = build(service_name, version, developerKey=api_key)
        logger.info(f"Successfully built Google service: {service_name} v{version}")
        return service
    except Exception as e:
        logger.error(f"Failed to build Google service {service_name}: {e}")
        raise

def google_search(query, api_key, cx_id, search_type='web', num_results=10, max_retries=3, retry_delay=5, **kwargs):
    """
    Thực hiện tìm kiếm Google Custom Search.
    search_type: 'web' hoặc 'image'.
    cx_id: Custom Search Engine ID.
    """
    attempt = 0
    while attempt < max_retries:
        try:
            logger.info(f"Performing Google Custom Search. Query: '{query}'. Type: {search_type}. CX_ID: {cx_id}. Attempt: {attempt + 1}")
            # service = get_google_service('customsearch', 'v1', api_key) # Không cần build service mỗi lần gọi
            # Thay vào đó, bạn có thể khởi tạo service một lần bên ngoài
            # Tuy nhiên, để đơn giản, build lại cũng không quá tệ nếu không gọi quá thường xuyên
            # Hoặc dùng requests trực tiếp như trong n8n
            
            params = {
                'key': api_key,
                'cx': cx_id,
                'q': query,
                'num': num_results
            }
            if search_type == 'image':
                params['searchType'] = 'image'
                # Bạn có thể thêm các tham số khác cho image search như imgSize, imgType,...
                # params['imgSize'] = 'large' (từ workflow image của bạn)
            
            params.update(kwargs) # Thêm các tham số tùy chọn khác

            response = requests.get("https://www.googleapis.com/customsearch/v1", params=params)
            response.raise_for_status() # Raise HTTPError cho bad responses (4xx or 5xx)
            
            results = response.json()
            logger.info(f"Google Custom Search successful. Found {len(results.get('items', []))} items.")
            return results.get('items', []) # Trả về list các items hoặc list rỗng
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during Google Custom Search (attempt {attempt + 1}/{max_retries}): {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during Google Custom Search (attempt {attempt + 1}/{max_retries}): {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Google Custom Search (attempt {attempt + 1}/{max_retries}): {e}")

        attempt += 1
        if attempt >= max_retries:
            logger.error("Max retries reached for Google Custom Search.")
            return [] # Trả về list rỗng nếu lỗi
        logger.info(f"Retrying Google Custom Search in {retry_delay} seconds...")
        time.sleep(retry_delay)
    return []

def youtube_search(query, api_key, part='snippet', type='video', num_results=5, max_retries=3, retry_delay=5):
    """Thực hiện tìm kiếm YouTube."""
    attempt = 0
    while attempt < max_retries:
        try:
            logger.info(f"Performing YouTube Search. Query: '{query}'. Attempt: {attempt + 1}")
            # service = get_google_service('youtube', 'v3', api_key) # Tương tự Google Search
            # request = service.search().list(
            #     q=query,
            #     part=part,
            #     type=type,
            #     maxResults=num_results
            # )
            # response = request.execute()
            # logger.info(f"YouTube Search successful. Found {len(response.get('items', []))} items.")
            # return response.get('items', [])

            # Hoặc dùng requests trực tiếp (như trong n8n node của bạn)
            params = {
                'key': api_key,
                'part': part,
                'q': query,
                'type': type,
                'maxResults': num_results
            }
            response = requests.get("https://www.googleapis.com/youtube/v3/search", params=params)
            response.raise_for_status()
            results = response.json()
            logger.info(f"YouTube Search successful. Found {len(results.get('items', []))} items.")
            return results.get('items', [])

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during YouTube Search (attempt {attempt + 1}/{max_retries}): {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during YouTube Search (attempt {attempt + 1}/{max_retries}): {e}")
        except Exception as e: # Bắt lỗi chung hơn nếu dùng googleapiclient
            logger.error(f"Error during YouTube Search (attempt {attempt + 1}/{max_retries}): {e}")

        attempt += 1
        if attempt >= max_retries:
            logger.error("Max retries reached for YouTube Search.")
            return []
        logger.info(f"Retrying YouTube Search in {retry_delay} seconds...")
        time.sleep(retry_delay)
    return []

# --- WordPress API Client Functions ---

def _wp_request(method, endpoint_url, auth_tuple, json_data=None, params=None, files=None, headers=None, max_retries=3, retry_delay=5):
    """Hàm helper chung cho các request tới WordPress API."""
    attempt = 0
    full_url = endpoint_url # endpoint_url đã bao gồm base_url
    
    # Headers mặc định
    default_headers = {
        'User-Agent': 'FretterVersePythonClient/1.0' # Nên có User-Agent
    }
    if headers:
        default_headers.update(headers)

    while attempt < max_retries:
        try:
            logger.debug(f"WordPress API Request ({method}). URL: {full_url}. Attempt: {attempt + 1}")
            if method.upper() == 'GET':
                response = requests.get(full_url, auth=auth_tuple, params=params, headers=default_headers)
            elif method.upper() == 'POST':
                response = requests.post(full_url, auth=auth_tuple, json=json_data, params=params, files=files, headers=default_headers)
            elif method.upper() == 'PUT':
                response = requests.put(full_url, auth=auth_tuple, json=json_data, params=params, headers=default_headers)
            else:
                logger.error(f"Unsupported HTTP method: {method}")
                return None

            logger.debug(f"WordPress API Response Status: {response.status_code}")
            response.raise_for_status() # Sẽ raise lỗi cho 4xx/5xx
            
            # Một số API (như upload media) có thể trả về 201 Created và không có JSON body
            # Hoặc trả về 200 OK với JSON body
            # Hoặc 204 No Content
            if response.status_code == 204:
                logger.info(f"WordPress API call to {full_url} successful with status 204 No Content.")
                return True # Hoặc một giá trị biểu thị thành công không có data
            
            # Kiểm tra content type trước khi parse JSON
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                data = response.json()
                logger.info(f"WordPress API call to {full_url} successful.")
                # logger.debug(f"Response JSON: {json.dumps(data, indent=2)}") # Có thể rất dài
                return data
            else:
                logger.info(f"WordPress API call to {full_url} successful. Non-JSON response: {response.text[:100]}...")
                return response.text # Hoặc response.content nếu là binary

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during WordPress API call ({method} {full_url}, attempt {attempt + 1}/{max_retries}): {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during WordPress API call ({method} {full_url}, attempt {attempt + 1}/{max_retries}): {e}")
        except Exception as e:
            logger.error(f"Unexpected error during WordPress API call ({method} {full_url}, attempt {attempt + 1}/{max_retries}): {e}")
        
        attempt += 1
        if attempt >= max_retries:
            logger.error(f"Max retries reached for WordPress API call: {method} {full_url}")
            return None
        logger.info(f"Retrying WordPress API call in {retry_delay} seconds...")
        time.sleep(retry_delay)
    return None


def get_wp_categories(base_url, auth_user, auth_pass, params=None):
    """Lấy danh sách categories từ WordPress."""
    endpoint = f"{base_url}/wp-json/wp/v2/categories"
    # Mặc định lấy nhiều categories (ví dụ per_page=100 để tránh paging phức tạp ban đầu)
    default_params = {'per_page': 100}
    if params:
        default_params.update(params)
    return _wp_request('GET', endpoint, (auth_user, auth_pass), params=default_params)

def create_wp_category(base_url, auth_user, auth_pass, name, parent_id=0, description=""):
    """Tạo một category mới trên WordPress."""
    endpoint = f"{base_url}/wp-json/wp/v2/categories"
    data = {
        "name": name,
        "description": description if description else name, # WP yêu cầu description
    }
    if parent_id and int(parent_id) > 0 : # Đảm bảo parent_id là số nguyên dương
        data["parent"] = int(parent_id)
    return _wp_request('POST', endpoint, (auth_user, auth_pass), json_data=data)

def upload_wp_media(base_url, auth_user, auth_pass, file_path_or_binary, filename, mime_type):
    """
    Upload file media lên WordPress.
    file_path_or_binary: Đường dẫn đến file hoặc đối tượng bytes của file.
    """
    endpoint = f"{base_url}/wp-json/wp/v2/media"
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': mime_type
    }
    
    if isinstance(file_path_or_binary, str): # Nếu là đường dẫn file
        with open(file_path_or_binary, 'rb') as f:
            files = {'file': (filename, f, mime_type)}
            # POST request với files sẽ tự xử lý data, không cần json_data
            return _wp_request('POST', endpoint, (auth_user, auth_pass), files=files, headers={'Content-Disposition': headers['Content-Disposition']}) # Chỉ cần Content-Disposition cho file upload
    else: # Nếu là binary data
        # Với requests, data phải là key 'file' trong một tuple
        # Hoặc truyền trực tiếp data=file_path_or_binary nếu API server hỗ trợ
        # files = {'file': (filename, file_path_or_binary, mime_type)} # Cách này thường dùng cho file object
        # Cách đơn giản hơn là truyền data trực tiếp
        return _wp_request('POST', endpoint, (auth_user, auth_pass), files={'file': (filename, file_path_or_binary, mime_type)}, headers={'Content-Disposition': headers['Content-Disposition']})


def create_wp_post(base_url, auth_user, auth_pass, title, content, slug, status, 
                   categories_ids, 
                   author_id, # Đây phải là SỐ NGUYÊN
                   excerpt, featured_media_id=None):
    """Tạo một bài viết mới trên WordPress."""
    endpoint = f"{base_url}/wp-json/wp/v2/posts"
    data = {
        "title": title,
        "content": content,
        "slug": slug,
        "status": status,
        "categories": categories_ids, # Phải là list các IDs, e.g., [1, 2]
        "author": int(author_id),
        "excerpt": excerpt
    }
    if featured_media_id:
        data["featured_media"] = featured_media_id
    return _wp_request('POST', endpoint, (auth_user, auth_pass), json_data=data)

def update_wp_post(base_url, auth_user, auth_pass, post_id, data_to_update):
    """
    Cập nhật một bài viết đã có trên WordPress.
    data_to_update: dict chứa các trường cần cập nhật, ví dụ:
                    {'excerpt': 'new excerpt', 'featured_media': 123}
    """
    endpoint = f"{base_url}/wp-json/wp/v2/posts/{post_id}"
    return _wp_request('PUT', endpoint, (auth_user, auth_pass), json_data=data_to_update) # Hoặc POST, tùy API docs

def get_wp_posts(base_url, auth_user, auth_pass, params=None):
    """Lấy danh sách bài viết từ WordPress."""
    endpoint = f"{base_url}/wp-json/wp/v2/posts"
    default_params = {'per_page': 10, '_fields': 'id,title,slug,link'} # Lấy ít trường cho nhẹ
    if params:
        default_params.update(params)
    return _wp_request('GET', endpoint, (auth_user, auth_pass), params=default_params)


# --- Example Usage (cần được gọi từ nơi có APP_CONFIG) ---
# if __name__ == "__main__":
#     # Load APP_CONFIG
#     # from utils.config_loader import APP_CONFIG # Giả sử APP_CONFIG đã được load
#     # setup_logging() # Gọi setup_logging
#
#     # Test OpenAI
#     # openai_api_key = APP_CONFIG.get('OPENAI_API_KEY')
#     # if openai_api_key:
#     #     chat_response = call_openai_chat([{"role": "user", "content": "Hello, what is 2+2?"}],
#     #                                      APP_CONFIG.get('DEFAULT_OPENAI_CHAT_MODEL'),
#     #                                      openai_api_key)
#     #     logger.info(f"OpenAI Chat Response: {chat_response}")
#
#     #     dalle_prompt = "A futuristic cityscape with flying cars, digital art"
#     #     dalle_url = call_openai_dalle(dalle_prompt, "1024x1024", openai_api_key)
#     #     logger.info(f"DALL-E Image URL: {dalle_url}")
#
#     #     embedding_text = "This is a test sentence for embeddings."
#     #     embedding_vector = call_openai_embeddings(embedding_text, APP_CONFIG.get('DEFAULT_OPENAI_EMBEDDINGS_MODEL'), openai_api_key)
#     #     logger.info(f"Embedding vector (first 5 dims): {embedding_vector[:5] if embedding_vector else 'N/A'}")
#
#     # Test Google Search
#     # google_api_key = APP_CONFIG.get('GOOGLE_API_KEY')
#     # google_cx_id = "YOUR_CUSTOM_SEARCH_ENGINE_ID" # Cần thay thế
#     # if google_api_key and google_cx_id:
#     #     search_results = google_search("best electric guitars 2024", google_api_key, google_cx_id, num_results=3)
#     #     logger.info(f"Google Search Results:")
#     #     for item in search_results:
#     #         logger.info(f"  - {item.get('title')}: {item.get('link')}")
#
#     # Test YouTube Search
#     # youtube_api_key = APP_CONFIG.get('YOUTUBE_API_KEY') # Hoặc GOOGLE_API_KEY
#     # if youtube_api_key:
#     #     video_results = youtube_search("learn python programming", youtube_api_key, num_results=2)
#     #     logger.info(f"YouTube Search Results:")
#     #     for item in video_results:
#     #         video_id = item.get('id', {}).get('videoId')
#     #         title = item.get('snippet', {}).get('title')
#     #         logger.info(f"  - {title}: https://www.youtube.com/watch?v={video_id}")
#
#     # Test WordPress
#     # wp_base = APP_CONFIG.get('WP_BASE_URL')
#     # wp_user = APP_CONFIG.get('WP_USER')
#     # wp_pass = APP_CONFIG.get('WP_PASSWORD')
#     # if wp_base and wp_user and wp_pass:
#     #     categories = get_wp_categories(wp_base, wp_user, wp_pass, params={'per_page': 5})
#     #     logger.info("WordPress Categories (first 5):")
#     #     if categories:
#     #         for cat in categories:
#     #             logger.info(f"  - ID: {cat['id']}, Name: {cat['name']}")
#         #
#         # # Test tạo category (cẩn thận khi chạy)
#         # new_cat_response = create_wp_category(wp_base, wp_user, wp_pass, "Test Category Python", description="A test category from Python.")
#         # if new_cat_response:
#         #     logger.info(f"New category created: {new_cat_response}")
#         #     new_cat_id = new_cat_response.get('id')
#
#             # Test đăng bài (cẩn thận khi chạy)
#             # post_data = {
#             #     "title": "My Test Post from Python",
#             #     "content": "<p>This is the content of my test post.</p>",
#             #     "slug": "my-test-post-python",
#             #     "status": "draft",
#             #     "categories_ids": [new_cat_id] if new_cat_id else [APP_CONFIG.get('DEFAULT_CATEGORY_ID')],
#             #     "author_id": APP_CONFIG.get('DEFAULT_AUTHOR_ID'),
#             #     "excerpt": "This is a short excerpt for the test post."
#             # }
#             # created_post = create_wp_post(wp_base, wp_user, wp_pass, **post_data)
#             # if created_post:
#             #     logger.info(f"New post created: {created_post.get('link')}")
#             #     post_id_to_update = created_post.get('id')
#                 # Test update post
#                 # updated_data = update_wp_post(wp_base, wp_user, wp_pass, post_id_to_update, {"title": "My Updated Test Post from Python"})
#                 # if updated_data:
#                 #     logger.info(f"Post updated: {updated_data.get('link')}")
#
#         # Test lấy danh sách posts
#         # posts = get_wp_posts(wp_base, wp_user, wp_pass, params={'per_page': 3})
#         # if posts:
#         #     logger.info("WordPress Posts (first 3):")
#         #     for p in posts:
#         #         logger.info(f"  - ID: {p['id']}, Title: {p['title']['rendered']}")