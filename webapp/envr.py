import os

# Environment-specific values are set in the environment in the WSGI file, not here.
DB_HOST = 'ngaither.mysql.pythonanywhere-services.com'
DB_USER = 'ngaither'
DB_PASSWORD = os.environ['DB_PASSWORD']
DB_NAME = os.environ['DB_NAME']
AP_UPLOAD_URL = 'https://archipelago.gg/uploads'
AP_ROOT = os.environ['AP_ROOT']
YAMLS_ROOT = os.environ['YAMLS_ROOT']
AP_DAILY_SEED_YAML_DIR = os.environ['AP_DAILY_SEED_YAML_DIR']
AP_DAILY_SEED_OUTPUT_DIR = os.environ['AP_DAILY_SEED_OUTPUT_DIR']
AP_DAILY_DUO_SEED_YAML_DIR = os.environ['AP_DAILY_DUO_SEED_YAML_DIR']
AP_DAILY_DUO_SEED_OUTPUT_DIR = os.environ['AP_DAILY_DUO_SEED_OUTPUT_DIR']
AP_LOGIN = os.environ['AP_LOGIN']
