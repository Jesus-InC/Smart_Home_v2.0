from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description='Activa o desactiva YOLO clasificación sin borrar calibraciones')
    parser.add_argument('--config', default='config_laptop.json')
    parser.add_argument('--modelo', default='modelos/best_cls.pt')
    parser.add_argument('--confianza', type=float, default=0.70)
    parser.add_argument('--desactivar', action='store_true')
    args = parser.parse_args()

    ruta = Path(args.config).resolve()
    if not ruta.exists():
        raise SystemExit(f'No existe {ruta}')
    with ruta.open('r', encoding='utf-8') as f:
        cfg = json.load(f)

    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    respaldo = ruta.with_name(f'{ruta.stem}_antes_yolo_{sello}{ruta.suffix}')
    shutil.copy2(ruta, respaldo)

    yolo = dict(cfg.get('yolo', {}))
    if args.desactivar:
        yolo['usar'] = False
    else:
        modelo = Path(args.modelo)
        if not modelo.is_absolute():
            modelo = ruta.parent / modelo
        if not modelo.exists():
            raise SystemExit(f'No existe el modelo: {modelo}')
        yolo.update({
            'usar': True,
            'tarea': 'clasificacion',
            'modelo': str(Path(args.modelo).as_posix()),
            'clase_dueno': 'auto_dueno',
            'clases_vehiculo': ['auto_dueno', 'otro_auto'],
            'confianza_min': float(args.confianza),
            'imgsz': 224,
            'cada_n_frames': 3,
            'margen_crop': 0.12,
            'validacion_hibrida': True,
            'score_visual_minimo_para_yolo': 50,
            'score_visual_minimo_por_zona': {'A': 50, 'B': 50, 'C': 45},
            'componentes_minimos_por_zona': {
                'A': {'color': 20, 'tamano': 8},
                'B': {'tamano': 9},
                'C': {'tamano': 5},
            },
        })
    cfg['yolo'] = yolo

    with ruta.open('w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'Respaldo: {respaldo.name}')
    print(f'YOLO activo: {cfg["yolo"].get("usar", False)}')
    if cfg['yolo'].get('usar'):
        print(f'Modelo: {cfg["yolo"]["modelo"]}')
        print(f'Confianza mínima: {cfg["yolo"]["confianza_min"]}')
        print(f'Validación híbrida: {cfg["yolo"].get("validacion_hibrida", True)}')
        print(f'Score visual mínimo para aceptar Y25: {cfg["yolo"].get("score_visual_minimo_para_yolo", 50)}')


if __name__ == '__main__':
    main()
