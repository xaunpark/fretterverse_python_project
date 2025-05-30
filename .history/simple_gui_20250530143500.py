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

def run_script(script_path, site_name_as_arg=None, site_name_as_option=None, extra_args=None):
    """
    Executes a Python script using subprocess and captures its output.
    Returns: (success_bool, stdout_str, stderr_str)
    """
    command = [PYTHON_EXECUTABLE, script_path]
    if site_name_as_arg: # For scripts that take site name as a positional argument
        command.append(site_name_as_arg)
    if site_name_as_option: # For scripts that take --site <name>
        command.extend(["--site", site_name_as_option])

    if extra_args:
        command.extend(extra_args)

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PROJECT_ROOT, # Chạy script từ thư mục gốc của dự án
            encoding='utf-8'  # Đảm bảo xử lý encoding đúng cách
        )
        stdout, stderr = process.communicate(timeout=600) # Thêm timeout (ví dụ 10 phút)
        success = process.returncode == 0
        return success, stdout, stderr
    except subprocess.TimeoutExpired:
        return False, "", "Lỗi: Script chạy quá thời gian cho phép (timeout)."
    except Exception as e:
        return False, "", f"Lỗi khi chạy script: {str(e)}"

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
if available_sites:
    selected_site_orchestrator = st.selectbox("Chọn Site cho Orchestrator:", available_sites, key="orchestrator_site_select")
    if st.button("Chạy Orchestrator", key="run_orchestrator_button"):
        if selected_site_orchestrator:
            with st.spinner(f"Đang chạy orchestrator cho {selected_site_orchestrator}... Vui lòng chờ."):
                success, stdout, stderr = run_script(MAIN_ORCHESTRATOR_SCRIPT, site_name_as_option=selected_site_orchestrator)
            
            if success:
                st.success(f"Orchestrator cho {selected_site_orchestrator} hoàn thành thành công.")
                if stdout:
                    st.subheader("Kết quả (stdout):")
                    st.text_area("Orchestrator Output", value=stdout, height=250, key="orch_stdout_text_area")
            else:
                st.error(f"Orchestrator cho {selected_site_orchestrator} thất bại.")
                if stderr:
                    st.subheader("Lỗi (stderr):")
                    st.text_area("Orchestrator Error", value=stderr, height=200, key="orch_stderr_text_area")
                if stdout:
                    st.subheader("Kết quả (stdout) khi có lỗi:")
                    st.text_area("Orchestrator Output (on error)", value=stdout, height=150, key="orch_stdout_fail_text_area")
        else:
            st.warning("Vui lòng chọn một site.")
else:
    st.info("Không có site nào để chạy orchestrator.")

# Section 2: Run Keyword Deletion
st.header("Chạy Xóa Keyword khỏi Pinecone")
if available_sites:
    selected_site_delete = st.selectbox("Chọn Site để Xóa Keyword:", available_sites, key="delete_site_select")
    confirm_delete = st.checkbox("Tôi hiểu rằng hành động này sẽ xóa keywords khỏi Pinecone cho site đã chọn, dựa trên sheet 'Delete' trong Google Sheets.", key="confirm_delete_checkbox")

    if st.button("Chạy Script Xóa Keyword", key="run_delete_button", disabled=not confirm_delete):
        if selected_site_delete and confirm_delete:
            with st.spinner(f"Đang chạy script xóa keyword cho {selected_site_delete}..."):
                # Script delete_keywords_from_pinecone.py đã được sửa để chấp nhận tham số --yes
                # và site_profile là tham số vị trí.
                success, stdout, stderr = run_script(DELETE_KEYWORDS_SCRIPT, site_name_as_arg=selected_site_delete, extra_args=["--yes"])
            
            if success:
                st.success(f"Script xóa keyword cho {selected_site_delete} hoàn thành.")
                if stdout:
                    st.subheader("Kết quả (stdout):")
                    st.text_area("Deletion Output", value=stdout, height=200, key="del_stdout_text_area")
            else:
                st.error(f"Script xóa keyword cho {selected_site_delete} thất bại.")
                if stderr:
                    st.subheader("Lỗi (stderr):")
                    st.text_area("Deletion Error", value=stderr, height=200, key="del_stderr_text_area")
                if stdout:
                    st.subheader("Kết quả (stdout) khi có lỗi:")
                    st.text_area("Deletion Output (on error)", value=stdout, height=150, key="del_stdout_fail_text_area")
        elif not confirm_delete:
            st.warning("Vui lòng xác nhận hành động xóa bằng cách tick vào ô checkbox.")
        else:
            st.warning("Vui lòng chọn một site.")
else:
    st.info("Không có site nào để chạy script xóa keyword.")

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
