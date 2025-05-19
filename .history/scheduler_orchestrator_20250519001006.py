import os
import json
import time
import logging
from pathlib import Path

# --- Configuration ---
BASE_DIR = Path(__file__).resolve().parent
SITE_PROFILES_DIR = BASE_DIR / "site_profiles"
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
LOG_LEVEL = logging.INFO

# --- Setup Logging ---
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger("SchedulerOrchestrator")

def load_site_config(site_name):
    """
    Loads the site_config.json for a given site.
    Returns the config dictionary or None if an error occurs.
    """
    config_path = SITE_PROFILES_DIR / site_name / "site_config.json"
    if not config_path.is_file():
        logger.error(f"Config file not found for site '{site_name}' at {config_path}")
        return None
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        logger.info(f"Successfully loaded config for site '{site_name}'")
        return config_data
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from config file for site '{site_name}' at {config_path}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading config for site '{site_name}': {e}", exc_info=True)
        return None

def get_all_site_configs():
    """
    Scans the SITE_PROFILES_DIR and loads configurations for all found sites.
    Returns a dictionary mapping site_name to its configuration.
    """
    site_configs = {}
    if not SITE_PROFILES_DIR.is_dir():
        logger.error(f"Site profiles directory not found: {SITE_PROFILES_DIR}")
        return site_configs

    for site_dir in SITE_PROFILES_DIR.iterdir():
        if site_dir.is_dir():
            site_name = site_dir.name
            config = load_site_config(site_name)
            if config:
                site_configs[site_name] = config
    return site_configs

def placeholder_process_site(site_name, site_config):
    """
    Placeholder function representing the actual processing logic for a site.
    This will be replaced by a call to the refactored logic from Step 3.
    """
    logger.info(f"SCHEDULER: --- Starting job for site: {site_name} ---")
    # In a real scenario, this would call your main processing function:
    # from main_orchestrator import process_single_site (or similar)
    # process_single_site(site_name, site_config)
    logger.info(f"Simulating work for {site_name}...")
    time.sleep(5) # Simulate some work
    logger.info(f"SCHEDULER: --- Finished job for site: {site_name} ---")

def main():
    logger.info("Scheduler Orchestrator starting...")
    
    all_configs = get_all_site_configs()
    
    if not all_configs:
        logger.warning("No site configurations loaded. Scheduler will not schedule any tasks.")
        # In a real scenario with a scheduling library, we might still start the loop
        # to allow for dynamic reloading or other management tasks.
        # For now, we can exit or just log.
        # return

    # This is where we would integrate with a scheduling library (e.g., 'schedule') - Step 5
    # For now, we'll just log what would be scheduled.
    
    logger.info("--- Initializing Schedulers (Conceptual) ---")
    for site_name, config in all_configs.items():
        schedule_enabled = config.get("SCHEDULE_ENABLED", False)
        if schedule_enabled:
            interval_hours = config.get("SCHEDULE_INTERVAL_HOURS", 0)
            interval_minutes = config.get("SCHEDULE_INTERVAL_MINUTES", 30)
            total_interval_minutes = (interval_hours * 60) + interval_minutes
            
            if total_interval_minutes > 0:
                logger.info(f"Site '{site_name}': Scheduling enabled. Will run every {total_interval_minutes} minutes.")
                # With 'schedule' library:
                # schedule.every(total_interval_minutes).minutes.do(placeholder_process_site, site_name=site_name, site_config=config)
            else:
                logger.warning(f"Site '{site_name}': Scheduling enabled but interval is 0. Task will not be scheduled.")
        else:
            logger.info(f"Site '{site_name}': Scheduling is disabled.")

    logger.info("--- Conceptual Schedulers Initialized ---")
    logger.info("Scheduler Orchestrator would now enter its main loop to run pending tasks.")
    # In a real scenario with 'schedule' library:
    # while True:
    #     schedule.run_pending()
    #     time.sleep(1) # Check every second, or adjust as needed

if __name__ == "__main__":
    main()