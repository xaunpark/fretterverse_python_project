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
    project_root_for_import = os.path.dirname(os.path.abspath(__file__))
    if project_root_for_import not in sys.path:
        sys.path.insert(0, project_root_for_import)
    from utils.config_loader import load_app_config, ENV_CONFIG_MAPPING
    from utils.logging_config import setup_logging # Corrected import

# --- Constants for Scheduler Control ---
# These file paths should be relative to the project root where scheduler.py is located
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)) # Defines project root based on scheduler.py location
SITE_PROFILES_DIR = os.path.join(PROJECT_ROOT, "site_profiles")
SCHEDULER_STATE_FILE = os.path.join(PROJECT_ROOT, "scheduler_state.json")
MAIN_ORCHESTRATOR_SCRIPT = os.path.join(PROJECT_ROOT, "main_orchestrator.py") # Script to run for each site
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs") # Ensure logs directory exists

# Control files (should be at the project root for simple_gui.py to find them easily)
SCHEDULER_PID_FILE = os.path.join(PROJECT_ROOT, "scheduler.pid")
SCHEDULER_STOP_REQUEST_FILE = os.path.join(PROJECT_ROOT, "scheduler.stop_request")

CHECK_INTERVAL_SECONDS = 60  # Check every 60 seconds

# Ensure logs directory exists
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR, exist_ok=True)

# Setup logger for the scheduler
# Ensure log_file_path uses LOGS_DIR
logger = setup_logging(
    log_level_str="INFO",
    log_to_file=True,
    log_file_path=os.path.join(LOGS_DIR, 'scheduler.log'), # Corrected log file path
    log_to_console=True
)

# Global flag to control the loop on signal or stop request
shutdown_flag = False

def handle_signal(signum, frame):
    global shutdown_flag
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    shutdown_flag = True
    # Attempt to create a stop request file as well, in case signals are missed by other checks
    try:
        with open(SCHEDULER_STOP_REQUEST_FILE, "w") as f:
            f.write("stop_signal")
        logger.info(f"Created stop request file '{SCHEDULER_STOP_REQUEST_FILE}' due to signal.")
    except Exception as e:
        logger.error(f"Could not create stop request file on signal: {e}")


# Register signal handlers
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal) # Handle Ctrl+C

def load_scheduler_state():
    """Loads the last run times for sites from the state file."""
    if not os.path.exists(SCHEDULER_STATE_FILE):
        return {}
    try:
        with open(SCHEDULER_STATE_FILE, 'r') as f:
            state_data = json.load(f)
            # Convert string timestamps back to datetime objects
            for site, ts_str in list(state_data.items()): # Iterate over a copy for safe deletion
                try:
                    state_data[site] = datetime.fromisoformat(ts_str)
                except ValueError:
                    logger.error(f"Invalid timestamp format for site {site} in state file: {ts_str}. Ignoring this entry.")
                    del state_data[site] # Remove invalid entry
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
        site_path = os.path.join(SITE_PROFILES_DIR, site_name)
        if os.path.isdir(site_path):
            if os.path.exists(os.path.join(site_path, "site_config.json")) or \
               os.path.exists(os.path.join(site_path, ".env")):
                sites.append(site_name)
            else:
                logger.debug(f"Skipping directory '{site_name}' as it doesn't appear to be a configured site (missing site_config.json or .env).")
    logger.info(f"Discovered sites: {sites}")
    return sites

