"""
OPC-UA to MQTT Agent
Subscribes to all OPC-UA variable changes and publishes them to MQTT.
Automatically reconnects on connection failures.
"""
import asyncio
import os
import json
import logging
from typing import Any

from asyncua import Client, Node, ua
import paho.mqtt.client as mqtt

# Configuration from environment variables
OPCUA_ENDPOINT = os.getenv("OPCUA_ENDPOINT", "opc.tcp://opcua-server:4840/pnp/")
MQTT_BROKER = os.getenv("MQTT_BROKER", "mqtt-broker")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_TOPIC = "machine/data"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SubscriptionHandler:
    """Handles OPC-UA data change notifications and publishes to MQTT."""
    def __init__(self, mqtt_client: mqtt.Client, node_map: dict):
        self.mqtt_client = mqtt_client
        self.node_map = node_map  # Maps NodeID to human-readable name

    def datachange_notification(self, node: Node, val: Any, data: ua.DataValue):
        """
        Callback for data change events.
        """
        try:
            node_id_raw = node.nodeid.Identifier
            node_name = self.node_map.get(node_id_raw, str(node_id_raw))
            
            timestamp = None
            if hasattr(data, 'SourceTimestamp'):
                timestamp = data.SourceTimestamp.isoformat()
            elif hasattr(data, 'monitored_item') and hasattr(data.monitored_item, 'Value') and hasattr(data.monitored_item.Value, 'SourceTimestamp'):
                 timestamp = data.monitored_item.Value.SourceTimestamp.isoformat()
            
            if not timestamp:
                import datetime
                timestamp = datetime.datetime.now().isoformat()

            payload = {
                "node_id": str(node_name),
                "value": val,
                "timestamp": timestamp
            }
            
            inf = self.mqtt_client.publish(MQTT_TOPIC, json.dumps(payload))
            inf.wait_for_publish(timeout=2)
            if inf.is_published():
                 logger.info(f"Published to MQTT: {node_name}")
            else:
                 logger.error(f"Failed to publish: {node_name}")
            
        except Exception as e:
            logger.error(f"Error processing data change: {e}")

async def main():
    logger.info("Starting OPC-UA to MQTT Agent...")
    
    # Setup MQTT
    if hasattr(mqtt, 'CallbackAPIVersion'):
        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    else:
        mqtt_client = mqtt.Client()

    # MQTT Connection Loop
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            mqtt_client.loop_start()
            logger.info(f"Connected to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}")
            break
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}. Retrying in 5s...")
            await asyncio.sleep(5)

    # Connect to OPC-UA with Retry
    client = None
    while True:
        try:
            client = Client(url=OPCUA_ENDPOINT)
            await client.connect()
            logger.info(f"Connected to OPC-UA Server at {OPCUA_ENDPOINT}")
            
            # Get Namespace Index
            idx = await client.get_namespace_index("urn:example:pick-and-place")
            
            # Get Root Object safely by browsing
            objects = client.nodes.objects
            children = await objects.get_children()
            root_obj = None
            
            for child in children:
                bn = await child.read_browse_name()
                # Check NodeID namespace
                if bn.Name == "PickAndPlace" and child.nodeid.NamespaceIndex == idx:
                    root_obj = child
                    logger.info(f"Found Root Object: {bn}")
                    break
            
            if not root_obj:
                logger.error(f"Node 'PickAndPlace' not found in namespace {idx}. Retrying...")
                await client.disconnect()
                await asyncio.sleep(5)
                continue

            # Browse variables
            children = await root_obj.get_children()
            nodes_to_subscribe = []
            node_map = {}
            for child in children:
                node_class = await child.read_node_class()
                if node_class == ua.NodeClass.Variable:
                    nodes_to_subscribe.append(child)
                    bn = await child.read_browse_name()
                    node_map[child.nodeid.Identifier] = bn.Name
                    
            logger.info(f"Found {len(nodes_to_subscribe)} variables.")
            
            # Create Subscription
            handler = SubscriptionHandler(mqtt_client, node_map)
            sub = await client.create_subscription(500, handler)
            handle = await sub.subscribe_data_change(nodes_to_subscribe)
            logger.info("Subscribed to data changes.")
            
            while True:
                await asyncio.sleep(5)
                if root_obj:
                    try:
                        await root_obj.read_browse_name()
                    except Exception:
                        raise ConnectionError("Active check failed")
                
        except asyncio.CancelledError:
            logger.info("Task cancelled")
            break
        except Exception as e:
            logger.error(f"OPC-UA Error/Disconnect: {e}. Reconnecting in 5s...")
            if client:
                try:
                    await client.disconnect()
                except:
                    pass
            await asyncio.sleep(5)
    
    if mqtt_client:
        mqtt_client.loop_stop()
        logger.info("MQTT Disconnected")

if __name__ == "__main__":
    asyncio.run(main())
