from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from detector_vision import (
    CamaraWorker,
    DetectorReferencia,
    crear_mascara,
    extraer_objetos,
    poligono_pix,
)

BBox = Tuple[int, int, int, int]


def cargar_config(ruta: Path) -> Dict:
    with ruta.open('r', encoding='utf-8') as f:
        return json.load(f)


def recortar_con_margen(frame: np.ndarray, bbox: BBox, margen: float = 0.15) -> np.ndarray:
    x, y, w, h = bbox
    alto, ancho = frame.shape[:2]
    mx = int(round(w * margen))
    my = int(round(h * margen))
    x1 = max(0, x - mx)
    y1 = max(0, y - my)
    x2 = min(ancho, x + w + mx)
    y2 = min(alto, y + h + my)
    return frame[y1:y2, x1:x2].copy()


def diferencia_normalizada(a: Optional[np.ndarray], b: np.ndarray) -> float:
    if a is None or a.size == 0 or b.size == 0:
        return 999.0
    aa = cv2.resize(a, (96, 96))
    bb = cv2.resize(b, (96, 96))
    aa = cv2.cvtColor(aa, cv2.COLOR_BGR2GRAY)
    bb = cv2.cvtColor(bb, cv2.COLOR_BGR2GRAY)
    return float(np.mean(cv2.absdiff(aa, bb)))


def bbox_estable(anterior: Optional[BBox], actual: BBox) -> bool:
    if anterior is None:
        return False
    x0, y0, w0, h0 = anterior
    x1, y1, w1, h1 = actual
    c0 = (x0 + w0 / 2.0, y0 + h0 / 2.0)
    c1 = (x1 + w1 / 2.0, y1 + h1 / 2.0)
    desplazamiento = ((c0[0] - c1[0]) ** 2 + (c0[1] - c1[1]) ** 2) ** 0.5
    escala = max(1.0, (w0 + h0 + w1 + h1) / 4.0)
    cambio_area = abs((w1 * h1) - (w0 * h0)) / max(1.0, w0 * h0)
    return desplazamiento / escala < 0.035 and cambio_area < 0.08


