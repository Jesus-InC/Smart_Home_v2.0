from __future__ import annotations

import argparse
import json
import signal
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

import cv2
import numpy as np

from detector_vision import (
    CalculadorScore,
    CamaraWorker,
    DetectorReferencia,
    ModeloYolo,
    ResultadoABC,
    ResultadoD,
    ResultadoYolo,
    SeguimientoTrayectoria,
    brillo_medio,
    crear_mascara,
    expandir_mascara,
    extraer_objetos,
    poligono_pix,
)
from mqtt_percepcion import PublicadorPercepcion
from modelo_porton_d import ModeloMovimientoPortonD


class EstabilizadorTemporal:
    """Suaviza el score sin ocultar el valor instantáneo de diagnóstico."""

    CLAVES_SCORE = ("yolo", "color", "tamano", "aspecto", "silueta", "trayectoria")

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.ventana_s = max(0.2, float(cfg.get("ventana_s", 0.8)))
        self.intervalo_muestra_s = max(0.03, float(cfg.get("intervalo_muestra_s", 0.10)))
        self.muestras_minimas = max(2, int(cfg.get("muestras_minimas", 4)))
        self.ausencia_reset_s = max(0.0, float(cfg.get("ausencia_reset_s", 0.4)))
        self.mantener_ingreso_s = max(0.0, float(cfg.get("mantener_ingreso_s", 0.8)))
        self._muestras: Deque[Tuple[float, Dict[str, int]]] = deque()
        self._zona = "NINGUNA"
        self._ultimo_muestreo = 0.0
        self._inicio_ausencia: Optional[float] = None
        self._ultimo_ingreso = -1e9

    def reiniciar(self) -> None:
        self._muestras.clear()
        self._zona = "NINGUNA"
        self._ultimo_muestreo = 0.0
        self._inicio_ausencia = None
        self._ultimo_ingreso = -1e9

    @staticmethod
    def _mediana_enteros(valores: List[int]) -> int:
        if not valores:
            return 0
        ordenados = sorted(int(v) for v in valores)
        n = len(ordenados)
        medio = n // 2
        if n % 2:
            return ordenados[medio]
        return int(round((ordenados[medio - 1] + ordenados[medio]) / 2.0))

    def actualizar(
        self,
        zona: str,
        hay_vehiculo: bool,
        detalle_bruto: Dict[str, int],
        trayectoria_bruta: str,
    ) -> Dict[str, Any]:
        ahora = time.monotonic()

        if trayectoria_bruta in {"INGRESO", "INGRESO_PROBABLE"}:
            self._ultimo_ingreso = ahora

        if not hay_vehiculo or zona == "NINGUNA":
            if self._inicio_ausencia is None:
                self._inicio_ausencia = ahora
            if ahora - self._inicio_ausencia >= self.ausencia_reset_s:
                self._muestras.clear()
                self._zona = "NINGUNA"
            return {
                "estable": False,
                "muestras": 0,
                "zona": "NINGUNA",
                "trayectoria": "SIN_VEHICULO",
                "score_detalle": {**{k: 0 for k in self.CLAVES_SCORE}, "total": 0},
            }

        self._inicio_ausencia = None

        if zona != self._zona:
            self._zona = zona
            self._muestras.clear()
            self._ultimo_muestreo = 0.0

        if ahora - self._ultimo_muestreo >= self.intervalo_muestra_s:
            muestra = {k: int(detalle_bruto.get(k, 0)) for k in self.CLAVES_SCORE}
            self._muestras.append((ahora, muestra))
            self._ultimo_muestreo = ahora

        while self._muestras and ahora - self._muestras[0][0] > self.ventana_s:
            self._muestras.popleft()

        detalle_estable = {
            clave: self._mediana_enteros([m[clave] for _, m in self._muestras])
            for clave in self.CLAVES_SCORE
        }
        detalle_estable["total"] = sum(detalle_estable.values())

        trayectoria_estable = trayectoria_bruta
        if zona == "A" and ahora - self._ultimo_ingreso <= self.mantener_ingreso_s:
            trayectoria_estable = "INGRESO"

        return {
            "estable": len(self._muestras) >= self.muestras_minimas,
            "muestras": len(self._muestras),
            "zona": self._zona,
            "trayectoria": trayectoria_estable,
            "score_detalle": detalle_estable,
        }


