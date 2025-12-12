"""
Hydration Agent
Consumes MQTT messages, enriches them with context data from Redis 
(operator name, last maintenance date), and forwards to Kafka.
"""
import os
import json
import logging
import time
import redis
import paho.mqtt.client as mqtt
from kafka import KafkaProducer

# Configuration
MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt-broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "machine/data"
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
KAFKA_TOPIC = "machine_events"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Producers
redis_client = None
kafka_producer = None

def init_redis():
    global redis_client
    while True:
        try:
            redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            # Seed initial data if not exists
            if not redis_client.exists("context:operator"):
                redis_client.set("context:operator", "John Doe")
                logger.info("Seeded Redis: context:operator")
            if not redis_client.exists("context:last_maintenance"):
                redis_client.set("context:last_maintenance", "2025-10-01")
                logger.info("Seeded Redis: context:last_maintenance")
            logger.info(f"Connected to Redis at {REDIS_HOST}")
            break
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}. Retrying in 5s...")
            time.sleep(5)

def init_kafka():
    global kafka_producer
    logger.info(f"Connecting to Kafka at {KAFKA_BOOTSTRAP_SERVERS}...")
    while True:
        try:
            kafka_producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            logger.info("Connected to Kafka")
            break
        except Exception as e:
            logger.warning(f"Kafka not ready, retrying... ({e})")
            time.sleep(5)

def on_connect(client, userdata, flags, rc):
    logger.info(f"Connected to MQTT Broker with result code {rc}")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        logger.info(f"Received MQTT: {payload}")
        
        operator = redis_client.get("context:operator")
        last_maintenance = redis_client.get("context:last_maintenance")
        
        enriched_payload = {
            "original_data": payload,
            "context": {
                "operator": operator,
                "last_maintenance": last_maintenance,
                "enriched_at": time.time()
            }
        }
        
        if kafka_producer:
            kafka_producer.send(KAFKA_TOPIC, enriched_payload)
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")

def main():
    logger.info("Starting Hydration Agent...")
    
    # Init dependencies
    init_redis()
    init_kafka()
    
    # Init MQTT
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    
    while True:
        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            logger.error(f"MQTT Error/Disconnect: {e}. Reconnecting in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    main()
