from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np


Punto = Tuple[int, int]
BBox = Tuple[int, int, int, int]
PoligonoNorm = List[List[float]]


@dataclass
class ObjetoDetectado:
    bbox: BBox
    centro: Punto
    area_contorno: float
    area_bbox: float
    area_ratio: float
    aspecto: float
    extent: float
    confianza: float
    hsv_mediana: Tuple[int, int, int]
    pixeles_color: int = 0
    zona: str = "NINGUNA"


@dataclass
class ResultadoABC:
    listo: bool = False
    hay_vehiculo: bool = False
    objetos: List[ObjetoDetectado] = field(default_factory=list)
    principal: Optional[ObjetoDetectado] = None
    mascara: Optional[np.ndarray] = None


@dataclass
class ResultadoD:
    listo: bool = False
    obstaculo: bool = False
    confianza: float = 0.0
    bbox: Optional[BBox] = None
    mascara: Optional[np.ndarray] = None
    estado_porton: str = "DESCONOCIDO"
    modo: str = "REFERENCIA_ESTATICA"
    indice_template: int = -1
    error_ajuste: float = 0.0
    error: str = ""


@dataclass
class ResultadoYolo:
    activo: bool = False
    disponible: bool = False
    clase_principal: str = "NINGUNA"
    confianza_principal: float = 0.0
    cantidad_vehiculos: int = 0
    boxes: List[Tuple[BBox, str, float]] = field(default_factory=list)
    error: str = ""


