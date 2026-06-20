from __future__ import annotations

import random
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

RAW_DIR = Path("dataset_yolo/raw")
OUT_DIR = Path("dataset_yolo_clasificacion_ligero")
ZIP_PATH = Path("dataset_yolo_clasificacion_ligero.zip")

CLASSES = ("auto_dueno", "otro_auto")
EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SEED = 42
SIZE = 320
JPEG_QUALITY = 88


def list_images(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTS
    )


def split_files(files: list[Path]) -> dict[str, list[Path]]:
    rnd = random.Random(SEED)
    files = files[:]
    rnd.shuffle(files)

    n = len(files)
    n_train = int(n * 0.70)
    n_val = int(n * 0.20)

    return {
        "train": files[:n_train],
        "val": files[n_train:n_train + n_val],
        "test": files[n_train + n_val:],
    }


def save_letterboxed(src: Path, dst: Path) -> bool:
    try:
        with Image.open(src) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((SIZE, SIZE), Image.Resampling.LANCZOS)

            canvas = Image.new("RGB", (SIZE, SIZE), (114, 114, 114))
            x = (SIZE - im.width) // 2
            y = (SIZE - im.height) // 2
            canvas.paste(im, (x, y))

            dst.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(
                dst,
                format="JPEG",
                quality=JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
        return True
    except Exception as exc:
        print(f"[AVISO] Se omitió {src}: {exc}")
        return False


def main() -> None:
    if not RAW_DIR.exists():
        raise SystemExit(
            "No existe dataset_yolo/raw. Ejecuta este script dentro de Vision_Artificial."
        )

    counts = {}
    class_files = {}
    for cls in CLASSES:
        folder = RAW_DIR / cls
        files = list_images(folder)
        class_files[cls] = files
        counts[cls] = len(files)

    print("[CONTEO RAW]")
    for cls, count in counts.items():
        print(f"  {cls}: {count}")

    if min(counts.values()) < 100:
        raise SystemExit(
            "Hay menos de 100 imágenes en una clase. Agrega más imágenes antes de entrenar."
        )

    ratio = max(counts.values()) / max(1, min(counts.values()))
    if ratio > 3:
        print(
            "[ADVERTENCIA] El dataset está muy desbalanceado. "
            "Conviene agregar más imágenes a la clase con menos fotos."
        )

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    total = sum(counts.values())
    done = 0
    saved = 0

    for cls, files in class_files.items():
        splits = split_files(files)
        for split, split_files_list in splits.items():
            for idx, src in enumerate(split_files_list, start=1):
                dst = OUT_DIR / split / cls / f"{cls}_{idx:05d}.jpg"
                if save_letterboxed(src, dst):
                    saved += 1
                done += 1
                if done % 100 == 0 or done == total:
                    print(f"[PROGRESO] {done}/{total}")

    print("[ZIP] Comprimiendo dataset ligero...")
    with zipfile.ZipFile(
        ZIP_PATH,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as zf:
        for path in OUT_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(OUT_DIR.parent))

    size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"[LISTO] Imágenes procesadas: {saved}")
    print(f"[LISTO] Carpeta: {OUT_DIR.resolve()}")
    print(f"[LISTO] ZIP: {ZIP_PATH.resolve()}")
    print(f"[LISTO] Tamaño ZIP: {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
