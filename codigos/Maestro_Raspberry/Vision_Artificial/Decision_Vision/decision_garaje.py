from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import paho.mqtt.client as mqtt


@dataclass
class EstadoCompartido:
    mqtt_conectado: bool = False
    laptop_estado: str = "DESCONOCIDO"
    modo_garaje: str = "DESCONOCIDO"
    porton: str = "DESCONOCIDO"
    alarma: str = "0"
    estop: str = "0"
    estado_seguro: str = "0"
    fc_abierto: str = "0"
    fc_cerrado: str = "0"
    percepcion: Optional[Dict[str, Any]] = None
    t_percepcion_monotonic: float = 0.0
    t_laptop_estado_monotonic: float = 0.0


@dataclass
class EstadoCiclo:
    zona: str = "NINGUNA"
    zona_desde: float = field(default_factory=time.monotonic)
    baja_confianza_desde: Optional[float] = None
    multiples_desde: Optional[float] = None
    ciclo_ingreso_activo: bool = False
    paso_por_d_detectado: bool = False
    d_libre_desde: Optional[float] = None
    porton_abierto_desde: Optional[float] = None
    alarma_activada_por_vision: bool = False
    alarma_razon: str = ""
    d_ocupada_anterior: bool = False
    ultima_decision: str = "INICIANDO"