class CamaraWorker:
    """Lee una cámara en segundo plano y conserva únicamente el frame más reciente."""

    def __init__(self, indice: int, cfg: Dict[str, Any], nombre: str) -> None:
        self.indice = indice
        self.cfg = cfg
        self.nombre = nombre
        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._ultimo_ok = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._bucle, daemon=True, name=f"camara-{nombre}")

    @staticmethod
    def _backend(nombre: str) -> int:
        nombre = nombre.strip().upper()
        if nombre == "DSHOW" and hasattr(cv2, "CAP_DSHOW"):
            return cv2.CAP_DSHOW
        if nombre == "MSMF" and hasattr(cv2, "CAP_MSMF"):
            return cv2.CAP_MSMF
        if nombre == "V4L2" and hasattr(cv2, "CAP_V4L2"):
            return cv2.CAP_V4L2
        return cv2.CAP_ANY

    def iniciar(self) -> bool:
        """
        Abre la cámara en el hilo principal y luego inicia el hilo de lectura.

        En Windows, el backend MSMF puede bloquearse si VideoCapture se crea
        directamente dentro de un hilo secundario. Por eso la apertura y el
        calentamiento se realizan aquí, de forma síncrona.
        """
        if self._thread.is_alive():
            return True

        self._stop.clear()
        self._cerrar_captura()

        with self._lock:
            self._frame = None
            self._ultimo_ok = 0.0

        if not self._abrir_captura():
            return False

        self._thread = threading.Thread(
            target=self._bucle,
            daemon=True,
            name=f"camara-{self.nombre}",
        )
        self._thread.start()
        return True

    def detener(self) -> None:
        """Detiene la cámara aunque el hilo nunca haya arrancado."""
        self._stop.set()

        if self._thread.is_alive():
            self._thread.join(timeout=3.0)

        self._cerrar_captura()

    def obtener(self) -> Tuple[bool, Optional[np.ndarray], float]:
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            edad = float("inf") if self._ultimo_ok <= 0 else time.monotonic() - self._ultimo_ok
        return frame is not None and edad < 1.5, frame, edad

    def _abrir_captura(self) -> bool:
        backend_nombre = str(self.cfg.get("backend", "AUTO"))
        backend = self._backend(backend_nombre)

        print(
            f"[CÁMARA] Abriendo {self.nombre} en índice {self.indice} "
            f"con backend {backend_nombre.upper()}..."
        )

        try:
            cap = cv2.VideoCapture(self.indice, backend)
        except Exception as exc:
            print(f"[CÁMARA] Error al crear {self.nombre}: {exc}")
            return False

        if not cap.isOpened():
            print(
                f"[CÁMARA] {self.nombre} no pudo abrirse "
                f"en el índice {self.indice}"
            )
            cap.release()
            return False

        fourcc = str(self.cfg.get("fourcc", "")).strip()
        if len(fourcc) == 4:
            cap.set(
                cv2.CAP_PROP_FOURCC,
                cv2.VideoWriter_fourcc(*fourcc),
            )

        cap.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            int(self.cfg.get("ancho", 640)),
        )
        cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            int(self.cfg.get("alto", 480)),
        )
        cap.set(
            cv2.CAP_PROP_FPS,
            int(self.cfg.get("fps", 15)),
        )

        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        calentamiento_s = float(self.cfg.get("calentamiento_s", 4.0))
        print(
            f"[CÁMARA] Calentando {self.nombre} "
            f"durante {calentamiento_s:.1f} s..."
        )

        ultimo_frame: Optional[np.ndarray] = None
        inicio = time.monotonic()

        while (
            time.monotonic() - inicio < calentamiento_s
            and not self._stop.is_set()
        ):
            ok, frame = cap.read()
            if ok and frame is not None and frame.size > 0:
                ultimo_frame = frame.copy()
            time.sleep(0.03)

        if ultimo_frame is None:
            print(
                f"[CÁMARA] {self.nombre} abrió, "
                "pero no entregó imagen válida"
            )
            cap.release()
            return False

        self._cap = cap

        with self._lock:
            self._frame = ultimo_frame
            self._ultimo_ok = time.monotonic()

        ancho_real = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto_real = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_real = cap.get(cv2.CAP_PROP_FPS)

        print(
            f"[CÁMARA] {self.nombre} abierta en índice {self.indice}: "
            f"{ancho_real}x{alto_real} @ {fps_real:.1f} FPS"
        )
        return True

    def _cerrar_captura(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _bucle(self) -> None:
        """
        Lee continuamente el stream ya abierto.

        La reconexión no se intenta desde este hilo porque MSMF puede bloquear
        la creación de VideoCapture fuera del hilo principal. Si la lectura
        falla, la cámara queda offline y la aplicación podrá reiniciarse de
        forma segura.
        """
        while not self._stop.is_set():
            if self._cap is None:
                break

            ok, frame = self._cap.read()
            if not ok or frame is None:
                print(
                    f"[CÁMARA] Falló la lectura de {self.nombre}; "
                    "la cámara quedó offline"
                )
                self._cerrar_captura()
                break

            with self._lock:
                self._frame = frame
                self._ultimo_ok = time.monotonic()


class DetectorReferencia:
    """Compara el frame actual con una referencia tomada con la maqueta despejada."""

    def __init__(self, frames_calibracion: int, umbral: int, area_min: int, kernel: int, max_objetos: int) -> None:
        self.frames_calibracion = max(5, int(frames_calibracion))
        self.umbral = int(umbral)
        self.area_min = float(area_min)
        self.kernel = max(3, int(kernel) | 1)
        self.max_objetos = max(1, int(max_objetos))
        self._acumulador: Optional[np.ndarray] = None
        self._contador = 0
        self.referencia: Optional[np.ndarray] = None

    @property
    def listo(self) -> bool:
        return self.referencia is not None

    @property
    def progreso(self) -> float:
        return min(1.0, self._contador / float(self.frames_calibracion))

    @staticmethod
    def _preparar(frame: np.ndarray) -> np.ndarray:
        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gris, (7, 7), 0)

    def reiniciar(self) -> None:
        self._acumulador = None
        self._contador = 0
        self.referencia = None

    def alimentar_referencia(self, frame: np.ndarray) -> None:
        gris = self._preparar(frame).astype(np.float32)
        if self._acumulador is None:
            self._acumulador = gris
        else:
            cv2.accumulateWeighted(gris, self._acumulador, 1.0 / float(self._contador + 1))
        self._contador += 1
        if self._contador >= self.frames_calibracion:
            self.referencia = cv2.convertScaleAbs(self._acumulador)
            print("[VISIÓN] Referencia visual lista")

    def detectar(self, frame: np.ndarray, mascara_zona: np.ndarray) -> Tuple[List[np.ndarray], np.ndarray]:
        if not self.listo:
            self.alimentar_referencia(frame)
            vacia = np.zeros(frame.shape[:2], dtype=np.uint8)
            return [], vacia

        actual = self._preparar(frame)
        diferencia = cv2.absdiff(self.referencia, actual)
        diferencia = cv2.bitwise_and(diferencia, diferencia, mask=mascara_zona)
        _, binaria = cv2.threshold(diferencia, self.umbral, 255, cv2.THRESH_BINARY)

        k = np.ones((self.kernel, self.kernel), dtype=np.uint8)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, k, iterations=1)
        binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, k, iterations=2)
        binaria = cv2.dilate(binaria, k, iterations=1)

        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filtrados = [c for c in contornos if cv2.contourArea(c) >= self.area_min]
        filtrados.sort(key=cv2.contourArea, reverse=True)
        return filtrados[: self.max_objetos], binaria


