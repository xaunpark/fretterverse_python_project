# simple_gui.py (Đặt ở thư mục gốc của project)
import streamlit as st
import subprocess
import os
import sys
import json
from datetime import datetime
import time # Để chờ scheduler dừng
try:
    import psutil # Để kiểm tra process
except ImportError:
    st.error("Vui lòng cài đặt thư viện 'psutil': pip install psutil")
    st.stop()


# --- Configuration ---
# Giả định simple_gui.py nằm ở thư mục gốc của project
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

SITE_PROFILES_DIR = os.path.join(PROJECT_ROOT, "site_profiles")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
SCHEDULER_STATE_FILE = os.path.join(PROJECT_ROOT, "scheduler_state.json")
MAIN_ORCHESTRATOR_SCRIPT = os.path.join(PROJECT_ROOT, "main_orchestrator.py")
SCHEDULER_SCRIPT = os.path.join(PROJECT_ROOT, "scheduler.py") # Thêm đường dẫn scheduler
DELETE_KEYWORDS_SCRIPT = os.path.join(PROJECT_ROOT, "delete_keywords_from_pinecone.py")
PYTHON_EXECUTABLE = sys.executable

# Files dùng để điều khiển scheduler
SCHEDULER_PID_FILE = os.path.join(PROJECT_ROOT, "scheduler.pid")
SCHEDULER_STOP_REQUEST_FILE = os.path.join(PROJECT_ROOT, "scheduler.stop_request")

# --- Helper Functions ---
def discover_sites():
    """Discovers site names from the site_profiles directory."""
    sites = []
    if not os.path.isdir(SITE_PROFILES_DIR):
        st.error(f"Thư mục cấu hình site '{SITE_PROFILES_DIR}' không tìm thấy.")
        return sites
    for site_name in os.listdir(SITE_PROFILES_DIR):
        if os.path.isdir(os.path.join(SITE_PROFILES_DIR, site_name)):
            if os.path.exists(os.path.join(SITE_PROFILES_DIR, site_name, "site_config.json")) or \
               os.path.exists(os.path.join(SITE_PROFILES_DIR, site_name, ".env")):
                sites.append(site_name)
    return sites

def run_script(script_path, site_name_as_arg=None, site_name_as_option=None, extra_args=None, wait_for_completion=True):
    """
    Executes a Python script using subprocess.
    If wait_for_completion is True, captures its output.
    If wait_for_completion is False, runs in background and returns the Popen object.
    Returns: (success_bool, stdout_str, stderr_str) OR Popen object
    """
    command = [PYTHON_EXECUTABLE, script_path]
    if site_name_as_arg:
        command.append(site_name_as_arg)
    if site_name_as_option:
        command.extend(["--site", site_name_as_option])
    if extra_args:
        command.extend(extra_args)

    try:
        if wait_for_completion:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=PROJECT_ROOT,
                encoding='utf-8'
            )
            stdout, stderr = process.communicate(timeout=600) # 10 phút timeout
            success = process.returncode == 0
            return success, stdout, stderr
        else: # Chạy nền
            process = subprocess.Popen(command, cwd=PROJECT_ROOT)
            return process # Trả về Popen object để có thể lấy PID nếu cần
    except subprocess.TimeoutExpired:
        return False, "", "Lỗi: Script chạy quá thời gian cho phép (timeout)."
    except Exception as e:
        if wait_for_completion:
            return False, "", f"Lỗi khi chạy script: {str(e)}"
        else:
            st.error(f"Lỗi khi khởi chạy script nền: {str(e)}")
            return None


def read_log_file(log_file_name, lines=100):
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
    if not os.path.exists(SCHEDULER_STATE_FILE):
        return "File trạng thái scheduler (scheduler_state.json) không tìm thấy."
    try:
        with open(SCHEDULER_STATE_FILE, 'r', encoding="utf-8") as f:
            state = json.load(f)
        formatted_state = ""
        if not state:
            formatted_state += "Không có dữ liệu trạng thái."
            return formatted_state
        for site, ts_str in state.items():
            try:
                dt_obj = datetime.fromisoformat(ts_str)
                formatted_state += f"  - {site}: Lần chạy cuối {dt_obj.strftime('%Y-%m-%d %H:%M:%S')}\n"
            except ValueError:
                formatted_state += f"  - {site}: Lần chạy cuối {ts_str} (timestamp thô)\n"
        return formatted_state
    except Exception as e:
        return f"Lỗi khi tải trạng thái scheduler: {str(e)}"