class CoordinadorMqtt:
    def __init__(self, cfg: Dict[str, Any], solo_monitoreo: bool = False) -> None:
        self.cfg = cfg
        self.solo_monitoreo = solo_monitoreo
        self.estado = EstadoCompartido()
        self.lock = threading.Lock()
        self._ultimos_comandos: Dict[Tuple[str, str], float] = {}
        self._ultimo_evento: Dict[str, float] = {}

        mqtt_cfg = cfg["mqtt"]
        topicos = cfg["topicos"]
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=str(mqtt_cfg.get("client_id", "rasp_decision_vision")),
        )
        self.client.will_set(str(topicos["decision_online"]), "OFFLINE", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    @staticmethod
    def _conexion_correcta(reason_code: Any) -> bool:
        return (
            reason_code == 0
            or getattr(reason_code, "value", None) == 0
            or str(reason_code).strip().lower() in {"0", "success", "connection accepted"}
        )

    def conectar(self) -> None:
        mqtt_cfg = self.cfg["mqtt"]
        self.client.connect_async(
            str(mqtt_cfg.get("host", "127.0.0.1")),
            int(mqtt_cfg.get("port", 1883)),
            int(mqtt_cfg.get("keepalive", 60)),
        )
        self.client.loop_start()

    def cerrar(self) -> None:
        try:
            self.publicar(self.cfg["topicos"]["decision_online"], "OFFLINE", qos=1, retain=True, es_comando=False)
            self.client.disconnect()
        finally:
            self.client.loop_stop()

    def snapshot(self) -> EstadoCompartido:
        with self.lock:
            return EstadoCompartido(
                mqtt_conectado=self.estado.mqtt_conectado,
                laptop_estado=self.estado.laptop_estado,
                modo_garaje=self.estado.modo_garaje,
                porton=self.estado.porton,
                alarma=self.estado.alarma,
                estop=self.estado.estop,
                estado_seguro=self.estado.estado_seguro,
                fc_abierto=self.estado.fc_abierto,
                fc_cerrado=self.estado.fc_cerrado,
                percepcion=None if self.estado.percepcion is None else dict(self.estado.percepcion),
                t_percepcion_monotonic=self.estado.t_percepcion_monotonic,
                t_laptop_estado_monotonic=self.estado.t_laptop_estado_monotonic,
            )

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        conectado = self._conexion_correcta(reason_code)
        with self.lock:
            self.estado.mqtt_conectado = conectado
        if not conectado:
            print(f"[MQTT] Error de conexión: {reason_code}")
            return

        print("[MQTT] Decisión conectada al broker local")
        t = self.cfg["topicos"]
        m = self.cfg["mqtt"]
        for topic in (
            m["topic_percepcion"],
            m["topic_laptop_estado"],
            t["modo_estado"],
            t["porton_estado"],
            t["alarma_estado"],
            t["estop_estado"],
            t["estado_seguro"],
            t["fc_abierto"],
            t["fc_cerrado"],
        ):
            client.subscribe(str(topic), qos=1)
        self.publicar(t["decision_online"], "ONLINE", qos=1, retain=True, es_comando=False)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        with self.lock:
            self.estado.mqtt_conectado = False
        print(f"[MQTT] Decisión desconectada: {reason_code}")

    def _on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        ahora = time.monotonic()
        t = self.cfg["topicos"]
        m = self.cfg["mqtt"]

        with self.lock:
            if topic == m["topic_percepcion"]:
                try:
                    datos = json.loads(payload)
                    if not isinstance(datos, dict) or int(datos.get("schema_version", 0)) != 1:
                        raise ValueError("schema_version no compatible")
                    self.estado.percepcion = datos
                    self.estado.t_percepcion_monotonic = ahora
                except (ValueError, json.JSONDecodeError, TypeError) as exc:
                    print(f"[MQTT] Percepción inválida descartada: {exc}")
            elif topic == m["topic_laptop_estado"]:
                self.estado.laptop_estado = payload.upper()
                self.estado.t_laptop_estado_monotonic = ahora
            elif topic == t["modo_estado"]:
                self.estado.modo_garaje = payload.upper()
            elif topic == t["porton_estado"]:
                self.estado.porton = payload.upper()
            elif topic == t["alarma_estado"]:
                self.estado.alarma = payload.upper()
            elif topic == t["estop_estado"]:
                self.estado.estop = payload.upper()
            elif topic == t["estado_seguro"]:
                self.estado.estado_seguro = payload.upper()
            elif topic == t["fc_abierto"]:
                self.estado.fc_abierto = payload.upper()
            elif topic == t["fc_cerrado"]:
                self.estado.fc_cerrado = payload.upper()

    def publicar(
        self,
        topic: str,
        payload: Any,
        *,
        qos: int = 0,
        retain: bool = False,
        es_comando: bool = False,
        forzar: bool = False,
    ) -> bool:
        texto = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        # El cooldown también aplica en --solo-monitoreo; antes el mensaje se
        # imprimía cada 100 ms y hacía ilegible la terminal.
        if es_comando and not forzar:
            clave = (topic, texto)
            ahora = time.monotonic()
            cooldown = float(self.cfg["umbrales"].get("cooldown_comando_s", 3.0))
            if ahora - self._ultimos_comandos.get(clave, 0.0) < cooldown:
                return False
            self._ultimos_comandos[clave] = ahora

        if es_comando and self.solo_monitoreo:
            print(f"[SOLO MONITOREO] No se envió {topic} = {texto}")
            return False

        self.client.publish(topic, texto, qos=qos, retain=retain)
        if es_comando:
            print(f"[COMANDO] {topic} = {texto}")
        return True

    def evento(self, mensaje: str) -> None:
        ahora = time.monotonic()
        cooldown = max(20.0, float(self.cfg["umbrales"].get("cooldown_evento_s", 20.0)))
        if ahora - self._ultimo_evento.get(mensaje, 0.0) < cooldown:
            return
        self._ultimo_evento[mensaje] = ahora
        print(f"[EVENTO] {mensaje}")
        self.publicar(self.cfg["topicos"]["evento"], mensaje, qos=0, retain=False, es_comando=False)


class LogicaDecisionGaraje:
    def __init__(self, cfg: Dict[str, Any], mqtt_coord: CoordinadorMqtt) -> None:
        self.cfg = cfg
        self.mqtt = mqtt_coord
        self.ciclo = EstadoCiclo()
        self.t_inicio = time.monotonic()
        self.detener = False
        self._t_ultimo_estado = 0.0
        self._ultima_decision_impresa = ""

    @staticmethod
    def _es_activo(valor: Any) -> bool:
        return str(valor).strip().upper() in {"1", "ON", "TRUE", "ACTIVO"}

    def ejecutar(self) -> None:
        print("\n=== DECISIÓN CENTRAL DE VISIÓN ===")
        print("La Raspberry valida seguridad y recién después ordena a la ESP32.")
        if self.mqtt.solo_monitoreo:
            print("ATENCIÓN: ejecución en modo --solo-monitoreo; no se enviarán comandos.\n")
        self.mqtt.conectar()

        try:
            while not self.detener:
                estado = self.mqtt.snapshot()
                self._evaluar(estado)
                self._imprimir_decision_si_cambia()
                self._publicar_estado(estado)
                time.sleep(0.10)
        finally:
            self._desactivar_alarma_si_corresponde()
            self.mqtt.cerrar()
            print("[FIN] Decisión detenida")

    def _imprimir_decision_si_cambia(self) -> None:
        decision = str(self.ciclo.ultima_decision)
        if decision == self._ultima_decision_impresa:
            return
        self._ultima_decision_impresa = decision
        print(f"[DECISIÓN] {decision}")

    def _evaluar(self, estado: EstadoCompartido) -> None:
        ahora = time.monotonic()
        modo = estado.modo_garaje.upper()
        porton = estado.porton.upper()

        if self._es_activo(estado.estop):
            self.ciclo.ultima_decision = "E-STOP ACTIVO: visión sin acciones"
            self._reset_ciclo_ingreso()
            return

        if not estado.mqtt_conectado:
            self.ciclo.ultima_decision = "Broker MQTT desconectado"
            return

        percepcion, problema = self._validar_percepcion(estado, ahora)
        if problema:
            self.ciclo.ultima_decision = problema
            self._manejar_falla_vision(modo, porton, problema)
            return
        assert percepcion is not None

        if bool(percepcion.get("calibrando", False)):
            self.ciclo.ultima_decision = "Laptop calibrando referencias: sin automatización"
            return

        zona = str(percepcion.get("zona", "NINGUNA")).upper()
        self._actualizar_permanencia_zona(zona, ahora)
        obstaculo_d = bool(percepcion.get("obstaculo_d", False))

        if obstaculo_d != self.ciclo.d_ocupada_anterior:
            self.ciclo.d_ocupada_anterior = obstaculo_d
            self.mqtt.evento(
                "Zona D ocupada detectada" if obstaculo_d else "Zona D nuevamente libre"
            )

        # La zona D es una protección independiente del modo automático.
        if obstaculo_d:
            self.ciclo.paso_por_d_detectado = self.ciclo.ciclo_ingreso_activo or self.ciclo.paso_por_d_detectado
            self.ciclo.d_libre_desde = None
            if self.cfg["seguridad"].get("detener_si_obstaculo_d", True):
                aplica_manual = bool(self.cfg["seguridad"].get("seguridad_d_en_manual", True))
                if porton in {"ABRIENDO", "CERRANDO"} and (modo != "MANUAL" or aplica_manual):
                    self._comando_porton(self.cfg["comandos"]["stop"])
                    self.ciclo.ultima_decision = "Obstáculo en D: portón detenido"
                    self.mqtt.evento(self.ciclo.ultima_decision)
                    return
        elif self.ciclo.ciclo_ingreso_activo:
            if self.ciclo.d_libre_desde is None:
                self.ciclo.d_libre_desde = ahora

        if modo == "MANUAL":
            self.ciclo.ultima_decision = "Modo MANUAL: solo supervisión; D permanece protegida"
            self._desactivar_alarma_si_corresponde()
            self._reset_ciclo_ingreso()
            return
        if modo == "VISITA":
            self.ciclo.ultima_decision = "Modo VISITA: sin apertura ni alarma automática"
            self._desactivar_alarma_si_corresponde()
            self._reset_ciclo_ingreso()
            return
        if modo != "NORMAL":
            self.ciclo.ultima_decision = f"Esperando estado válido del modo garaje ({modo})"
            return

        if self._condicion_critica(percepcion, ahora, porton):
            return

        # Cierre automático solo para un ciclo que fue iniciado por esta lógica.
        if self._evaluar_cierre_automatico(percepcion, estado, ahora):
            return

        if obstaculo_d:
            self.ciclo.ultima_decision = "Zona D ocupada: movimiento automático bloqueado"
            return

        vehiculo = bool(percepcion.get("vehiculo_detectado", False))
        if not vehiculo:
            self.ciclo.ultima_decision = "Sin vehículo: monitoreando"
            self._desactivar_alarma_si_corresponde()
            return

        score = int(percepcion.get("score_propietario", 0))
        confianza = float(percepcion.get("confianza_deteccion", 0.0))
        trayectoria = str(percepcion.get("trayectoria", "DESCONOCIDA")).upper()
        permanencia = ahora - self.ciclo.zona_desde
        u = self.cfg["umbrales"]

        if confianza < float(u.get("confianza_minima", 0.45)):
            self.ciclo.ultima_decision = f"Detección de baja confianza ({confianza:.2f}): no abrir"
            return

        if zona == "A":
            if score >= int(u.get("score_dueno", 70)):
                tray_ok = trayectoria in {"INGRESO", "INGRESO_PROBABLE"}
                exigir = bool(self.cfg["automatizacion"].get("exigir_trayectoria_ingreso", True))
                if (tray_ok or not exigir) and bool(self.cfg["automatizacion"].get("apertura_automatica", True)):
                    if porton in {"CERRADO", "DETENIDO"} and not self._es_activo(estado.fc_abierto):
                        enviado = self._comando_porton(self.cfg["comandos"]["abrir"])
                        if enviado:
                            self.ciclo.ciclo_ingreso_activo = True
                            self.ciclo.paso_por_d_detectado = False
                            self.ciclo.d_libre_desde = None
                        self.ciclo.ultima_decision = "Dueño en A con trayectoria de ingreso: abrir portón"
                        self._desactivar_alarma_si_corresponde()
                    else:
                        self.ciclo.ultima_decision = f"Dueño autorizado; portón ya está {porton}"
                    return
                self.ciclo.ultima_decision = "Dueño probable en A, pero sin trayectoria de ingreso"
                return

            if score >= int(u.get("score_dudoso", 40)):
                self.ciclo.ultima_decision = "Vehículo dudoso en A: no abrir y notificar"
                self.mqtt.evento(self.ciclo.ultima_decision)
                return

            if permanencia >= float(u.get("t_alerta_a_s", 10.0)):
                self._activar_alarma("Vehículo ajeno permanece en zona A")
                self.ciclo.ultima_decision = "Ajeno en A: alarma por permanencia"
            else:
                self.ciclo.ultima_decision = f"Ajeno en A: monitoreando ({permanencia:.1f} s)"
            return

        if zona == "B":
            if score >= int(u.get("score_dueno", 70)):
                self.ciclo.ultima_decision = "Auto del dueño en B: no abrir"
                self._desactivar_alarma_si_corresponde()
                return
            if permanencia >= float(u.get("t_bloqueo_b_s", 12.0)):
                self._activar_alarma("Vehículo ajeno bloquea la zona B")
                self.ciclo.ultima_decision = "Ajeno en B: alarma visual y notificación"
            else:
                self.ciclo.ultima_decision = f"Ajeno/dudoso en B: esperando permanencia ({permanencia:.1f} s)"
            return

        if zona == "C":
            self._desactivar_alarma_si_corresponde()
            if score < int(u.get("score_dueno", 70)) and permanencia >= float(u.get("t_notificar_c_s", 3.0)):
                self.mqtt.evento("Vehículo ajeno detectado en zona C")
                self.ciclo.ultima_decision = "Ajeno en C: solo notificación"
            else:
                self.ciclo.ultima_decision = "Vehículo en C: monitoreando"
            return

        self.ciclo.ultima_decision = "Vehículo fuera de las zonas configuradas"

    def _validar_percepcion(self, estado: EstadoCompartido, ahora: float) -> Tuple[Optional[Dict[str, Any]], str]:
        gracia = float(self.cfg["umbrales"].get("gracia_arranque_s", 12.0))
        if ahora - self.t_inicio < gracia and estado.percepcion is None:
            return None, "Esperando primera percepción durante gracia de arranque"

        if estado.laptop_estado == "OFFLINE":
            return None, "Laptop de visión OFFLINE"
        if estado.percepcion is None:
            return None, "No se recibió percepción de la laptop"

        edad = ahora - estado.t_percepcion_monotonic
        # La visión publica varias veces por segundo, pero Windows/OpenCV puede
        # tener pausas breves al mover ventanas o cambiar de escena. Ocho
        # segundos evita falsos "vencida"; el LWT OFFLINE sigue protegiendo
        # ante una desconexión real de la laptop.
        max_edad = max(8.0, float(self.cfg["umbrales"].get("max_edad_percepcion_s", 8.0)))
        if edad > max_edad:
            return None, f"Percepción vencida ({edad:.1f} s)"

        p = estado.percepcion
        if not bool(p.get("camara_abc_ok", False)):
            return None, "Falla de cámara ABC"
        if not bool(p.get("camara_d_ok", False)):
            return None, "Falla de cámara D"
        return p, ""

    def _manejar_falla_vision(self, modo: str, porton: str, razon: str) -> None:
        if razon.startswith("Esperando primera percepción"):
            return
        self.mqtt.evento(razon)
        if porton in {"ABRIENDO", "CERRANDO"}:
            self._comando_porton(self.cfg["comandos"]["stop"])

        # Ya no existe el modo SEGURO: el sistema se queda en el modo actual
        # (NORMAL/VISITA/MANUAL) pero la automatización queda bloqueada por
        # el "return" en _evaluar(); aquí solo se activa la alarma si
        # corresponde, sin tocar modo_garaje.
        seg = self.cfg["seguridad"]
        es_laptop = "OFFLINE" in razon or "Percepción" in razon or "percepción" in razon
        debe_alertar = bool(seg.get("alarma_si_laptop_offline", True)) if es_laptop else bool(seg.get("alarma_si_falla_camara", True))
        if modo == "MANUAL" and not bool(seg.get("alarma_estando_en_manual", False)):
            debe_alertar = False
        if debe_alertar:
            self._activar_alarma(f"Bloqueo de seguridad por visión: {razon}")

    def _condicion_critica(self, p: Dict[str, Any], ahora: float, porton: str) -> bool:
        seg = self.cfg["seguridad"]
        u = self.cfg["umbrales"]

        cantidad = int(p.get("cantidad_vehiculos", 0))
        yolo_disponible = bool(p.get("yolo_disponible", False))
        requiere_yolo = bool(seg.get("multiples_requiere_yolo", True))
        multiples_validos = cantidad > 1 and (yolo_disponible or not requiere_yolo)
        if multiples_validos:
            if self.ciclo.multiples_desde is None:
                self.ciclo.multiples_desde = ahora
            if ahora - self.ciclo.multiples_desde >= float(u.get("t_multiples_s", 1.5)):
                self.ciclo.ultima_decision = "Múltiples vehículos: decisión automática ambigua"
                self.mqtt.evento(self.ciclo.ultima_decision)
                if porton in {"ABRIENDO", "CERRANDO"}:
                    self._comando_porton(self.cfg["comandos"]["stop"])
                if bool(seg.get("alarma_por_multiples", True)):
                    self._activar_alarma("Bloqueo de seguridad por múltiples vehículos")
                return True
        else:
            self.ciclo.multiples_desde = None

        baja_luz = bool(p.get("baja_iluminacion", False))
        if baja_luz:
            if self.ciclo.baja_confianza_desde is None:
                self.ciclo.baja_confianza_desde = ahora
            if ahora - self.ciclo.baja_confianza_desde >= float(u.get("t_baja_confianza_s", 4.0)):
                self.ciclo.ultima_decision = "Iluminación insuficiente: no abrir automáticamente"
                self.mqtt.evento(self.ciclo.ultima_decision)
                if bool(seg.get("alarma_por_baja_iluminacion", False)):
                    self._activar_alarma("Bloqueo de seguridad por baja iluminación")
                return True
        else:
            self.ciclo.baja_confianza_desde = None
        return False

    def _evaluar_cierre_automatico(self, p: Dict[str, Any], estado: EstadoCompartido, ahora: float) -> bool:
        if not self.ciclo.ciclo_ingreso_activo:
            return False

        porton = estado.porton.upper()
        obstaculo = bool(p.get("obstaculo_d", False))
        zona = str(p.get("zona", "NINGUNA")).upper()
        auto = self.cfg["automatizacion"]
        u = self.cfg["umbrales"]

        if porton == "ABIERTO" and self.ciclo.porton_abierto_desde is None:
            self.ciclo.porton_abierto_desde = ahora

        if obstaculo:
            self.ciclo.paso_por_d_detectado = True
            self.ciclo.d_libre_desde = None
            self.ciclo.ultima_decision = "Ciclo de ingreso: vehículo/obstáculo atravesando D"
            return True

        if self.ciclo.d_libre_desde is None:
            self.ciclo.d_libre_desde = ahora

        d_libre_tiempo = ahora - self.ciclo.d_libre_desde
        espera_d = float(u.get("t_d_libre_para_cerrar_s", 2.5))
        puede_cerrar_por_paso = self.ciclo.paso_por_d_detectado and d_libre_tiempo >= espera_d

        puede_cerrar_timeout = False
        if (
            bool(auto.get("cerrar_sin_detectar_paso_d", False))
            and self.ciclo.porton_abierto_desde is not None
            and ahora - self.ciclo.porton_abierto_desde >= float(u.get("timeout_porton_abierto_s", 25.0))
        ):
            puede_cerrar_timeout = True

        if (
            porton == "ABIERTO"
            and zona != "A"
            and bool(auto.get("cierre_automatico_tras_paso_d", True))
            and (puede_cerrar_por_paso or puede_cerrar_timeout)
        ):
            enviado = self._comando_porton(self.cfg["comandos"]["cerrar"])
            self.ciclo.ultima_decision = "Zona D libre después del ingreso: cerrar portón"
            if enviado:
                self._reset_ciclo_ingreso()
            return True

        if porton in {"ABRIENDO", "ABIERTO", "DETENIDO"}:
            self.ciclo.ultima_decision = "Ciclo de ingreso activo: esperando paso y zona D libre"
            return True

        if porton == "CERRADO":
            self._reset_ciclo_ingreso()
        return False

    def _actualizar_permanencia_zona(self, zona: str, ahora: float) -> None:
        if zona != self.ciclo.zona:
            self.ciclo.zona = zona
            self.ciclo.zona_desde = ahora

    def _activar_alarma(self, razon: str) -> None:
        nueva_activacion = not self.ciclo.alarma_activada_por_vision
        cambio_razon = razon != self.ciclo.alarma_razon

        if nueva_activacion:
            enviado = self.mqtt.publicar(
                self.cfg["topicos"]["alarma_cmd"],
                self.cfg["comandos"]["alarma_on"],
                es_comando=True,
            )
            # En solo monitoreo el comando no sale al broker, pero se simula
            # el estado interno para no solicitar ON en cada ciclo.
            if enviado or self.mqtt.solo_monitoreo:
                self.ciclo.alarma_activada_por_vision = True

        if nueva_activacion or cambio_razon:
            self.ciclo.alarma_razon = razon
            self.mqtt.evento(razon)

    def _desactivar_alarma_si_corresponde(self) -> None:
        if not self.ciclo.alarma_activada_por_vision:
            return
        enviado = self.mqtt.publicar(
            self.cfg["topicos"]["alarma_cmd"],
            self.cfg["comandos"]["alarma_off"],
            es_comando=True,
        )
        if enviado or self.mqtt.solo_monitoreo:
            self.ciclo.alarma_activada_por_vision = False
            self.ciclo.alarma_razon = ""

    def _comando_porton(self, payload: str) -> bool:
        return self.mqtt.publicar(
            self.cfg["topicos"]["porton_cmd"],
            payload,
            qos=1,
            retain=False,
            es_comando=True,
        )

    def _comando_modo(self, payload: str) -> bool:
        return self.mqtt.publicar(
            self.cfg["topicos"]["modo_cmd"],
            payload,
            qos=1,
            retain=False,
            es_comando=True,
        )

    def _reset_ciclo_ingreso(self) -> None:
        self.ciclo.ciclo_ingreso_activo = False
        self.ciclo.paso_por_d_detectado = False
        self.ciclo.d_libre_desde = None
        self.ciclo.porton_abierto_desde = None

    def _publicar_estado(self, estado: EstadoCompartido) -> None:
        ahora = time.monotonic()
        if ahora - self._t_ultimo_estado < 1.0:
            return
        self._t_ultimo_estado = ahora
        edad = None if estado.t_percepcion_monotonic <= 0 else round(ahora - estado.t_percepcion_monotonic, 2)
        resumen = {
            "timestamp": round(time.time(), 3),
            "online": estado.mqtt_conectado,
            "laptop": estado.laptop_estado,
            "edad_percepcion_s": edad,
            "modo_garaje": estado.modo_garaje,
            "porton": estado.porton,
            "decision": self.ciclo.ultima_decision,
            "zona": self.ciclo.zona,
            "ciclo_ingreso_activo": self.ciclo.ciclo_ingreso_activo,
            "paso_d_detectado": self.ciclo.paso_por_d_detectado,
            "alarma_vision": self.ciclo.alarma_activada_por_vision,
            "solo_monitoreo": self.mqtt.solo_monitoreo,
        }
        self.mqtt.publicar(
            self.cfg["topicos"]["decision_estado"],
            resumen,
            qos=0,
            retain=True,
            es_comando=False,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Decisión central del garaje en Raspberry Pi")
    parser.add_argument("--config", default="config_decision.json")
    parser.add_argument("--solo-monitoreo", action="store_true", help="Evalúa y muestra decisiones sin mandar comandos")
    args = parser.parse_args()

    ruta = Path(args.config).resolve()
    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    coordinador = CoordinadorMqtt(cfg, solo_monitoreo=args.solo_monitoreo)
    app = LogicaDecisionGaraje(cfg, coordinador)

    def manejar_senal(signum, frame) -> None:
        app.detener = True

    signal.signal(signal.SIGINT, manejar_senal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, manejar_senal)
    app.ejecutar()


if __name__ == "__main__":
    main()
