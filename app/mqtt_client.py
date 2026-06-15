import json
import os

import paho.mqtt.client as mqtt

from app.models import SessionLocal
from app.services import (
    get_product_by_device,
    register_telemetry_with_alert,
)

BROKER = os.getenv("MQTT_BROKER_HOST", "mqtt")
PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))

USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"MQTT conectado RC={rc}")

    result, mid = client.subscribe(
        "coldchain/+/telemetry"
    )

    print(
        f"Suscripcion resultado={result}"
    )

def on_message(client, userdata, msg):

    print("================================")
    print("MENSAJE MQTT RECIBIDO")
    print("TOPIC:", msg.topic)
    print("PAYLOAD:", msg.payload.decode())
    print("================================")

    try:

        payload = json.loads(
            msg.payload.decode()
        )

        device_id = payload["device_id"]

        temperature = payload["temperature"]

        humidity = payload["humidity"]

        battery = payload.get("battery")

        db = SessionLocal()

        try:

            product = get_product_by_device(
                db,
                device_id
            )

            print(
                "PRODUCTO:",
                product
            )

            if not product:

                print(
                    f"Dispositivo no registrado: {device_id}"
                )

                return

            row = register_telemetry_with_alert(
                db=db,
                product=product,
                device_id=device_id,
                temperature=float(temperature),
                humidity=float(humidity),
                battery=battery,
                raw_json=json.dumps(payload),
            )

            print(
                f"Telemetry guardada ID={row.id}"
            )

        finally:
            db.close()

    except Exception as e:

        print(
            f"ERROR MQTT: {repr(e)}"
        )

client = mqtt.Client()

if USERNAME and PASSWORD:
    client.username_pw_set(
        USERNAME,
        PASSWORD
    )
def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    print(
        f"SUBSCRITO mid={mid} qos={granted_qos}"
    )
    
client.on_connect = on_connect
client.on_message = on_message
client.on_subscribe = on_subscribe

client.connect(
    BROKER,
    PORT,
    60
)

client.loop_start()