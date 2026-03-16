import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


_db_engine = os.getenv('DJANGO_DB_ENGINE', '').strip().lower()
if _db_engine in ('mysql', 'django.db.backends.mysql'):
	import pymysql

	pymysql.version_info = (2, 2, 1, 'final', 0)
	pymysql.__version__ = '2.2.1'
	pymysql.install_as_MySQLdb()
