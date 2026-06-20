from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import cv2
import numpy as np

from detector_vision import (
    DetectorReferencia,
    centro_hue_circular,
    crear_mascara,
    distancia_hue,
    extraer_objetos,
    poligono_pix,
)


def backend_cv(nombre: str) -> int:
    nombre = nombre.strip().upper()
    if nombre == "DSHOW" and hasattr(cv2, "CAP_DSHOW"):
        return cv2.CAP_DSHOW
    if nombre == "MSMF" and hasattr(cv2, "CAP_MSMF"):
        return cv2.CAP_MSMF
    if nombre == "V4L2" and hasattr(cv2, "CAP_V4L2"):
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def abrir_camara(cam_cfg: Dict[str, Any]) -> cv2.VideoCapture:
    indice = int(cam_cfg["indice"])
    cap = cv2.VideoCapture(indice, backend_cv(str(cam_cfg.get("backend", "AUTO"))))
    if not cap.isOpened():
        cap.release()
        raise RuntimeError("No se pudo abrir la cámara ABC")

    fourcc = str(cam_cfg.get("fourcc", "")).strip()
    if len(fourcc) == 4:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(cam_cfg.get("ancho", 1280)))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(cam_cfg.get("alto", 720)))
    cap.set(cv2.CAP_PROP_FPS, int(cam_cfg.get("fps", 15)))

    calentamiento_s = float(cam_cfg.get("calentamiento_s", 4.0))
    print(f"Calentando cámara ABC durante {calentamiento_s:.1f} s...")
    ultimo = None
    inicio = time.monotonic()
    while time.monotonic() - inicio < calentamiento_s:
        ok, frame = cap.read()
        if ok and frame is not None and frame.size > 0:
            ultimo = frame
        time.sleep(0.03)

    if ultimo is None:
        cap.release()
        raise RuntimeError("La cámara ABC no entregó imagen válida")

    print(
        "Resolución real ABC: "
        f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
        f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}"
    )
    return cap


def esperar_espacio(cap: cv2.VideoCapture, titulo: str, mensaje: str) -> bool:
    print(mensaje)
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        vista = frame.copy()
        cv2.putText(vista, mensaje[:100], (15, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 255, 255), 2)
        cv2.putText(vista, "ESPACIO: continuar | Q: cancelar", (15, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 255, 255), 2)
        cv2.imshow(titulo, vista)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord(" "):
            return True
        if tecla in {ord("q"), 27}:
            return False


def percentil_desviacion(valores: np.ndarray, centro: float, q: float = 90.0) -> float:
    if valores.size == 0:
        return 0.0
    return float(np.percentile(np.abs(valores.astype(np.float64) - centro), q))


def limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def calcular_perfil(muestras: List[Dict[str, float]], zona: str) -> Dict[str, Any]:
    h = np.array([m["h"] for m in muestras], dtype=np.float64)
    s = np.array([m["s"] for m in muestras], dtype=np.float64)
    v = np.array([m["v"] for m in muestras], dtype=np.float64)
    area = np.array([m["area_ratio"] for m in muestras], dtype=np.float64)
    aspecto = np.array([m["aspecto"] for m in muestras], dtype=np.float64)
    extent = np.array([m["extent"] for m in muestras], dtype=np.float64)

    h_centro = centro_hue_circular(h)
    s_centro = float(np.median(s))
    v_centro = float(np.median(v))
    area_centro = float(np.median(area))
    aspecto_centro = float(np.median(aspecto))
    extent_centro = float(np.median(extent))

    desv_h = np.array([distancia_hue(x, h_centro) for x in h], dtype=np.float64)
    h_tol = limitar(float(np.percentile(desv_h, 90)) * 2.0 + 5.0, 10.0, 35.0)
    s_tol = limitar(percentil_desviacion(s, s_centro) * 2.0 + 15.0, 35.0, 110.0)
    v_tol = limitar(percentil_desviacion(v, v_centro) * 2.0 + 15.0, 35.0, 110.0)
    area_tol = limitar(percentil_desviacion(area, area_centro) * 2.2 + 0.008, 0.012, 0.060)
    aspecto_tol = limitar(percentil_desviacion(aspecto, aspecto_centro) * 2.2 + 0.12, 0.25, 1.10)
    extent_tol = limitar(percentil_desviacion(extent, extent_centro) * 2.2 + 0.08, 0.12, 0.45)

    return {
        "zona": zona,
        "hsv_centro": [int(round(h_centro)) % 180, int(round(s_centro)), int(round(v_centro))],
        "hsv_tolerancia": [int(round(h_tol)), int(round(s_tol)), int(round(v_tol))],
        "area_ratio_esperada": round(area_centro, 5),
        "area_ratio_tolerancia": round(area_tol, 5),
        "aspecto_esperado": round(aspecto_centro, 4),
        "aspecto_tolerancia": round(aspecto_tol, 4),
        "extent_esperado": round(extent_centro, 4),
        "extent_tolerancia": round(extent_tol, 4),
        "metodo": "multimuestreo_por_zona_detector_referencia",
        "muestras_usadas": len(muestras),
    }