class FiltroSeguridadD:
    """Aplica una salida fail-safe e histéresis temporal a la zona D.

    La ocupación se confirma de inmediato por seguridad. La liberación exige
    varios fotogramas consecutivos sin cambios para evitar parpadeos. Mientras
    la referencia D se está construyendo, la salida permanece bloqueada.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.frames_confirmar_ocupado = max(1, int(cfg.get("frames_confirmar_ocupado", 1)))
        self.frames_confirmar_libre = max(1, int(cfg.get("frames_confirmar_libre", 6)))
        self._ocupada = True
        self._contador_ocupado = 0
        self._contador_libre = 0

    def reiniciar(self) -> None:
        self._ocupada = True
        self._contador_ocupado = 0
        self._contador_libre = 0

    def actualizar(self, listo: bool, ocupada_bruta: bool) -> Dict[str, Any]:
        if not listo:
            self.reiniciar()
            return {
                "obstaculo": True,
                "estado": "CALIBRANDO",
                "ocupada_bruta": False,
                "frames_libres": 0,
                "frames_ocupados": 0,
            }

        if ocupada_bruta:
            self._contador_ocupado += 1
            self._contador_libre = 0
            if self._contador_ocupado >= self.frames_confirmar_ocupado:
                self._ocupada = True
        else:
            self._contador_libre += 1
            self._contador_ocupado = 0
            if self._contador_libre >= self.frames_confirmar_libre:
                self._ocupada = False

        return {
            "obstaculo": self._ocupada,
            "estado": "OCUPADA" if self._ocupada else "LIBRE",
            "ocupada_bruta": bool(ocupada_bruta),
            "frames_libres": self._contador_libre,
            "frames_ocupados": self._contador_ocupado,
        }


class AplicacionPercepcion:
    def __init__(self, ruta_config: Path, mostrar: bool, sin_mqtt: bool) -> None:
        self.ruta_config = ruta_config
        self.base_dir = ruta_config.parent.resolve()
        self.cfg = self._cargar_config(ruta_config)
        self.mostrar = mostrar
        self.publicador = PublicadorPercepcion(self.cfg, sin_mqtt=sin_mqtt)
        self.session_id = uuid.uuid4().hex[:12]
        self.secuencia = 0
        self.detener = False

        cam_cfg = self.cfg["camaras"]
        cfg_abc = cam_cfg["abc"]
        cfg_d = cam_cfg["d"]

        self.cam_abc = CamaraWorker(
            int(cfg_abc["indice"]),
            cfg_abc,
            "ABC",
        )
        self.cam_d = CamaraWorker(
            int(cfg_d["indice"]),
            cfg_d,
            "D",
        )

        det_cfg = self.cfg["deteccion_referencia"]
        self.det_abc = DetectorReferencia(
            det_cfg["frames_calibracion"],
            det_cfg["umbral_diferencia_abc"],
            det_cfg["area_min_abc"],
            det_cfg["morfologia_kernel"],
            det_cfg["max_objetos"],
        )
        self.det_d = DetectorReferencia(
            det_cfg["frames_calibracion"],
            det_cfg["umbral_diferencia_d"],
            det_cfg["area_min_d"],
            det_cfg["morfologia_kernel"],
            det_cfg["max_objetos"],
        )
        self.yolo = ModeloYolo(self.cfg["yolo"], self.base_dir)
        self.seguimiento = SeguimientoTrayectoria(self.cfg["seguimiento"])
        self.score = CalculadorScore(self.cfg)
        self.estabilizador = EstabilizadorTemporal(self.cfg.get("estabilizacion", {}))
        self.filtro_d = FiltroSeguridadD(self.cfg.get("seguridad_d", {}))
        self.modelo_porton_d = ModeloMovimientoPortonD(
            self.cfg.get("modelo_porton_d", {}),
            self.base_dir,
        )
        # El detector estático de ABIERTO no llama al modelo móvil. Guardamos
        # aquí el estado para reiniciar el seguimiento exactamente una vez al
        # comenzar cada apertura, cierre o llegada a un extremo.
        self._ultimo_estado_procesado_d = "DESCONOCIDO"

    @staticmethod
    def _cargar_config(ruta: Path) -> Dict[str, Any]:
        with ruta.open("r", encoding="utf-8") as archivo:
            cfg = json.load(archivo)
        camaras = cfg["camaras"]
        indice_abc = int(camaras["abc"]["indice"])
        indice_d = int(camaras["d"]["indice"])
        if indice_abc == indice_d:
            raise ValueError(
                "Las cámaras ABC y D no pueden usar el mismo índice"
            )
        return cfg
    
    def _esperar_camara(
        self,
        camara: CamaraWorker,
        nombre: str,
        timeout_s: float = 15.0,
    ) -> bool:
        print(f"[INICIO] Esperando cámara {nombre}...")

        limite = time.monotonic() + timeout_s

        while time.monotonic() < limite and not self.detener:
            ok, frame, _ = camara.obtener()

            if ok and frame is not None:
                print(f"[INICIO] Cámara {nombre} lista")
                return True

            time.sleep(0.1)

        print(
            f"[ERROR] La cámara {nombre} no inició "
            f"después de {timeout_s:.1f} segundos"
        )
        return False

    def iniciar(self) -> None:
        print("\n=== PERCEPCIÓN VISUAL DISTRIBUIDA ===")
        print("Deja A/B/C y D despejadas durante la calibración inicial.")
        print("La laptop SOLO publica percepción; no controla el motor.")
        print("Controles: q=salir | r=recalibrar ABC+D | d=recalibrar SOLO D")
        print("Prueba local sin MQTT: 1=ABIERTO 2=CERRANDO 3=CERRADO 4=ABRIENDO\n")
        self.publicador.conectar()
        # Se abre primero ABC desde el hilo principal. Esto evita que
        # el backend MSMF se bloquee al crear VideoCapture en segundo plano.
        if not self.cam_abc.iniciar():
            print(
                "[ERROR] No se pudo abrir la cámara ABC. "
                "Cierra otros programas que utilicen cámaras."
            )
            self.cerrar()
            return

        if not self._esperar_camara(
            self.cam_abc,
            "ABC",
            timeout_s=3.0,
        ):
            print("[ERROR] ABC abrió, pero no entregó frames recientes.")
            self.cerrar()
            return

        # D se abre únicamente cuando ABC ya está lista.
        if not self.cam_d.iniciar():
            print("[ERROR] No se pudo abrir la cámara D.")
            self.cerrar()
            return

        if not self._esperar_camara(
            self.cam_d,
            "D",
            timeout_s=3.0,
        ):
            print("[ERROR] D abrió, pero no entregó frames recientes.")
            self.cerrar()
            return

        periodo = 1.0 / max(0.5, float(self.cfg["publicacion"].get("hz", 5.0)))
        siguiente_publicacion = 0.0

        try:
            while not self.detener:
                inicio = time.monotonic()
                ok_abc, frame_abc, edad_abc = self.cam_abc.obtener()
                ok_d, frame_d, edad_d = self.cam_d.obtener()
                estado_porton, edad_estado_porton = self.publicador.obtener_estado_porton()
                timeout_configurado = float(
                    self.cfg.get("modelo_porton_d", {}).get("estado_timeout_s", 12.0)
                )
                timeout_estado = max(12.0, timeout_configurado)
                if edad_estado_porton > timeout_estado:
                    estado_porton = "DESCONOCIDO"

                resultado_abc = self._procesar_abc(frame_abc) if ok_abc and frame_abc is not None else ResultadoABC()
                resultado_d = (
                    self._procesar_d(frame_d, estado_porton)
                    if ok_d and frame_d is not None
                    else ResultadoD(
                        listo=False,
                        obstaculo=True,
                        estado_porton=estado_porton,
                        modo="CAMARA_D_OFFLINE",
                        error="Cámara D no disponible",
                    )
                )
                estado_d_filtrado = self.filtro_d.actualizar(
                    resultado_d.listo and ok_d,
                    resultado_d.obstaculo,
                )

                principal = resultado_abc.principal
                resultado_yolo = (
                    self.yolo.inferir(
                        frame_abc,
                        principal.bbox if principal is not None else None,
                    )
                    if ok_abc and frame_abc is not None
                    else ResultadoYolo(
                        activo=self.yolo.activo,
                        disponible=False,
                        error="Cámara ABC no disponible",
                    )
                )
                zona_bruta = principal.zona if principal is not None else "NINGUNA"
                centro_norm = (0.0, 0.0)
                bbox_norm = [0.0, 0.0, 0.0, 0.0]
                if principal is not None and frame_abc is not None:
                    alto, ancho = frame_abc.shape[:2]
                    centro_norm = (principal.centro[0] / ancho, principal.centro[1] / alto)
                    x, y, w, h = principal.bbox
                    bbox_norm = [x / ancho, y / alto, w / ancho, h / alto]

                trayectoria_bruta, permanencia = self.seguimiento.actualizar(
                    zona_bruta,
                    centro_norm,
                    resultado_abc.hay_vehiculo,
                )
                zona = (
                    self.seguimiento.zona_estable
                    if resultado_abc.hay_vehiculo
                    else "NINGUNA"
                )
                score_detalle_bruto = self.score.calcular(
                    principal,
                    trayectoria_bruta,
                    resultado_yolo,
                )
                total_bruto = int(score_detalle_bruto["total"])
                estabilizado = self.estabilizador.actualizar(
                    zona,
                    resultado_abc.hay_vehiculo,
                    score_detalle_bruto,
                    trayectoria_bruta,
                )
                score_detalle = estabilizado["score_detalle"]
                total = int(score_detalle["total"]) if estabilizado["estable"] else 0
                score_visual_bruto = int(
                    score_detalle_bruto.get("color", 0)
                    + score_detalle_bruto.get("tamano", 0)
                    + score_detalle_bruto.get("aspecto", 0)
                    + score_detalle_bruto.get("silueta", 0)
                )
                score_visual = int(
                    score_detalle.get("color", 0)
                    + score_detalle.get("tamano", 0)
                    + score_detalle.get("aspecto", 0)
                    + score_detalle.get("silueta", 0)
                ) if estabilizado["estable"] else 0
                yolo_validado = bool(score_detalle.get("yolo", 0) > 0) if estabilizado["estable"] else False
                trayectoria = str(estabilizado["trayectoria"])
                if not resultado_abc.hay_vehiculo:
                    tipo = "NINGUNO"
                elif not estabilizado["estable"]:
                    tipo = "EVALUANDO"
                else:
                    tipo = self._clasificar_score(total)

                brillo_abc = brillo_medio(frame_abc)
                brillo_d = brillo_medio(frame_d)
                brillo_min = float(self.cfg["calidad"].get("brillo_minimo", 35.0))
                baja_iluminacion = (ok_abc and brillo_abc < brillo_min) or (ok_d and brillo_d < brillo_min)

                d_lista = (
                    self.det_d.listo
                    if estado_porton == "ABIERTO"
                    else resultado_d.listo
                )
                calibrando = not (self.det_abc.listo and d_lista)
                cantidad_cv = 1 if resultado_abc.hay_vehiculo else 0
                cantidad = resultado_yolo.cantidad_vehiculos if resultado_yolo.disponible else cantidad_cv
                confianza = principal.confianza if principal is not None else 0.0
                if resultado_yolo.disponible and resultado_yolo.confianza_principal > 0:
                    confianza = max(confianza, resultado_yolo.confianza_principal)

                obj = resultado_abc.principal
                datos = {
                    "schema_version": 1,
                    "session_id": self.session_id,
                    "secuencia": self.secuencia,
                    "timestamp": round(time.time(), 3),
                    "calibrando": calibrando,
                    "progreso_calibracion_abc": round(self.det_abc.progreso, 3),
                    "progreso_calibracion_d": round(self.det_d.progreso, 3),
                    "camara_abc_ok": bool(ok_abc),
                    "camara_d_ok": bool(ok_d),
                    "edad_frame_abc_s": round(edad_abc, 3) if edad_abc != float("inf") else 999.0,
                    "edad_frame_d_s": round(edad_d, 3) if edad_d != float("inf") else 999.0,
                    "vehiculo_detectado": bool(resultado_abc.hay_vehiculo),
                    "cantidad_vehiculos": int(cantidad),
                    "zona": zona,
                    "zona_bruta": zona_bruta,
                    "centro_norm": [round(centro_norm[0], 4), round(centro_norm[1], 4)],
                    "bbox_norm": [round(v, 4) for v in bbox_norm],
                    "hsv_objeto": list(obj.hsv_mediana) if obj is not None else [0, 0, 0],
                    "pixeles_color": int(obj.pixeles_color) if obj is not None else 0,
                    "area_ratio_objeto": round(float(obj.area_ratio), 5) if obj is not None else 0.0,
                    "aspecto_objeto": round(float(obj.aspecto), 4) if obj is not None else 0.0,
                    "extent_objeto": round(float(obj.extent), 4) if obj is not None else 0.0,
                    "permanencia_zona_s": round(permanencia, 2),
                    "trayectoria": trayectoria,
                    "trayectoria_bruta": trayectoria_bruta,
                    "score_propietario": total,
                    "score_detalle": score_detalle,
                    "score_visual": score_visual,
                    "score_bruto": total_bruto,
                    "score_detalle_bruto": score_detalle_bruto,
                    "score_visual_bruto": score_visual_bruto,
                    "perfil_dueno_zona": str(self.score.ultima_zona_perfil),
                    "yolo_validado_hibrido": yolo_validado,
                    "yolo_motivo_hibrido": str(self.score.ultimo_motivo_yolo),
                    "score_estable": bool(estabilizado["estable"]),
                    "muestras_estabilizacion": int(estabilizado["muestras"]),
                    "tipo_vehiculo": tipo,
                    "confianza_deteccion": round(float(confianza), 3),
                    "yolo_activo": bool(resultado_yolo.activo),
                    "yolo_disponible": bool(resultado_yolo.disponible),
                    "yolo_clase": resultado_yolo.clase_principal,
                    "yolo_confianza": round(float(resultado_yolo.confianza_principal), 3),
                    "yolo_error": resultado_yolo.error,
                    "obstaculo_d": bool(estado_d_filtrado["obstaculo"]),
                    "obstaculo_d_bruto": bool(estado_d_filtrado["ocupada_bruta"]),
                    "estado_d": str(estado_d_filtrado["estado"]),
                    "estado_porton": str(resultado_d.estado_porton),
                    "edad_estado_porton_s": round(float(edad_estado_porton), 3),
                    "modo_d": str(resultado_d.modo),
                    "template_d": int(resultado_d.indice_template),
                    "error_ajuste_d": round(float(resultado_d.error_ajuste), 3),
                    "error_d": str(resultado_d.error),
                    "modelo_porton_d_disponible": bool(self.modelo_porton_d.disponible),
                    "frames_libres_d": int(estado_d_filtrado["frames_libres"]),
                    "frames_ocupados_d": int(estado_d_filtrado["frames_ocupados"]),
                    "confianza_obstaculo_d": round(float(resultado_d.confianza), 3),
                    "brillo_abc": round(brillo_abc, 1),
                    "brillo_d": round(brillo_d, 1),
                    "baja_iluminacion": bool(baja_iluminacion),
                }

                ahora = time.monotonic()
                if ahora >= siguiente_publicacion:
                    self.publicador.publicar_percepcion(datos)
                    siguiente_publicacion = ahora + periodo
                    self.secuencia += 1
                    self._imprimir_resumen(datos)

                if self.mostrar:
                    tecla = self._mostrar(frame_abc, frame_d, resultado_abc, resultado_d, resultado_yolo.boxes, datos)
                    if tecla == ord("q"):
                        break
                    if tecla in {ord("d"), ord("D")}:
                        if estado_porton != "ABIERTO":
                            print(
                                "\n[VISIÓN] No se recalibra D: el portón debe estar ABIERTO."
                            )
                        else:
                            print(
                                "\n[VISIÓN] Recalibrando SOLO la referencia D. "
                                "Mantén D vacía y el portón abierto/quieto."
                            )
                            self.det_d.reiniciar()
                            self.filtro_d.reiniciar()
                            self.modelo_porton_d.reiniciar_seguimiento()
                            self._ultimo_estado_procesado_d = "DESCONOCIDO"
                    if tecla == ord("1"):
                        self.publicador.fijar_estado_porton_local("ABIERTO")
                    if tecla == ord("2"):
                        self.publicador.fijar_estado_porton_local("CERRANDO")
                    if tecla == ord("3"):
                        self.publicador.fijar_estado_porton_local("CERRADO")
                    if tecla == ord("4"):
                        self.publicador.fijar_estado_porton_local("ABRIENDO")
                    if tecla in {ord("r"), ord("R")}:
                        print(
                            "\n[VISIÓN] Recalibrando referencias ABC y D. "
                            "Despeja toda la maqueta."
                        )
                        self.det_abc.reiniciar()
                        self.det_d.reiniciar()
                        self.filtro_d.reiniciar()
                        self.modelo_porton_d.reiniciar_seguimiento()
                        self._ultimo_estado_procesado_d = "DESCONOCIDO"
                        self.seguimiento.reiniciar()
                        self.estabilizador.reiniciar()

                restante = min(0.02, max(0.0, periodo - (time.monotonic() - inicio)))
                if restante > 0:
                    time.sleep(restante)
        finally:
            self.cerrar()

    def _procesar_abc(self, frame: np.ndarray) -> ResultadoABC:
        zonas = self.cfg["zonas_abc"]
        mascara_zonas = crear_mascara(frame, [zonas["A"], zonas["B"], zonas["C"]])
        contornos, mascara = self.det_abc.detectar(frame, mascara_zonas)
        objetos = extraer_objetos(
            frame,
            contornos,
            zonas,
            self.cfg.get("extraccion_color", {}),
        )
        objetos_validos = [obj for obj in objetos if obj.zona != "NINGUNA"]
        principal = max(objetos_validos, key=lambda obj: obj.area_contorno) if objetos_validos else None
        return ResultadoABC(
            listo=self.det_abc.listo,
            hay_vehiculo=principal is not None,
            objetos=objetos_validos,
            principal=principal,
            mascara=mascara,
        )

    def _procesar_d(self, frame: np.ndarray, estado_porton: str) -> ResultadoD:
        mascara_base = crear_mascara(frame, [self.cfg["zona_d"]])
        margen_px = int(self.cfg.get("seguridad_d", {}).get("margen_px", 0))
        mascara_zona = expandir_mascara(mascara_base, margen_px)
        alto, ancho = frame.shape[:2]
        for poly_ignorar in self.cfg.get("zonas_ignorar_d", []):
            cv2.fillPoly(mascara_zona, [poligono_pix(poly_ignorar, ancho, alto)], 0)

        estado = str(estado_porton or "DESCONOCIDO").strip().upper()

        if estado != self._ultimo_estado_procesado_d:
            self.modelo_porton_d.reiniciar_seguimiento()
            self._ultimo_estado_procesado_d = estado

        # Con el portón completamente abierto se conserva la referencia estática
        # recalibrable mediante la tecla d.
        if estado == "ABIERTO":
            contornos, mascara = self.det_d.detectar(frame, mascara_zona)
            if not contornos:
                return ResultadoD(
                    listo=self.det_d.listo,
                    mascara=mascara,
                    estado_porton=estado,
                    modo="REFERENCIA_ABIERTO",
                )
            contorno = max(contornos, key=cv2.contourArea)
            area = float(cv2.contourArea(contorno))
            x, y, w, h = cv2.boundingRect(contorno)
            area_min = float(self.cfg["deteccion_referencia"].get("area_min_d", 600))
            confianza = min(1.0, area / max(1.0, 3.0 * area_min))
            return ResultadoD(
                listo=self.det_d.listo,
                obstaculo=True,
                confianza=confianza,
                bbox=(x, y, w, h),
                mascara=mascara,
                estado_porton=estado,
                modo="REFERENCIA_ABIERTO",
            )

        # Durante apertura/cierre o con el portón cerrado se usa el modelo de
        # movimiento limpio. Cualquier diferencia residual se considera obstáculo.
        resultado_modelo = self.modelo_porton_d.detectar(
            frame,
            estado,
            mascara_zona,
        )
        return ResultadoD(
            listo=resultado_modelo.listo,
            obstaculo=resultado_modelo.obstaculo,
            confianza=resultado_modelo.confianza,
            bbox=resultado_modelo.bbox,
            mascara=resultado_modelo.mascara,
            estado_porton=resultado_modelo.estado_porton,
            modo=resultado_modelo.modo,
            indice_template=resultado_modelo.indice_template,
            error_ajuste=resultado_modelo.error_ajuste,
            error=resultado_modelo.error,
        )

    def _clasificar_score(self, total: int) -> str:
        cfg = self.cfg["score"]
        if total >= int(cfg.get("umbral_dueno", 70)):
            return "DUENO"
        if total >= int(cfg.get("umbral_dudoso", 40)):
            return "DUDOSO"
        return "AJENO" if total > 0 else "NINGUNO"

    @staticmethod
    def _imprimir_resumen(datos: Dict[str, Any]) -> None:
        if datos["calibrando"]:
            print(
                f"[CALIBRACIÓN] ABC={datos['progreso_calibracion_abc']:.0%} "
                f"D={datos['progreso_calibracion_d']:.0%}",
                end="\r",
            )
            return
        detalle = datos["score_detalle"]
        bruto = datos["score_detalle_bruto"]
        estado_score = "EST" if datos["score_estable"] else "EVAL"
        print(
            f"[PERCEPCIÓN] zona={datos['zona']:<7} "
            f"score={datos['score_propietario']:>3}({estado_score}) "
            f"raw={datos['score_bruto']:>3} "
            f"V={datos.get('score_visual', 0):02d}/{datos.get('score_visual_bruto', 0):02d} "
            f"PV={datos.get('perfil_dueno_zona', '---'):<8} "
            f"E[Y{detalle['yolo']:02d} C{detalle['color']:02d} "
            f"Ta{detalle['tamano']:02d} As{detalle['aspecto']:02d} "
            f"Si{detalle['silueta']:02d} Tr{detalle['trayectoria']:02d}] "
            f"R[Y{bruto['yolo']:02d} C{bruto['color']:02d} "
            f"Ta{bruto['tamano']:02d} As{bruto['aspecto']:02d} "
            f"Si{bruto['silueta']:02d} Tr{bruto['trayectoria']:02d}] "
            f"tray={datos['trayectoria']:<12} "
            f"D={datos.get('estado_d', 'OCUPADA'):<10} "
            f"P={datos.get('estado_porton', 'DESCONOCIDO'):<9} "
            f"Md={datos.get('modo_d', '---'):<20} "
            f"Tpl={datos.get('template_d', -1):>2} "
            f"vehículos={datos['cantidad_vehiculos']} "
            f"n={datos['muestras_estabilizacion']:02d} "
            f"HSV={tuple(datos['hsv_objeto'])} "
            f"Ar={datos['area_ratio_objeto']:.4f} "
            f"Asp={datos['aspecto_objeto']:.2f} "
            f"Ext={datos['extent_objeto']:.2f}    ",
            end="\r",
        )

    def _mostrar(self, frame_abc, frame_d, resultado_abc, resultado_d, boxes_yolo, datos) -> int:
        if frame_abc is not None:
            vista_abc = frame_abc.copy()
            alto, ancho = vista_abc.shape[:2]
            for nombre, poly in self.cfg["zonas_abc"].items():
                pts = poligono_pix(poly, ancho, alto)
                cv2.polylines(vista_abc, [pts], True, (255, 255, 255), 2)
                x, y = pts[0]
                cv2.putText(vista_abc, nombre, (x + 5, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            for obj in resultado_abc.objetos:
                x, y, w, h = obj.bbox
                cv2.rectangle(vista_abc, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(vista_abc, obj.zona, (x, max(20, y - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            clase_dueno = str(self.cfg.get("yolo", {}).get("clase_dueno", "auto_dueno")).lower()
            for bbox, clase, conf in boxes_yolo:
                x, y, w, h = bbox
                clase_norm = str(clase).lower()
                if clase_norm == clase_dueno:
                    if datos.get("yolo_validado_hibrido", False):
                        etiqueta = f"{clase} VALIDADO {conf:.2f}"
                        color_yolo = (0, 255, 0)
                    else:
                        motivo = str(datos.get("yolo_motivo_hibrido", "RECHAZADO"))
                        etiqueta = f"{clase}? {motivo} {conf:.2f}"
                        color_yolo = (0, 165, 255)
                else:
                    etiqueta = f"{clase} {conf:.2f}"
                    color_yolo = (255, 255, 0)
                cv2.rectangle(vista_abc, (x, y), (x + w, y + h), color_yolo, 2)
                cv2.putText(vista_abc, etiqueta, (x, y + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_yolo, 2)
            detalle = datos["score_detalle"]
            bruto = datos["score_detalle_bruto"]
            estado_score = "ESTABLE" if datos["score_estable"] else "EVALUANDO"
            cv2.putText(
                vista_abc,
                (
                    f"{datos['zona']} | Score {datos['score_propietario']} "
                    f"({estado_score}) raw {datos['score_bruto']} | {datos['trayectoria']}"
                ),
                (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.68,
                (0, 255, 255),
                2,
            )
            cv2.putText(
                vista_abc,
                (
                    f"EST Y{detalle['yolo']} C{detalle['color']} Ta{detalle['tamano']} "
                    f"As{detalle['aspecto']} Si{detalle['silueta']} "
                    f"Tr{detalle['trayectoria']} | V={datos.get('score_visual', 0)} "
                    f"PV={datos.get('perfil_dueno_zona', '---')} | n={datos['muestras_estabilizacion']}"
                ),
                (10, 56),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (0, 255, 255),
                2,
            )
            cv2.putText(
                vista_abc,
                (
                    f"RAW Y{bruto['yolo']} C{bruto['color']} Ta{bruto['tamano']} "
                    f"As{bruto['aspecto']} Si{bruto['silueta']} Tr{bruto['trayectoria']}"
                ),
                (10, 84),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                (0, 200, 255),
                2,
            )
            cv2.imshow("Camara ABC", vista_abc)
            if resultado_abc.mascara is not None:
                cv2.imshow("Mascara ABC", resultado_abc.mascara)

        if frame_d is not None:
            vista_d = frame_d.copy()
            alto, ancho = vista_d.shape[:2]
            pts = poligono_pix(self.cfg["zona_d"], ancho, alto)
            cv2.polylines(vista_d, [pts], True, (255, 255, 255), 2)
            margen_px = int(self.cfg.get("seguridad_d", {}).get("margen_px", 0))
            if margen_px > 0:
                mascara_base = crear_mascara(frame_d, [self.cfg["zona_d"]])
                mascara_ampliada = expandir_mascara(mascara_base, margen_px)
                contornos_margen, _ = cv2.findContours(
                    mascara_ampliada,
                    cv2.RETR_EXTERNAL,
                    cv2.CHAIN_APPROX_SIMPLE,
                )
                cv2.drawContours(vista_d, contornos_margen, -1, (0, 255, 255), 1)
            if resultado_d.bbox is not None:
                x, y, w, h = resultado_d.bbox
                cv2.rectangle(vista_d, (x, y), (x + w, y + h), (0, 0, 255), 2)
            estado_d = str(datos.get("estado_d", "OCUPADA"))
            if estado_d == "CALIBRANDO":
                texto = "D CALIBRANDO"
                color_texto = (0, 165, 255)
            elif estado_d == "OCUPADA":
                texto = "D OCUPADA"
                color_texto = (0, 0, 255)
            else:
                texto = "D LIBRE"
                color_texto = (0, 255, 0)
            cv2.putText(
                vista_d, texto, (10, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color_texto, 2
            )
            cv2.putText(
                vista_d,
                (
                    f"Porton={datos.get('estado_porton', 'DESCONOCIDO')} | "
                    f"{datos.get('modo_d', '---')} | "
                    f"tpl={datos.get('template_d', -1)} err={datos.get('error_ajuste_d', 0.0):.1f}"
                ),
                (10, 54),
                cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1
            )
            cv2.putText(
                vista_d, "d=ref D r=ambas q=salir | local: 1 abierto 2 cerrando 3 cerrado 4 abriendo",
                (10, max(75, alto - 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1
            )
            cv2.imshow("Camara D", vista_d)
            if resultado_d.mascara is not None:
                cv2.imshow("Mascara D", resultado_d.mascara)

        return cv2.waitKey(1) & 0xFF

    def cerrar(self) -> None:
        self.detener = True
        self.cam_abc.detener()
        self.cam_d.detener()
        self.publicador.cerrar()
        cv2.destroyAllWindows()
        print("\n[FIN] Percepción detenida de forma segura")


def main() -> None:
    parser = argparse.ArgumentParser(description="Percepción visual del garaje ejecutada en la laptop")
    parser.add_argument("--config", default="config_laptop.json")
    parser.add_argument("--mostrar", action="store_true", help="Muestra cámaras, zonas y máscaras")
    parser.add_argument("--sin-mqtt", action="store_true", help="Prueba local sin broker")
    args = parser.parse_args()

    ruta = Path(args.config).resolve()
    app = AplicacionPercepcion(ruta, mostrar=args.mostrar, sin_mqtt=args.sin_mqtt)

    def manejar_senal(signum, frame) -> None:
        app.detener = True

    signal.signal(signal.SIGINT, manejar_senal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, manejar_senal)
    app.iniciar()


if __name__ == "__main__":
    main()