class ModeloYolo:
    """Clasificador opcional aplicado al recorte detectado por OpenCV.

    También conserva un modo ``deteccion`` por compatibilidad con modelos YOLO
    anteriores. Para este proyecto se usa ``tarea=clasificacion``.
    """

    def __init__(self, cfg: Dict[str, Any], base_dir: Path) -> None:
        self.cfg = cfg
        self.base_dir = base_dir
        self.activo = bool(cfg.get("usar", False))
        self.tarea = str(cfg.get("tarea", "clasificacion")).strip().lower()
        self.disponible = False
        self.error = ""
        self._model = None
        self._contador = 0
        self._cache = ResultadoYolo(activo=self.activo)

        if not self.activo:
            return

        ruta = Path(str(cfg.get("modelo", "modelos/best_cls.pt")))
        if not ruta.is_absolute():
            ruta = base_dir / ruta
        if not ruta.exists():
            self.error = f"No existe el modelo: {ruta}"
            print(f"[YOLO] {self.error}")
            return

        try:
            from ultralytics import YOLO  # importación diferida

            self._model = YOLO(str(ruta))
            self.disponible = True
            print(f"[YOLO] Modelo cargado ({self.tarea}): {ruta}")
        except Exception as exc:  # noqa: BLE001
            self.error = f"No se pudo cargar YOLO: {exc}"
            print(f"[YOLO] {self.error}")

    @staticmethod
    def _nombre_clase(nombres: Any, indice: int) -> str:
        if isinstance(nombres, dict):
            return str(nombres.get(indice, indice))
        if isinstance(nombres, (list, tuple)) and 0 <= indice < len(nombres):
            return str(nombres[indice])
        return str(indice)

    def _recortar(self, frame: np.ndarray, bbox: BBox) -> Optional[np.ndarray]:
        x, y, w, h = bbox
        alto, ancho = frame.shape[:2]
        margen = max(0.0, float(self.cfg.get("margen_crop", 0.12)))
        mx = int(round(w * margen))
        my = int(round(h * margen))
        x1 = max(0, x - mx)
        y1 = max(0, y - my)
        x2 = min(ancho, x + w + mx)
        y2 = min(alto, y + h + my)
        if x2 - x1 < 20 or y2 - y1 < 20:
            return None
        return frame[y1:y2, x1:x2].copy()

    def inferir(self, frame: np.ndarray, bbox: Optional[BBox] = None) -> ResultadoYolo:
        if not self.activo or not self.disponible or self._model is None:
            return ResultadoYolo(activo=self.activo, disponible=False, error=self.error)

        if self.tarea in {"clasificacion", "classification", "classify", "cls"}:
            if bbox is None:
                self._cache = ResultadoYolo(activo=True, disponible=True)
                return self._cache
            return self._inferir_clasificacion(frame, bbox)
        return self._inferir_deteccion(frame)

    def _inferir_clasificacion(self, frame: np.ndarray, bbox: BBox) -> ResultadoYolo:
        self._contador += 1
        cada_n = max(1, int(self.cfg.get("cada_n_frames", 3)))
        if self._contador % cada_n != 0 and self._cache.cantidad_vehiculos > 0:
            return self._cache

        recorte = self._recortar(frame, bbox)
        if recorte is None:
            self._cache = ResultadoYolo(activo=True, disponible=True)
            return self._cache

        conf_min = float(self.cfg.get("confianza_min", 0.70))
        imgsz = int(self.cfg.get("imgsz", 224))
        permitidas = {str(x).lower() for x in self.cfg.get("clases_vehiculo", [])}

        try:
            resultados = self._model.predict(source=recorte, imgsz=imgsz, verbose=False)
            if not resultados or getattr(resultados[0], "probs", None) is None:
                self._cache = ResultadoYolo(
                    activo=True,
                    disponible=False,
                    error="El modelo no devolvió probabilidades de clasificación",
                )
                return self._cache

            resultado = resultados[0]
            top1 = int(resultado.probs.top1)
            confianza = float(resultado.probs.top1conf.item())
            clase_real = self._nombre_clase(resultado.names, top1)
            clase_publicada = clase_real
            if permitidas and clase_real.lower() not in permitidas:
                clase_publicada = "OTRA_CLASE"
            elif confianza < conf_min:
                clase_publicada = "INCIERTA"

            self._cache = ResultadoYolo(
                activo=True,
                disponible=True,
                clase_principal=clase_publicada,
                confianza_principal=confianza,
                cantidad_vehiculos=1,
                boxes=[(bbox, clase_publicada, confianza)],
            )
        except Exception as exc:  # noqa: BLE001
            self._cache = ResultadoYolo(activo=True, disponible=False, error=str(exc))
        return self._cache

    def _inferir_deteccion(self, frame: np.ndarray) -> ResultadoYolo:
        self._contador += 1
        cada_n = max(1, int(self.cfg.get("cada_n_frames", 1)))
        if self._contador % cada_n != 0:
            return self._cache

        conf_min = float(self.cfg.get("confianza_min", 0.55))
        imgsz = int(self.cfg.get("imgsz", 640))
        permitidas = {str(x).lower() for x in self.cfg.get("clases_vehiculo", [])}

        try:
            resultados = self._model.predict(frame, conf=conf_min, imgsz=imgsz, verbose=False)
            boxes_salida: List[Tuple[BBox, str, float]] = []
            if resultados:
                resultado = resultados[0]
                nombres = resultado.names
                for box in resultado.boxes:
                    cls_id = int(box.cls[0].item())
                    clase = self._nombre_clase(nombres, cls_id)
                    confianza = float(box.conf[0].item())
                    if permitidas and clase.lower() not in permitidas:
                        continue
                    x1, y1, x2, y2 = [int(round(v)) for v in box.xyxy[0].tolist()]
                    boxes_salida.append(((x1, y1, max(1, x2 - x1), max(1, y2 - y1)), clase, confianza))

            boxes_salida.sort(key=lambda item: item[2], reverse=True)
            principal = boxes_salida[0] if boxes_salida else ((0, 0, 0, 0), "NINGUNA", 0.0)
            self._cache = ResultadoYolo(
                activo=True,
                disponible=True,
                clase_principal=principal[1],
                confianza_principal=principal[2],
                cantidad_vehiculos=len(boxes_salida),
                boxes=boxes_salida,
            )
        except Exception as exc:  # noqa: BLE001
            self._cache = ResultadoYolo(activo=True, disponible=False, error=str(exc))
        return self._cache


