import pymysql

try:
    connection = pymysql.connect(
        host='localhost',
        user='root',
        password='Password123#!',  # Your MySQL password
        database='smashed_sfs'
    )
    print("✅ Database connection successful!")
    connection.close()
except Exception as e:
    print(f"❌ Database connection failed: {e}")