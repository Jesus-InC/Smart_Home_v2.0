from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

import paho.mqtt.client as mqtt


class PublicadorPercepcion:
    """Publica la percepción de la laptop; nunca ordena mover el portón."""

    def __init__(self, cfg: Dict[str, Any], sin_mqtt: bool = False) -> None:
        self.cfg = cfg
        self.sin_mqtt = sin_mqtt
        self.conectado = False
        self._lock = threading.Lock()
        self._client: Optional[mqtt.Client] = None
        self._ultimos_individuales: Dict[str, str] = {}
        self._estado_porton = "ABIERTO" if sin_mqtt else "DESCONOCIDO"
        self._ultimo_estado_porton = time.monotonic() if sin_mqtt else 0.0

        if not sin_mqtt:
            mqtt_cfg = cfg["mqtt"]
            self._client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=str(mqtt_cfg.get("client_id", "laptop_percepcion_smarthome")),
            )
            topic_estado = str(mqtt_cfg.get("topic_estado", "casa/vision/laptop/estado"))
            self._client.will_set(topic_estado, "OFFLINE", qos=1, retain=True)
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

    @staticmethod
    def _conexion_correcta(reason_code: Any) -> bool:
        return (
            reason_code == 0
            or getattr(reason_code, "value", None) == 0
            or str(reason_code).strip().lower() in {"0", "success", "connection accepted"}
        )

    def conectar(self) -> None:
        if self.sin_mqtt:
            return
        assert self._client is not None
        mqtt_cfg = self.cfg["mqtt"]
        self._client.connect_async(
            str(mqtt_cfg.get("host", "192.168.1.19")),
            int(mqtt_cfg.get("port", 1883)),
            int(mqtt_cfg.get("keepalive", 60)),
        )
        self._client.loop_start()

    def cerrar(self) -> None:
        if self.sin_mqtt or self._client is None:
            return
        try:
            self.publicar_estado("OFFLINE")
            self._client.disconnect()
        finally:
            self._client.loop_stop()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        with self._lock:
            self.conectado = self._conexion_correcta(reason_code)
        if self.conectado:
            print("[MQTT] Laptop conectada al broker de la Raspberry")
            topic_porton = str(
                self.cfg["mqtt"].get(
                    "topic_porton_estado",
                    "casa/garaje/porton/estado",
                )
            )
            client.subscribe(topic_porton, qos=1)
            self.publicar_estado("ONLINE")
        else:
            print(f"[MQTT] No se pudo conectar: {reason_code}")


    def _on_message(self, client, userdata, msg) -> None:
        topic_porton = str(
            self.cfg["mqtt"].get(
                "topic_porton_estado",
                "casa/garaje/porton/estado",
            )
        )
        if msg.topic != topic_porton:
            return
        try:
            estado = msg.payload.decode("utf-8", errors="replace").strip().upper()
        except Exception:
            estado = "DESCONOCIDO"
        if estado not in {"ABIERTO", "CERRADO", "ABRIENDO", "CERRANDO", "DETENIDO"}:
            estado = "DESCONOCIDO"
        with self._lock:
            self._estado_porton = estado
            self._ultimo_estado_porton = time.monotonic()

    def obtener_estado_porton(self) -> Tuple[str, float]:
        with self._lock:
            estado = self._estado_porton
            ultimo = self._ultimo_estado_porton
        if self.sin_mqtt:
            return estado, 0.0
        edad = 999.0 if ultimo <= 0 else time.monotonic() - ultimo
        return estado, edad

    def fijar_estado_porton_local(self, estado: str) -> None:
        """Simula el estado del portón únicamente durante pruebas sin MQTT."""
        if not self.sin_mqtt:
            return
        estado = str(estado).strip().upper()
        if estado not in {"ABIERTO", "CERRADO", "ABRIENDO", "CERRANDO", "DETENIDO"}:
            return
        with self._lock:
            self._estado_porton = estado
            self._ultimo_estado_porton = time.monotonic()
        print(f"\n[PRUEBA LOCAL] Estado del portón = {estado}")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        with self._lock:
            self.conectado = False
        print(f"[MQTT] Laptop desconectada: {reason_code}")

    def publicar(self, topic: str, payload: Any, *, qos: int = 0, retain: bool = False) -> None:
        texto = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if self.sin_mqtt:
            return
        if self._client is not None:
            self._client.publish(topic, texto, qos=qos, retain=retain)

    def publicar_estado(self, estado: str) -> None:
        topic = str(self.cfg["mqtt"].get("topic_estado", "casa/vision/laptop/estado"))
        self.publicar(topic, estado, qos=1, retain=True)

    def publicar_percepcion(self, datos: Dict[str, Any]) -> None:
        topic = str(self.cfg["mqtt"].get("topic_percepcion", "casa/vision/percepcion"))

        self.publicar(topic, datos, qos=1, retain=False)

        if not bool(self.cfg.get("publicacion", {}).get("publicar_topicos_individuales", True)):
            return

        detalle = datos.get("score_detalle", {})
        individuales = {
            "casa/vision/camara_abc/estado": "ONLINE" if datos.get("camara_abc_ok") else "OFFLINE",
            "casa/vision/camara_d/estado": "ONLINE" if datos.get("camara_d_ok") else "OFFLINE",
            "casa/vision/vehiculo_detectado": int(bool(datos.get("vehiculo_detectado"))),
            "casa/vision/cantidad_vehiculos": int(datos.get("cantidad_vehiculos", 0)),
            "casa/vision/zona": datos.get("zona", "NINGUNA"),
            "casa/vision/trayectoria": datos.get("trayectoria", "DESCONOCIDA"),
            "casa/vision/score": int(datos.get("score_propietario", 0)),
            "casa/vision/score_visual": int(datos.get("score_visual", 0)),
            "casa/vision/score_bruto": int(datos.get("score_bruto", 0)),
            "casa/vision/score_visual_bruto": int(datos.get("score_visual_bruto", 0)),
            "casa/vision/perfil_dueno_zona": datos.get("perfil_dueno_zona", "NINGUNA"),
            "casa/vision/yolo_validado_hibrido": int(bool(datos.get("yolo_validado_hibrido"))),
            "casa/vision/yolo_motivo_hibrido": str(datos.get("yolo_motivo_hibrido", "")),
            "casa/vision/score_estable": int(bool(datos.get("score_estable"))),
            "casa/vision/muestras_estabilizacion": int(datos.get("muestras_estabilizacion", 0)),
            "casa/vision/score_detalle": detalle,
            "casa/vision/zona_bruta": datos.get("zona_bruta", "NINGUNA"),
            "casa/vision/trayectoria_bruta": datos.get("trayectoria_bruta", "DESCONOCIDA"),
            "casa/vision/tipo_vehiculo": datos.get("tipo_vehiculo", "NINGUNO"),
            "casa/vision/confianza": round(float(datos.get("confianza_deteccion", 0.0)), 3),
            "casa/vision/obstaculo_d": int(bool(datos.get("obstaculo_d"))),
            "casa/vision/obstaculo_d_bruto": int(bool(datos.get("obstaculo_d_bruto"))),
            "casa/vision/estado_d": datos.get("estado_d", "CALIBRANDO"),
            "casa/vision/estado_porton_percibido": datos.get("estado_porton", "DESCONOCIDO"),
            "casa/vision/modo_d": datos.get("modo_d", "DESCONOCIDO"),
            "casa/vision/template_d": int(datos.get("template_d", -1)),
            "casa/vision/error_ajuste_d": round(float(datos.get("error_ajuste_d", 0.0)), 3),
            "casa/vision/baja_iluminacion": int(bool(datos.get("baja_iluminacion"))),
        }

        for topic_i, payload_i in individuales.items():
            texto_i = (
                payload_i
                if isinstance(payload_i, str)
                else json.dumps(payload_i, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            )

            anterior = self._ultimos_individuales.get(topic_i)
            if anterior == texto_i:
                continue

            if topic_i in {"casa/vision/score", "casa/vision/score_visual", "casa/vision/score_bruto", "casa/vision/score_visual_bruto"} and anterior is not None:
                try:
                    if abs(int(payload_i) - int(anterior)) < 2:
                        continue
                except (TypeError, ValueError):
                    pass

            self._ultimos_individuales[topic_i] = texto_i
            self.publicar(topic_i, texto_i, qos=0, retain=True)
