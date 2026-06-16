from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import paho.mqtt.client as mqtt


Punto = Tuple[int, int]
PoligonoNorm = List[List[float]]


@dataclass
class Deteccion:
    hay: bool
    zona: str = "NINGUNA"
    bbox: Tuple[int, int, int, int] = (0, 0, 0, 0)
    centro: Tuple[int, int] = (0, 0)
    area_contorno: float = 0.0
    area_bbox: float = 0.0
    area_ratio: float = 0.0
    aspecto: float = 0.0
    extent: float = 0.0
    confianza: float = 0.0
    hsv_mediana: Tuple[int, int, int] = (0, 0, 0)


@dataclass
class ScoreDetalle:
    total: int = 0
    yolo: int = 0
    color: int = 0
    tamano: int = 0
    aspecto: int = 0
    silueta: int = 0
    trayectoria: int = 0


class EstadoMqtt:
    def __init__(self) -> None:
        self.modo_garaje = "NORMAL"
        self.porton = "--"
        self.alarma = "0"
        self.estop = "0"
        self.fc_abierto = "0"
        self.fc_cerrado = "0"
        self.conectado = False


class PublicadorMqtt:
    def __init__(self, cfg: Dict[str, Any], sin_mqtt: bool = False) -> None:
        self.cfg = cfg
        self.sin_mqtt = sin_mqtt
        self.estado = EstadoMqtt()
        self.ultimo_evento = ""
        self.t_ultimo_evento = 0.0

        self.client: Optional[mqtt.Client] = None
        if not self.sin_mqtt:
            self.client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=str(cfg["mqtt"].get("client_id", "rasp_vision_garaje")),
            )
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message

    def conectar(self) -> None:
        if self.sin_mqtt:
            print("[MQTT] Modo sin MQTT activo")
            return
        assert self.client is not None
        host = self.cfg["mqtt"].get("host", "127.0.0.1")
        port = int(self.cfg["mqtt"].get("port", 1883))
        keepalive = int(self.cfg["mqtt"].get("keepalive", 60))
        self.client.connect_async(host, port, keepalive)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        self.estado.conectado = str(reason_code) in ("0", "Success", "Connection accepted") or getattr(reason_code, "value", None) == 0
        if self.estado.conectado:
            print("[MQTT] Vision conectada")
            client.subscribe("casa/garaje/#")
            client.subscribe("casa/sistema/estop/estado")
            client.subscribe("casa/fisico/fc_abierto/estado")
            client.subscribe("casa/fisico/fc_cerrado/estado")
            self.publicar("casa/vision/estado", "ONLINE", retain=True)
        else:
            print(f"[MQTT] Error conectando: {reason_code}")

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        self.estado.conectado = False
        print(f"[MQTT] Vision desconectada: {reason_code}")

    def on_message(self, client, userdata, msg) -> None:
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        topic = msg.topic

        if topic == "casa/garaje/modo/estado":
            self.estado.modo_garaje = payload.upper()
        elif topic == "casa/garaje/porton/estado":
            self.estado.porton = payload.upper()
        elif topic == "casa/garaje/alarma/estado":
            self.estado.alarma = payload
        elif topic == "casa/sistema/estop/estado":
            self.estado.estop = payload
        elif topic == "casa/fisico/fc_abierto/estado":
            self.estado.fc_abierto = payload
        elif topic == "casa/fisico/fc_cerrado/estado":
            self.estado.fc_cerrado = payload

    def publicar(self, topic: str, payload: Any, retain: bool = False) -> None:
        texto = str(payload)
        if self.sin_mqtt:
            print(f"[MQTT sim] {topic} = {texto}")
            return
        if self.client is not None:
            self.client.publish(topic, texto, qos=0, retain=retain)

    def evento(self, mensaje: str, cooldown: float = 4.0) -> None:
        ahora = time.monotonic()
        if mensaje == self.ultimo_evento and (ahora - self.t_ultimo_evento) < cooldown:
            return
        self.ultimo_evento = mensaje
        self.t_ultimo_evento = ahora
        print(f"[EVENTO] {mensaje}")
        self.publicar("casa/vision/evento", mensaje)


