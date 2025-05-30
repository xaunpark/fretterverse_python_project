# i:\VS-Project\fretterverse_python_project\simple_gui.py
import streamlit as st
import subprocess
import os
import sys
import json
from datetime import datetime

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_PROFILES_DIR = os.path.join(PROJECT_ROOT, "site_profiles")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
SCHEDULER_STATE_FILE = os.path.join(PROJECT_ROOT, "scheduler_state.json")
MAIN_ORCHESTRATOR_SCRIPT = os.path.join(PROJECT_ROOT, "main_orchestrator.py")
DELETE_KEYWORDS_SCRIPT = os.path.join(PROJECT_ROOT, "delete_keywords_from_pinecone.py")
PYTHON_EXECUTABLE = sys.executable

# --- Initialize session state ---
if 'orchestrator_process' not in st.session_state:
    st.session_state.orchestrator_process = None
    st.session_state.orchestrator_stdout = None
    st.session_state.orchestrator_stderr = None
    st.session_state.orchestrator_site = None # To store which site is being processed

if 'delete_keywords_process' not in st.session_state:
    st.session_state.delete_keywords_process = None
    st.session_state.delete_keywords_stdout = None
    st.session_state.delete_keywords_stderr = None
    st.session_state.delete_keywords_site = None

if 'test_connections_process' not in st.session_state: # Added for test_connections
    st.session_state.test_connections_process = None
    st.session_state.test_connections_stdout = None
    st.session_state.test_connections_stderr = None
    st.session_state.test_connections_site = None

# --- Helper Functions ---
def discover_sites():
    """Discovers site names from the site_profiles directory."""
    sites = []
    if not os.path.isdir(SITE_PROFILES_DIR):
        st.error(f"Thư mục cấu hình site '{SITE_PROFILES_DIR}' không tìm thấy.")
        return sites
    for site_name in os.listdir(SITE_PROFILES_DIR):
        if os.path.isdir(os.path.join(SITE_PROFILES_DIR, site_name)):
            # Kiểm tra sự tồn tại của file cấu hình
            if os.path.exists(os.path.join(SITE_PROFILES_DIR, site_name, "site_config.json")) or \
               os.path.exists(os.path.join(SITE_PROFILES_DIR, site_name, ".env")):
                sites.append(site_name)
    return sites

def read_log_file(log_file_name, lines=100):
    """Reads the last N lines of a specified log file."""
    log_path = os.path.join(LOGS_DIR, log_file_name)
    if not os.path.exists(log_path):
        return f"File log '{log_file_name}' không tìm thấy trong '{LOGS_DIR}'."
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log_lines = f.readlines()
            return "".join(log_lines[-lines:])
    except Exception as e:
        return f"Lỗi khi đọc file log '{log_file_name}': {str(e)}"

def load_scheduler_state_for_gui():
    """Reads and formats the scheduler_state.json file for display."""
    if not os.path.exists(SCHEDULER_STATE_FILE):
        return "File trạng thái scheduler (scheduler_state.json) không tìm thấy."
    try:
        with open(SCHEDULER_STATE_FILE, 'r', encoding="utf-8") as f:
            state = json.load(f)
            formatted_state = "Trạng thái Scheduler:\n"
            if not state:
                formatted_state += "Không có dữ liệu trạng thái."
                return formatted_state
            for site, ts_str in state.items():
                try:
                    dt_obj = datetime.fromisoformat(ts_str)
                    # Hiển thị theo giờ địa phương nếu có thể (cần điều chỉnh timezone)
                    formatted_state += f"  - {site}: Lần chạy cuối lúc {dt_obj.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                except ValueError:
                    formatted_state += f"  - {site}: Lần chạy cuối lúc {ts_str} (timestamp thô)\n"
            return formatted_state
    except Exception as e:
        return f"Lỗi khi tải trạng thái scheduler: {str(e)}"

# --- Streamlit App UI ---
st.set_page_config(layout="wide", page_title="Project GUI")
st.title("GUI Điều Khiển Project")

available_sites = discover_sites()
if not available_sites:
    st.warning("Không tìm thấy cấu hình site nào. Vui lòng kiểm tra thư mục `site_profiles`.")

# Section 1: Run Orchestrator
st.header("Chạy Orchestrator Tạo Bài Viết")
selected_site_orchestrator_ui = st.selectbox(
    "Chọn Site cho Orchestrator:",
    available_sites if available_sites else ["Không có site nào"],
    key="orchestrator_site_select",
    disabled=not available_sites or st.session_state.orchestrator_process is not None
)

if st.button("Chạy Orchestrator", key="run_orchestrator_button", disabled=not available_sites or st.session_state.orchestrator_process is not None):
    if selected_site_orchestrator_ui and selected_site_orchestrator_ui != "Không có site nào":
        st.session_state.orchestrator_site = selected_site_orchestrator_ui
        st.session_state.orchestrator_stdout = None
        st.session_state.orchestrator_stderr = None
        command = [PYTHON_EXECUTABLE, MAIN_ORCHESTRATOR_SCRIPT, "--site", st.session_state.orchestrator_site]
        st.session_state.orchestrator_process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=PROJECT_ROOT, encoding='utf-8'
        )
        st.rerun()
    else:
        st.warning("Vui lòng chọn một site hợp lệ.")

