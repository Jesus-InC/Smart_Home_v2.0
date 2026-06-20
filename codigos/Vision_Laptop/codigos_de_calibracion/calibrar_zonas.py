from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2


puntos: List[Tuple[int, int]] = []


def clic(event, x, y, flags, param) -> None:
    if event == cv2.EVENT_LBUTTONDOWN:
        puntos.append((x, y))
    elif event == cv2.EVENT_RBUTTONDOWN and puntos:
        puntos.pop()


def backend_cv(nombre: str) -> int:
    nombre = nombre.strip().upper()
    if nombre == "DSHOW" and hasattr(cv2, "CAP_DSHOW"):
        return cv2.CAP_DSHOW
    if nombre == "MSMF" and hasattr(cv2, "CAP_MSMF"):
        return cv2.CAP_MSMF
    if nombre == "V4L2" and hasattr(cv2, "CAP_V4L2"):
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def capturar_frame(cam_cfg: Dict[str, Any]):
    indice = int(cam_cfg["indice"])
    backend = str(cam_cfg.get("backend", "AUTO"))
    cap = cv2.VideoCapture(indice, backend_cv(backend))

    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"No se pudo abrir la cámara {indice}")

    fourcc = str(cam_cfg.get("fourcc", "")).strip()
    if len(fourcc) == 4:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(cam_cfg.get("ancho", 640)))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(cam_cfg.get("alto", 480)))
    cap.set(cv2.CAP_PROP_FPS, int(cam_cfg.get("fps", 15)))

    calentamiento_s = float(cam_cfg.get("calentamiento_s", 4.0))
    print(
        f"Calentando cámara {indice} durante "
        f"{calentamiento_s:.1f} s..."
    )

    frame = None
    inicio = time.monotonic()
    while time.monotonic() - inicio < calentamiento_s:
        ok, actual = cap.read()
        if ok and actual is not None and actual.size > 0:
            frame = actual.copy()
        time.sleep(0.03)

    ancho_real = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto_real = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    if frame is None:
        raise RuntimeError("La cámara no entregó imagen")

    print(f"Resolución real para calibración: {ancho_real}x{alto_real}")
    return frame


def seleccionar(nombre: str, frame) -> List[List[float]]:
    global puntos
    puntos = []
    ventana = f"Zona {nombre}"
    cv2.namedWindow(ventana, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(ventana, clic)
    alto, ancho = frame.shape[:2]

    print(
        f"\nZona {nombre}: clic izquierdo agrega, "
        "clic derecho deshace, ENTER confirma, ESC cancela."
    )

    while True:
        vista = frame.copy()
        for punto in puntos:
            cv2.circle(vista, punto, 5, (0, 255, 0), -1)
        if len(puntos) >= 2:
            for p1, p2 in zip(puntos[:-1], puntos[1:]):
                cv2.line(vista, p1, p2, (0, 255, 0), 2)
        if len(puntos) >= 3:
            cv2.line(vista, puntos[-1], puntos[0], (0, 255, 0), 2)

        cv2.putText(
            vista,
            f"Zona {nombre} - puntos: {len(puntos)}",
            (10, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
        )
        cv2.imshow(ventana, vista)
        tecla = cv2.waitKey(20) & 0xFF

        if tecla in (13, 10) and len(puntos) >= 3:
            break
        if tecla == 27:
            cv2.destroyWindow(ventana)
            raise KeyboardInterrupt

    cv2.destroyWindow(ventana)
    return [
        [round(x / ancho, 5), round(y / alto, 5)]
        for x, y in puntos
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dibuja las zonas A/B/C o D sobre una captura"
    )
    parser.add_argument("--config", default="config_laptop.json")
    parser.add_argument(
        "--tipo",
        choices=["abc", "d", "ignorar_d"],
        required=True,
    )
    args = parser.parse_args()

    ruta = Path(args.config).resolve()
    cfg = json.loads(ruta.read_text(encoding="utf-8"))

    clave_camara = "abc" if args.tipo == "abc" else "d"
    cam_cfg = cfg["camaras"][clave_camara]
    frame = capturar_frame(cam_cfg)

    try:
        if args.tipo == "abc":
            for nombre in ("A", "B", "C"):
                cfg["zonas_abc"][nombre] = seleccionar(nombre, frame)
        elif args.tipo == "d":
            cfg["zona_d"] = seleccionar("D", frame)
        else:
            cfg.setdefault("zonas_ignorar_d", []).append(
                seleccionar("IGNORAR_D", frame)
            )
    except KeyboardInterrupt:
        print("Calibración cancelada; no se modificó el archivo.")
        cv2.destroyAllWindows()
        return

    respaldo = ruta.with_suffix(".json.bak")
    respaldo.write_text(
        ruta.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ruta.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    cv2.destroyAllWindows()
    print(f"Zonas guardadas en {ruta}")
    print(f"Respaldo anterior: {respaldo}")


if __name__ == "__main__":
    main()
