import os
import sys

import pymysql

# Same convention as settings.py: no hardcoded fallback for a live
# credential - fail loudly instead of silently connecting with a
# guessable default.
db_password = os.environ.get('DB_PASSWORD')
if not db_password:
    sys.exit('DB_PASSWORD is not set - export it (or load your .env) before running db_check.py.')

try:
    connection = pymysql.connect(
        host='localhost',
        user=os.environ.get('DB_USER', 'root'),
        password=db_password,
        database='smashed_sfs'
    )
    print("Database connection successful!")
    connection.close()
except Exception as e:
    print(f"Database connection failed: {e}")