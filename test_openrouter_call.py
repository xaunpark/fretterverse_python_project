import os
import requests
import json
from dotenv import load_dotenv

# Xác định đường dẫn đến thư mục chứa script này
script_dir = os.path.dirname(os.path.abspath(__file__))
# Xây dựng đường dẫn đến tệp .env trong thư mục config
dotenv_path = os.path.join(script_dir, 'config', '.env')

# Tải các biến môi trường từ tệp .env được chỉ định
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f"Cảnh báo: Không tìm thấy tệp .env tại {dotenv_path}. Đảm bảo bạn đã tạo tệp này.")
    print("Đang thử tải OPENROUTER_API_KEY từ biến môi trường hệ thống (nếu có).")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"

# Các thông tin tùy chọn, bạn có thể thay thế nếu cần
YOUR_SITE_URL = "http://localhost:3000" # Hoặc URL ứng dụng của bạn
YOUR_APP_NAME = "My OpenRouter Test App" # Hoặc tên ứng dụng của bạn

def test_openrouter_call():
    """
    Thực hiện một cuộc gọi thử nghiệm đến API OpenRouter,
    tải API key từ config/.env.
    """
    if not OPENROUTER_API_KEY:
        print("Lỗi: Biến môi trường OPENROUTER_API_KEY chưa được đặt hoặc không thể tải từ config/.env.")
        print(f"Vui lòng kiểm tra tệp {dotenv_path} hoặc đặt biến môi trường hệ thống.")
        return

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # Các header tùy chọn nhưng được khuyến nghị để OpenRouter theo dõi và hỗ trợ tốt hơn:
        # "HTTP-Referer": YOUR_SITE_URL,
        # "X-Title": YOUR_APP_NAME,
    }

    data = {
        "model": "mistralai/mistral-7b-instruct", # Bạn có thể thay đổi model này
        "messages": [
            {"role": "user", "content": "What is the capital of France? Respond in one word."}
        ]
    }

    print(f"Đang gửi yêu cầu đến OpenRouter với model: {data['model']}...")

    try:
        response = requests.post(
            f"{OPENROUTER_API_BASE}/chat/completions",
            headers=headers,
            data=json.dumps(data),
            timeout=30 # Thời gian chờ (giây)
        )
        response.raise_for_status()  # Ném lỗi nếu mã trạng thái HTTP là 4xx/5xx

        print("Yêu cầu thành công!")
        response_data = response.json()
        print("Phản hồi từ OpenRouter:")
        print(json.dumps(response_data, indent=2))

    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi gọi API OpenRouter: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Chi tiết lỗi từ server (mã trạng thái {e.response.status_code}): {e.response.text}")

if __name__ == "__main__":
    test_openrouter_call()