def guardar_csv(csv_path: Path, fila: Dict[str, object]) -> None:
    existe = csv_path.exists()
    with csv_path.open('a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(fila.keys()))
        if not existe:
            writer.writeheader()
        writer.writerow(fila)


def main() -> None:
    parser = argparse.ArgumentParser(description='Captura recortes para clasificación YOLO')
    parser.add_argument('--config', default='config_laptop.json')
    parser.add_argument('--salida', default='dataset_yolo/raw')
    parser.add_argument('--intervalo', type=float, default=0.45)
    parser.add_argument('--diferencia-min', type=float, default=5.0)
    args = parser.parse_args()

    ruta_config = Path(args.config).resolve()
    base = ruta_config.parent
    cfg = cargar_config(ruta_config)
    salida = (base / args.salida).resolve()
    clases = ('auto_dueno', 'otro_auto')
    for clase in clases:
        (salida / clase).mkdir(parents=True, exist_ok=True)
    csv_path = salida / 'capturas.csv'

    cam_cfg = cfg['camaras']['abc']
    cam = CamaraWorker(int(cam_cfg['indice']), cam_cfg, 'ABC-DATASET')
    det_cfg = cfg['deteccion_referencia']
    detector = DetectorReferencia(
        det_cfg['frames_calibracion'],
        det_cfg['umbral_diferencia_abc'],
        det_cfg['area_min_abc'],
        det_cfg['morfologia_kernel'],
        det_cfg['max_objetos'],
    )

    clase_actual = 'auto_dueno'
    continuo = False
    ultimo_guardado = 0.0
    ultimos_recortes: Dict[str, Optional[np.ndarray]] = {c: None for c in clases}
    bbox_anterior: Optional[BBox] = None
    frames_estables = 0
    contador = {
        clase: len(list((salida / clase).glob('*.jpg')))
        for clase in clases
    }

    print('\n=== CAPTURA DATASET YOLO CLASIFICACIÓN ===')
    print('Comienza con A/B/C vacías hasta que la referencia llegue a 100%.')
    print('1=auto_dueño | 2=otro_auto | s=guardar una | c=continuo ON/OFF')
    print('r=recalibrar fondo | q=salir')
    print('En modo continuo: mueve el auto, retira la mano y espera un instante.\n')

    if not cam.iniciar():
        raise SystemExit('No se pudo abrir la cámara ABC')

    try:
        while True:
            ok, frame, _ = cam.obtener()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            zonas = cfg['zonas_abc']
            mascara_zonas = crear_mascara(frame, [zonas['A'], zonas['B'], zonas['C']])
            contornos, mascara = detector.detectar(frame, mascara_zonas)
            objetos = extraer_objetos(frame, contornos, zonas, cfg.get('extraccion_color', {}))
            objetos = [o for o in objetos if o.zona != 'NINGUNA']
            principal = max(objetos, key=lambda o: o.area_contorno) if objetos else None

            vista = frame.copy()
            alto, ancho = vista.shape[:2]
            for nombre, poly in zonas.items():
                pts = poligono_pix(poly, ancho, alto)
                cv2.polylines(vista, [pts], True, (255, 255, 255), 2)
                px, py = pts[0]
                cv2.putText(vista, nombre, (px + 4, py + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

            recorte = None
            if principal is not None:
                x, y, w, h = principal.bbox
                cv2.rectangle(vista, (x, y), (x + w, y + h), (0, 255, 0), 2)
                recorte = recortar_con_margen(frame, principal.bbox)
                if bbox_estable(bbox_anterior, principal.bbox):
                    frames_estables += 1
                else:
                    frames_estables = 0
                bbox_anterior = principal.bbox
            else:
                bbox_anterior = None
                frames_estables = 0

            progreso = detector.progreso
            estado = 'LISTA' if detector.listo else f'CALIBRANDO {progreso:.0%}'
            cv2.putText(vista, f'Clase: {clase_actual} | {estado}', (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(vista, f'Continuo: {continuo} | dueno={contador["auto_dueno"]} otros={contador["otro_auto"]}', (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 255, 255), 2)
            cv2.putText(vista, '1 dueno | 2 otro | s guardar | c continuo | r fondo | q salir', (10, alto - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            solicitud_guardar = False
            ahora = time.monotonic()
            if continuo and detector.listo and recorte is not None and frames_estables >= 7:
                if ahora - ultimo_guardado >= max(0.15, args.intervalo):
                    if diferencia_normalizada(ultimos_recortes[clase_actual], recorte) >= args.diferencia_min:
                        solicitud_guardar = True

            cv2.imshow('Captura Dataset ABC', vista)
            cv2.imshow('Mascara Dataset ABC', mascara)
            if recorte is not None:
                cv2.imshow('Recorte YOLO', recorte)

            tecla = cv2.waitKey(1) & 0xFF
            if tecla == ord('q'):
                break
            if tecla == ord('1'):
                clase_actual = 'auto_dueno'
                continuo = False
                print('[DATASET] Clase seleccionada: auto_dueno')
            elif tecla == ord('2'):
                clase_actual = 'otro_auto'
                continuo = False
                print('[DATASET] Clase seleccionada: otro_auto')
            elif tecla in {ord('c'), ord('C')}:
                continuo = not continuo
                print(f'[DATASET] Captura continua: {continuo}')
            elif tecla in {ord('s'), ord('S')}:
                solicitud_guardar = True
            elif tecla in {ord('r'), ord('R')}:
                detector.reiniciar()
                continuo = False
                print('[DATASET] Fondo reiniciado. Deja A/B/C vacías.')

            if solicitud_guardar:
                if not detector.listo:
                    print('[DATASET] Aún se está calibrando el fondo')
                elif recorte is None or principal is None:
                    print('[DATASET] No hay un vehículo válido para guardar')
                elif recorte.shape[0] < 40 or recorte.shape[1] < 40:
                    print('[DATASET] Recorte demasiado pequeño')
                else:
                    contador[clase_actual] += 1
                    nombre = f'{clase_actual}_{contador[clase_actual]:05d}_{int(time.time()*1000)}.jpg'
                    destino = salida / clase_actual / nombre
                    if cv2.imwrite(str(destino), recorte, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                        ultimos_recortes[clase_actual] = recorte.copy()
                        ultimo_guardado = ahora
                        guardar_csv(csv_path, {
                            'archivo': str(destino.relative_to(salida)),
                            'clase': clase_actual,
                            'zona': principal.zona,
                            'x': principal.bbox[0],
                            'y': principal.bbox[1],
                            'w': principal.bbox[2],
                            'h': principal.bbox[3],
                            'timestamp': round(time.time(), 3),
                        })
                        print(f'[DATASET] Guardada {destino.name}')
    finally:
        cam.detener()
        cv2.destroyAllWindows()
        print('\n[DATASET] Conteo final:')
        for clase in clases:
            print(f'  {clase}: {contador[clase]} imágenes')


if __name__ == '__main__':
    main()