class DetectorMovimiento:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.bg_abc = cv2.createBackgroundSubtractorMOG2(history=180, varThreshold=45, detectShadows=False)
        self.bg_d = cv2.createBackgroundSubtractorMOG2(history=120, varThreshold=40, detectShadows=False)

    @staticmethod
    def poligono_pix(poly_norm: PoligonoNorm, w: int, h: int) -> np.ndarray:
        pts = []
        for x, y in poly_norm:
            pts.append([int(x * w), int(y * h)])
        return np.array(pts, dtype=np.int32)

    @staticmethod
    def mascara_zonas(frame: np.ndarray, zonas: Dict[str, PoligonoNorm], nombres: List[str]) -> np.ndarray:
        h, w = frame.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        for nombre in nombres:
            if nombre in zonas:
                pts = DetectorMovimiento.poligono_pix(zonas[nombre], w, h)
                cv2.fillPoly(mask, [pts], 255)
        return mask

    @staticmethod
    def punto_en_zona(punto: Tuple[int, int], frame: np.ndarray, zonas: Dict[str, PoligonoNorm], nombres: List[str]) -> str:
        h, w = frame.shape[:2]
        for nombre in nombres:
            pts = DetectorMovimiento.poligono_pix(zonas[nombre], w, h)
            if cv2.pointPolygonTest(pts, punto, False) >= 0:
                return nombre
        return "NINGUNA"

    @staticmethod
    def _limpiar_mascara(mask: np.ndarray) -> np.ndarray:
        _, binaria = cv2.threshold(mask, 180, 255, cv2.THRESH_BINARY)
        kernel = np.ones((5, 5), np.uint8)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel, iterations=1)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel, iterations=2)
        return binaria

    def detectar_abc(self, frame: np.ndarray) -> Deteccion:
        zonas = self.cfg["zonas"]
        det_cfg = self.cfg["deteccion"]
        learning_rate = float(det_cfg.get("learning_rate", 0.001))
        area_min = int(det_cfg.get("area_min_abc", 900))

        mask_zonas = self.mascara_zonas(frame, zonas, ["A", "B", "C"])
        fg = self.bg_abc.apply(frame, learningRate=learning_rate)
        fg = cv2.bitwise_and(fg, fg, mask=mask_zonas)
        fg = self._limpiar_mascara(fg)

        contornos, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contornos = [c for c in contornos if cv2.contourArea(c) >= area_min]
        if not contornos:
            return Deteccion(False)

        c = max(contornos, key=cv2.contourArea)
        area = float(cv2.contourArea(c))
        x, y, w, h = cv2.boundingRect(c)
        if w <= 0 or h <= 0:
            return Deteccion(False)

        cx, cy = x + w // 2, y + h // 2
        zona = self.punto_en_zona((cx, cy), frame, zonas, ["A", "B", "C"])
        area_bbox = float(w * h)
        area_ratio = area_bbox / float(frame.shape[0] * frame.shape[1])
        aspecto = float(w) / float(h)
        extent = area / area_bbox if area_bbox > 0 else 0.0
        confianza = min(1.0, area / float(max(area_min * 4, 1)))

        recorte = frame[max(0, y):y + h, max(0, x):x + w]
        hsv_mediana = (0, 0, 0)
        if recorte.size > 0:
            hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
            hsv_mediana = tuple(int(v) for v in np.median(hsv.reshape(-1, 3), axis=0))

        return Deteccion(
            hay=True,
            zona=zona,
            bbox=(x, y, w, h),
            centro=(cx, cy),
            area_contorno=area,
            area_bbox=area_bbox,
            area_ratio=area_ratio,
            aspecto=aspecto,
            extent=extent,
            confianza=confianza,
            hsv_mediana=hsv_mediana,
        )

    def detectar_d(self, frame: np.ndarray) -> Tuple[bool, float, Optional[Tuple[int, int, int, int]]]:
        zonas = self.cfg["zonas"]
        det_cfg = self.cfg["deteccion"]
        learning_rate = float(det_cfg.get("learning_rate", 0.001))
        area_min = int(det_cfg.get("area_min_d", 650))

        mask_zona = self.mascara_zonas(frame, zonas, ["D"])
        fg = self.bg_d.apply(frame, learningRate=learning_rate)
        fg = cv2.bitwise_and(fg, fg, mask=mask_zona)
        fg = self._limpiar_mascara(fg)

        contornos, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contornos = [c for c in contornos if cv2.contourArea(c) >= area_min]
        if not contornos:
            return False, 0.0, None

        c = max(contornos, key=cv2.contourArea)
        area = float(cv2.contourArea(c))
        x, y, w, h = cv2.boundingRect(c)
        confianza = min(1.0, area / float(max(area_min * 3, 1)))
        return True, confianza, (x, y, w, h)


