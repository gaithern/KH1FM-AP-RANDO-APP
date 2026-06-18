import os

DB_HOST = 'ngaither.mysql.pythonanywhere-services.com'
DB_USER = 'ngaither'
DB_PASSWORD = os.environ['DB_PASSWORD']
DB_NAME = 'ngaither$kh1apdev'
AP_UPLOAD_URL = 'https://archipelago.gg/uploads'
AP_ROOT = '/home/ngaither/mysite/'
YAMLS_ROOT = '/home/ngaither/players/'
AP_DAILY_SEED_YAML_DIR = '/home/ngaither/daily_seed_yaml/'
AP_DAILY_SEED_OUTPUT_DIR = '/home/ngaither/daily_seed_output/'
AP_DAILY_DUO_SEED_YAML_DIR = '/home/ngaither/daily_duo_seed_yaml/'
AP_DAILY_DUO_SEED_OUTPUT_DIR = '/home/ngaither/daily_duo_seed_output/'
AP_LOGIN = os.environ['AP_LOGIN']