class SeguimientoTrayectoria:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.historial: Deque[Tuple[float, str, Tuple[float, float]]] = deque()
        self._zona_candidata = "NINGUNA"
        self._contador_zona = 0
        self.zona_estable = "NINGUNA"
        self.zona_anterior = "NINGUNA"
        self.zona_desde = time.monotonic()

    def reiniciar(self) -> None:
        self.historial.clear()
        self._zona_candidata = "NINGUNA"
        self._contador_zona = 0
        self.zona_estable = "NINGUNA"
        self.zona_anterior = "NINGUNA"
        self.zona_desde = time.monotonic()

    def actualizar(self, zona: str, centro_norm: Tuple[float, float], hay: bool) -> Tuple[str, float]:
        ahora = time.monotonic()
        zona = zona if hay else "NINGUNA"
        frames_estables = max(1, int(self.cfg.get("frames_estables_zona", 2)))

        if zona == self._zona_candidata:
            self._contador_zona += 1
        else:
            self._zona_candidata = zona
            self._contador_zona = 1

        if self._contador_zona >= frames_estables and zona != self.zona_estable:
            self.zona_anterior = self.zona_estable
            self.zona_estable = zona
            self.zona_desde = ahora

        ventana = float(self.cfg.get("ventana_s", 5.0))
        self.historial.append((ahora, self.zona_estable, centro_norm))
        while self.historial and ahora - self.historial[0][0] > ventana:
            self.historial.popleft()

        trayectoria = self._calcular_trayectoria(hay)
        permanencia = max(0.0, ahora - self.zona_desde)
        return trayectoria, permanencia

    def _calcular_trayectoria(self, hay: bool) -> str:
        if not hay:
            return "SIN_VEHICULO"

        zonas = [item[1] for item in self.historial]
        if self.zona_estable == "A" and "B" in zonas[:-1]:
            return "INGRESO"
        if self.zona_estable == "B" and "A" in zonas[:-1]:
            return "SALIDA"
        if self.zona_estable == "A" and bool(self.cfg.get("permitir_ingreso_directo_a", False)):
            return "INGRESO_PROBABLE"

        if len(self.historial) >= 2:
            p0 = self.historial[0][2]
            p1 = self.historial[-1][2]
            distancia = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            if distancia >= float(self.cfg.get("desplazamiento_min_norm", 0.025)):
                return "MOVIENDOSE"
        return "QUIETO"


