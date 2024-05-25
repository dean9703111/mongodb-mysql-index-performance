from pymongo import MongoClient, ASCENDING, UpdateOne
import random
import time
from datetime import datetime, timedelta

# MongoDB 連接設置
client = MongoClient('mongodb://localhost:27017/')
db = client.testdb

# 清空集合並創建新集合
db.product_stats.drop()
db.create_collection('product_stats')

# 加入 index
db.product_stats.create_index([("product_name", ASCENDING), ("stats.timestamp", ASCENDING)])

# 寫入數據
start_time = datetime.now()
insert_batch_size = 2000  # 每批次寫入數據量
product_size = 2000 # 要測試的商品總量
total_records = 0  # 記錄寫入的數據總量
time_range = 8 * 60 # 總時間 8 hours

# 開始計時
insert_start_time = time.time()

# 建立數據並批量寫入
product_dict = {}
for minute in range(time_range):  # 8 小時
    timestamp = start_time + timedelta(minutes=minute)
    for i in range(product_size):  # 每分鐘要寫入的商品紀錄
        product_name = f"商品名稱{i}"  # 模擬 product_size 種不同商品
        stats = {
            "timestamp": timestamp,
            "data": f"統計資料{i}"
        }
        
        if product_name not in product_dict:
            product_dict[product_name] = []
        
        product_dict[product_name].append(stats)
        total_records += 1

        # 批量更新
        if total_records % insert_batch_size == 0:
            operations = [
                UpdateOne(
                    {"product_name": p_name},
                    {"$push": {"stats": {"$each": stats_array}}},
                    upsert=True
                )
                for p_name, stats_array in product_dict.items()
            ]
            db.product_stats.bulk_write(operations)
            product_dict.clear()

# 寫入剩餘的數據
if product_dict:
    operations = [
        UpdateOne(
            {"product_name": p_name},
            {"$push": {"stats": {"$each": stats_array}}},
            upsert=True
        )
        for p_name, stats_array in product_dict.items()
    ]
    db.product_stats.bulk_write(operations)

# 計時結束
insert_end_time = time.time()

# 查詢性能測試
query_times = []
for _ in range(100):
    # 隨機生成查詢的時間區間
    start_timestamp = start_time + timedelta(minutes=random.randint(0, time_range-30))  # 最大值為 - 30 為 30 分鐘
    end_timestamp = start_timestamp + timedelta(minutes=30)
    
    product_names = [f"商品名稱{random.randint(1, product_size)}" for _ in range(10)]  # 隨機查詢 10 個商品
    aggregate_query = [
        {"$match": {"product_name": {"$in": product_names}}},
        {"$unwind": "$stats"},
        {"$match": {"stats.timestamp": {"$gt": start_timestamp, "$lte": end_timestamp}}},
        {"$project": {
            "_id": 0,
            "product_name": 1,
            "timestamp": "$stats.timestamp",
            "data": "$stats.data"
        }}
    ]
    
    # 執行查詢
    start_query = time.time()
    result = db.product_stats.aggregate(aggregate_query)
    end_query = time.time()
    
    query_times.append(end_query - start_query)

print(f"MongoDB 寫入時間: {insert_end_time - insert_start_time} 秒")
print(f"MongoDB 寫入總量: {total_records} 條")
# 計算平均查詢時間
average_query_time = sum(query_times) / len(query_times)
print(f"MongoDB 平均查詢時間: {average_query_time} 秒")

client.close()