class LogicaVisionGaraje:
    def __init__(self, cfg: Dict[str, Any], mqtt_pub: PublicadorMqtt) -> None:
        self.cfg = cfg
        self.mqtt = mqtt_pub
        self.historial: List[Tuple[float, str, Tuple[int, int]]] = []
        self.zona_actual = "NINGUNA"
        self.zona_anterior = "NINGUNA"
        self.t_inicio_zona = time.monotonic()
        self.t_ultimo_comando = 0.0
        self.frames_sin_vehiculo = 0
        self.alarma_vision_activa = False

    @staticmethod
    def _puntaje_lineal(valor: float, esperado: float, tolerancia: float, puntos: int) -> int:
        if tolerancia <= 0:
            return puntos if abs(valor - esperado) < 1e-6 else 0
        error = abs(valor - esperado)
        if error >= tolerancia:
            return 0
        return int(round(puntos * (1.0 - error / tolerancia)))

    @staticmethod
    def _dist_hue(h1: int, h2: int) -> int:
        d = abs(int(h1) - int(h2))
        return min(d, 180 - d)

    def actualizar_historial(self, det: Deteccion) -> None:
        ahora = time.monotonic()
        if det.hay:
            self.frames_sin_vehiculo = 0
            if det.zona != self.zona_actual:
                self.zona_anterior = self.zona_actual
                self.zona_actual = det.zona
                self.t_inicio_zona = ahora
            self.historial.append((ahora, det.zona, det.centro))
        else:
            self.frames_sin_vehiculo += 1
            if self.frames_sin_vehiculo >= int(self.cfg["deteccion"].get("frames_perdidos_para_limpiar", 10)):
                self.zona_anterior = self.zona_actual
                self.zona_actual = "NINGUNA"
                self.t_inicio_zona = ahora

        self.historial = [h for h in self.historial if ahora - h[0] <= 8.0]

    def trayectoria(self, det: Deteccion) -> str:
        if not det.hay:
            return "NINGUNA"

        zonas_recientes = [z for _, z, _ in self.historial if z != "NINGUNA"]
        if len(zonas_recientes) >= 2 and "B" in zonas_recientes[:-1] and zonas_recientes[-1] == "A":
            return "INGRESO"

        segundos_a = float(self.cfg["tiempos"].get("abrir_si_dueno_aparece_en_a_segundos", 0.0))
        if det.zona == "A" and segundos_a > 0 and (time.monotonic() - self.t_inicio_zona) >= segundos_a:
            return "INGRESO_PROBABLE"

        if det.zona == "B":
            return "FRENTE_GARAJE"
        if det.zona == "C":
            return "LATERAL"
        return "INCIERTA"

    def calcular_score(self, det: Deteccion, trayectoria: str) -> ScoreDetalle:
        score_cfg = self.cfg["score"]
        perfil = self.cfg["perfil_dueno"]
        total = ScoreDetalle()

        # YOLO se integrará después. Por ahora no suma, salvo que se active un detector externo.
        total.yolo = 0

        hsv_c = perfil.get("hsv_centro", [100, 120, 120])
        hsv_tol = perfil.get("hsv_tolerancia", [18, 80, 90])
        h, s, v = det.hsv_mediana
        dh = self._dist_hue(h, int(hsv_c[0])) / max(float(hsv_tol[0]), 1.0)
        ds = abs(s - int(hsv_c[1])) / max(float(hsv_tol[1]), 1.0)
        dv = abs(v - int(hsv_c[2])) / max(float(hsv_tol[2]), 1.0)
        error_color = max(dh, ds, dv)
        total.color = 0 if error_color >= 1.0 else int(round(int(score_cfg.get("p_color", 25)) * (1.0 - error_color)))

        total.tamano = self._puntaje_lineal(
            det.area_ratio,
            float(perfil.get("area_ratio_esperada", 0.055)),
            float(perfil.get("area_ratio_tolerancia", 0.045)),
            int(score_cfg.get("p_tamano", 15)),
        )
        total.aspecto = self._puntaje_lineal(
            det.aspecto,
            float(perfil.get("aspecto_esperado", 1.8)),
            float(perfil.get("aspecto_tolerancia", 0.75)),
            int(score_cfg.get("p_aspecto", 15)),
        )
        total.silueta = self._puntaje_lineal(
            det.extent,
            float(perfil.get("extent_esperado", 0.55)),
            float(perfil.get("extent_tolerancia", 0.35)),
            int(score_cfg.get("p_silueta", 10)),
        )
        total.trayectoria = int(score_cfg.get("p_trayectoria", 10)) if trayectoria in ("INGRESO", "INGRESO_PROBABLE") else 0
        total.total = total.yolo + total.color + total.tamano + total.aspecto + total.silueta + total.trayectoria
        return total

    def _puede_publicar_comando(self) -> bool:
        ahora = time.monotonic()
        cooldown = float(self.cfg["tiempos"].get("cooldown_comando", 5.0))
        if ahora - self.t_ultimo_comando < cooldown:
            return False
        self.t_ultimo_comando = ahora
        return True

    def _publicar_comando(self, topic: str, payload: str) -> None:
        if self._puede_publicar_comando():
            self.mqtt.publicar(topic, payload)

    def _alarma(self, activa: bool, razon: str = "") -> None:
        if activa == self.alarma_vision_activa:
            return
        self.alarma_vision_activa = activa
        self.mqtt.publicar("casa/garaje/alarma/cmd", "ON" if activa else "OFF")
        if razon:
            self.mqtt.evento(razon, cooldown=float(self.cfg["tiempos"].get("cooldown_evento", 4.0)))

    def decidir(self, det: Deteccion, obstaculo_d: bool, camaras_ok: bool) -> Tuple[str, ScoreDetalle, str]:
        self.actualizar_historial(det)
        tray = self.trayectoria(det)
        score = self.calcular_score(det, tray) if det.hay else ScoreDetalle()

        modo = self.mqtt.estado.modo_garaje.upper()
        porton = self.mqtt.estado.porton.upper()
        estop = str(self.mqtt.estado.estop).strip() == "1"
        seguridad = self.cfg["seguridad"]
        comandos = self.cfg["comandos"]
        decision = "MONITOREANDO"

        if estop:
            self._alarma(False)
            return "E-STOP activo: vision solo monitorea", score, tray

        if not camaras_ok:
            self.mqtt.publicar("casa/vision/decision", "FALLA_CAMARA")
            if seguridad.get("forzar_modo_seguro_si_falla_camara", True):
                self._publicar_comando("casa/garaje/modo/cmd", "SEGURO")
            if seguridad.get("activar_alarma_en_modo_seguro", True):
                self._alarma(True, "Falla de camara: modo seguro")
            return "Falla de cámara: modo seguro", score, tray

        if obstaculo_d:
            self.mqtt.publicar("casa/vision/obstaculo_d", "1")
            if seguridad.get("detener_si_obstaculo_d", True):
                aplica_en_manual = seguridad.get("seguridad_d_activa_en_manual", True)
                if porton in ("ABRIENDO", "CERRANDO") and (modo != "MANUAL" or aplica_en_manual):
                    self._publicar_comando("casa/garaje/porton/cmd", comandos.get("stop", "STOP"))
                    decision = "Obstáculo en D: STOP portón"
                    self.mqtt.evento(decision)
                    return decision, score, tray
        else:
            self.mqtt.publicar("casa/vision/obstaculo_d", "0")

        if modo == "SEGURO":
            return "Garaje en modo SEGURO: no hay acciones automáticas", score, tray

        if modo == "MANUAL":
            self._alarma(False)
            return "Garaje en MANUAL: vision solo monitorea", score, tray

        if not det.hay:
            self._alarma(False)
            return "Sin vehículo detectado", score, tray

        umbral_dueno = int(self.cfg["score"].get("umbral_dueno", 70))
        umbral_dudoso = int(self.cfg["score"].get("umbral_dudoso", 40))
        confianza_min = float(self.cfg["deteccion"].get("confianza_minima", 0.45))
        tiempo_zona = time.monotonic() - self.t_inicio_zona

        tipo = "DUENO" if score.total >= umbral_dueno else "DUDOSO" if score.total >= umbral_dudoso else "AJENO"
        self.mqtt.publicar("casa/vision/tipo_vehiculo", tipo)

        if modo == "VISITA":
            self._alarma(False)
            return f"Modo VISITA: se registra {tipo} en zona {det.zona}, sin alarma", score, tray

        if det.confianza < confianza_min:
            self._alarma(False)
            self.mqtt.evento("Detección de baja confianza: no se ejecuta acción")
            return "Baja confianza: no se ejecuta acción", score, tray

        if det.zona == "A":
            if score.total >= umbral_dueno and tray in ("INGRESO", "INGRESO_PROBABLE") and not obstaculo_d:
                if porton not in ("ABIERTO", "ABRIENDO"):
                    self._publicar_comando("casa/garaje/porton/cmd", comandos.get("abrir", "ABRIR"))
                    self._alarma(False)
                    decision = "Dueño en zona A con trayectoria válida: abrir portón"
                else:
                    decision = "Dueño en zona A, pero el portón ya está abierto/abriendo"
                self.mqtt.evento(decision)
                return decision, score, tray

            if score.total >= umbral_dudoso:
                self._alarma(False)
                decision = "Vehículo dudoso en zona A: no abrir, notificar"
                self.mqtt.evento(decision)
                return decision, score, tray

            if tiempo_zona >= float(self.cfg["tiempos"].get("t_alerta_a", 10.0)):
                self._alarma(True, "Vehículo ajeno permanece en zona A")
                return "Ajeno en A con permanencia: alarma", score, tray
            return "Ajeno en A: monitoreando permanencia", score, tray

        if det.zona == "B":
            if score.total >= umbral_dueno:
                self._alarma(False)
                return "Dueño en zona B: no abrir, monitorear", score, tray

            if tiempo_zona >= float(self.cfg["tiempos"].get("t_bloqueo_b", 12.0)):
                self._alarma(True, "Vehículo no autorizado bloquea zona B")
                return "Ajeno en B con permanencia: alarma", score, tray
            self._alarma(False)
            return "Ajeno/dudoso en B: esperando permanencia mínima", score, tray

        if det.zona == "C":
            if score.total >= umbral_dueno:
                self._alarma(False)
                return "Dueño en zona C: monitorear", score, tray
            self._alarma(False)
            self.mqtt.evento("Vehículo ajeno en zona C: solo notificación")
            return "Ajeno en C: solo notificación", score, tray

        return decision, score, tray


