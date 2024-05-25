# MongoDB 與 MySQL 建立 Index 對 Read/Write 的效能影響

[上篇文章](https://medium.com/dean-lin/d89310099473)分享了朋友遇到資料庫瓶頸的案例，收到許多網友的熱情回饋。

其中有個留言很有意思：「如果在 MongoDB 建立 Index，那麼資料寫入的速度會比 MySQL 快很多嗎（有建立相同 Index 的情況下）？」

儘管網路上有許多資料顯示 MongoDB 建立 Index 後的效能比 MySQL 好，但這篇文章我想要透過程式來驗證兩者的寫入、讀取、資料大小差異。

> 非常建議看到最後，因為測試結果可能跟你想的不一樣。

```
文章大綱

▋ 測試參數說明
▋ 前置作業 1 ── docker image pull
▋ 前置作業 2 ── 安裝 Python 相關套件
▋ Script 設計說明
▋ MySQL 測試方案
▋ MongoDB 測試方案 1 ── 單筆資料的 Index 設計
▋ MongoDB 測試方案 2 ── Time Series Collection
▋ MongoDB 測試方案 3 ── Embedded Documents
▋ 結論：想象跟實際的落差
```

### ▋ 測試參數說明

這邊我以上一篇談到的商品統計圖表來做設計，因為主要比對效能上的差異，所以用的資料量級比較小（否則某些情境會跑到天荒地老）。

- 商品種類: 2000 筆
- 統計頻率: 1 分鐘
- 時間長度: 8 小時
- 總資料量: 96 萬筆（2000 * 8 * 60）
- 電腦規格: Apple M1 Max

### ▋ 前置作業 1 ── docker image pull

如果你有興趣，可以跟著文章步驟一起實作，為求公平，我這邊使用最新版的 MongoDB 跟 MySQL 來做測試（當然也可以直接滑到最後看實驗結果）。

如果有使用 Docker，可以使用下面的 `docker-compose.yaml` 取的對應的資源。

```yaml
version: '1.1'

services:
  mongodb:
    image: mongodb/mongodb-community-server:latest
    container_name: mongodb
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    networks:
      - mynetwork

  mongo-express:
    image: mongo-express:latest
    container_name: mongo-express
    ports:
      - "8081:8081"
    environment:
      ME_CONFIG_MONGODB_SERVER: mongodb
      ME_CONFIG_BASICAUTH_USERNAME: root
      ME_CONFIG_BASICAUTH_PASSWORD: example
    networks:
      - mynetwork

  mysql:
    image: mysql/mysql-server:latest
    container_name: mysql
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: example
      MYSQL_DATABASE: exampledb
    volumes:
      - mysql_data:/var/lib/mysql
      - ./mysql-conf.d:/etc/mysql/conf.d
    networks:
      - mynetwork

  phpmyadmin:
    image: phpmyadmin/phpmyadmin:latest
    container_name: phpmyadmin
    depends_on:
      - mysql
    ports:
      - "8080:80"
    environment:
      PMA_HOST: mysql
      PMA_PORT: 3306
    networks:
      - mynetwork

volumes:
  mongodb_data:
  mysql_data:

networks:
  mynetwork:
    driver: bridge
```

下面是對應的 GUI 連結:
- phpMyAdmin（帳號:root、密碼:example）: http://localhost:8080
- Mongo Express（帳號:root、密碼:example）: http://localhost:8081

### ▋ 前置作業 2 ── 安裝 Python 相關套件

我使用的 Python 版本為: 3.10.14

這邊我使用 Python 來撰寫測試用的 Script，若你尚未安裝，可以直接去官網下載: https://www.python.org/downloads/

執行下面指令便可安裝專安會用到的套件：
```cmd
pip install pymysql pymongo cryptography
```

### ▋ Script 設計說明

我總共寫了 4 個測試腳本，MySQL 1 個，MongoDB 3 個，基本上每個腳本都會做如下任務，差別在於資料結構設計不同。

1. 與資料庫（MySQL/MongoDB）建立連線
2. 建立 Table/Collection，並在「商品名稱(product_name)、紀錄時間(timestamp)」的欄位加上 index
3. 寫入資料，模擬為期 8 小時、1 分鐘寫入 2000 筆資料的情境。
4. 查詢效能測試，會亂數產生 100 次不同參數的搜尋條件。
5. 印出寫入時間/寫入總量/平均查詢時間

### ▋ MySQL 測試方案

MySQL 版本: 8.0.32

這個腳本沒什麼特別的，只是在「商品名稱(product_name)、紀錄時間(timestamp)」加上了 index。

```python
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
```

下面為 MySQL 測試結果:
- 寫入時間: 11.6187 秒
- 寫入總量: 960000 條
- 平均查詢時間: 0.0058 秒
- 資料大小: 151.4 MB

### ▋ MongoDB 測試方案 1 ── 單筆資料的 Index 設計

MongoDB 版本: 7.0.9

這個腳本是可以直接與 MySQL 比對的版本，因為都是採 row data 的概念，僅在「商品名稱(product_name)、紀錄時間(timestamp)」加上了 index。數據格式如下：

```json
{
    "product_name" : "商品名稱2",
    "timestamp" : ISODate("2024-05-25T15:24:46.492+0000"),
    "data" : "統計資料2"
}
```

```python
from pymongo import MongoClient, ASCENDING
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
db.product_stats.create_index([("product_name", ASCENDING), ("timestamp", ASCENDING)])

# 寫入數據
start_time = datetime.now()
insert_batch_size = 2000  # 每批次寫入數據量
product_size = 2000 # 要測試的商品總量
total_records = 0  # 記錄寫入的數據總量
time_range = 8 * 60 # 總時間 8 hours

# 開始計時
insert_start_time = time.time()

# 建立數據並批量寫入
batch = []
for minute in range(time_range):  # 8 小時
    timestamp = start_time + timedelta(minutes=minute)
    for i in range(product_size):  # 每分鐘要寫入的商品紀錄
        product_name = f"商品名稱{i}"  # 模擬 product_size 種不同商品
        stats = f"統計資料{i}"
        batch.append({
            "product_name": product_name,
            "timestamp": timestamp,
            "data": stats
        })
        total_records += 1

        # 批量寫入
        if len(batch) >= insert_batch_size:
            db.product_stats.insert_many(batch)
            batch.clear()

# 寫入剩餘的數據
if batch:
    db.product_stats.insert_many(batch)

# 計時結束
insert_end_time = time.time()

# 查詢效能測試
query_times = []
for _ in range(100):
    # 隨機生成查詢的時間區間
    start_timestamp = start_time + timedelta(minutes=random.randint(0, time_range-30))  # 最大值為 - 30 為 30 分鐘
    end_timestamp = start_timestamp + timedelta(minutes=30)

    product_names = [f"商品名稱{random.randint(1, product_size)}" for _ in range(10)]  # 隨機查詢 10 個商品
    query = {
        "product_name": {"$in": product_names},
        "timestamp": {"$gt": start_timestamp, "$lte": end_timestamp}
    }

    # 執行查詢
    start_query = time.time()
    result = db.product_stats.find(query)
    end_query = time.time()
    query_times.append(end_query - start_query)


print(f"MongoDB 寫入時間: {insert_end_time - insert_start_time} 秒")
print(f"MongoDB 寫入總量: {total_records} 條")
# 計算平均查詢時間
average_query_time = sum(query_times) / len(query_times)
print(f"MongoDB 平均查詢時間: {average_query_time} 秒")

client.close()
```

下面為 MongoDB 測試方案 1 的結果:
- 寫入時間: 6.8597 秒
- 寫入總量: 960000 條
- 平均查詢時間: 6.3467e-06 秒
- 資料大小: 97.8 MB

### ▋ MongoDB 測試方案 2 ── Time Series Collection

第二個方案則是採用 MongoDB Time Series Collection 的設計，設定如下：

```json
{
    "product_stats",
    timeseries={
        "timeField": "timestamp",
        "metaField": "product_name",
        "granularity": "minutes"
    }
}
```

```python
from pymongo import MongoClient, ASCENDING
import random
import time
from datetime import datetime, timedelta

# MongoDB 連接設置
client = MongoClient('mongodb://localhost:27017/')
db = client.testdb

# 清空集合並創建新集合
db.product_stats.drop()
db.create_collection(
    "product_stats",
    timeseries={
        "timeField": "timestamp",
        "metaField": "product_name",
        "granularity": "minutes"
    }
)

# 寫入數據
start_time = datetime.now()
insert_batch_size = 2000  # 每批次寫入數據量
product_size = 2000 # 要測試的商品總量
total_records = 0  # 記錄寫入的數據總量
time_range = 8 * 60 # 總時間 8 hours

# 開始計時
insert_start_time = time.time()

# 建立數據並批量寫入
batch = []
for minute in range(time_range):  # 8 小時
    timestamp = start_time + timedelta(minutes=minute)
    for i in range(product_size):  # 每分鐘要寫入的商品紀錄
        product_name = f"商品名稱{i}"  # 模擬 product_size 種不同商品
        data = f"統計資料{i}"
        
        batch.append({
            "timestamp": timestamp,
            "product_name": product_name,
            "data": data
        })
        total_records += 1

        # 批量寫入
        if len(batch) >= insert_batch_size:
            db.product_stats.insert_many(batch)
            batch.clear()

# 寫入剩餘的數據
if batch:
    db.product_stats.insert_many(batch)

# 計時結束
insert_end_time = time.time()

# 查詢性能測試
query_times = []
for _ in range(100):
    # 隨機生成查詢的時間區間
    start_timestamp = start_time + timedelta(minutes=random.randint(0, time_range-30))  # 最大值為 - 30 為 30 分鐘
    end_timestamp = start_timestamp + timedelta(minutes=30)
    
    product_names = [f"商品名稱{random.randint(1, product_size)}" for _ in range(10)]  # 隨機查詢 10 個商品
    query = {
        "product_name": {"$in": product_names},
        "timestamp": {"$gt": start_timestamp, "$lte": end_timestamp}
    }
    
    # 執行查詢
    start_query = time.time()
    result = db.product_stats.find(query)
    end_query = time.time()
    query_times.append(end_query - start_query)

print(f"MongoDB Time Series Collection 寫入時間: {insert_end_time - insert_start_time} 秒")
print(f"MongoDB Time Series Collection 寫入總量: {total_records} 條")
# 計算平均查詢時間
average_query_time = sum(query_times) / len(query_times)
print(f"MongoDB Time Series Collection 平均查詢時間: {average_query_time} 秒")

client.close()
```

下面為 MongoDB 測試方案 2 的結果:
- 寫入時間: 31.0204 秒
- 寫入總量: 960000 條
- 平均查詢時間: 6.7949e-06 秒
- 資料大小: 53.1 MB

### MongoDB 測試方案 3 ── Embedded Documents

第三個方案是上篇文章的方案，將統計數據紀錄到商品名稱（product_name）底下，並對「商品名稱(product_name)、紀錄時間(timestamp)」加上了 index。數據格式如下：

```json
{
    "_id" : ObjectId("6651a4d6329cedfc74f40dde"),
    "product_name" : "商品名稱0",
    "stats" : [
        {
            "timestamp" : ISODate("2024-05-25T16:44:06.728+0000"),
            "data" : "統計資料0"
        },
        {
            "timestamp" : ISODate("2024-05-25T16:45:06.728+0000"),
            "data" : "統計資料0"
        },
        ...
    ]
}
```

```python
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
```

下面為 MongoDB 測試方案 3 的結果:
- 寫入時間: 166.6052 秒
- 寫入總量: 960000 條
- 平均查詢時間: 0.0032 秒
- 資料大小: 53.1 MB

### ▋ 結論：想象跟實際的落差

下面我先用 Table 的方式，向大家展示這四個案例的測試結果:

| 測試方案                  | 寫入時間 (秒) | 平均查詢時間 (秒) | 資料大小 (MB) |
|---------------------------|---------------|-------------------|---------------|
| MySQL            | 11.6187       | 0.0058            | 151.4         |
| MongoDB 單筆 index        | 6.8597        | 6.3467e-06        | 97.8          |
| MongoDB Time Series Collection | 31.0204       | 6.7949e-06        | 53.1          |
| MongoDB Embedded Documents | 166.6052      | 0.0032            | 53.1          |

從寫入與讀取效能的角度來說，MongoDB 單筆 index 的方案就夠了；但如果想要壓縮資料大小，可以考慮 Time Series Collection 的方案。

至於上一篇文章原本打算使用的 Embedded Documents 方案，在寫入效能方面真的不太好，種類越多效能越差，真的是沒實驗過不知道。

至於 MySQL 就是一個安全牌，除非有很極致的需求，不然這個方案沒什麼大缺點。

下面整理一下我這次的實驗心得吧:
- 相同資料庫，在資料結構不同的狀況下，效能會有巨大差異。
- 如果只看搜尋效率，MongoDB 大多數情境下會贏
- 其實 MongoDB 跟 MySQL 都能處理這個案例，就看實際業務更關注哪塊的效能。

當然小弟的實驗可能有許多考量不足的地方，歡迎各位大神留言交流，謝謝。