def is_scheduler_process_running():
    if not os.path.exists(SCHEDULER_PID_FILE):
        return False
    try:
        with open(SCHEDULER_PID_FILE, "r") as f:
            pid = int(f.read().strip())
        if psutil.pid_exists(pid):
            # Kiểm tra thêm tên process nếu có thể (phụ thuộc HĐH và quyền)
            # p = psutil.Process(pid)
            # if "python" in p.name().lower() and any("scheduler.py" in cmd_part for cmd_part in p.cmdline()):
            #     return True
            return True # Đơn giản hóa: nếu PID tồn tại thì coi là đang chạy
        else: # PID không tồn tại, dọn dẹp file PID cũ
            try: os.remove(SCHEDULER_PID_FILE)
            except OSError: pass
            return False
    except (IOError, ValueError, psutil.NoSuchProcess):
        if os.path.exists(SCHEDULER_PID_FILE): # Nếu lỗi đọc file PID mà file vẫn còn
            try: os.remove(SCHEDULER_PID_FILE) # Dọn dẹp file PID nếu process không còn
            except OSError: pass
        return False
    except Exception as e:
        # st.error(f"Lỗi kiểm tra scheduler PID: {e}") # Không nên hiện lỗi này liên tục
        print(f"Lỗi kiểm tra scheduler PID: {e}")
        return False

# --- Streamlit App UI ---
st.set_page_config(layout="wide", page_title="Project Control GUI")
st.title("Dashboard Điều Khiển Project")

# --- Session State Initialization ---
if 'last_action_message' not in st.session_state:
    st.session_state.last_action_message = ""
if 'orchestrator_output' not in st.session_state:
    st.session_state.orchestrator_output = {"stdout": "", "stderr": ""}
if 'delete_output' not in st.session_state:
    st.session_state.delete_output = {"stdout": "", "stderr": ""}

# --- Sidebar ---
st.sidebar.header("Điều Khiển Scheduler")
scheduler_running_status = is_scheduler_process_running()
status_text = "ĐANG CHẠY" if scheduler_running_status else "ĐÃ DỪNG"
status_color = "green" if scheduler_running_status else "red"
st.sidebar.markdown(f"**Trạng thái Scheduler:** <font color='{status_color}'>{status_text}</font>", unsafe_allow_html=True)

if st.sidebar.button("Start Scheduler", key="start_scheduler_btn", disabled=scheduler_running_status, help="Khởi động tiến trình scheduler nền."):
    if not scheduler_running_status:
        process_obj = run_script(SCHEDULER_SCRIPT, wait_for_completion=False)
        if process_obj:
            time.sleep(2) # Chờ scheduler tạo PID file
            if is_scheduler_process_running():
                st.session_state.last_action_message = f"INFO: Đã gửi yêu cầu khởi động Scheduler (PID: {process_obj.pid})."
            else:
                st.session_state.last_action_message = "ERROR: Khởi động Scheduler nhưng không thấy PID file hoặc process."
        else:
            st.session_state.last_action_message = "ERROR: Không thể khởi động Scheduler."
        st.rerun()

if st.sidebar.button("Stop Scheduler", key="stop_scheduler_btn", disabled=not scheduler_running_status, help="Gửi yêu cầu dừng an toàn cho scheduler."):
    if scheduler_running_status:
        try:
            with open(SCHEDULER_STOP_REQUEST_FILE, "w") as f:
                f.write("stop")
            st.session_state.last_action_message = "INFO: Đã gửi yêu cầu dừng Scheduler. Vui lòng chờ và kiểm tra lại trạng thái."
            # Không nên chờ lâu ở đây vì Streamlit sẽ bị block
            # time.sleep(5) # Chờ một chút
            st.rerun()
        except Exception as e:
            st.session_state.last_action_message = f"ERROR: Lỗi khi gửi yêu cầu dừng Scheduler: {e}"
            st.rerun()

if st.session_state.last_action_message:
    st.sidebar.info(st.session_state.last_action_message)
    # Không xóa message ngay, để người dùng thấy

st.sidebar.markdown("---")
with st.sidebar.expander("Trạng Thái Lần Chạy Cuối Của Các Site"):
    st.text(load_scheduler_state_for_gui())

# --- Main Content Area (Sử dụng Tabs) ---
available_sites = discover_sites()

tab_sites, tab_keywords, tab_logs = st.tabs([
    "Quản Lý Sites", "Quản Lý Keywords (GSheet - TBD)", "Xem Logs"
])