def instruccion_pose(zona: str, pose: int) -> str:
    instrucciones = {
        "A": [
            "centro de A, orientación normal de ingreso",
            "otra posición dentro de A, un poco más cerca o lejos",
            "otra orientación leve dentro de A, sin salir del polígono",
        ],
        "B": [
            "centro de B, apuntando aproximadamente hacia A",
            "otra posición dentro de B, un poco más cerca o lejos",
            "otra orientación leve dentro de B, sin salir del polígono",
        ],
        "C": [
            "centro de C, completamente visible",
            "otra posición dentro de C, un poco más cerca o lejos",
            "otra orientación leve dentro de C, sin salir del polígono",
        ],
    }
    lista = instrucciones.get(zona, instrucciones["A"])
    return lista[min(pose, len(lista) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Calibra perfiles del auto dueño por zona. Por defecto genera "
            "perfiles independientes para A y B."
        )
    )
    parser.add_argument("--config", default="config_laptop.json")
    parser.add_argument("--zonas", nargs="+", default=["A", "B"], choices=["A", "B", "C"])
    parser.add_argument("--poses", type=int, default=3, help="Poses por cada zona")
    parser.add_argument("--muestras-por-pose", type=int, default=20)
    parser.add_argument("--timeout-pose", type=float, default=30.0)
    args = parser.parse_args()

    zonas_calibrar: List[str] = []
    for zona in args.zonas:
        zona = zona.upper()
        if zona not in zonas_calibrar:
            zonas_calibrar.append(zona)

    ruta = Path(args.config).resolve()
    cfg = json.loads(ruta.read_text(encoding="utf-8"))
    zonas_cfg = cfg["zonas_abc"]
    faltantes = [z for z in zonas_calibrar if z not in zonas_cfg]
    if faltantes:
        raise SystemExit(f"Faltan zonas en config_laptop.json: {faltantes}")

    cap = abrir_camara(cfg["camaras"]["abc"])
    det_cfg = cfg["deteccion_referencia"]
    detector = DetectorReferencia(
        det_cfg["frames_calibracion"],
        det_cfg["umbral_diferencia_abc"],
        det_cfg["area_min_abc"],
        det_cfg["morfologia_kernel"],
        det_cfg["max_objetos"],
    )

    color_cfg = cfg.get("extraccion_color", {})
    poses = max(1, int(args.poses))
    muestras_por_pose = max(8, int(args.muestras_por_pose))
    perfiles: Dict[str, Dict[str, Any]] = {}

    try:
        if not esperar_espacio(
            cap,
            "Calibración dueño por zona",
            "Retira TODOS los autos de A/B/C. Presiona ESPACIO para crear el fondo.",
        ):
            return

        print("Construyendo referencia con la maqueta vacía...")
        while not detector.listo:
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            detector.alimentar_referencia(frame)
            vista = frame.copy()
            cv2.putText(vista, f"Fondo vacío: {detector.progreso:.0%}", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            cv2.imshow("Calibración dueño por zona", vista)
            if (cv2.waitKey(1) & 0xFF) in {ord("q"), 27}:
                return

        for zona_actual in zonas_calibrar:
            muestras_zona: List[Dict[str, float]] = []
            print(f"\n=== CALIBRANDO PERFIL DEL DUEÑO EN ZONA {zona_actual} ===")

            for pose in range(poses):
                texto = instruccion_pose(zona_actual, pose)
                if not esperar_espacio(
                    cap,
                    "Calibración dueño por zona",
                    f"Zona {zona_actual}, pose {pose + 1}/{poses}: coloca SOLO el auto dueño en {texto}.",
                ):
                    return

                recogidas = 0
                ultimo_muestreo = 0.0
                limite = time.monotonic() + max(10.0, float(args.timeout_pose))

                while recogidas < muestras_por_pose and time.monotonic() < limite:
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        continue

                    mascara_zona = crear_mascara(frame, [zonas_cfg[zona_actual]])
                    contornos, mascara = detector.detectar(frame, mascara_zona)
                    objetos = extraer_objetos(frame, contornos, zonas_cfg, color_cfg)
                    candidatos = [obj for obj in objetos if obj.zona == zona_actual]
                    principal = max(candidatos, key=lambda obj: obj.area_contorno) if candidatos else None

                    vista = frame.copy()
                    alto, ancho = vista.shape[:2]
                    for nombre, poly in zonas_cfg.items():
                        color = (0, 255, 0) if nombre == zona_actual else (255, 255, 255)
                        grosor = 3 if nombre == zona_actual else 1
                        pts = poligono_pix(poly, ancho, alto)
                        cv2.polylines(vista, [pts], True, color, grosor)
                        px, py = pts[0]
                        cv2.putText(vista, nombre, (px + 4, py + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

                    if principal is not None:
                        x, y, w, h = principal.bbox
                        cv2.rectangle(vista, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        ahora = time.monotonic()
                        if ahora - ultimo_muestreo >= 0.08 and principal.pixeles_color >= 20:
                            hh, ss, vv = principal.hsv_mediana
                            muestras_zona.append(
                                {
                                    "h": float(hh),
                                    "s": float(ss),
                                    "v": float(vv),
                                    "area_ratio": float(principal.area_ratio),
                                    "aspecto": float(principal.aspecto),
                                    "extent": float(principal.extent),
                                }
                            )
                            recogidas += 1
                            ultimo_muestreo = ahora

                        cv2.putText(
                            vista,
                            f"HSV={principal.hsv_mediana} Ar={principal.area_ratio:.4f} Asp={principal.aspecto:.2f} Ext={principal.extent:.2f}",
                            (15, 78),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.62,
                            (0, 255, 255),
                            2,
                        )
                    else:
                        cv2.putText(
                            vista,
                            f"No se detecta el auto completo dentro de {zona_actual}",
                            (15, 78),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.70,
                            (0, 0, 255),
                            2,
                        )

                    cv2.putText(
                        vista,
                        f"Zona {zona_actual} | Pose {pose + 1}/{poses}: {recogidas}/{muestras_por_pose} muestras",
                        (15, 38),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.78,
                        (0, 255, 255),
                        2,
                    )
                    cv2.imshow("Calibración dueño por zona", vista)
                    cv2.imshow("Máscara calibración", mascara)
                    if (cv2.waitKey(1) & 0xFF) in {ord("q"), 27}:
                        return

                if recogidas < muestras_por_pose:
                    raise RuntimeError(
                        f"Solo se obtuvieron {recogidas}/{muestras_por_pose} muestras "
                        f"en zona {zona_actual}, pose {pose + 1}. Comprueba que el auto "
                        f"esté completo dentro de {zona_actual} y que la máscara lo detecte."
                    )

            perfiles[zona_actual] = calcular_perfil(muestras_zona, zona_actual)
            print(f"Perfil de zona {zona_actual} listo con {len(muestras_zona)} muestras.")

        cfg["perfiles_dueno"] = perfiles
        if "A" in perfiles:
            cfg["perfil_dueno"] = perfiles["A"]
        cfg["perfiles_dueno_version"] = 1

        sello = datetime.now().strftime("%Y%m%d_%H%M%S")
        respaldo = ruta.with_name(f"{ruta.stem}_antes_perfiles_zona_{sello}{ruta.suffix}")
        respaldo.write_text(ruta.read_text(encoding="utf-8"), encoding="utf-8")
        ruta.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        print("\nPerfiles por zona guardados correctamente:")
        print(json.dumps(perfiles, indent=2, ensure_ascii=False))
        print(f"Respaldo anterior: {respaldo.name}")
        print("\nIMPORTANTE: el dueño debe alcanzar >=70 tanto en A como en B.")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
