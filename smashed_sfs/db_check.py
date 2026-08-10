import os
import pymysql

try:
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password=os.environ.get('DB_PASSWORD', 'Password123#!'),
        database='smashed_sfs'
    )
    print("✅ Database connection successful!")
    connection.close()
except Exception as e:
    print(f"❌ Database connection failed: {e}")