def run_site_script(site_name):
    """Executes the main_orchestrator.py script for the given site."""
    logger.info(f"Attempting to run script for site: {site_name}")
    try:
        python_executable = sys.executable
        # MAIN_ORCHESTRATOR_SCRIPT is already an absolute path or resolved relative to PROJECT_ROOT
        
        if not os.path.exists(MAIN_ORCHESTRATOR_SCRIPT):
            logger.error(f"Main orchestrator script '{MAIN_ORCHESTRATOR_SCRIPT}' not found.")
            return False

        process = subprocess.Popen(
            [python_executable, MAIN_ORCHESTRATOR_SCRIPT, "--site", site_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PROJECT_ROOT # Run from project root
        )
        stdout, stderr = process.communicate()

        if process.returncode == 0:
            logger.info(f"Successfully ran script for site: {site_name}")
            if stdout:
                logger.info(f"Stdout for {site_name} (success):\n{stdout}")
            return True
        else:
            logger.error(f"Error running script for site: {site_name}. Return code: {process.returncode}")
            if stderr: logger.error(f"Stderr for {site_name}:\n{stderr}")
            if stdout: logger.info(f"Stdout for {site_name} (on error):\n{stdout}")
            return False
    except Exception as e:
        logger.error(f"Exception while trying to run script for site {site_name}: {e}", exc_info=True)
        return False

def create_pid_file():
    try:
        with open(SCHEDULER_PID_FILE, "w") as f:
            f.write(str(os.getpid()))
        logger.info(f"Scheduler PID {os.getpid()} saved to {SCHEDULER_PID_FILE}")
    except Exception as e:
        logger.error(f"Could not write PID file '{SCHEDULER_PID_FILE}': {e}")

def remove_pid_file():
    try:
        if os.path.exists(SCHEDULER_PID_FILE):
            os.remove(SCHEDULER_PID_FILE)
            logger.info(f"Scheduler PID file '{SCHEDULER_PID_FILE}' removed.")
    except Exception as e:
        logger.error(f"Could not remove PID file '{SCHEDULER_PID_FILE}': {e}")

def check_for_stop_request():
    global shutdown_flag
    if os.path.exists(SCHEDULER_STOP_REQUEST_FILE):
        logger.info(f"Stop request file '{SCHEDULER_STOP_REQUEST_FILE}' found. Initiating shutdown.")
        shutdown_flag = True
        try:
            os.remove(SCHEDULER_STOP_REQUEST_FILE)
            logger.info(f"Removed stop request file '{SCHEDULER_STOP_REQUEST_FILE}'.")
        except OSError as e:
            logger.error(f"Error removing stop request file: {e}")
        return True
    return False

def main_scheduler_loop():
    global shutdown_flag
    create_pid_file() # Create PID file at the start

    logger.info("Scheduler started.")
    scheduler_state = load_scheduler_state()

    try:
        while not shutdown_flag:
            if check_for_stop_request(): # Check for stop request file at the beginning of each major loop
                break

            now_utc = datetime.now(timezone.utc)
            logger.debug(f"Scheduler check at {now_utc.isoformat()}")

            sites_to_process = discover_sites()

            for site_name in sites_to_process:
                if shutdown_flag or check_for_stop_request(): # Check again before processing each site
                    logger.info("Shutdown signal or stop request received during site processing. Breaking loop.")
                    break
                
                logger.debug(f"Processing site: {site_name}")
                try:
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
                        should_run = True
                    else:
                        # Ensure last_run_time is timezone-aware (UTC) if it came from state
                        if last_run_time.tzinfo is None:
                            logger.warning(f"Timestamp for site {site_name} from state file is naive. Assuming UTC.")
                            last_run_time = last_run_time.replace(tzinfo=timezone.utc)

                        next_run_time_calculated = last_run_time + schedule_interval
                        if now_utc >= next_run_time_calculated:
                            logger.info(f"Site {site_name} is due. Last run: {last_run_time.isoformat()}, Next run: {next_run_time_calculated.isoformat()}")
                            should_run = True
                        else:
                            logger.debug(f"Site {site_name} is not due yet. Next run at {next_run_time_calculated.isoformat()}")
                    
                    logger.info(f"Site: {site_name}, Calculated should_run: {should_run}")

                    if should_run:
                        time_to_record_as_last_run = now_utc
                        if last_run_time is not None:
                            # Use the calculated next_run_time_calculated if available and due
                            # This helps maintain the schedule more accurately
                             time_to_record_as_last_run = next_run_time_calculated if 'next_run_time_calculated' in locals() and now_utc >= next_run_time_calculated else now_utc


                        logger.info(f"Proceeding to run script for site: {site_name} as should_run is True.")
                        if run_site_script(site_name):
                            scheduler_state[site_name] = time_to_record_as_last_run
                            save_scheduler_state(scheduler_state)
                        else:
                            logger.error(f"Failed to execute script for {site_name}. Will retry at next scheduled interval.")
                except Exception as e:
                    logger.error(f"Error processing site {site_name} in scheduler: {e}", exc_info=True)
            
            if shutdown_flag: # Check flag after processing all sites in a cycle
                logger.info("Shutdown signal or stop request received. Exiting main loop.")
                break

            logger.debug(f"Scheduler check complete. Sleeping for {CHECK_INTERVAL_SECONDS} seconds.")
            
            for i in range(CHECK_INTERVAL_SECONDS):
                if shutdown_flag or check_for_stop_request(): # Check frequently during sleep
                    break
                time.sleep(1)
        
    except Exception as e:
        logger.critical(f"Unhandled exception in main scheduler loop: {e}", exc_info=True)
    finally:
        logger.info("Scheduler shutting down gracefully or due to an error.")
        remove_pid_file() # Ensure PID file is removed on exit

if __name__ == "__main__":
    # Check if another instance is already running using the PID file
    if os.path.exists(SCHEDULER_PID_FILE):
        try:
            with open(SCHEDULER_PID_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if the process with that PID is actually running
            # (This requires a library like psutil, or OS-specific commands)
            # For simplicity, we'll just assume if PID file exists, another instance might be running.
            # A more robust check would use psutil.pid_exists(pid)
            logger.warning(f"Scheduler PID file '{SCHEDULER_PID_FILE}' already exists (PID: {pid}). "
                           "Another instance might be running. If not, delete the PID file and retry. Exiting.")
            sys.exit(1)
        except (IOError, ValueError) as e:
            logger.warning(f"Error reading PID file '{SCHEDULER_PID_FILE}': {e}. "
                           "If another instance is not running, delete the file and retry. Exiting.")
            sys.exit(1)
        except Exception as e_psutil_check: # Placeholder if psutil was used
            logger.warning(f"Error checking existing process with psutil: {e_psutil_check}. Exiting.")
            sys.exit(1)


    main_scheduler_loop()