with tab_sites:
    st.header("Chạy Tác Vụ & Quản Lý Site")
    if not available_sites:
        st.warning("Không tìm thấy cấu hình site nào. Vui lòng kiểm tra thư mục `site_profiles`.")
    else:
        selected_site_main = st.selectbox("Chọn Site cho các tác vụ:", available_sites, key="main_site_select_for_actions")

        if selected_site_main:
            st.subheader(f"Tác vụ cho Site: {selected_site_main}")
            
            # Bật/Tắt Schedule
            site_config_path = os.path.join(SITE_PROFILES_DIR, selected_site_main, "site_config.json")
            current_site_cfg = {}
            schedule_currently_enabled = False
            if os.path.exists(site_config_path):
                try:
                    with open(site_config_path, 'r') as f_cfg_read:
                        current_site_cfg = json.load(f_cfg_read)
                    schedule_currently_enabled = current_site_cfg.get("SCHEDULE_ENABLED", False)
                except Exception as e:
                    st.error(f"Lỗi đọc config cho {selected_site_main}: {e}")

            toggle_btn_label = "Tắt Schedule Site" if schedule_currently_enabled else "Bật Schedule Site"
            if st.button(toggle_btn_label, key=f"toggle_schedule_{selected_site_main}"):
                if current_site_cfg:
                    current_site_cfg["SCHEDULE_ENABLED"] = not schedule_currently_enabled
                    try:
                        with open(site_config_path, 'w') as f_cfg_write:
                            json.dump(current_site_cfg, f_cfg_write, indent=4)
                        st.success(f"Đã cập nhật SCHEDULE_ENABLED thành '{not schedule_currently_enabled}' cho {selected_site_main}.")
                        st.rerun()
                    except Exception as e_write_cfg:
                        st.error(f"Lỗi khi ghi lại cấu hình cho {selected_site_main}: {e_write_cfg}")
                else:
                    st.error("Không thể tải cấu hình để thay đổi.")

            # Chạy Orchestrator
            st.markdown("---")
            st.markdown("##### Chạy Orchestrator Tạo Bài Viết")
            if st.button(f"Chạy Orchestrator cho {selected_site_main}", key=f"run_orchestrator_site_{selected_site_main}"):
                with st.spinner(f"Đang chạy orchestrator cho {selected_site_main}... (có thể mất vài phút)"):
                    success, stdout, stderr = run_script(MAIN_ORCHESTRATOR_SCRIPT, site_name_as_option=selected_site_main)
                st.session_state.orchestrator_output = {"stdout": stdout, "stderr": stderr, "success": success, "site": selected_site_main}
                st.rerun() # Rerun để hiển thị output

            if st.session_state.orchestrator_output.get("site") == selected_site_main:
                orch_out = st.session_state.orchestrator_output
                if orch_out.get("success"):
                    st.success(f"Orchestrator cho {selected_site_main} hoàn thành.")
                else:
                    st.error(f"Orchestrator cho {selected_site_main} có lỗi.")
                
                if orch_out.get("stdout"):
                    with st.expander("Xem Output (stdout) của Orchestrator", expanded=False):
                        st.text_area("Orchestrator Output", value=orch_out["stdout"], height=300, key="orch_stdout_disp")
                if orch_out.get("stderr"):
                    with st.expander("Xem Lỗi (stderr) của Orchestrator", expanded=True):
                        st.text_area("Orchestrator Error", value=orch_out["stderr"], height=200, key="orch_stderr_disp")
            
            # Chạy Xóa Keyword
            st.markdown("---")
            st.markdown("##### Chạy Xóa Keyword khỏi Pinecone")
            confirm_delete = st.checkbox(f"Xác nhận xóa keywords khỏi Pinecone cho site {selected_site_main} (dựa trên sheet 'Delete')", key=f"confirm_delete_{selected_site_main}")
            if st.button(f"Chạy Script Xóa Keyword cho {selected_site_main}", key=f"run_delete_site_{selected_site_main}", disabled=not confirm_delete):
                with st.spinner(f"Đang chạy script xóa keyword cho {selected_site_main}..."):
                    success, stdout, stderr = run_script(DELETE_KEYWORDS_SCRIPT, site_name_as_arg=selected_site_main, extra_args=["--yes"])
                st.session_state.delete_output = {"stdout": stdout, "stderr": stderr, "success": success, "site": selected_site_main}
                st.rerun()

            if st.session_state.delete_output.get("site") == selected_site_main:
                del_out = st.session_state.delete_output
                if del_out.get("success"):
                    st.success(f"Script xóa keyword cho {selected_site_main} hoàn thành.")
                else:
                    st.error(f"Script xóa keyword cho {selected_site_main} có lỗi.")

                if del_out.get("stdout"):
                    with st.expander("Xem Output (stdout) của Script Xóa", expanded=False):
                        st.text_area("Deletion Output", value=del_out["stdout"], height=200, key="del_stdout_disp")
                if del_out.get("stderr"):
                    with st.expander("Xem Lỗi (stderr) của Script Xóa", expanded=True):
                        st.text_area("Deletion Error", value=del_out["stderr"], height=200, key="del_stderr_disp")

            # Xem cấu hình site
            st.markdown("---")
            st.markdown(f"##### Cấu hình `site_config.json` cho {selected_site_main}")
            with st.expander("Xem/Ẩn Cấu hình JSON"):
                if os.path.exists(site_config_path):
                    try:
                        with open(site_config_path, 'r') as f_cfg_disp:
                            st.json(json.load(f_cfg_disp))
                    except Exception as e_disp_cfg:
                        st.error(f"Không thể đọc cấu hình cho {selected_site_main}: {e_disp_cfg}")
                else:
                    st.warning(f"File site_config.json cho {selected_site_main} không tìm thấy.")

