import os
import json
import logging
from datetime import datetime
import re

# Initialize logging
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
ALLOWED_IDS = {5809601894, 1285451259}
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Site domains (default values)
SITE_CONFIG = {
    'hdmovie2': 'hdmovie2.trading',
    'hdhub4u': 'hdhub4u.gratis',
    'cinevood': '1cinevood.asia'
}

# File to store updated domains
CONFIG_FILE = 'site_config.json'

def validate_domain(domain, site_key):
    """Accept any domain string for the given site without strict validation."""
    
    if not domain.strip():
        logger.warning(f"Empty domain provided for {site_key}")
        return False
    
    logger.debug(f"Domain '{domain}' accepted for {site_key}")
    return True

def load_site_config():
    """Load site domains from file or use defaults."""
    global SITE_CONFIG
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                loaded_config = json.load(f)
                for key in SITE_CONFIG.keys():
                    if key in loaded_config and validate_domain(loaded_config[key], key):
                        SITE_CONFIG[key] = loaded_config[key]
                logger.info("Loaded site config from file")
        else:
            logger.info("No site_config.json found, using default SITE_CONFIG")
    except Exception as e:
        logger.error(f"Error loading site config: {e}")
        save_site_config()

def save_site_config():
    """Save site domains to file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(SITE_CONFIG, f, indent=2)
        logger.info("Saved site config to file")
    except Exception as e:
        logger.error(f"Error saving site config: {e}")

def update_site_domain(site_key, new_domain):
    """Update a site's domain and save to file."""
    if site_key not in SITE_CONFIG:
        logger.warning(f"Invalid site key: {site_key}")
        return False

    cleaned_domain = re.sub(r'^https?://', '', new_domain.strip().rstrip('/'))
    
    if not validate_domain(cleaned_domain, site_key):
        logger.warning(f"Invalid domain for {site_key}: {cleaned_domain}")
        return False

    SITE_CONFIG[site_key] = cleaned_domain
    save_site_config()
    logger.info(f"Updated {site_key} domain to {cleaned_domain}")
    return True

load_site_config()

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")