import os
import json
import logging
import time
from kafka import KafkaConsumer
import psycopg2

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
KAFKA_TOPIC = "machine_events"
DB_HOST = os.getenv("DB_HOST", "timescaledb")
DB_NAME = os.getenv("DB_NAME", "industrial_data")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    while True:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            return conn
        except Exception as e:
            logger.warning(f"Database not ready, retrying... ({e})")
            time.sleep(5)

def main():
    logger.info("Starting Kafka to DB Agent...")
    
    # Connect to DB
    conn = get_db_connection()
    logger.info("Connected to Database")
    
    # Init Kafka Consumer
    consumer = None
    while True:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                auto_offset_reset='earliest',
                enable_auto_commit=True,
                group_id='db-writer-group',
                value_deserializer=lambda x: json.loads(x.decode('utf-8'))
            )
            logger.info(f"Subscribed to Kafka topic: {KAFKA_TOPIC}")
            break
        except Exception as e:
            logger.warning(f"Kafka not ready, retrying... ({e})")
            time.sleep(5)
    
    logger.info(f"Subscribed to Kafka topic: {KAFKA_TOPIC}")

    cursor = conn.cursor()
    
    for message in consumer:
        try:
            data = message.value
            # data structure: {"original_data": {"node_id":..., "value":..., "timestamp":...}, "context": {...}}
            
            orig = data.get("original_data", {})
            ctx = data.get("context", {})
            
            metric = orig.get("node_id")
            val = orig.get("value")
            ts = orig.get("timestamp") or time.strftime('%Y-%m-%d %H:%M:%S%z')
            
            operator = ctx.get("operator")
            
            # Determine value type
            val_num = None
            val_str = None
            
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                val_num = float(val)
            else:
                val_str = str(val)
                
            try:
                cursor.execute(
                    """
                    INSERT INTO opcua_data (time, metric, value_num, value_str, operator)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (ts, metric, val_num, val_str, operator)
                )
                conn.commit()
                logger.info(f"Inserted {metric}: {val}")
            except psycopg2.Error as e:
                logger.error(f"DB Error on Insert: {e}")
                conn.rollback()
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")

if __name__ == "__main__":
    main()