class CalculadorScore:
    """Calcula el score usando un perfil específico para cada zona.

    También aplica una validación híbrida: YOLO solo aporta sus puntos cuando
    la apariencia geométrica/color del objeto es mínimamente compatible con el
    propietario. Esto evita que un clasificador sobreajustado entregue Y25 a
    cualquier vehículo.
    """

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.perfil_fallback = cfg.get("perfil_dueno", {})
        self.perfiles = cfg.get("perfiles_dueno", {})
        self.puntos = cfg["score"]
        self.yolo_cfg = cfg["yolo"]
        self.ultima_zona_perfil = "NINGUNA"
        self.ultimo_score_visual = 0
        self.ultimo_yolo_validado = False
        self.ultimo_motivo_yolo = "SIN_EVALUAR"

    @staticmethod
    def _lineal(valor: float, esperado: float, tolerancia: float, maximo: int) -> int:
        if tolerancia <= 0:
            return maximo if abs(valor - esperado) < 1e-9 else 0
        error = abs(valor - esperado)
        return int(round(maximo * max(0.0, 1.0 - error / tolerancia)))

    def _perfil_para_zona(self, zona: str) -> Dict[str, Any]:
        zona = str(zona or "NINGUNA").upper()
        perfil = self.perfiles.get(zona)
        if isinstance(perfil, dict) and perfil:
            self.ultima_zona_perfil = zona
            return perfil
        self.ultima_zona_perfil = "FALLBACK"
        return self.perfil_fallback

    def _umbral_visual_yolo(self, zona: str) -> int:
        por_zona = self.yolo_cfg.get("score_visual_minimo_por_zona", {})
        if isinstance(por_zona, dict) and zona in por_zona:
            return int(por_zona[zona])
        return int(self.yolo_cfg.get("score_visual_minimo_para_yolo", 50))

    def _componentes_minimos_yolo(self, zona: str) -> Dict[str, int]:
        """Devuelve los mínimos visuales por componente exigidos para aceptar Y25.

        Esta segunda barrera evita que un vehículo del mismo color que el dueño
        sea aceptado únicamente porque YOLO lo clasificó mal y porque la suma
        visual global quedó cerca del umbral.
        """
        reglas_defecto = {
            "A": {"color": 20, "tamano": 8},
            "B": {"tamano": 9},
            "C": {"tamano": 5},
        }
        reglas = self.yolo_cfg.get("componentes_minimos_por_zona", reglas_defecto)
        if not isinstance(reglas, dict):
            reglas = reglas_defecto
        zona_norm = str(zona or "NINGUNA").upper()
        zona_cfg = reglas.get(zona_norm, reglas_defecto.get(zona_norm, {}))
        if not isinstance(zona_cfg, dict):
            return {}
        permitidos = {"color", "tamano", "aspecto", "silueta"}
        salida: Dict[str, int] = {}
        for nombre, valor in zona_cfg.items():
            if nombre in permitidos:
                try:
                    salida[nombre] = max(0, int(valor))
                except (TypeError, ValueError):
                    continue
        return salida

    def calcular(self, obj: Optional[ObjetoDetectado], trayectoria: str, yolo: ResultadoYolo) -> Dict[str, int]:
        detalle = {"yolo": 0, "color": 0, "tamano": 0, "aspecto": 0, "silueta": 0, "trayectoria": 0}
        self.ultimo_score_visual = 0
        self.ultimo_yolo_validado = False
        self.ultimo_motivo_yolo = "SIN_EVALUAR"
        self.ultima_zona_perfil = "NINGUNA"

        if obj is None:
            detalle["total"] = 0
            return detalle

        zona = str(obj.zona or "NINGUNA").upper()
        perfil = self._perfil_para_zona(zona)

        hsv_ref = perfil.get("hsv_centro", [100, 130, 130])
        hsv_tol = perfil.get("hsv_tolerancia", [20, 90, 100])
        h, s, v = obj.hsv_mediana
        similitud_h = max(
            0.0,
            1.0 - distancia_hue(float(h), float(hsv_ref[0])) / max(1.0, float(hsv_tol[0])),
        )
        similitud_s = max(
            0.0,
            1.0 - abs(float(s) - float(hsv_ref[1])) / max(1.0, float(hsv_tol[1])),
        )
        similitud_v = max(
            0.0,
            1.0 - abs(float(v) - float(hsv_ref[2])) / max(1.0, float(hsv_tol[2])),
        )
        similitud_color = 0.60 * similitud_h + 0.22 * similitud_s + 0.18 * similitud_v
        detalle["color"] = int(round(int(self.puntos.get("p_color", 25)) * similitud_color))

        detalle["tamano"] = self._lineal(
            obj.area_ratio,
            float(perfil.get("area_ratio_esperada", 0.055)),
            float(perfil.get("area_ratio_tolerancia", 0.045)),
            int(self.puntos.get("p_tamano", 15)),
        )
        detalle["aspecto"] = self._lineal(
            obj.aspecto,
            float(perfil.get("aspecto_esperado", 1.8)),
            float(perfil.get("aspecto_tolerancia", 0.75)),
            int(self.puntos.get("p_aspecto", 15)),
        )
        detalle["silueta"] = self._lineal(
            obj.extent,
            float(perfil.get("extent_esperado", 0.58)),
            float(perfil.get("extent_tolerancia", 0.35)),
            int(self.puntos.get("p_silueta", 10)),
        )

        score_visual = detalle["color"] + detalle["tamano"] + detalle["aspecto"] + detalle["silueta"]
        self.ultimo_score_visual = int(score_visual)

        clase_dueno = str(self.yolo_cfg.get("clase_dueno", "auto_dueno")).lower()
        conf_min = max(0.01, float(self.yolo_cfg.get("confianza_min", 0.70)))
        yolo_dice_dueno = (
            yolo.disponible
            and yolo.clase_principal.lower() == clase_dueno
            and float(yolo.confianza_principal) >= conf_min
        )

        validar_hibrido = bool(self.yolo_cfg.get("validacion_hibrida", True))
        umbral_visual = self._umbral_visual_yolo(zona)
        componentes_minimos = self._componentes_minimos_yolo(zona)

        cumple_visual = score_visual >= umbral_visual
        componentes_fallidos = [
            f"{nombre}<{minimo}"
            for nombre, minimo in componentes_minimos.items()
            if int(detalle.get(nombre, 0)) < int(minimo)
        ]
        cumple_componentes = not componentes_fallidos

        if not yolo.disponible:
            self.ultimo_motivo_yolo = "YOLO_NO_DISPONIBLE"
        elif yolo.clase_principal.lower() != clase_dueno:
            self.ultimo_motivo_yolo = f"CLASE_{yolo.clase_principal or 'NINGUNA'}"
        elif float(yolo.confianza_principal) < conf_min:
            self.ultimo_motivo_yolo = f"CONF<{conf_min:.2f}"
        elif validar_hibrido and not cumple_visual:
            self.ultimo_motivo_yolo = f"V<{umbral_visual}"
        elif validar_hibrido and not cumple_componentes:
            self.ultimo_motivo_yolo = "+".join(componentes_fallidos)
        else:
            self.ultimo_motivo_yolo = "VALIDADO"

        yolo_validado = yolo_dice_dueno and (
            not validar_hibrido or (cumple_visual and cumple_componentes)
        )

        if yolo_validado:
            detalle["yolo"] = int(self.puntos.get("p_yolo_dueno", 25))
            self.ultimo_yolo_validado = True

        if trayectoria in {"INGRESO", "INGRESO_PROBABLE"}:
            detalle["trayectoria"] = int(self.puntos.get("p_trayectoria", 10))

        detalle["total"] = (
            detalle["yolo"]
            + detalle["color"]
            + detalle["tamano"]
            + detalle["aspecto"]
            + detalle["silueta"]
            + detalle["trayectoria"]
        )
        return detalle

