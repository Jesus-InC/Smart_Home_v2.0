from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2


def backend_cv(nombre: str) -> int:
    nombre = nombre.strip().upper()
    if nombre == "DSHOW" and hasattr(cv2, "CAP_DSHOW"):
        return cv2.CAP_DSHOW
    if nombre == "MSMF" and hasattr(cv2, "CAP_MSMF"):
        return cv2.CAP_MSMF
    if nombre == "V4L2" and hasattr(cv2, "CAP_V4L2"):
        return cv2.CAP_V4L2
    return cv2.CAP_ANY


def probar(
    indice: int,
    out_dir: Path,
    backend: str,
    mostrar: bool,
    calentamiento_s: float,
    ancho: int,
    alto: int,
    fps: int,
    fourcc: str,
) -> bool:
    print(
        f"Probando cámara {indice} con backend {backend}, "
        f"solicitud {ancho}x{alto}. Esperando "
        f"{calentamiento_s:.1f} s..."
    )

    cap = cv2.VideoCapture(indice, backend_cv(backend))
    if not cap.isOpened():
        print(f"Cámara {indice}: NO abre")
        cap.release()
        return False

    fourcc = fourcc.strip()
    if len(fourcc) == 4:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, ancho)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, alto)
    cap.set(cv2.CAP_PROP_FPS, fps)

    ultimo_frame = None
    inicio = time.monotonic()
    while time.monotonic() - inicio < calentamiento_s:
        ok, frame = cap.read()
        if ok and frame is not None and frame.size > 0:
            ultimo_frame = frame.copy()
        time.sleep(0.03)

    if ultimo_frame is None:
        print(f"Cámara {indice}: abre, pero NO entrega imagen")
        cap.release()
        return False

    ancho_real = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    alto_real = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps_real = cap.get(cv2.CAP_PROP_FPS)

    out_dir.mkdir(parents=True, exist_ok=True)
    archivo = out_dir / (
        f"camara_{indice}_{backend.upper()}_"
        f"{ancho_real}x{alto_real}.jpg"
    )
    cv2.imwrite(str(archivo), ultimo_frame)

    print(
        f"Cámara {indice}: OK -> {archivo} "
        f"({ancho_real}x{alto_real} @ {fps_real:.1f} FPS)"
    )

    if mostrar:
        titulo = (
            f"Cámara {indice} - {backend.upper()} - "
            f"{ancho_real}x{alto_real}"
        )
        cv2.imshow(titulo, ultimo_frame)
        cv2.waitKey(1800)
        cv2.destroyWindow(titulo)

    cap.release()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identifica los índices y resoluciones de las cámaras"
    )
    parser.add_argument("--desde", type=int, default=0)
    parser.add_argument("--hasta", type=int, default=5)
    parser.add_argument("--backend", default="MSMF")
    parser.add_argument("--salida", default="capturas_prueba")
    parser.add_argument("--mostrar", action="store_true")
    parser.add_argument("--calentamiento", type=float, default=4.0)
    parser.add_argument("--ancho", type=int, default=640)
    parser.add_argument("--alto", type=int, default=480)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--fourcc", default="")
    args = parser.parse_args()

    print(
        "\nCierra primero la aplicación Cámara, Teams, Zoom "
        "y cualquier programa que utilice las webcams.\n"
    )

    for indice in range(args.desde, args.hasta + 1):
        probar(
            indice=indice,
            out_dir=Path(args.salida),
            backend=args.backend,
            mostrar=args.mostrar,
            calentamiento_s=args.calentamiento,
            ancho=args.ancho,
            alto=args.alto,
            fps=args.fps,
            fourcc=args.fourcc,
        )


if __name__ == "__main__":
    main()
