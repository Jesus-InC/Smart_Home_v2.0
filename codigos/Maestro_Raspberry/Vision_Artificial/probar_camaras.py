from __future__ import annotations

import argparse
from pathlib import Path
import time

import cv2


def probar(indice: int, out_dir: Path, mostrar: bool = False) -> bool:
    cap = cv2.VideoCapture(indice)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    time.sleep(0.5)

    if not cap.isOpened():
        print(f"Camara {indice}: NO abre")
        return False

    ok, frame = cap.read()
    if not ok or frame is None:
        print(f"Camara {indice}: abre, pero NO entrega imagen")
        cap.release()
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    archivo = out_dir / f"camara_{indice}.jpg"
    cv2.imwrite(str(archivo), frame)
    print(f"Camara {indice}: OK -> captura guardada en {archivo}")

    if mostrar:
        cv2.imshow(f"Camara {indice}", frame)
        cv2.waitKey(1200)
        cv2.destroyWindow(f"Camara {indice}")

    cap.release()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba indices de camaras OpenCV")
    parser.add_argument("--desde", type=int, default=0)
    parser.add_argument("--hasta", type=int, default=5)
    parser.add_argument("--salida", default="capturas_prueba")
    parser.add_argument("--mostrar", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.salida)
    print("Probando camaras. Usa las imagenes guardadas para saber cual es ABC y cual es D.\n")
    for i in range(args.desde, args.hasta + 1):
        probar(i, out_dir, mostrar=args.mostrar)


if __name__ == "__main__":
    main()
