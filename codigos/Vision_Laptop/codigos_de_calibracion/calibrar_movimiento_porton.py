from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np

from detector_vision import CamaraWorker
from modelo_porton_d import ModeloMovimientoPortonD


def cargar_config(ruta: Path) -> Dict[str, Any]:
    with ruta.open("r", encoding="utf-8") as f:
        return json.load(f)


def remuestrear(frames: List[np.ndarray], cantidad: int) -> np.ndarray:
    if len(frames) < 3:
        raise RuntimeError("La secuencia tiene menos de 3 frames válidos")
    cantidad = max(3, min(cantidad, len(frames)))
    indices = np.linspace(0, len(frames) - 1, cantidad).round().astype(int)
    return np.stack([frames[i] for i in indices]).astype(np.uint8)


def intercalar_por_fase(ciclos: List[np.ndarray]) -> np.ndarray:
    """Convierte C x T x H x W en T*C x H x W, intercalado por fase."""
    arr = np.stack(ciclos).astype(np.uint8)
    return arr.transpose(1, 0, 2, 3).reshape(-1, arr.shape[2], arr.shape[3])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibra varios ciclos limpios del portón para la cámara D"
    )
    parser.add_argument("--config", default="config_laptop.json")
    parser.add_argument("--ciclos", type=int, default=None)
    args = parser.parse_args()

    ruta_config = Path(args.config).resolve()
    cfg = cargar_config(ruta_config)
    cfg_d = cfg["camaras"]["d"]
    cfg_modelo = cfg.get("modelo_porton_d", {})

    ciclos_objetivo = max(
        2,
        int(args.ciclos if args.ciclos is not None else cfg_modelo.get("ciclos_calibracion", 3)),
    )
    min_frames = max(10, int(cfg_modelo.get("min_frames_secuencia", 15)))
    templates_por_ciclo = max(15, int(cfg_modelo.get("max_templates", 45)))
    intervalo = max(0.03, float(cfg_modelo.get("intervalo_captura_s", 0.08)))

    cam = CamaraWorker(int(cfg_d["indice"]), cfg_d, "D-CAL-MULTI")
    if not cam.iniciar():
        raise RuntimeError("No se pudo abrir la cámara D")

    print("\n=== CALIBRACIÓN MULTICICLO DEL PORTÓN ===")
    print(f"Se grabarán {ciclos_objetivo} cierres y {ciclos_objetivo} aperturas limpias.")
    print("Retira cualquier auto, mano u objeto de D.")
    print("No muevas la cámara, la mesa ni la iluminación.")
    print("Haz cada recorrido completo entre finales de carrera.")
    print("Controles:")
    print("  c = comenzar el siguiente CIERRE limpio")
    print("  a = comenzar la siguiente APERTURA limpia")
    print("  s = detener y validar la grabación actual")
    print("  r = borrar todas las grabaciones")
    print("  q = salir sin guardar\n")

    cierres: List[np.ndarray] = []
    aperturas: List[np.ndarray] = []
    actual_frames: List[np.ndarray] = []
    modo = "ESPERA"
    ultimo_muestreo = 0.0

    def esperado() -> str:
        if len(cierres) == len(aperturas) and len(cierres) < ciclos_objetivo:
            return "CIERRE"
        if len(cierres) > len(aperturas):
            return "APERTURA"
        return "COMPLETO"

    try:
        while True:
            ok, frame, _ = cam.obtener()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            ahora = time.monotonic()
            if modo in {"CIERRE", "APERTURA"} and ahora - ultimo_muestreo >= intervalo:
                actual_frames.append(ModeloMovimientoPortonD.preparar(frame))
                ultimo_muestreo = ahora

            vista = frame.copy()
            if modo == "ESPERA":
                texto = (
                    f"ESPERA | cierre {len(cierres)}/{ciclos_objetivo} | "
                    f"apertura {len(aperturas)}/{ciclos_objetivo} | sigue: {esperado()}"
                )
                color = (0, 255, 255)
            else:
                numero = len(cierres) + 1 if modo == "CIERRE" else len(aperturas) + 1
                texto = f"GRABANDO {modo} {numero}/{ciclos_objetivo}: {len(actual_frames)} frames"
                color = (0, 0, 255)

            cv2.putText(vista, texto, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.56, color, 2)
            cv2.putText(
                vista,
                "c=cierre a=apertura s=detener r=borrar q=salir",
                (10, max(80, vista.shape[0] - 15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (255, 255, 255),
                1,
            )
            cv2.imshow("Calibracion multiciclo porton D", vista)
            tecla = cv2.waitKey(1) & 0xFF

            if tecla in {ord("q"), 27}:
                print("Calibración cancelada")
                return
            if tecla in {ord("r"), ord("R")}:
                cierres.clear()
                aperturas.clear()
                actual_frames.clear()
                modo = "ESPERA"
                print("[CAL] Todas las grabaciones fueron borradas")
                continue

            if tecla in {ord("c"), ord("C")} and modo == "ESPERA":
                if len(cierres) >= ciclos_objetivo:
                    print("[CAL] Ya se completaron todos los cierres")
                elif esperado() != "CIERRE":
                    print("[CAL] Primero corresponde una APERTURA para volver al origen")
                else:
                    actual_frames = [ModeloMovimientoPortonD.preparar(frame)]
                    modo = "CIERRE"
                    ultimo_muestreo = time.monotonic()
                    print(f"[CAL] Cierre {len(cierres)+1}/{ciclos_objetivo}: acciona CERRAR y pulsa s al final")

            elif tecla in {ord("a"), ord("A")} and modo == "ESPERA":
                if len(aperturas) >= ciclos_objetivo:
                    print("[CAL] Ya se completaron todas las aperturas")
                elif esperado() != "APERTURA":
                    print("[CAL] Primero corresponde un CIERRE")
                else:
                    actual_frames = [ModeloMovimientoPortonD.preparar(frame)]
                    modo = "APERTURA"
                    ultimo_muestreo = time.monotonic()
                    print(f"[CAL] Apertura {len(aperturas)+1}/{ciclos_objetivo}: acciona ABRIR y pulsa s al final")

            elif tecla in {ord("s"), ord("S")} and modo != "ESPERA":
                actual_frames.append(ModeloMovimientoPortonD.preparar(frame))
                if len(actual_frames) < min_frames:
                    print(
                        f"[CAL] Secuencia descartada: {len(actual_frames)} frames; "
                        f"se requieren al menos {min_frames}"
                    )
                else:
                    secuencia = np.stack(actual_frames).astype(np.uint8)
                    if modo == "CIERRE":
                        cierres.append(secuencia)
                        print(f"[CAL] Cierre {len(cierres)}/{ciclos_objetivo} aceptado")
                    else:
                        aperturas.append(secuencia)
                        print(f"[CAL] Apertura {len(aperturas)}/{ciclos_objetivo} aceptada")
                actual_frames = []
                modo = "ESPERA"

            if (
                modo == "ESPERA"
                and len(cierres) >= ciclos_objetivo
                and len(aperturas) >= ciclos_objetivo
            ):
                secuencias_usadas = cierres[:ciclos_objetivo] + aperturas[:ciclos_objetivo]
                templates_reales = max(
                    15,
                    min(templates_por_ciclo, min(len(sec) for sec in secuencias_usadas)),
                )
                cierres_r = [remuestrear(list(sec), templates_reales) for sec in cierres[:ciclos_objetivo]]
                aperturas_r = [remuestrear(list(sec), templates_reales) for sec in aperturas[:ciclos_objetivo]]
                cierre_out = intercalar_por_fase(cierres_r)
                apertura_out = intercalar_por_fase(aperturas_r)

                ruta = Path(str(cfg_modelo.get("archivo", "modelos/modelo_porton_d.npz")))
                if not ruta.is_absolute():
                    ruta = ruta_config.parent / ruta
                ruta.parent.mkdir(parents=True, exist_ok=True)

                respaldo = ruta.with_name(ruta.stem + "_antes_multiciclo" + ruta.suffix)
                if ruta.exists():
                    respaldo.write_bytes(ruta.read_bytes())
                    print(f"[CAL] Respaldo anterior: {respaldo}")

                np.savez_compressed(
                    ruta,
                    version=np.array([2], dtype=np.int16),
                    ciclos=np.array([ciclos_objetivo], dtype=np.int16),
                    templates_cierre_por_ciclo=np.array([templates_reales], dtype=np.int16),
                    templates_apertura_por_ciclo=np.array([templates_reales], dtype=np.int16),
                    cierre=cierre_out,
                    apertura=apertura_out,
                    ancho=np.array([frame.shape[1]], dtype=np.int32),
                    alto=np.array([frame.shape[0]], dtype=np.int32),
                    creado_unix=np.array([time.time()], dtype=np.float64),
                )
                print(
                    f"\nModelo multicíclo guardado en: {ruta}\n"
                    f"Ciclos limpios: {ciclos_objetivo}\n"
                    f"Fases por ciclo: {templates_reales}\n"
                    f"Plantillas cierre totales: {len(cierre_out)}\n"
                    f"Plantillas apertura totales: {len(apertura_out)}\n"
                )
                return
    finally:
        cam.detener()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
