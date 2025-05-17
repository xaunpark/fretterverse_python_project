# utils/api_clients.py
import requests
import time
import json
import logging
from openai import OpenAI # Thư viện OpenAI chính thức
from googleapiclient.discovery import build # Thư viện Google API
# Giả sử APP_CONFIG được load từ một module config_loader
# from utils.config_loader import APP_CONFIG
# Hoặc bạn có thể truyền config vào từng hàm/class

# Khởi tạo logger
logger = logging.getLogger(__name__)

# --- OpenAI Client Functions ---

# Nên khởi tạo OpenAI client một lần và tái sử dụng nếu có thể
# Tuy nhiên, để đơn giản, chúng ta có thể khởi tạo trong hàm hoặc truyền vào
# openai_client = OpenAI(api_key=APP_CONFIG.get('OPENAI_API_KEY'))

def get_openai_client(api_key):
    """Helper function to get an OpenAI client instance."""
    if not api_key:
        logger.error("OpenAI API key is not configured.")
        raise ValueError("OpenAI API key is missing.")
    return OpenAI(api_key=api_key)

def call_openai_chat(prompt_messages, 
                     model_name, 
                     api_key, # Đây là OpenAI API key gốc, dùng khi target_api="openai"
                     is_json_output=False, 
                     max_retries=3, 
                     retry_delay=5,
                     target_api="openai", # "openai" hoặc "openrouter"
                     openrouter_api_key=None,
                     openrouter_base_url=None):
    """
    Gửi request đến API chat của OpenAI hoặc OpenRouter.
    prompt_messages: list of message objects, e.g., [{"role": "user", "content": "Hello"}]
    is_json_output: Nếu True, yêu cầu OpenAI trả về JSON và cố gắng parse.
    target_api: "openai" để gọi trực tiếp OpenAI, "openrouter" để gọi qua OpenRouter.
    openrouter_api_key: API key cho OpenRouter (chỉ dùng khi target_api="openrouter").
    openrouter_base_url: Base URL cho OpenRouter (chỉ dùng khi target_api="openrouter").
    """
    attempt = 0
    client = None

    if target_api == "openrouter":
        if not openrouter_api_key or not openrouter_base_url:
            logger.error("OpenRouter API key or base URL is missing for target_api='openrouter'.")
            return None
        client = OpenAI(api_key=openrouter_api_key, base_url=openrouter_base_url)
    else: # Mặc định hoặc target_api == "openai"
        client = get_openai_client(api_key) # Sử dụng OpenAI API key gốc

    if not client: # Nếu client vẫn là None (ví dụ do thiếu key cho OpenRouter)
        return None

    while attempt < max_retries:
        try:
            logger.info(f"Calling LLM API ({target_api}). Model: {model_name}. JSON output: {is_json_output}. Attempt: {attempt + 1}")
            # logger.debug(f"Prompt messages: {prompt_messages}") # Có thể quá dài để log

            request_params = {
                "model": model_name,
                "messages": prompt_messages
            }
            if is_json_output:
                request_params["response_format"] = {"type": "json_object"}
            
            response = client.chat.completions.create(**request_params)

            content = response.choices[0].message.content
            logger.info(f"LLM API ({target_api}) call successful.")

            if is_json_output:
                try:
                    parsed_json = json.loads(content)
                    logger.debug("Successfully parsed JSON response from LLM.")
                    return parsed_json
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response from LLM ({target_api}): {e}. Raw content: {content}")
                    if attempt + 1 >= max_retries:
                        logger.warning("Max retries reached for JSON parsing. Returning error dict.")
                        return {"error": "JSONDecodeError", "raw_content": content, "message": f"Failed to parse JSON after {max_retries} attempts."}
                    # Fall through to retry logic
            else:
                return content # Trả về string nếu không yêu cầu JSON

        except Exception as e:
            logger.error(f"Error calling LLM API ({target_api}) (attempt {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            if attempt >= max_retries:
                logger.error(f"Max retries reached for LLM API ({target_api}) call. Returning None.")
                return None 
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    return None

def call_openai_dalle(prompt, size, api_key, model="dall-e-3", n=1, max_retries=3, retry_delay=5):
    """Tạo ảnh với DALL-E."""
    client = get_openai_client(api_key)
    attempt = 0
    while attempt < max_retries:
        try:
            logger.info(f"Calling OpenAI DALL-E API. Model: {model}. Prompt: '{prompt[:50]}...'. Attempt: {attempt + 1}")
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                n=n,
                response_format="url" # Hoặc "b64_json" nếu muốn lấy base64
            )
            image_url = response.data[0].url # Giả sử n=1
            logger.info(f"OpenAI DALL-E API call successful. Image URL: {image_url}")
            return image_url
        except Exception as e:
            logger.error(f"Error calling OpenAI DALL-E API (attempt {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            if attempt >= max_retries:
                logger.error("Max retries reached for DALL-E API call.")
                return None
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    return None

def call_openai_embeddings(text_input, model_name, api_key, max_retries=3, retry_delay=5):
    """Lấy embeddings từ OpenAI."""
    client = get_openai_client(api_key)
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
        except Exception as e:
            logger.error(f"Error calling OpenAI Embeddings API (attempt {attempt + 1}/{max_retries}): {e}")
            attempt += 1
            if attempt >= max_retries:
                logger.error("Max retries reached for Embeddings API call.")
                return None
            logger.info(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
    return None

# --- Google API Client Functions (Legacy and YouTube) ---

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
    Thực hiện tìm kiếm Google Custom Search và chuẩn hóa kết quả.
    search_type: 'web' hoặc 'image'.
    cx_id: Custom Search Engine ID.
    **kwargs: Các tham số bổ sung như imgSize, gl, hl.
    Trả về list các dict theo định dạng chuẩn.
    """
    attempt = 0
    standardized_results = []
    while attempt < max_retries:
        try:
            logger.info(f"Performing Google Custom Search. Query: '{query}'. Type: {search_type}. CX_ID: {cx_id}. Attempt: {attempt + 1}")
            
            params = {
                'key': api_key,
                'cx': cx_id,
                'q': query,
                'num': num_results
            }
            if search_type == 'image':
                params['searchType'] = 'image'
                if 'imgSize' in kwargs: # Chuyển imgSize từ kwargs vào params
                    params['imgSize'] = kwargs.pop('imgSize')
            
            params.update(kwargs) # Thêm các tham số tùy chọn khác (gl, hl, etc.)

            response = requests.get("https://www.googleapis.com/customsearch/v1", params=params)
            response.raise_for_status() 
            
            results_json = response.json()
            raw_items = results_json.get('items', [])
            logger.info(f"Google Custom Search successful. Found {len(raw_items)} raw items.")

            for item in raw_items:
                if search_type == 'web':
                    standardized_results.append({
                        'title': item.get('title'),
                        'link': item.get('link'),
                        'snippet': item.get('snippet'),
                        'source': 'google'
                    })
                elif search_type == 'image':
                    standardized_results.append({
                        'title': item.get('title'),
                        'link': item.get('link'), # URL trực tiếp của ảnh
                        'imageUrl': item.get('link'), # Alias cho link ảnh
                        'sourceUrl': item.get('image', {}).get('contextLink'), # URL trang chứa ảnh
                        'snippet': item.get('snippet'), # Mô tả ngắn của ảnh
                        'source': 'google'
                    })
            return standardized_results # Trả về ngay khi thành công
        
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during Google Custom Search (attempt {attempt + 1}/{max_retries}): {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during Google Custom Search (attempt {attempt + 1}/{max_retries}): {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Google Custom Search (attempt {attempt + 1}/{max_retries}): {e}")

        attempt += 1
        if attempt >= max_retries:
            logger.error("Max retries reached for Google Custom Search.")
            return [] 
        logger.info(f"Retrying Google Custom Search in {retry_delay} seconds...")
        time.sleep(retry_delay)
    return []

def youtube_search(query, api_key, part='snippet', type='video', num_results=5, max_retries=3, retry_delay=5):
    """Thực hiện tìm kiếm YouTube. (Hàm này giữ nguyên, không cần chuẩn hóa đặc biệt vì nó dùng cho mục đích khác)"""
    attempt = 0
    while attempt < max_retries:
        try:
            logger.info(f"Performing YouTube Search. Query: '{query}'. Attempt: {attempt + 1}")
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
        except Exception as e: 
            logger.error(f"Error during YouTube Search (attempt {attempt + 1}/{max_retries}): {e}")

        attempt += 1
        if attempt >= max_retries:
            logger.error("Max retries reached for YouTube Search.")
            return []
        logger.info(f"Retrying YouTube Search in {retry_delay} seconds...")
        time.sleep(retry_delay)
    return []

# --- Serper API Client Function ---
def call_serper_search(query, api_key, serper_base_url, num_results=10, search_type='search', max_retries=3, retry_delay=5, **kwargs):
    """
    Thực hiện tìm kiếm qua Serper.dev API và chuẩn hóa kết quả.
    search_type: 'search' (web), 'images', 'news', 'videos'.
    **kwargs: Các tham số bổ sung như gl, hl.
    Trả về list các dict theo định dạng chuẩn.
    """
    attempt = 0
    standardized_results = []
    
    # Serper API endpoint là /search cho web, /images cho ảnh, etc.
    # search_type của Serper khác với search_type chúng ta dùng ('web', 'image')
    serper_endpoint_map = {
        'web': '/search',
        'image': '/images',
        # 'video': '/videos', # Thêm nếu cần
        # 'news': '/news'     # Thêm nếu cần
    }
    endpoint = serper_endpoint_map.get(search_type)
    if not endpoint:
        logger.error(f"Unsupported search_type '{search_type}' for Serper. Use 'web' or 'image'.")
        return []

    url = f"{serper_base_url}{endpoint}"
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    payload = {
        'q': query,
        'num': num_results
    }
    # Thêm các tham số tùy chọn từ kwargs vào payload
    if 'gl' in kwargs: payload['gl'] = kwargs['gl']
    if 'hl' in kwargs: payload['hl'] = kwargs['hl']
    # Serper không có imgSize trực tiếp, nhưng có thể có các tham số khác cho 'images' type
    # if search_type == 'image' and 'imgSize' in kwargs:
    #     # payload['size'] = map_google_imgsize_to_serper(kwargs['imgSize']) # Cần hàm map nếu Serper có
    #     logger.warning("Serper image search does not directly support 'imgSize' like Google. This parameter will be ignored for Serper.")


    while attempt < max_retries:
        try:
            logger.info(f"Performing Serper Search. Query: '{query}'. Type: {search_type} (Endpoint: {endpoint}). URL: {url}. Attempt: {attempt + 1}")
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            
            results_json = response.json()
            
            if search_type == 'web':
                raw_items = results_json.get('organic', [])
                logger.info(f"Serper Web Search successful. Found {len(raw_items)} raw items.")
                for item in raw_items:
                    standardized_results.append({
                        'title': item.get('title'),
                        'link': item.get('link'),
                        'snippet': item.get('snippet'),
                        'source': 'serper'
                    })
            elif search_type == 'image':
                raw_items = results_json.get('images', [])
                logger.info(f"Serper Image Search successful. Found {len(raw_items)} raw items.")
                for item in raw_items:
                    standardized_results.append({
                        'title': item.get('title'),
                        'link': item.get('imageUrl'), # Serper trả về imageUrl là link trực tiếp ảnh
                        'imageUrl': item.get('imageUrl'),
                        'sourceUrl': item.get('link'), # Serper trả về link là trang chứa ảnh
                        'snippet': item.get('title'), # Serper không có snippet riêng cho ảnh, dùng title
                        'source': 'serper'
                    })
            return standardized_results # Trả về ngay khi thành công

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error during Serper Search (attempt {attempt + 1}/{max_retries}): {e.response.status_code} - {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error during Serper Search (attempt {attempt + 1}/{max_retries}): {e}")
        except Exception as e:
            logger.error(f"Unexpected error during Serper Search (attempt {attempt + 1}/{max_retries}): {e}")

        attempt += 1
        if attempt >= max_retries:
            logger.error("Max retries reached for Serper Search.")
            return []
        logger.info(f"Retrying Serper Search in {retry_delay} seconds...")
        time.sleep(retry_delay)
    return []

# --- Unified Search Function ---
def perform_search(query, search_type, config, num_results=10, **kwargs):
    """
    Hàm điều phối tìm kiếm, gọi Google hoặc Serper dựa trên cấu hình.
    search_type: 'web' hoặc 'image'.
    config: Đối tượng config chứa SEARCH_PROVIDER và các API keys.
    **kwargs: Các tham số bổ sung như gl, hl, imgSize.
    """
    provider = config.get('SEARCH_PROVIDER', 'google').lower()
    logger.info(f"Performing search via provider: '{provider}' for type: '{search_type}'")

    # QUAN TRỌNG: Xử lý tìm kiếm ảnh
    # Hiện tại, Serper không có tham số imgSize rõ ràng như Google.
    # Để đảm bảo chất lượng ảnh (ví dụ: imgSize="large"), nếu search_type là 'image',
    # chúng ta sẽ ưu tiên dùng Google nếu có thể, hoặc chấp nhận hạn chế của Serper.
    # Quyết định: Nếu search_type là 'image', LUÔN DÙNG GOOGLE để có imgSize.
    if search_type == 'image':
        if provider == 'serper':
            logger.warning(f"Search provider is '{provider}' but search_type is 'image'. "
                           f"Forcing Google Search for better image filtering (e.g., imgSize).")
        # Luôn dùng Google cho tìm kiếm ảnh
        google_api_key = config.get('GOOGLE_API_KEY')
        google_cx_id = config.get('GOOGLE_CX_ID')
        if not google_api_key or not google_cx_id:
            logger.error("Google API key or CX_ID missing. Cannot perform image search via Google.")
            return []
        return google_search(query, google_api_key, google_cx_id, 
                             search_type='image', num_results=num_results, **kwargs)

    # Xử lý tìm kiếm web
    if provider == 'serper':
        serper_api_key = config.get('SERPER_API_KEY')
        serper_base_url = config.get('SERPER_BASE_URL')
        if not serper_api_key or not serper_base_url:
            logger.error("Serper API key or base URL missing. Cannot perform search via Serper.")
            return []
        return call_serper_search(query, serper_api_key, serper_base_url, 
                                  num_results=num_results, search_type='web', **kwargs)
    elif provider == 'google':
        google_api_key = config.get('GOOGLE_API_KEY')
        google_cx_id = config.get('GOOGLE_CX_ID')
        if not google_api_key or not google_cx_id:
            logger.error("Google API key or CX_ID missing. Cannot perform search via Google.")
            return []
        return google_search(query, google_api_key, google_cx_id, 
                             search_type='web', num_results=num_results, **kwargs)
    else:
        logger.error(f"Unsupported search provider: {provider}. Please use 'google' or 'serper'.")
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
            
            if response.status_code == 204:
                logger.info(f"WordPress API call to {full_url} successful with status 204 No Content.")
                return True 
            
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' in content_type:
                data = response.json()
                logger.info(f"WordPress API call to {full_url} successful.")
                return data
            else:
                logger.info(f"WordPress API call to {full_url} successful. Non-JSON response: {response.text[:100]}...")
                return response.text 

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
    default_params = {'per_page': 100}
    if params:
        default_params.update(params)
    return _wp_request('GET', endpoint, (auth_user, auth_pass), params=default_params)

def create_wp_category(base_url, auth_user, auth_pass, name, parent_id=0, description=""):
    """Tạo một category mới trên WordPress."""
    endpoint = f"{base_url}/wp-json/wp/v2/categories"
    data = {
        "name": name,
        "description": description if description else name, 
    }
    if parent_id and int(parent_id) > 0 : 
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
        # 'Content-Type': mime_type # Sẽ được requests.post tự đặt khi dùng `files`
    }
    
    if isinstance(file_path_or_binary, str): 
        with open(file_path_or_binary, 'rb') as f:
            files_data = {'file': (filename, f, mime_type)}
            return _wp_request('POST', endpoint, (auth_user, auth_pass), files=files_data, headers=headers)
    else: 
        files_data = {'file': (filename, file_path_or_binary, mime_type)}
        return _wp_request('POST', endpoint, (auth_user, auth_pass), files=files_data, headers=headers)


def create_wp_post(base_url, auth_user, auth_pass, title, content, slug, status, 
                   categories_ids, 
                   author_id, 
                   excerpt, featured_media_id=None):
    """Tạo một bài viết mới trên WordPress."""
    endpoint = f"{base_url}/wp-json/wp/v2/posts"
    data = {
        "title": title,
        "content": content,
        "slug": slug,
        "status": status,
        "categories": categories_ids, 
        "author": int(author_id),
        "excerpt": excerpt
    }
    if featured_media_id:
        data["featured_media"] = featured_media_id
    return _wp_request('POST', endpoint, (auth_user, auth_pass), json_data=data)

def update_wp_post(base_url, auth_user, auth_pass, post_id, data_to_update):
    """
    Cập nhật một bài viết đã có trên WordPress.
    """
    endpoint = f"{base_url}/wp-json/wp/v2/posts/{post_id}"
    return _wp_request('POST', endpoint, (auth_user, auth_pass), json_data=data_to_update) # WP API dùng POST cho update

def get_wp_posts(base_url, auth_user, auth_pass, params=None):
    """Lấy danh sách bài viết từ WordPress."""
    endpoint = f"{base_url}/wp-json/wp/v2/posts"
    default_params = {'per_page': 10, '_fields': 'id,title,slug,link'} 
    if params:
        default_params.update(params)
    return _wp_request('GET', endpoint, (auth_user, auth_pass), params=default_params)