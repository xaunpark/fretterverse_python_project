import os
import sys
import json
import time
import logging
import subprocess
from datetime import datetime, timedelta, timezone
import signal

# Assuming utils.config_loader is in the "utils" directory at the project root
# and scheduler.py is also at the project root.
try:
    from utils.config_loader import load_app_config, ENV_CONFIG_MAPPING
    from utils.logging_config import setup_logging # Corrected import
except ImportError:
    # This is to help locate modules if script is run from a different CWD
    # For example, if your project root is not directly in PYTHONPATH
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)
    from utils.config_loader import load_app_config, ENV_CONFIG_MAPPING
    from utils.logging_config import setup_logging # Corrected import

SITE_PROFILES_DIR = "site_profiles"
SCHEDULER_STATE_FILE = "scheduler_state.json"
MAIN_ORCHESTRATOR_SCRIPT = "main_orchestrator.py"
CHECK_INTERVAL_SECONDS = 60  # Check every 60 seconds

# Setup logger for the scheduler
logger = setup_logging(log_level_str="INFO", log_to_file=True, log_file_path='logs/scheduler.log', log_to_console=True)

# Biến toàn cục để kiểm soát vòng lặp khi nhận tín hiệu
shutdown_flag = False

def handle_signal(signum, frame):
    global shutdown_flag
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    shutdown_flag = True

# Đăng ký xử lý tín hiệu
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal) # Xử lý cả Ctrl+C

def load_scheduler_state():
    """Loads the last run times for sites from the state file."""
    if not os.path.exists(SCHEDULER_STATE_FILE):
        return {}
    try:
        with open(SCHEDULER_STATE_FILE, 'r') as f:
            state_data = json.load(f)
            # Convert string timestamps back to datetime objects
            for site, ts_str in state_data.items():
                try:
                    state_data[site] = datetime.fromisoformat(ts_str)
                except ValueError:
                    logger.error(f"Invalid timestamp format for site {site} in state file: {ts_str}. Ignoring this entry.")
                    # Optionally remove or mark as needing immediate run
                    del state_data[site]
            return state_data
    except json.JSONDecodeError:
        logger.error(f"Error decoding {SCHEDULER_STATE_FILE}. Starting with an empty state.")
        return {}
    except Exception as e:
        logger.error(f"Failed to load scheduler state: {e}. Starting with an empty state.")
        return {}

def save_scheduler_state(state):
    """Saves the last run times for sites to the state file."""
    try:
        # Convert datetime objects to ISO format strings for JSON serialization
        serializable_state = {site: dt.isoformat() for site, dt in state.items()}
        with open(SCHEDULER_STATE_FILE, 'w') as f:
            json.dump(serializable_state, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save scheduler state: {e}")

def discover_sites():
    """Discovers site names from the site_profiles directory."""
    sites = []
    if not os.path.isdir(SITE_PROFILES_DIR):
        logger.error(f"Site profiles directory '{SITE_PROFILES_DIR}' not found.")
        return sites
    for site_name in os.listdir(SITE_PROFILES_DIR):
        if os.path.isdir(os.path.join(SITE_PROFILES_DIR, site_name)):
            # Check if a config file (e.g., site_config.json or .env) exists
            # This is a basic check; load_app_config will do the actual loading
            if os.path.exists(os.path.join(SITE_PROFILES_DIR, site_name, "site_config.json")) or \
               os.path.exists(os.path.join(SITE_PROFILES_DIR, site_name, ".env")):
                sites.append(site_name)
            else:
                logger.debug(f"Skipping directory '{site_name}' as it doesn't appear to be a configured site (missing site_config.json or .env).")
    logger.info(f"Discovered sites: {sites}")
    return sites

def run_site_script(site_name):
    """Executes the main_orchestrator.py script for the given site."""
    logger.info(f"Attempting to run script for site: {site_name}")
    try:
        python_executable = sys.executable  # Use the same python interpreter
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), MAIN_ORCHESTRATOR_SCRIPT)
        
        if not os.path.exists(script_path):
            logger.error(f"Main orchestrator script '{MAIN_ORCHESTRATOR_SCRIPT}' not found at '{script_path}'.")
            return False

        process = subprocess.Popen(
            [python_executable, script_path, "--site", site_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)) # Run from project root
        )
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            logger.info(f"Successfully ran script for site: {site_name}")
            # Luôn ghi log stdout cho các lần chạy thành công trong quá trình gỡ lỗi
            if stdout: # Chỉ ghi log nếu có stdout
                logger.info(f"Stdout for {site_name} (success):\n{stdout}")
            return True
        else:
            logger.error(f"Error running script for site: {site_name}. Return code: {process.returncode}")
            logger.error(f"Stderr for {site_name}:\n{stderr}")
            if stdout: # Cũng ghi log stdout khi có lỗi, nếu có
                 logger.info(f"Stdout for {site_name} (on error):\n{stdout}")
            return False
    except Exception as e:
        logger.error(f"Exception while trying to run script for site {site_name}: {e}", exc_info=True)
        return False