if st.session_state.orchestrator_process:
    if st.session_state.orchestrator_process.poll() is None:
        st.info(f"Orchestrator cho site '{st.session_state.orchestrator_site}' đang chạy... Vui lòng chờ hoặc thực hiện tác vụ khác.")
        # Để GUI tự động cập nhật trạng thái, bạn có thể thêm một vòng lặp ngắn với sleep và rerun,
        # nhưng điều này có thể làm nặng GUI. Một nút refresh thủ công có thể tốt hơn.
        if st.button("Làm mới trạng thái Orchestrator"):
            st.rerun()
    else:
        # Process finished
        stdout, stderr = st.session_state.orchestrator_process.communicate()
        st.session_state.orchestrator_stdout = stdout
        st.session_state.orchestrator_stderr = stderr
        if st.session_state.orchestrator_process.returncode == 0:
            st.success(f"Orchestrator cho site '{st.session_state.orchestrator_site}' đã hoàn thành thành công.")
        else:
            st.error(f"Orchestrator cho site '{st.session_state.orchestrator_site}' đã thất bại.")
        st.session_state.orchestrator_process = None # Clear the process
        st.rerun() # Rerun to update button state and display output

if st.session_state.orchestrator_stdout:
    st.subheader(f"Kết quả Orchestrator (stdout) cho '{st.session_state.orchestrator_site}':")
    st.text_area("Orchestrator Output Display", value=st.session_state.orchestrator_stdout, height=250, key="orch_stdout_display_area")
if st.session_state.orchestrator_stderr:
    st.subheader(f"Lỗi Orchestrator (stderr) cho '{st.session_state.orchestrator_site}':")
    st.text_area("Orchestrator Error Display", value=st.session_state.orchestrator_stderr, height=200, key="orch_stderr_display_area")


# Section 2: Run Keyword Deletion
st.header("Chạy Xóa Keyword khỏi Pinecone")
selected_site_delete_ui = st.selectbox(
    "Chọn Site để Xóa Keyword:",
    available_sites if available_sites else ["Không có site nào"],
    key="delete_site_select",
    disabled=not available_sites or st.session_state.delete_keywords_process is not None
)
confirm_delete = st.checkbox(
    "Tôi hiểu rằng hành động này sẽ xóa keywords khỏi Pinecone cho site đã chọn, dựa trên sheet 'Delete' trong Google Sheets.",
    key="confirm_delete_checkbox",
    disabled=st.session_state.delete_keywords_process is not None
)

if st.button("Chạy Script Xóa Keyword", key="run_delete_button", disabled=not available_sites or not confirm_delete or st.session_state.delete_keywords_process is not None):
    if selected_site_delete_ui and selected_site_delete_ui != "Không có site nào":
        st.session_state.delete_keywords_site = selected_site_delete_ui
        st.session_state.delete_keywords_stdout = None
        st.session_state.delete_keywords_stderr = None
        command = [PYTHON_EXECUTABLE, DELETE_KEYWORDS_SCRIPT, st.session_state.delete_keywords_site, "--yes"]
        st.session_state.delete_keywords_process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=PROJECT_ROOT, encoding='utf-8'
        )
        st.rerun()
    else:
        st.warning("Vui lòng chọn một site hợp lệ.")

if st.session_state.delete_keywords_process:
    if st.session_state.delete_keywords_process.poll() is None:
        st.info(f"Script xóa keyword cho site '{st.session_state.delete_keywords_site}' đang chạy...")
        if st.button("Làm mới trạng thái Xóa Keyword"):
            st.rerun()
    else:
        stdout, stderr = st.session_state.delete_keywords_process.communicate()
        st.session_state.delete_keywords_stdout = stdout
        st.session_state.delete_keywords_stderr = stderr
        if st.session_state.delete_keywords_process.returncode == 0:
            st.success(f"Script xóa keyword cho site '{st.session_state.delete_keywords_site}' đã hoàn thành.")
        else:
            st.error(f"Script xóa keyword cho site '{st.session_state.delete_keywords_site}' đã thất bại.")
        st.session_state.delete_keywords_process = None
        st.rerun()

if st.session_state.delete_keywords_stdout:
    st.subheader(f"Kết quả Xóa Keyword (stdout) cho '{st.session_state.delete_keywords_site}':")
    st.text_area("Deletion Output Display", value=st.session_state.delete_keywords_stdout, height=200, key="del_stdout_display_area")
if st.session_state.delete_keywords_stderr:
    st.subheader(f"Lỗi Xóa Keyword (stderr) cho '{st.session_state.delete_keywords_site}':")
    st.text_area("Deletion Error Display", value=st.session_state.delete_keywords_stderr, height=200, key="del_stderr_display_area")


# Section 3: View Scheduler Status
st.header("Trạng Thái Scheduler")
if st.button("Tải Trạng Thái Scheduler", key="load_scheduler_state_button"):
    state_info = load_scheduler_state_for_gui()
    st.text_area("Thông tin Trạng thái Scheduler", value=state_info, height=200, key="scheduler_state_display_area")

# Section 4: View Logs
st.header("Xem Logs")
log_files_list = []
if os.path.isdir(LOGS_DIR):
    log_files_list = [f for f in os.listdir(LOGS_DIR) if os.path.isfile(os.path.join(LOGS_DIR, f)) and f.endswith(".log")]

if log_files_list:
    selected_log_file = st.selectbox("Chọn File Log:", sorted(log_files_list, reverse=True), key="log_file_select_box") # Sắp xếp cho dễ tìm
    lines_to_show = st.number_input("Số dòng cuối muốn xem:", min_value=10, max_value=1000, value=100, step=10, key="log_lines_number_input")
    if st.button("Xem Log", key="view_log_button"):
        if selected_log_file:
            log_content = read_log_file(selected_log_file, lines_to_show)
            st.text_area(f"Nội dung Log: {selected_log_file}", value=log_content, height=400, key="log_display_text_area")
else:
    st.info(f"Không tìm thấy file log nào trong thư mục '{LOGS_DIR}'.")

st.markdown("---")
st.caption("GUI được tạo bằng Streamlit cho FretterVerse Python Project")
