from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import paho.mqtt.client as mqtt


ESCENARIOS = {
    "vacio": dict(vehiculo_detectado=False, cantidad_vehiculos=0, zona="NINGUNA", trayectoria="SIN_VEHICULO", score_propietario=0, obstaculo_d=False),
    "dueno_b": dict(vehiculo_detectado=True, cantidad_vehiculos=1, zona="B", trayectoria="QUIETO", score_propietario=84, obstaculo_d=False),
    "dueno_ingreso": dict(vehiculo_detectado=True, cantidad_vehiculos=1, zona="A", trayectoria="INGRESO", score_propietario=84, obstaculo_d=False),
    "ajeno_b": dict(vehiculo_detectado=True, cantidad_vehiculos=1, zona="B", trayectoria="QUIETO", score_propietario=22, obstaculo_d=False),
    "ajeno_c": dict(vehiculo_detectado=True, cantidad_vehiculos=1, zona="C", trayectoria="QUIETO", score_propietario=20, obstaculo_d=False),
    "obstaculo_d": dict(vehiculo_detectado=True, cantidad_vehiculos=1, zona="A", trayectoria="INGRESO", score_propietario=84, obstaculo_d=True),
    "dos_autos": dict(vehiculo_detectado=True, cantidad_vehiculos=2, zona="B", trayectoria="QUIETO", score_propietario=55, obstaculo_d=False),
    "falla_camara": dict(vehiculo_detectado=False, cantidad_vehiculos=0, zona="NINGUNA", trayectoria="SIN_VEHICULO", score_propietario=0, obstaculo_d=False, camara_abc_ok=False),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Simula percepción para probar la Raspberry sin cámaras")
    parser.add_argument("escenario", choices=sorted(ESCENARIOS))
    parser.add_argument("--config", default="config_laptop.json")
    parser.add_argument("--segundos", type=float, default=15.0)
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    mqtt_cfg = cfg["mqtt"]
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id="simulador_percepcion_smarthome")
    client.connect(str(mqtt_cfg["host"]), int(mqtt_cfg["port"]), int(mqtt_cfg.get("keepalive", 60)))
    client.loop_start()
    client.publish(str(mqtt_cfg.get("topic_estado", "casa/vision/laptop/estado")), "ONLINE", qos=1, retain=True)

    base = {
        "schema_version": 1,
        "session_id": "SIMULADOR",
        "calibrando": False,
        "camara_abc_ok": True,
        "camara_d_ok": True,
        "confianza_deteccion": 0.90,
        "confianza_obstaculo_d": 0.90,
        "baja_iluminacion": False,
        "yolo_activo": True,
        "yolo_disponible": True,
        "score_detalle": {"yolo": 25, "color": 20, "tamano": 12, "aspecto": 12, "silueta": 8, "trayectoria": 7, "total": 84},
        "tipo_vehiculo": "DUENO",
    }
    base.update(ESCENARIOS[args.escenario])

    print(f"Publicando escenario '{args.escenario}' durante {args.segundos} s")
    inicio = time.monotonic()
    secuencia = 0
    try:
        while time.monotonic() - inicio < args.segundos:
            datos = dict(base)
            datos["timestamp"] = time.time()
            datos["secuencia"] = secuencia
            client.publish(str(mqtt_cfg.get("topic_percepcion", "casa/vision/percepcion")), json.dumps(datos), qos=0, retain=False)
            secuencia += 1
            time.sleep(0.2)
    finally:
        client.publish(str(mqtt_cfg.get("topic_estado", "casa/vision/laptop/estado")), "OFFLINE", qos=1, retain=True)
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