def dibujar_zonas(frame: np.ndarray, zonas: Dict[str, PoligonoNorm], nombres: List[str]) -> None:
    h, w = frame.shape[:2]
    for nombre in nombres:
        if nombre not in zonas:
            continue
        pts = DetectorMovimiento.poligono_pix(zonas[nombre], w, h)
        cv2.polylines(frame, [pts], True, (255, 255, 255), 2)
        x, y = pts[0]
        cv2.putText(frame, nombre, (int(x), int(y) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)


def abrir_camara(indice: int, ancho: int, alto: int, fps: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(indice)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def cargar_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vision artificial para garaje SmartHome v2.0")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config_vision.json")))
    parser.add_argument("--mostrar", action="store_true", help="Muestra ventanas OpenCV para depuración")
    parser.add_argument("--sin-mqtt", action="store_true", help="Ejecuta sin publicar MQTT")
    args = parser.parse_args()

    cfg = cargar_config(args.config)
    cam_cfg = cfg["camaras"]
    ancho = int(cam_cfg.get("ancho", 640))
    alto = int(cam_cfg.get("alto", 480))
    fps = int(cam_cfg.get("fps", 15))

    mqtt_pub = PublicadorMqtt(cfg, sin_mqtt=args.sin_mqtt)
    mqtt_pub.conectar()

    cap_abc = abrir_camara(int(cam_cfg.get("abc", 0)), ancho, alto, fps)
    cap_d = abrir_camara(int(cam_cfg.get("d", 1)), ancho, alto, fps)

    detector = DetectorMovimiento(cfg)
    logica = LogicaVisionGaraje(cfg, mqtt_pub)

    if not cap_abc.isOpened():
        mqtt_pub.publicar("casa/vision/camara_abc/estado", "FALLA", retain=True)
        print("[ERROR] No se pudo abrir cámara ABC")
    if not cap_d.isOpened():
        mqtt_pub.publicar("casa/vision/camara_d/estado", "FALLA", retain=True)
        print("[ERROR] No se pudo abrir cámara D")

    t_pub_estado = 0.0
    try:
        while True:
            ok_abc, frame_abc = cap_abc.read() if cap_abc.isOpened() else (False, None)
            ok_d, frame_d = cap_d.read() if cap_d.isOpened() else (False, None)
            camaras_ok = bool(ok_abc and ok_d)

            det = Deteccion(False)
            obstaculo_d = False
            bbox_d = None
            conf_d = 0.0

            if ok_abc and frame_abc is not None:
                det = detector.detectar_abc(frame_abc)
            if ok_d and frame_d is not None:
                obstaculo_d, conf_d, bbox_d = detector.detectar_d(frame_d)

            decision, score, tray = logica.decidir(det, obstaculo_d, camaras_ok)

            ahora = time.monotonic()
            if ahora - t_pub_estado >= 1.0:
                t_pub_estado = ahora
                mqtt_pub.publicar("casa/vision/camara_abc/estado", "OK" if ok_abc else "FALLA", retain=True)
                mqtt_pub.publicar("casa/vision/camara_d/estado", "OK" if ok_d else "FALLA", retain=True)
                mqtt_pub.publicar("casa/vision/vehiculo_detectado", "1" if det.hay else "0")
                mqtt_pub.publicar("casa/vision/zona", det.zona if det.hay else "NINGUNA")
                mqtt_pub.publicar("casa/vision/score", score.total)
                mqtt_pub.publicar("casa/vision/score_detalle", json.dumps(score.__dict__, ensure_ascii=False))
                mqtt_pub.publicar("casa/vision/trayectoria", tray)
                mqtt_pub.publicar("casa/vision/confianza", f"{det.confianza:.2f}")
                mqtt_pub.publicar("casa/vision/decision", decision)

            if args.mostrar:
                if ok_abc and frame_abc is not None:
                    dibujar_zonas(frame_abc, cfg["zonas"], ["A", "B", "C"])
                    if det.hay:
                        x, y, w, h = det.bbox
                        cv2.rectangle(frame_abc, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        cv2.circle(frame_abc, det.centro, 4, (0, 255, 0), -1)
                    texto = f"Zona:{det.zona} Score:{score.total} Tray:{tray}"
                    cv2.putText(frame_abc, texto, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)
                    cv2.imshow("Camara ABC", frame_abc)

                if ok_d and frame_d is not None:
                    dibujar_zonas(frame_d, cfg["zonas"], ["D"])
                    if obstaculo_d and bbox_d is not None:
                        x, y, w, h = bbox_d
                        cv2.rectangle(frame_d, (x, y), (x + w, y + h), (0, 0, 255), 2)
                    cv2.putText(frame_d, f"Obstaculo D:{int(obstaculo_d)} conf:{conf_d:.2f}", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2)
                    cv2.imshow("Camara D", frame_d)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            time.sleep(0.04)
    except KeyboardInterrupt:
        print("\n[INFO] Vision detenida por usuario")
    finally:
        mqtt_pub.publicar("casa/vision/estado", "OFFLINE", retain=True)
        cap_abc.release()
        cap_d.release()
        if args.mostrar:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
