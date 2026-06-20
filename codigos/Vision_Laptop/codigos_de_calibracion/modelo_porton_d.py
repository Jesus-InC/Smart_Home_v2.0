from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np


BBox = Tuple[int, int, int, int]


@dataclass
class ResultadoModeloPortonD:
    disponible: bool = False
    listo: bool = False
    obstaculo: bool = True
    confianza: float = 0.0
    bbox: Optional[BBox] = None
    mascara: Optional[np.ndarray] = None
    estado_porton: str = "DESCONOCIDO"
    modo: str = "SIN_MODELO"
    indice_template: int = -1
    error_ajuste: float = 999.0
    area_residual: float = 0.0
    error: str = ""


class ModeloMovimientoPortonD:
    """Modelo visual del movimiento limpio del portón corredizo.

    La calibración guarda secuencias limpias de cierre y apertura. Durante el
    movimiento no se compara contra una sola plantilla rígida: se usa una
    pequeña ventana de plantillas vecinas y, para cada píxel, se conserva la
    diferencia mínima. Esto absorbe desfases de velocidad, sombras móviles y
    pequeñas variaciones en los bordes laterales sin ignorar objetos nuevos.
    """

    ESTADOS_VALIDOS = {"ABIERTO", "CERRADO", "ABRIENDO", "CERRANDO", "DETENIDO"}

    def __init__(self, cfg: Dict[str, Any], base_dir: Path) -> None:
        self.cfg = cfg
        self.base_dir = base_dir
        self.usar = bool(cfg.get("usar", True))
        self.disponible = False
        self.error = ""

        self.cierre: Optional[np.ndarray] = None
        self.apertura: Optional[np.ndarray] = None
        self.cierre_small: Optional[np.ndarray] = None
        self.apertura_small: Optional[np.ndarray] = None
        self.ref_abierto: Optional[np.ndarray] = None
        self.ref_cerrado: Optional[np.ndarray] = None
        # Modelo multicíclo. Las plantillas se guardan intercaladas por fase:
        # fase 0 de todos los ciclos, fase 1 de todos los ciclos, etc.
        self.ciclos_cierre = 1
        self.ciclos_apertura = 1
        self.templates_cierre_por_ciclo = 0
        self.templates_apertura_por_ciclo = 0

        self._ultimo_estado = "DESCONOCIDO"
        self._ultimo_indice = -1
        # Si un obstáculo altera la selección de fase, el siguiente fotograma
        # se vuelve a localizar globalmente. Así, al retirar el objeto no se
        # conserva una plantilla incorrecta por la penalización de continuidad.
        self._obstaculo_previo_movimiento = False
        self._borde_apertura_inicio: Optional[float] = None
        self._borde_apertura_lado: str = ""
        self._borde_apertura_bbox: Optional[BBox] = None
        self._borde_cierre_inicio: Optional[float] = None
        self._borde_cierre_lado: str = ""
        self._borde_cierre_bbox: Optional[BBox] = None

        # Confirmación específica para objetos pequeños que apenas ingresan
        # por el extremo izquierdo cuando el portón está CERRADO.
        self._borde_estatico_inicio: Optional[float] = None
        self._borde_estatico_bbox: Optional[BBox] = None
        self._borde_estatico_confirmado: bool = False

        if self.usar:
            self._cargar()

    @staticmethod
    def preparar(frame: np.ndarray) -> np.ndarray:
        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(gris, (7, 7), 0)

    @property
    def ruta_modelo(self) -> Path:
        ruta = Path(str(self.cfg.get("archivo", "modelos/modelo_porton_d.npz")))
        return ruta if ruta.is_absolute() else self.base_dir / ruta

    def _cargar(self) -> None:
        ruta = self.ruta_modelo
        if not ruta.exists():
            self.error = f"No existe el modelo del portón: {ruta}"
            return

        try:
            datos = np.load(ruta, allow_pickle=False)
            cierre = np.asarray(datos["cierre"], dtype=np.uint8)
            apertura = np.asarray(datos["apertura"], dtype=np.uint8)
            if cierre.ndim != 3 or apertura.ndim != 3:
                raise ValueError("Las secuencias deben tener forma N x H x W")
            if len(cierre) < 3 or len(apertura) < 3:
                raise ValueError("Se requieren al menos 3 plantillas por secuencia")
            if cierre.shape[1:] != apertura.shape[1:]:
                raise ValueError("Apertura y cierre tienen resoluciones diferentes")

            self.cierre = cierre
            self.apertura = apertura

            ciclos = int(np.asarray(datos["ciclos"]).ravel()[0]) if "ciclos" in datos else 1
            tpc_c = int(np.asarray(datos["templates_cierre_por_ciclo"]).ravel()[0]) if "templates_cierre_por_ciclo" in datos else len(cierre)
            tpc_a = int(np.asarray(datos["templates_apertura_por_ciclo"]).ravel()[0]) if "templates_apertura_por_ciclo" in datos else len(apertura)
            ciclos = max(1, ciclos)
            if ciclos * tpc_c != len(cierre) or ciclos * tpc_a != len(apertura):
                raise ValueError("Metadatos multicíclo incompatibles con las plantillas guardadas")
            self.ciclos_cierre = ciclos
            self.ciclos_apertura = ciclos
            self.templates_cierre_por_ciclo = tpc_c
            self.templates_apertura_por_ciclo = tpc_a

            ancho_match = int(self.cfg.get("match_ancho", 160))
            alto_match = int(self.cfg.get("match_alto", 120))
            self.cierre_small = np.stack(
                [cv2.resize(f, (ancho_match, alto_match), interpolation=cv2.INTER_AREA) for f in cierre]
            )
            self.apertura_small = np.stack(
                [cv2.resize(f, (ancho_match, alto_match), interpolation=cv2.INTER_AREA) for f in apertura]
            )

            n_extremos = max(1, int(self.cfg.get("frames_extremo", 1)))
            fases_c_abierto = range(0, min(n_extremos, self.templates_cierre_por_ciclo))
            fases_a_abierto = range(max(0, self.templates_apertura_por_ciclo - n_extremos), self.templates_apertura_por_ciclo)
            fases_c_cerrado = range(max(0, self.templates_cierre_por_ciclo - n_extremos), self.templates_cierre_por_ciclo)
            fases_a_cerrado = range(0, min(n_extremos, self.templates_apertura_por_ciclo))

            def refs_fases(arr: np.ndarray, fases, ciclos_n: int) -> np.ndarray:
                idx = [fase * ciclos_n + ciclo for fase in fases for ciclo in range(ciclos_n)]
                return arr[np.asarray(idx, dtype=np.int32)]

            abiertos = np.concatenate([
                refs_fases(cierre, fases_c_abierto, self.ciclos_cierre),
                refs_fases(apertura, fases_a_abierto, self.ciclos_apertura),
            ], axis=0)
            cerrados = np.concatenate([
                refs_fases(cierre, fases_c_cerrado, self.ciclos_cierre),
                refs_fases(apertura, fases_a_cerrado, self.ciclos_apertura),
            ], axis=0)
            self.ref_abierto = np.median(abiertos, axis=0).astype(np.uint8)
            self.ref_cerrado = np.median(cerrados, axis=0).astype(np.uint8)
            self.disponible = True
            self.error = ""
            print(
                f"[PORTÓN D] Modelo cargado: {ruta} "
                f"({self.ciclos_cierre} ciclos, "
                f"{self.templates_cierre_por_ciclo} fases/cierre, "
                f"{self.templates_apertura_por_ciclo} fases/apertura)"
            )
        except Exception as exc:  # noqa: BLE001
            self.error = f"No se pudo cargar el modelo del portón: {exc}"
            self.disponible = False

    def recargar(self) -> bool:
        self.disponible = False
        self.error = ""
        self._cargar()
        return self.disponible

    def reiniciar_seguimiento(self) -> None:
        self._ultimo_estado = "DESCONOCIDO"
        self._ultimo_indice = -1
        self._obstaculo_previo_movimiento = False
        self._reiniciar_borde_apertura()
        self._reiniciar_borde_cierre()
        self._reiniciar_borde_estatico()

    def _reiniciar_borde_apertura(self) -> None:
        self._borde_apertura_inicio = None
        self._borde_apertura_lado = ""
        self._borde_apertura_bbox = None

    def _reiniciar_borde_cierre(self) -> None:
        self._borde_cierre_inicio = None
        self._borde_cierre_lado = ""
        self._borde_cierre_bbox = None

    def _reiniciar_borde_estatico(self) -> None:
        self._borde_estatico_inicio = None
        self._borde_estatico_bbox = None
        self._borde_estatico_confirmado = False

    @staticmethod
    def _iou_bbox(a: Optional[BBox], b: Optional[BBox]) -> float:
        if a is None or b is None:
            return 0.0
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ax2, ay2 = ax + aw, ay + ah
        bx2, by2 = bx + bw, by + bh
        ix1, iy1 = max(ax, bx), max(ay, by)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = float(iw * ih)
        union = float(aw * ah + bw * bh) - inter
        return inter / union if union > 0.0 else 0.0

    def _mismo_candidato_borde(
        self,
        anterior: Optional[BBox],
        actual: BBox,
    ) -> bool:
        if anterior is None:
            return False
        ax, ay, aw, ah = anterior
        bx, by, bw, bh = actual
        acx, acy = ax + aw / 2.0, ay + ah / 2.0
        bcx, bcy = bx + bw / 2.0, by + bh / 2.0
        distancia = float(((acx - bcx) ** 2 + (acy - bcy) ** 2) ** 0.5)
        iou = self._iou_bbox(anterior, actual)
        area_a = max(1.0, float(aw * ah))
        area_b = max(1.0, float(bw * bh))
        razon_area = max(area_a, area_b) / min(area_a, area_b)

        iou_min = float(self.cfg.get("borde_tracking_iou_min", 0.35))
        distancia_max = float(self.cfg.get("borde_tracking_distancia_px", 14.0))
        razon_area_max = float(self.cfg.get("borde_tracking_razon_area_max", 2.2))
        return (iou >= iou_min or distancia <= distancia_max) and razon_area <= razon_area_max

    def _es_firma_lineal_porton(
        self,
        contorno: np.ndarray,
        area_min: float,
    ) -> bool:
        """Reconoce la firma residual del canto móvil del portón.

        En los videos limpios, el falso positivo es una línea larga, muy delgada
        y con poco relleno dentro de su rectángulo. Un obstáculo real usado en
        la maqueta genera una región mucho más compacta. Esta clasificación se
        aplica solo mientras el portón está en movimiento.
        """
        area = float(cv2.contourArea(contorno))
        if area <= 0.0:
            return False

        x, y, w, h = cv2.boundingRect(contorno)
        area_bbox = max(1.0, float(w * h))
        extent = area / area_bbox

        hull = cv2.convexHull(contorno)
        area_hull = max(1.0, float(cv2.contourArea(hull)))
        solidez = area / area_hull

        rect = cv2.minAreaRect(contorno)
        lado_a, lado_b = rect[1]
        largo = max(float(lado_a), float(lado_b))
        corto = min(float(lado_a), float(lado_b))
        espesor_estimado = area / max(1.0, largo)

        largo_min = float(self.cfg.get("firma_porton_largo_min_px", 48.0))
        corto_max = float(self.cfg.get("firma_porton_corto_max_px", 15.0))
        espesor_max = float(self.cfg.get("firma_porton_espesor_max_px", 10.0))
        extent_max = float(self.cfg.get("firma_porton_extent_max", 0.22))
        solidez_max = float(self.cfg.get("firma_porton_solidez_max", 0.98))
        area_max = float(self.cfg.get("firma_porton_area_max", max(6000.0, 10.0 * area_min)))

        return (
            largo >= largo_min
            and area <= area_max
            and extent <= extent_max
            and solidez <= solidez_max
            and (corto <= corto_max or espesor_estimado <= espesor_max)
        )


    def _evaluar_borde_estatico_cerrado(
        self,
        contornos: list[np.ndarray],
        binaria: np.ndarray,
        pixels: np.ndarray,
        area_min: float,
        modo: str,
        indice_template: int,
    ) -> Optional[ResultadoModeloPortonD]:
        """Refuerza el extremo izquierdo con el portón completamente cerrado.

        El objeto de prueba a veces entra solo parcialmente en la máscara y su
        área queda por debajo del umbral general. Se acepta un umbral menor
        únicamente en la banda izquierda y se exige persistencia, evitando que
        ruido aislado produzca una ocupación.
        """
        area_min_borde = float(
            self.cfg.get("cerrado_izquierdo_area_min", max(90.0, 0.18 * area_min))
        )
        candidatos = [
            c for c in contornos
            if area_min_borde <= float(cv2.contourArea(c)) < area_min
        ]
        if not candidatos:
            self._reiniciar_borde_estatico()
            return None

        mascara_zona_u8 = np.zeros_like(binaria, dtype=np.uint8)
        mascara_zona_u8[pixels] = 255
        banda_px = max(4, int(self.cfg.get("cerrado_izquierdo_banda_px", 34)))
        kernel_banda = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * banda_px + 1, 2 * banda_px + 1),
        )
        interior = cv2.erode(mascara_zona_u8, kernel_banda, iterations=1)
        banda_borde = (mascara_zona_u8 > 0) & (interior == 0)

        ys_z, xs_z = np.nonzero(pixels)
        centro_zona_x = float(np.median(xs_z)) if len(xs_z) else binaria.shape[1] / 2.0
        solape_min = float(self.cfg.get("cerrado_izquierdo_solape_min", 0.20))

        elegibles: list[tuple[float, np.ndarray, BBox]] = []
        for contorno in candidatos:
            x, y, w, h = cv2.boundingRect(contorno)
            if x + w / 2.0 >= centro_zona_x:
                continue
            mascara_c = np.zeros_like(binaria, dtype=np.uint8)
            cv2.drawContours(mascara_c, [contorno], -1, 255, thickness=-1)
            pix_c = mascara_c > 0
            total = max(1, int(np.count_nonzero(pix_c)))
            solape = float(np.count_nonzero(pix_c & banda_borde)) / total
            if solape >= solape_min:
                elegibles.append((float(cv2.contourArea(contorno)), contorno, (x, y, w, h)))

        if not elegibles:
            self._reiniciar_borde_estatico()
            return None

        elegibles.sort(key=lambda item: item[0], reverse=True)
        area, _, bbox = elegibles[0]
        ahora = time.monotonic()
        mismo = self._mismo_candidato_borde(self._borde_estatico_bbox, bbox)
        if self._borde_estatico_inicio is None or not mismo:
            self._borde_estatico_inicio = ahora
            self._borde_estatico_bbox = bbox
            self._borde_estatico_confirmado = False

        confirmacion_s = max(
            0.05, float(self.cfg.get("cerrado_izquierdo_confirmacion_s", 0.30))
        )
        if ahora - self._borde_estatico_inicio >= confirmacion_s:
            self._borde_estatico_confirmado = True

        if not self._borde_estatico_confirmado:
            return ResultadoModeloPortonD(
                disponible=True,
                listo=True,
                obstaculo=False,
                confianza=0.0,
                bbox=None,
                mascara=binaria,
                estado_porton="CERRADO",
                modo="BORDE_IZQUIERDO_EVALUANDO",
                indice_template=indice_template,
                error_ajuste=0.0,
                area_residual=area,
            )

        x, y, w, h = bbox
        confianza = min(1.0, area / max(1.0, area_min))
        return ResultadoModeloPortonD(
            disponible=True,
            listo=True,
            obstaculo=True,
            confianza=confianza,
            bbox=bbox,
            mascara=binaria,
            estado_porton="CERRADO",
            modo="OBSTACULO_BORDE_IZQUIERDO_CERRADO",
            indice_template=indice_template,
            error_ajuste=0.0,
            area_residual=area,
        )


    def detectar(
        self,
        frame: np.ndarray,
        estado_porton: str,
        mascara_zona: np.ndarray,
    ) -> ResultadoModeloPortonD:
        estado = str(estado_porton or "DESCONOCIDO").strip().upper()
        if not self.usar:
            return ResultadoModeloPortonD(
                disponible=False,
                listo=False,
                obstaculo=True,
                estado_porton=estado,
                modo="DESACTIVADO",
                error="Modelo de portón desactivado",
            )
        if not self.disponible:
            return ResultadoModeloPortonD(
                disponible=False,
                listo=False,
                obstaculo=True,
                estado_porton=estado,
                modo="SIN_MODELO",
                error=self.error,
            )
        if estado not in self.ESTADOS_VALIDOS:
            self._reiniciar_borde_apertura()
            self._reiniciar_borde_cierre()
            return ResultadoModeloPortonD(
                disponible=True,
                listo=False,
                obstaculo=True,
                estado_porton=estado,
                modo="ESTADO_DESCONOCIDO",
                error="Estado del portón desconocido",
            )

        if estado != "ABRIENDO":
            self._reiniciar_borde_apertura()
        if estado != "CERRANDO":
            self._reiniciar_borde_cierre()
        if estado != "CERRADO":
            self._reiniciar_borde_estatico()

        actual = self.preparar(frame)
        if self.cierre is not None and actual.shape != self.cierre.shape[1:]:
            return ResultadoModeloPortonD(
                disponible=True,
                listo=False,
                obstaculo=True,
                estado_porton=estado,
                modo="RESOLUCION_INCOMPATIBLE",
                error=(
                    f"La cámara D entrega {actual.shape[1]}x{actual.shape[0]}, "
                    f"pero el modelo usa {self.cierre.shape[2]}x{self.cierre.shape[1]}"
                ),
            )
        if self.ref_abierto is None or self.ref_cerrado is None:
            return ResultadoModeloPortonD(
                disponible=False,
                listo=False,
                obstaculo=True,
                estado_porton=estado,
                modo="MODELO_INCOMPLETO",
                error="Referencias de extremo no disponibles",
            )

        # Cada cambio real de estado inicia una búsqueda de fase nueva. Esto es
        # especialmente importante entre ciclos consecutivos: la apertura o el
        # cierre anterior no debe arrastrar el índice final al siguiente ciclo.
        if estado != self._ultimo_estado:
            self._ultimo_indice = -1
            self._obstaculo_previo_movimiento = False

        if estado == "ABIERTO":
            self._ultimo_estado = estado
            self._ultimo_indice = -1
            self._obstaculo_previo_movimiento = False
            return self._detectar_con_referencia_estatica(
                actual,
                self.ref_abierto,
                mascara_zona,
                estado,
                "REFERENCIA_ABIERTO",
            )
        if estado == "CERRADO":
            self._ultimo_estado = estado
            self._ultimo_indice = -1
            self._obstaculo_previo_movimiento = False
            return self._detectar_con_referencia_estatica(
                actual,
                self.ref_cerrado,
                mascara_zona,
                estado,
                "REFERENCIA_CERRADO",
            )

        if estado == "CERRANDO":
            secuencia = self.cierre
            secuencia_small = self.cierre_small
            modo = "PLANTILLA_CIERRE_ROBUSTA"
        elif estado == "ABRIENDO":
            secuencia = self.apertura
            secuencia_small = self.apertura_small
            modo = "PLANTILLA_APERTURA_ROBUSTA"
        else:  # DETENIDO: seleccionar entre ambas secuencias
            assert self.cierre is not None and self.apertura is not None
            assert self.cierre_small is not None and self.apertura_small is not None
            secuencia = np.concatenate([self.cierre, self.apertura], axis=0)
            secuencia_small = np.concatenate([self.cierre_small, self.apertura_small], axis=0)
            modo = "PLANTILLA_DETENIDO_ROBUSTA"

        assert secuencia is not None and secuencia_small is not None
        # Mientras hubo obstáculo, la imagen puede haber elegido una fase
        # incorrecta. En ese caso se desactiva temporalmente la penalización de
        # salto y se hace un reenganche global. Al quitar el objeto, el modelo
        # recupera la fase correcta en el siguiente fotograma, no varios
        # segundos después.
        reenganche_global = bool(self._obstaculo_previo_movimiento)
        indice, error = self._seleccionar_template(
            actual,
            secuencia_small,
            mascara_zona,
            estado,
            usar_continuidad=not reenganche_global,
        )
        self._ultimo_estado = estado
        self._ultimo_indice = indice

        resultado = self._detectar_con_ventana_templates(
            actual,
            secuencia,
            indice,
            mascara_zona,
            estado,
            modo,
        )
        resultado.error_ajuste = error

        error_max = float(self.cfg.get("error_ajuste_max", 30.0))
        if error > error_max:
            resultado.obstaculo = True
            resultado.listo = False
            resultado.error = f"Ajuste visual incierto ({error:.1f} > {error_max:.1f})"
            resultado.modo = "AJUSTE_INCIERTO"

        if reenganche_global and not resultado.obstaculo and resultado.listo:
            resultado.modo = f"{resultado.modo}_REENGANCHADO"
        self._obstaculo_previo_movimiento = bool(resultado.obstaculo)
        return resultado

    def _seleccionar_template(
        self,
        actual: np.ndarray,
        secuencia_small: np.ndarray,
        mascara_zona: np.ndarray,
        estado: str,
        usar_continuidad: bool = True,
    ) -> Tuple[int, float]:
        alto_match = secuencia_small.shape[1]
        ancho_match = secuencia_small.shape[2]
        actual_small = cv2.resize(actual, (ancho_match, alto_match), interpolation=cv2.INTER_AREA)
        mascara_small = cv2.resize(
            mascara_zona,
            (ancho_match, alto_match),
            interpolation=cv2.INTER_NEAREST,
        ) > 0

        diferencias = np.abs(secuencia_small.astype(np.int16) - actual_small.astype(np.int16))
        clip = int(self.cfg.get("match_clip", 40))
        diferencias = np.minimum(diferencias, clip)
        pixeles = max(1, int(np.count_nonzero(mascara_small)))
        errores = np.sum(diferencias[:, mascara_small], axis=1) / float(pixeles)

        ciclos, fases = self._estructura_secuencia(estado, len(errores))
        if usar_continuidad and estado == self._ultimo_estado and self._ultimo_indice >= 0:
            penalizacion = float(self.cfg.get("penalizacion_salto", 0.08))
            indices = np.arange(len(errores), dtype=np.int32)
            fases_actuales = indices // ciclos
            fase_previa = self._ultimo_indice // ciclos
            errores = errores + penalizacion * np.abs(fases_actuales - fase_previa)

        indice = int(np.argmin(errores))
        return indice, float(errores[indice])

    def _estructura_secuencia(self, estado: str, cantidad: int) -> Tuple[int, int]:
        if estado == "CERRANDO":
            return self.ciclos_cierre, self.templates_cierre_por_ciclo
        if estado == "ABRIENDO":
            return self.ciclos_apertura, self.templates_apertura_por_ciclo
        return 1, cantidad

    def _indices_vecinos(self, cantidad: int, indice: int, estado: str) -> np.ndarray:
        # La envolvente necesita observar varias fases cercanas de todos los
        # ciclos limpios. Así representa no solo posiciones discretas, sino el
        # intervalo real de sombras y holguras que puede adoptar el mecanismo.
        radio = max(0, int(self.cfg.get("radio_envolvente_fases", 5)))
        ciclos, fases = self._estructura_secuencia(estado, cantidad)
        if ciclos <= 1:
            inicio = max(0, indice - radio)
            fin = min(cantidad, indice + radio + 1)
            return np.arange(inicio, fin, dtype=np.int32)

        fase = indice // ciclos
        inicio_fase = max(0, fase - radio)
        fin_fase = min(fases, fase + radio + 1)
        indices = [f * ciclos + c for f in range(inicio_fase, fin_fase) for c in range(ciclos)]
        return np.asarray(indices, dtype=np.int32)

    def _ajustar_actual_a_referencia(
        self,
        actual: np.ndarray,
        referencia: np.ndarray,
        pixels: np.ndarray,
    ) -> np.ndarray:
        actual_ajustado = actual.astype(np.int16)
        ref_i16 = referencia.astype(np.int16)
        if np.any(pixels):
            delta = float(np.median(ref_i16[pixels]) - np.median(actual_ajustado[pixels]))
            limite = float(self.cfg.get("compensacion_brillo_max", 20.0))
            delta = max(-limite, min(limite, delta))
            actual_ajustado = np.clip(actual_ajustado + delta, 0, 255)
        return actual_ajustado

    def _desplazar_referencia(
        self,
        referencia: np.ndarray,
        dx: int,
        dy: int,
    ) -> np.ndarray:
        """Desplaza una plantilla unos pocos píxeles sin crear bordes negros."""
        if dx == 0 and dy == 0:
            return referencia
        matriz = np.float32([[1.0, 0.0, float(dx)], [0.0, 1.0, float(dy)]])
        return cv2.warpAffine(
            referencia,
            matriz,
            (referencia.shape[1], referencia.shape[0]),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

    def _estimar_microdesplazamiento(
        self,
        actual: np.ndarray,
        referencia: np.ndarray,
        pixels: np.ndarray,
    ) -> Tuple[int, int]:
        """Compensa vibraciones o pequeños movimientos de cámara/maqueta.

        El ajuste está limitado a pocos píxeles y se calcula con diferencias
        recortadas, de modo que un objeto pequeño no pueda arrastrar el registro
        hacia sí mismo. Si la mejora frente a (0, 0) es mínima, no se desplaza.
        """
        max_px = max(0, int(self.cfg.get("registro_max_px", 4)))
        if max_px <= 0 or not np.any(pixels):
            return 0, 0

        paso = max(1, int(self.cfg.get("registro_muestreo_px", 3)))
        clip = max(5.0, float(self.cfg.get("registro_clip", 38.0)))
        penalizacion = max(0.0, float(self.cfg.get("registro_penalizacion_px", 0.12)))
        mejora_min = max(0.0, float(self.cfg.get("registro_mejora_min", 0.18)))

        # El fondo ocupa la mayor parte de D y puede ocultar un desfase pequeño
        # de la hoja/rieles. Para registrar, se prioriza una banda alrededor de
        # los bordes estructurales de la plantilla; si no hay suficientes puntos,
        # se vuelve a usar toda la zona.
        canny_bajo = int(self.cfg.get("registro_canny_bajo", 30))
        canny_alto = int(self.cfg.get("registro_canny_alto", 95))
        bordes_registro = cv2.Canny(referencia, canny_bajo, canny_alto)
        radio_registro = max(2, int(self.cfg.get("registro_banda_bordes_px", 10)))
        kernel_registro = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (2 * radio_registro + 1, 2 * radio_registro + 1),
        )
        banda_registro = cv2.dilate(bordes_registro, kernel_registro, iterations=1) > 0
        pixels_registro = pixels & banda_registro
        if np.count_nonzero(pixels_registro) < 300:
            pixels_registro = pixels

        ys, xs = np.nonzero(pixels_registro)
        seleccionar = ((ys % paso) == 0) & ((xs % paso) == 0)
        ys = ys[seleccionar]
        xs = xs[seleccionar]
        if len(xs) < 50:
            return 0, 0

        actual_i16 = actual.astype(np.int16)
        ref_i16 = referencia.astype(np.int16)
        alto, ancho = actual.shape[:2]

        def error_para(dx: int, dy: int) -> float:
            src_x = xs - dx
            src_y = ys - dy
            validos = (src_x >= 0) & (src_x < ancho) & (src_y >= 0) & (src_y < alto)
            if np.count_nonzero(validos) < 50:
                return 1e9
            av = actual_i16[ys[validos], xs[validos]].astype(np.float32)
            rv = ref_i16[src_y[validos], src_x[validos]].astype(np.float32)
            delta = float(np.median(rv) - np.median(av))
            limite = float(self.cfg.get("compensacion_brillo_max", 20.0))
            delta = max(-limite, min(limite, delta))
            diferencia = np.minimum(np.abs(rv - (av + delta)), clip)
            return float(np.mean(diferencia)) + penalizacion * (abs(dx) + abs(dy))

        error_cero = error_para(0, 0)
        mejor_error = error_cero
        mejor_dx = 0
        mejor_dy = 0
        for dy in range(-max_px, max_px + 1):
            for dx in range(-max_px, max_px + 1):
                if dx == 0 and dy == 0:
                    continue
                error = error_para(dx, dy)
                if error < mejor_error:
                    mejor_error = error
                    mejor_dx = dx
                    mejor_dy = dy

        if error_cero - mejor_error < mejora_min:
            return 0, 0
        return mejor_dx, mejor_dy

    def _detectar_con_ventana_templates(
        self,
        actual: np.ndarray,
        secuencia: np.ndarray,
        indice: int,
        mascara_zona: np.ndarray,
        estado: str,
        modo: str,
    ) -> ResultadoModeloPortonD:
        """Detecta obstáculos mediante una envolvente visual aprendida.

        La versión anterior comparaba cada píxel con muestras discretas. Una
        sombra normal situada entre dos intensidades grabadas podía quedar lejos
        de ambas y generar una franja falsa. Aquí cada píxel dispone de un rango
        limpio [inferior, superior] construido con varios ciclos y fases vecinas.
        Solo la parte de la imagen que queda fuera de ese rango se considera
        residual.
        """
        pixels = mascara_zona > 0
        indices = self._indices_vecinos(len(secuencia), indice, estado)
        referencias_sin_alinear = secuencia[indices]

        # Conservamos una compensación pequeña de vibración. Está limitada a
        # pocos píxeles y no modifica ni aprende el modelo almacenado.
        dx, dy = self._estimar_microdesplazamiento(actual, secuencia[indice], pixels)
        referencias = np.stack(
            [self._desplazar_referencia(ref, dx, dy) for ref in referencias_sin_alinear],
            axis=0,
        )

        refs_f = referencias.astype(np.float32)
        referencia_mediana = np.median(refs_f, axis=0).astype(np.uint8)
        actual_ajustado = self._ajustar_actual_a_referencia(
            actual, referencia_mediana, pixels
        ).astype(np.float32)

        # Percentiles robustos: un frame anómalo de la calibración no ensancha
        # por sí solo toda la envolvente. Con 3 ciclos y varias fases vecinas hay
        # suficientes muestras para representar la variación mecánica real.
        p_bajo = float(self.cfg.get("envolvente_percentil_bajo", 3.0))
        p_alto = float(self.cfg.get("envolvente_percentil_alto", 97.0))
        p_bajo = max(0.0, min(49.0, p_bajo))
        p_alto = max(51.0, min(100.0, p_alto))
        inferior = np.percentile(refs_f, p_bajo, axis=0)
        superior = np.percentile(refs_f, p_alto, axis=0)

        rango_limpio = np.maximum(0.0, superior - inferior)
        margen_base = float(self.cfg.get("envolvente_margen_base", 7.0))
        factor_rango = float(self.cfg.get("envolvente_factor_rango", 0.18))
        extra_max = float(self.cfg.get("envolvente_extra_max", 18.0))
        margen = margen_base + np.minimum(rango_limpio * factor_rango, extra_max)
        inferior = np.clip(inferior - margen, 0.0, 255.0)
        superior = np.clip(superior + margen, 0.0, 255.0)

        por_debajo = np.maximum(inferior - actual_ajustado, 0.0)
        por_encima = np.maximum(actual_ajustado - superior, 0.0)
        residual = np.maximum(por_debajo, por_encima)
        residual = np.clip(residual, 0, 255).astype(np.uint8)

        # Como el residual ya representa distancia FUERA de la envolvente, su
        # umbral debe ser menor que el usado por la resta absoluta antigua.
        umbral_fuera = float(self.cfg.get("envolvente_umbral_fuera", 11.0))
        mapa_umbral = np.full_like(residual, umbral_fuera, dtype=np.float32)

        # En píxeles extremadamente variables se concede una tolerancia extra,
        # pero con límite. No se anula la región: un objeto suficientemente
        # diferente continúa saliendo fuera de la envolvente.
        rango_inicio = float(self.cfg.get("envolvente_rango_dinamico_inicio", 55.0))
        extra_dinamico_max = float(
            self.cfg.get("envolvente_umbral_dinamico_extra_max", 12.0)
        )
        extra_dinamico = np.clip(
            (rango_limpio - rango_inicio) * 0.15, 0.0, extra_dinamico_max
        )
        mapa_umbral += extra_dinamico.astype(np.float32)

        modo_env = (
            "ENVOLVENTE_CIERRE" if estado == "CERRANDO"
            else "ENVOLVENTE_APERTURA" if estado == "ABRIENDO"
            else "ENVOLVENTE_DETENIDO"
        )
        return self._clasificar_residual(
            residual,
            mapa_umbral,
            pixels,
            estado,
            modo_env,
            indice,
        )

    def _detectar_con_referencia_estatica(
        self,
        actual: np.ndarray,
        referencia: np.ndarray,
        mascara_zona: np.ndarray,
        estado: str,
        modo: str,
    ) -> ResultadoModeloPortonD:
        pixels = mascara_zona > 0
        dx, dy = self._estimar_microdesplazamiento(actual, referencia, pixels)
        referencia_alineada = self._desplazar_referencia(referencia, dx, dy)
        actual_ajustado = self._ajustar_actual_a_referencia(actual, referencia_alineada, pixels)
        residual = np.abs(referencia_alineada.astype(np.int16) - actual_ajustado)
        residual = np.clip(residual, 0, 255).astype(np.uint8)
        umbral_base = float(self.cfg.get("umbral_residual", 30.0))
        mapa_umbral = np.full_like(residual, umbral_base, dtype=np.float32)
        return self._clasificar_residual(
            residual,
            mapa_umbral,
            pixels,
            estado,
            modo,
            -1,
        )

    def _clasificar_residual(
        self,
        residual: np.ndarray,
        mapa_umbral: np.ndarray,
        pixels: np.ndarray,
        estado: str,
        modo: str,
        indice_template: int,
    ) -> ResultadoModeloPortonD:
        binaria = np.zeros_like(residual, dtype=np.uint8)
        binaria[(residual.astype(np.float32) > mapa_umbral) & pixels] = 255

        # La dilatación final de la versión anterior convertía franjas estrechas
        # de los rieles en contornos mayores al área mínima. Ahora las operaciones
        # son configurables y, por defecto, no se dilata.
        kernel_n = max(3, int(self.cfg.get("morfologia_kernel_movimiento", 3)) | 1)
        kernel = np.ones((kernel_n, kernel_n), dtype=np.uint8)
        open_iter = max(0, int(self.cfg.get("morfologia_open_iter", 1)))
        close_iter = max(0, int(self.cfg.get("morfologia_close_iter", 1)))
        dilate_iter = max(0, int(self.cfg.get("morfologia_dilate_iter", 0)))
        if open_iter:
            binaria = cv2.morphologyEx(binaria, cv2.MORPH_OPEN, kernel, iterations=open_iter)
        if close_iter:
            binaria = cv2.morphologyEx(binaria, cv2.MORPH_CLOSE, kernel, iterations=close_iter)
        if dilate_iter:
            binaria = cv2.dilate(binaria, kernel, iterations=dilate_iter)

        contornos, _ = cv2.findContours(binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area_min = float(self.cfg.get("area_min", 600.0))

        # El canto móvil del portón aparece en los videos como una línea larga,
        # diagonal y muy poco rellena. Durante ABRIENDO/CERRANDO se elimina solo
        # esa firma geométrica antes de evaluar obstáculos. Un objeto compacto
        # permanece intacto y continúa bloqueando inmediatamente.
        contornos_analisis = list(contornos)
        firma_porton_filtrada = False
        if estado in {"ABRIENDO", "CERRANDO"}:
            firmas_lineales = [
                c for c in contornos_analisis
                if float(cv2.contourArea(c)) >= area_min
                and self._es_firma_lineal_porton(c, area_min)
            ]
            if firmas_lineales:
                firma_porton_filtrada = True
                cv2.drawContours(binaria, firmas_lineales, -1, 0, thickness=-1)
                contornos_analisis = [
                    c for c in contornos_analisis
                    if not any(c is firma for firma in firmas_lineales)
                ]
                # Recalcular después de borrar las firmas, porque una línea podía
                # unir dos regiones que en realidad son independientes.
                contornos_analisis, _ = cv2.findContours(
                    binaria, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )

        validos = [
            c for c in contornos_analisis
            if float(cv2.contourArea(c)) >= area_min
        ]
        validos.sort(key=cv2.contourArea, reverse=True)

        if not validos:
            # Caso especial y controlado: con el portón CERRADO, un objeto que
            # apenas entra por el extremo izquierdo puede quedar por debajo del
            # área general. Se usa umbral menor más persistencia solo ahí.
            if estado == "CERRADO":
                borde_estatico = self._evaluar_borde_estatico_cerrado(
                    contornos_analisis,
                    binaria,
                    pixels,
                    area_min,
                    modo,
                    indice_template,
                )
                if borde_estatico is not None:
                    self._reiniciar_borde_apertura()
                    self._reiniciar_borde_cierre()
                    return borde_estatico
            else:
                self._reiniciar_borde_estatico()

            self._reiniciar_borde_apertura()
            self._reiniciar_borde_cierre()
            return ResultadoModeloPortonD(
                disponible=True,
                listo=True,
                obstaculo=False,
                confianza=0.0,
                mascara=binaria,
                estado_porton=estado,
                modo=(
                    f"FIRMA_PORTON_FILTRADA_{estado}"
                    if firma_porton_filtrada else modo
                ),
                indice_template=indice_template,
                error_ajuste=0.0,
                area_residual=0.0,
            )

        self._reiniciar_borde_estatico()

        # Durante la apertura, los vídeos reales mostraron residuos breves y
        # estrechos pegados a los bordes laterales. No se ignoran: reciben una
        # pequeña ventana temporal. Un residuo central, grande o cualquier
        # residuo durante el cierre continúa bloqueando inmediatamente.
        if estado == "ABRIENDO":
            candidato = validos[0]
            area_candidato = float(cv2.contourArea(candidato))
            x, y, w, h = cv2.boundingRect(candidato)

            mascara_zona_u8 = np.zeros_like(binaria, dtype=np.uint8)
            mascara_zona_u8[pixels] = 255
            banda_px = max(3, int(self.cfg.get("apertura_borde_banda_px", 24)))
            kernel_banda = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (2 * banda_px + 1, 2 * banda_px + 1),
            )
            interior = cv2.erode(mascara_zona_u8, kernel_banda, iterations=1)
            banda_borde = (mascara_zona_u8 > 0) & (interior == 0)

            mascara_contorno = np.zeros_like(binaria, dtype=np.uint8)
            cv2.drawContours(mascara_contorno, [candidato], -1, 255, thickness=-1)
            pix_contorno = mascara_contorno > 0
            total_contorno = max(1, int(np.count_nonzero(pix_contorno)))
            solape_borde = float(np.count_nonzero(pix_contorno & banda_borde)) / total_contorno

            area_max = float(
                self.cfg.get("apertura_borde_area_max", max(1800.0, 3.0 * area_min))
            )
            solape_min = float(self.cfg.get("apertura_borde_solape_min", 0.30))

            # Si existe además otro contorno válido fuera de esta categoría, se
            # considera obstáculo real sin demora.
            hay_otro_relevante = False
            for otro in validos[1:]:
                area_otro = float(cv2.contourArea(otro))
                if area_otro >= area_min:
                    hay_otro_relevante = True
                    break

            es_borde_pequeno = (
                area_candidato <= area_max
                and solape_borde >= solape_min
                and not hay_otro_relevante
            )

            if es_borde_pequeno:
                ys, xs = np.nonzero(pixels)
                centro_zona_x = float(np.median(xs)) if len(xs) else binaria.shape[1] / 2.0
                centro_candidato_x = x + w / 2.0
                lado = "IZQUIERDO" if centro_candidato_x < centro_zona_x else "DERECHO"
                ahora = time.monotonic()

                bbox_actual = (x, y, w, h)
                mismo = (
                    self._borde_apertura_lado == lado
                    and self._mismo_candidato_borde(self._borde_apertura_bbox, bbox_actual)
                )
                if self._borde_apertura_inicio is None or not mismo:
                    self._borde_apertura_inicio = ahora
                    self._borde_apertura_lado = lado
                    self._borde_apertura_bbox = bbox_actual

                persistencia = ahora - self._borde_apertura_inicio
                espera_s = max(0.1, float(self.cfg.get("apertura_borde_confirmacion_s", 1.10)))
                if persistencia < espera_s:
                    return ResultadoModeloPortonD(
                        disponible=True,
                        listo=True,
                        obstaculo=False,
                        confianza=0.0,
                        bbox=None,
                        mascara=binaria,
                        estado_porton=estado,
                        modo=f"BORDE_TRANSITORIO_{lado}",
                        indice_template=indice_template,
                        error_ajuste=0.0,
                        area_residual=area_candidato,
                    )

                # Si el cambio del borde persiste, deja de considerarse transitorio.
                modo = f"OBSTACULO_BORDE_PERSISTENTE_{lado}"
            else:
                self._reiniciar_borde_apertura()
        else:
            self._reiniciar_borde_apertura()

        # Durante el cierre se conserva la respuesta inmediata para cualquier
        # residuo central, grande o que penetre claramente dentro de D. Solo una
        # franja pequeña, delgada y pegada al límite lateral recibe una breve
        # confirmación temporal. Esto corrige los falsos positivos repetitivos
        # observados en el riel derecho sin desensibilizar el centro de la zona.
        if estado == "CERRANDO":
            candidato = validos[0]
            area_candidato = float(cv2.contourArea(candidato))
            x, y, w, h = cv2.boundingRect(candidato)

            mascara_zona_u8 = np.zeros_like(binaria, dtype=np.uint8)
            mascara_zona_u8[pixels] = 255
            banda_px = max(3, int(self.cfg.get("cierre_borde_banda_px", 22)))
            kernel_banda = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (2 * banda_px + 1, 2 * banda_px + 1),
            )
            interior = cv2.erode(mascara_zona_u8, kernel_banda, iterations=1)
            banda_borde = (mascara_zona_u8 > 0) & (interior == 0)

            mascara_contorno = np.zeros_like(binaria, dtype=np.uint8)
            cv2.drawContours(mascara_contorno, [candidato], -1, 255, thickness=-1)
            pix_contorno = mascara_contorno > 0
            total_contorno = max(1, int(np.count_nonzero(pix_contorno)))
            solape_borde = float(np.count_nonzero(pix_contorno & banda_borde)) / total_contorno
            solape_interior = float(np.count_nonzero(pix_contorno & (interior > 0))) / total_contorno

            # Profundidad máxima del residuo dentro de D. Una franja del riel se
            # mantiene muy cerca del límite; un objeto real suele penetrar más.
            distancia_borde = cv2.distanceTransform(mascara_zona_u8, cv2.DIST_L2, 5)
            penetracion_px = (
                float(np.max(distancia_borde[pix_contorno]))
                if np.any(pix_contorno)
                else 0.0
            )

            area_max = float(
                self.cfg.get("cierre_borde_area_max", max(1500.0, 2.5 * area_min))
            )
            solape_min = float(self.cfg.get("cierre_borde_solape_min", 0.55))
            interior_max = float(self.cfg.get("cierre_borde_interior_max", 0.12))
            penetracion_max = float(self.cfg.get("cierre_borde_penetracion_max_px", 24.0))
            ancho_max = float(self.cfg.get("cierre_borde_ancho_max_px", 52.0))

            hay_otro_relevante = any(
                float(cv2.contourArea(otro)) >= area_min for otro in validos[1:]
            )
            es_borde_pequeno = (
                area_candidato <= area_max
                and solape_borde >= solape_min
                and solape_interior <= interior_max
                and penetracion_px <= penetracion_max
                and w <= ancho_max
                and not hay_otro_relevante
            )

            if es_borde_pequeno:
                ys, xs = np.nonzero(pixels)
                centro_zona_x = float(np.median(xs)) if len(xs) else binaria.shape[1] / 2.0
                centro_candidato_x = x + w / 2.0
                lado = "IZQUIERDO" if centro_candidato_x < centro_zona_x else "DERECHO"
                ahora = time.monotonic()

                bbox_actual = (x, y, w, h)
                mismo = (
                    self._borde_cierre_lado == lado
                    and self._mismo_candidato_borde(self._borde_cierre_bbox, bbox_actual)
                )
                if self._borde_cierre_inicio is None or not mismo:
                    self._borde_cierre_inicio = ahora
                    self._borde_cierre_lado = lado
                    self._borde_cierre_bbox = bbox_actual

                persistencia = ahora - self._borde_cierre_inicio
                espera_s = max(0.1, float(self.cfg.get("cierre_borde_confirmacion_s", 0.75)))
                if persistencia < espera_s:
                    return ResultadoModeloPortonD(
                        disponible=True,
                        listo=True,
                        obstaculo=False,
                        confianza=0.0,
                        bbox=None,
                        mascara=binaria,
                        estado_porton=estado,
                        modo=f"BORDE_TRANSITORIO_CIERRE_{lado}",
                        indice_template=indice_template,
                        error_ajuste=0.0,
                        area_residual=area_candidato,
                    )

                modo = f"OBSTACULO_BORDE_CIERRE_PERSISTENTE_{lado}"
            else:
                self._reiniciar_borde_cierre()
        else:
            self._reiniciar_borde_cierre()

        contorno = validos[0]
        area = float(cv2.contourArea(contorno))
        x, y, w, h = cv2.boundingRect(contorno)
        confianza = min(1.0, area / max(1.0, 3.0 * area_min))
        return ResultadoModeloPortonD(
            disponible=True,
            listo=True,
            obstaculo=True,
            confianza=confianza,
            bbox=(x, y, w, h),
            mascara=binaria,
            estado_porton=estado,
            modo=modo,
            indice_template=indice_template,
            error_ajuste=0.0,
            area_residual=area,
        )