with tab_keywords:
    st.header("Quản Lý Keywords (từ Google Sheets)")
    st.info("Tính năng này đang được phát triển.")
    st.markdown("""
    Để tích hợp:
    1. Cấu hình Google Sheets API credentials (service account).
    2. Sử dụng thư viện `gspread` và `GoogleSheetsHandler` của bạn (nếu có).
    3. Thêm Selectbox để chọn Site (nếu GSheet của bạn quản lý nhiều site).
    4. Thêm Selectbox để chọn Sheet (ví dụ: "Keyword Used = 0", "Keyword", "Delete").
    5. Nút "Tải dữ liệu" để fetch và hiển thị bằng `st.dataframe` hoặc `st.data_editor`.
    6. Cân nhắc sử dụng `@st.cache_data` để tránh gọi API GSheet quá thường xuyên.
    """)
    # Placeholder cho việc hiển thị (nếu bạn có dữ liệu mẫu hoặc logic cơ bản)
    # if st.button("Tải dữ liệu Keyword mẫu"):
    #     sample_keyword_data = [
    #         {"Keyword": "Best electric guitars 2024", "Site": "Fretterverse", "Used": "0", "Status": "Pending"},
    #         {"Keyword": "How to clean your rifle", "Site": "LegallyArmed", "Used": "1", "Status": "Published"},
    #     ]
    #     st.dataframe(sample_keyword_data)

with tab_logs:
    st.header("Xem Logs")
    log_files_list = []
    if os.path.isdir(LOGS_DIR):
        log_files_list = sorted(
            [f for f in os.listdir(LOGS_DIR) if os.path.isfile(os.path.join(LOGS_DIR, f)) and f.endswith(".log")],
            reverse=True # File mới nhất lên đầu
        )

    if log_files_list:
        selected_log_file = st.selectbox("Chọn File Log:", log_files_list, key="log_file_select_tab")
        lines_to_show_logs = st.number_input("Số dòng cuối muốn xem:", min_value=10, max_value=1000, value=200, step=10, key="log_lines_tab_input")
        
        # Key duy nhất cho nút để tránh lỗi duplicate widget ID
        refresh_button_key = f"refresh_log_{selected_log_file.replace('.', '_')}" 
        
        if st.button("Tải Log", key=refresh_button_key):
            if selected_log_file:
                log_content = read_log_file(selected_log_file, lines_to_show_logs)
                st.session_state[f"log_content_{selected_log_file}"] = log_content # Lưu vào session_state
        
        # Hiển thị log từ session_state nếu có
        if selected_log_file and f"log_content_{selected_log_file}" in st.session_state:
            st.text_area(f"Nội dung Log: {selected_log_file}", value=st.session_state[f"log_content_{selected_log_file}"], height=500, key=f"log_display_area_{selected_log_file}")
        elif selected_log_file: # Hiển thị lần đầu hoặc nếu chưa có trong session
             log_content_init = read_log_file(selected_log_file, lines_to_show_logs)
             st.text_area(f"Nội dung Log: {selected_log_file}", value=log_content_init, height=500, key=f"log_display_area_{selected_log_file}_init")

    else:
        st.info(f"Không tìm thấy file log nào trong thư mục '{LOGS_DIR}'.")

st.markdown("---")
st.caption(f"Project GUI - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")