def poligono_pix(poligono: PoligonoNorm, ancho: int, alto: int) -> np.ndarray:
    return np.array([[int(x * ancho), int(y * alto)] for x, y in poligono], dtype=np.int32)


def crear_mascara(frame: np.ndarray, poligonos: Sequence[PoligonoNorm]) -> np.ndarray:
    alto, ancho = frame.shape[:2]
    mascara = np.zeros((alto, ancho), dtype=np.uint8)
    for poly in poligonos:
        cv2.fillPoly(mascara, [poligono_pix(poly, ancho, alto)], 255)
    return mascara


def expandir_mascara(mascara: np.ndarray, margen_px: int) -> np.ndarray:
    """Amplía una región de seguridad sin modificar el polígono guardado."""
    margen = max(0, int(margen_px))
    if margen <= 0:
        return mascara.copy()
    tam = 2 * margen + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tam, tam))
    return cv2.dilate(mascara, kernel, iterations=1)


def distancia_hue(h1: float, h2: float) -> float:
    diferencia = abs(float(h1) - float(h2))
    return min(diferencia, 180.0 - diferencia)


def centro_hue_circular(valores: np.ndarray, pesos: Optional[np.ndarray] = None) -> float:
    """Promedio circular del canal H de OpenCV (rango 0..179)."""
    if valores.size == 0:
        return 0.0
    angulos = valores.astype(np.float64) * (2.0 * math.pi / 180.0)
    if pesos is None or pesos.size != valores.size:
        pesos = np.ones_like(angulos, dtype=np.float64)
    else:
        pesos = np.maximum(1e-6, pesos.astype(np.float64))
    seno = float(np.sum(np.sin(angulos) * pesos))
    coseno = float(np.sum(np.cos(angulos) * pesos))
    angulo = math.atan2(seno, coseno)
    if angulo < 0:
        angulo += 2.0 * math.pi
    return (angulo * 180.0 / (2.0 * math.pi)) % 180.0


