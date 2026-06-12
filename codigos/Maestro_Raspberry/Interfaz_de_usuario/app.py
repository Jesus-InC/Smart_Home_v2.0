from __future__ import annotations

import threading
import time
from typing import Any, Dict

from flask import Flask, jsonify, render_template, request
import paho.mqtt.client as mqtt

from config import MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE, WEB_HOST, WEB_PORT

app = Flask(__name__)

estado: Dict[str, Any] = {
    "mqtt_conectado": False,
    "ultima_actualizacion": "--",
    "topicos": {},
}

lock_estado = threading.Lock()

cliente_mqtt = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
    client_id="rasp_interfaz_smarthome"
)


def guardar_topico(topic: str, payload: str) -> None:
    with lock_estado:
        estado["topicos"][topic] = payload
        estado["ultima_actualizacion"] = time.strftime("%H:%M:%S")


def publicar(topic: str, payload: str, retain: bool = False) -> None:
    cliente_mqtt.publish(topic, payload, qos=0, retain=retain)


def mqtt_conexion_correcta(reason_code) -> bool:
    if reason_code == 0:
        return True

    valor = getattr(reason_code, "value", None)
    if valor == 0:
        return True

    texto = str(reason_code).strip().lower()
    return texto in ("0", "success", "connection accepted")


def on_connect(client, userdata, flags, reason_code, properties):
    conectado = mqtt_conexion_correcta(reason_code)

    with lock_estado:
        estado["mqtt_conectado"] = conectado

    if conectado:
        print("MQTT conectado correctamente")
        client.subscribe("casa/#")
        guardar_topico("interfaz/estado", "MQTT conectado")
    else:
        print(f"Error conectando MQTT: {reason_code}")
        guardar_topico("interfaz/estado", f"MQTT error: {reason_code}")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    with lock_estado:
        estado["mqtt_conectado"] = False

    print(f"MQTT desconectado: {reason_code}")
    guardar_topico("interfaz/estado", "MQTT desconectado")


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8", errors="replace")
    except Exception:
        payload = str(msg.payload)

    guardar_topico(msg.topic, payload)


def iniciar_mqtt() -> None:
    cliente_mqtt.on_connect = on_connect
    cliente_mqtt.on_disconnect = on_disconnect
    cliente_mqtt.on_message = on_message

    cliente_mqtt.connect_async(MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE)
    cliente_mqtt.loop_start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/estado")
def api_estado():
    with lock_estado:
        topicos = dict(estado["topicos"])
        conectado = estado["mqtt_conectado"]
        ultima_actualizacion = estado["ultima_actualizacion"]

    resumen = {
        "mqtt_conectado": conectado,
        "ultima_actualizacion": ultima_actualizacion,

        "modo_interior": topicos.get("casa/interior/modo/estado", "--"),
        "estop": topicos.get("casa/sistema/estop/estado", "--"),
        "estado_seguro": topicos.get("casa/sistema/estado_seguro", "--"),

        "wifi_estado": topicos.get("casa/sistema/wifi/estado", "--"),
        "wifi_ip": topicos.get("casa/sistema/wifi/ip", "--"),
        "wifi_rssi": topicos.get("casa/sistema/wifi/rssi", "--"),

        "ultima_falla": topicos.get("casa/sistema/falla/ultima", "--"),
        "contador_fallas": topicos.get("casa/sistema/falla/contador", "--"),

        "foco": topicos.get("casa/interior/foco/estado", "0"),
        "vent": topicos.get("casa/interior/vent/estado", "0"),
        "bomba": topicos.get("casa/interior/bomba/estado", "0"),

        "foco_override": topicos.get("casa/interior/foco/override", "0"),
        "vent_override": topicos.get("casa/interior/vent/override", "0"),
        "bomba_override": topicos.get("casa/interior/bomba/override", "0"),

        "temp": topicos.get("casa/interior/sensor/temp", "--"),
        "hum_amb": topicos.get("casa/interior/sensor/hum_amb", "--"),
        "hum_suelo": topicos.get("casa/interior/sensor/hum_suelo", "--"),

        "zc_freq": topicos.get("casa/foco/zc/freq", "--"),

        "garaje_modo": topicos.get("casa/garaje/modo/estado", "--"),
        "porton": topicos.get("casa/garaje/porton/estado", "--"),
        "alarma": topicos.get("casa/garaje/alarma/estado", "0"),

        "temp_min": topicos.get("casa/config/interior/temp_min/estado", topicos.get("casa/interior/config/temp_min/estado", "22")),
        "temp_max": topicos.get("casa/config/interior/temp_max/estado", topicos.get("casa/interior/config/temp_max/estado", "28")),
        "hum_amb_min": topicos.get("casa/config/interior/hum_amb_min/estado", topicos.get("casa/interior/config/hum_amb_min/estado", "45")),
        "hum_amb_max": topicos.get("casa/config/interior/hum_amb_max/estado", topicos.get("casa/interior/config/hum_amb_max/estado", "70")),
        "hum_suelo_min": topicos.get("casa/config/interior/hum_suelo_min/estado", topicos.get("casa/interior/config/hum_suelo_min/estado", "35")),
        "hum_suelo_max": topicos.get("casa/config/interior/hum_suelo_max/estado", topicos.get("casa/interior/config/hum_suelo_max/estado", "55")),
        "bomba_umbral": topicos.get("casa/config/interior/bomba_umbral/estado", topicos.get("casa/interior/config/bomba_umbral/estado", "35")),

        "presencia": topicos.get("casa/ia/presencia", "--"),
        "prob_lluvia": topicos.get("casa/ia/prob_lluvia", "--"),
    }

    return jsonify(resumen)


@app.route("/api/publicar", methods=["POST"])
def api_publicar():
    datos = request.get_json(force=True)

    topic = str(datos.get("topic", "")).strip()
    payload = str(datos.get("payload", "")).strip()

    if not topic or not topic.startswith("casa/"):
        return jsonify({"ok": False, "error": "Topico invalido"}), 400

    publicar(topic, payload)

    return jsonify({
        "ok": True,
        "topic": topic,
        "payload": payload
    })


@app.route("/api/config", methods=["POST"])
def api_config():
    datos = request.get_json(force=True)

    mapa = {
        "temp_min": "casa/config/interior/temp_min/cmd",
        "temp_max": "casa/config/interior/temp_max/cmd",
        "hum_amb_min": "casa/config/interior/hum_amb_min/cmd",
        "hum_amb_max": "casa/config/interior/hum_amb_max/cmd",
        "hum_suelo_min": "casa/config/interior/hum_suelo_min/cmd",
        "hum_suelo_max": "casa/config/interior/hum_suelo_max/cmd",
        "bomba_umbral": "casa/config/interior/bomba_umbral/cmd",
    }

    publicados = []

    for clave, topic in mapa.items():
        if clave in datos:
            valor = str(datos[clave]).strip()
            publicar(topic, valor)
            publicados.append({"topic": topic, "payload": valor})

    return jsonify({
        "ok": True,
        "publicados": publicados
    })


@app.route("/api/topicos")
def api_topicos():
    with lock_estado:
        topicos = dict(sorted(estado["topicos"].items()))

    return jsonify(topicos)


if __name__ == "__main__":
    iniciar_mqtt()
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)