def main_scheduler_loop():
    """The main loop for the scheduler."""
    global shutdown_flag # Khai báo sử dụng biến toàn cục
    logger.info("Scheduler started.")
    scheduler_state = load_scheduler_state()

    while not shutdown_flag: # Kiểm tra cờ shutdown
        now_utc = datetime.now(timezone.utc)
        logger.debug(f"Scheduler check at {now_utc.isoformat()}")

        sites_to_process = discover_sites()

        for site_name in sites_to_process:
            if shutdown_flag: # Kiểm tra cờ trong vòng lặp site
                logger.info("Shutdown signal received during site processing. Breaking loop.")
                break                
            logger.debug(f"Processing site: {site_name}")
            try:
                # Load site-specific configuration
                # Pass a base_path if your config_loader needs it, or ensure it resolves paths correctly
                # For simplicity, assuming config_loader can find site configs from site_name
                site_config = load_app_config(site_name=site_name)

                schedule_enabled = site_config.get('SCHEDULE_ENABLED', False)
                interval_hours = site_config.get('SCHEDULE_INTERVAL_HOURS', 0)
                interval_minutes = site_config.get('SCHEDULE_INTERVAL_MINUTES', 0)

                if not schedule_enabled:
                    logger.debug(f"Scheduling is disabled for site: {site_name}. Skipping.")
                    continue

                total_interval_minutes = (interval_hours * 60) + interval_minutes
                if total_interval_minutes <= 0:
                    logger.warning(f"Schedule interval for site {site_name} is zero or negative ({total_interval_minutes} mins). Skipping.")
                    continue

                schedule_interval = timedelta(minutes=total_interval_minutes)
                last_run_time = scheduler_state.get(site_name)

                logger.debug(f"Site: {site_name}, Enabled: {schedule_enabled}, Interval (mins): {total_interval_minutes}, Last Run: {last_run_time.isoformat() if last_run_time else 'Never'}")

                should_run = False
                if last_run_time is None:
                    logger.info(f"Site {site_name} has no previous run time recorded. Scheduling to run now.")
                    should_run = True # Sẽ chạy nếu enabled và interval > 0
                else:
                    next_run_time = last_run_time + schedule_interval
                    if now_utc >= next_run_time:
                        logger.info(f"Site {site_name} is due. Last run: {last_run_time.isoformat()}, Next run: {next_run_time.isoformat()}")
                        should_run = True
                    else:
                        logger.debug(f"Site {site_name} is not due yet. Next run at {next_run_time.isoformat()}")
                logger.info(f"Site: {site_name}, Calculated should_run: {should_run}")

                if should_run:
                    # Xác định thời điểm để ghi nhận là lần chạy cuối cùng
                    # Nếu đây là lần chạy đầu tiên (last_run_time is None), ghi nhận now_utc (thời điểm quyết định chạy)
                    # Nếu là các lần chạy tiếp theo, ghi nhận next_run_time (thời điểm được lên lịch mà nó vừa đạt tới)
                    time_to_record_as_last_run = now_utc # Mặc định cho lần chạy đầu tiên
                    if last_run_time is not None:
                        # 'next_run_time' đã được tính toán và điều kiện chạy đã được đáp ứng (hoặc vượt qua)
                        # Biến này chỉ được định nghĩa nếu last_run_time không phải là None
                        time_to_record_as_last_run = next_run_time

                    logger.info(f"Proceeding to run script for site: {site_name} as should_run is True.")
                    if run_site_script(site_name):
                        scheduler_state[site_name] = time_to_record_as_last_run
                        save_scheduler_state(scheduler_state)
                    else:
                        logger.error(f"Failed to execute script for {site_name}. Will retry at next scheduled interval.")
                        # Optionally, implement a more sophisticated retry/backoff or error state
            except Exception as e:
                logger.error(f"Error processing site {site_name} in scheduler: {e}", exc_info=True)
        
        if shutdown_flag: # Kiểm tra cờ sau khi xử lý tất cả các site trong một chu kỳ
            logger.info("Shutdown signal received. Exiting main loop.")
            break

        logger.debug(f"Scheduler check complete. Sleeping for {CHECK_INTERVAL_SECONDS} seconds.")
        
        # Thay vì time.sleep trực tiếp, chia nhỏ để kiểm tra shutdown_flag thường xuyên hơn
        for _ in range(CHECK_INTERVAL_SECONDS):
            if shutdown_flag:
                break
            time.sleep(1)
            
    logger.info("Scheduler shutting down gracefully.")
    # Có thể bạn muốn lưu trạng thái một lần cuối ở đây nếu cần,
    # tuy nhiên, save_scheduler_state đã được gọi sau mỗi lần run_site_script thành công.
    # save_scheduler_state(scheduler_state) # Cân nhắc nếu logic của bạn cần điều này

if __name__ == "__main__":
    main_scheduler_loop()