def hsv_representativo(
    hsv: np.ndarray,
    mascara_objeto: np.ndarray,
    cfg_color: Optional[Dict[str, Any]] = None,
) -> Tuple[Tuple[int, int, int], int]:
    """
    Calcula el color del objeto usando solo píxeles cromáticos y luminosos.

    Esto elimina gran parte del suelo gris, ruedas, ventanas y sombras que antes
    dominaban la mediana HSV del vehículo.
    """
    cfg = cfg_color or {}
    s_min = int(cfg.get("saturacion_min", 55))
    v_min = int(cfg.get("valor_min", 55))
    min_pixeles = max(20, int(cfg.get("min_pixeles", 80)))
    erosion_px = max(0, int(cfg.get("erosion_px", 2)))

    mascara = (mascara_objeto > 0).astype(np.uint8) * 255
    if erosion_px > 0:
        tam = 2 * erosion_px + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (tam, tam))
        erosionada = cv2.erode(mascara, kernel, iterations=1)
        if cv2.countNonZero(erosionada) >= min_pixeles:
            mascara = erosionada

    seleccion = (
        (mascara > 0)
        & (hsv[:, :, 1] >= s_min)
        & (hsv[:, :, 2] >= v_min)
    )
    pixeles = hsv[seleccion]

    # Respaldo: si el objeto tiene pocos píxeles cromáticos, se relajan los
    # límites, pero nunca se usa directamente todo el rectángulo envolvente.
    if len(pixeles) < min_pixeles:
        seleccion = (
            (mascara > 0)
            & (hsv[:, :, 1] >= max(25, s_min // 2))
            & (hsv[:, :, 2] >= max(35, v_min // 2))
        )
        pixeles = hsv[seleccion]

    if len(pixeles) == 0:
        return (0, 0, 0), 0

    pesos = np.maximum(1.0, pixeles[:, 1].astype(np.float64))
    h = centro_hue_circular(pixeles[:, 0], pesos)
    s = float(np.median(pixeles[:, 1]))
    v = float(np.median(pixeles[:, 2]))
    return (int(round(h)) % 180, int(round(s)), int(round(v))), int(len(pixeles))


def zona_de_punto(punto: Punto, frame: np.ndarray, zonas: Dict[str, PoligonoNorm]) -> str:
    alto, ancho = frame.shape[:2]
    for nombre in ("A", "B", "C"):
        poly = zonas.get(nombre)
        if poly and cv2.pointPolygonTest(poligono_pix(poly, ancho, alto), punto, False) >= 0:
            return nombre
    return "NINGUNA"


def extraer_objetos(
    frame: np.ndarray,
    contornos: List[np.ndarray],
    zonas: Dict[str, PoligonoNorm],
    cfg_color: Optional[Dict[str, Any]] = None,
) -> List[ObjetoDetectado]:
    alto, ancho = frame.shape[:2]
    area_frame = float(max(1, alto * ancho))
    objetos: List[ObjetoDetectado] = []

    for contorno in contornos:
        area = float(cv2.contourArea(contorno))
        x, y, w, h = cv2.boundingRect(contorno)
        if w <= 0 or h <= 0:
            continue
        bbox_area = float(w * h)
        centro = (x + w // 2, y + h // 2)
        zona = zona_de_punto(centro, frame, zonas)

        mascara_obj = np.zeros((h, w), dtype=np.uint8)
        contorno_local = contorno.copy()
        contorno_local[:, 0, 0] -= x
        contorno_local[:, 0, 1] -= y
        cv2.drawContours(mascara_obj, [contorno_local], -1, 255, thickness=-1)
        recorte = frame[y : y + h, x : x + w]
        hsv = cv2.cvtColor(recorte, cv2.COLOR_BGR2HSV)
        hsv_mediana, pixeles_color = hsv_representativo(hsv, mascara_obj, cfg_color)

        confianza = min(1.0, area / max(1.0, 4.0 * 900.0))
        objetos.append(
            ObjetoDetectado(
                bbox=(x, y, w, h),
                centro=centro,
                area_contorno=area,
                area_bbox=bbox_area,
                area_ratio=bbox_area / area_frame,
                aspecto=float(w) / float(h),
                extent=area / bbox_area,
                confianza=confianza,
                hsv_mediana=hsv_mediana,
                pixeles_color=pixeles_color,
                zona=zona,
            )
        )
    return objetos


def brillo_medio(frame: Optional[np.ndarray]) -> float:
    if frame is None or frame.size == 0:
        return 0.0
    gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gris))
