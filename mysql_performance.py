import pymysql
import random
import time
from datetime import datetime, timedelta

# MySQL 連接設定
conn = pymysql.connect(
    host='localhost',
    user='root',
    password='example',
    database='exampledb'
)
cursor = conn.cursor()

# 建立 DB 和 Table
sql_commands = [
    "CREATE DATABASE IF NOT EXISTS exampledb;",
    "USE exampledb;",
    """
    CREATE TABLE IF NOT EXISTS product_stats (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        product_name VARCHAR(255),
        timestamp DATETIME,
        data TEXT,
        INDEX idx_product_name_timestamp (product_name, timestamp)
    );
    """,
    "TRUNCATE product_stats;"
]

# 執行 SQL 指令
for command in sql_commands:
    cursor.execute(command)

conn.commit()

# 寫入資料
start_time = datetime.now()
insert_batch_size = 2000  # 每批次寫入數據量
product_size = 2000 # 要測試的商品總量
total_records = 0  # 紀錄寫入的數據總量
time_range = 8 * 60 # 總時間 8 hours

# 開始計時
insert_start_time = time.time()

# 建立數據並批量寫入
batch = []
for minute in range(time_range):
    timestamp = start_time + timedelta(minutes=minute)
    for i in range(product_size):  # 每分鐘要寫入的商品紀錄
        product_name = f"商品名稱{i}"  # 模擬 product_size 種不同商品
        stats = f"統計資料{i}"
        batch.append((product_name, timestamp, stats))
        total_records += 1
        
        # 批量寫入
        if len(batch) >= insert_batch_size:
            cursor.executemany(
                "INSERT INTO product_stats (product_name, timestamp, data) VALUES (%s, %s, %s)",
                batch
            )
            conn.commit()
            batch = []

# 寫入剩餘的數據
if batch:
    cursor.executemany(
        "INSERT INTO product_stats (product_name, timestamp, data) VALUES (%s, %s, %s)",
        batch
    )
    conn.commit()

# 計時結束
insert_end_time = time.time()

# 查詢效能測試
query_times = []
for _ in range(100):
    # 隨機生成查詢的時間區間
    start_timestamp = start_time + timedelta(minutes=random.randint(0, time_range-30))  # 最大值為 - 30 為 30 分鐘
    end_timestamp = start_timestamp + timedelta(minutes=30)

    # 查詢多筆商品名稱在特定時間範圍內的資料
    product_names = [f"商品名稱{random.randint(1, product_size)}" for _ in range(10)]  # 隨機查詢 10 個商品

    # 使用 IN 進行多商品名稱查詢
    format_strings = ','.join([f"'{name}'" for name in product_names])
    query = f"SELECT * FROM product_stats WHERE product_name IN ({format_strings}) AND timestamp BETWEEN '{start_timestamp}' AND '{end_timestamp}'"

    # 執行查詢
    start_query = time.time()
    cursor.execute(query)
    rows = cursor.fetchall()
    end_query = time.time()
    query_times.append(end_query - start_query)

print(f"MySQL 寫入時間: {insert_end_time - insert_start_time} 秒")
print(f"MySQL 寫入總量: {total_records} 條")
# 計算平均查詢時間
average_query_time = sum(query_times) / len(query_times)
print(f"MySQL 平均查詢時間: {average_query_time} 秒")

cursor.close()
conn.close()