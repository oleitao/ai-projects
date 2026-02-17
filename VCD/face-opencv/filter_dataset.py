#!/usr/bin/env python3
import json
import os
import shutil
from pathlib import Path

# === CONFIGURAÇÃO ===

# Caminho para o export do Label Studio (JSON)
LABEL_STUDIO_EXPORT = "project-35-at-2025-12-02-11-43-db3148c1.json"

# Pastas onde estão TODAS as imagens originais
SOURCE_DIRS = [
    Path("dataset/actor-pedro-dia"),
    Path("dataset/actor-pedro-noite"),
    Path("dataset/actor-pedro-sem_oculos"),
]

# Pasta de destino dos datasets filtrados
DEST_ROOT = Path("dataset-filtrado")

# Mapeamento label -> subpasta de destino
LABEL_MAP = {
    "Óculos": "com_oculos",
    "Oculos": "com_oculos",       # caso escrevas sem acento
    "Sem_Óculos": "sem_oculos",
    "Sem_Oculos": "sem_oculos",   # idem
}

# === FUNÇÕES AUXILIARES ===

def find_source_file(file_upload_name: str) -> Path | None:
    """
    Tenta encontrar o ficheiro original nas SOURCE_DIRS.
    Primeiro tenta o nome inteiro (com hash), depois a parte depois do primeiro '-'.
    """
    candidates = []

    for src_dir in SOURCE_DIRS:
        # 1) nome tal como está no file_upload
        candidates.append(src_dir / file_upload_name)

        # 2) nome sem o hash antes do primeiro '-'
        if "-" in file_upload_name:
            suffix = file_upload_name.split("-", 1)[1]
            candidates.append(src_dir / suffix)

    for c in candidates:
        if c.is_file():
            return c

    return None


def main():
    LABEL_STUDIO_EXPORT_PATH = Path(LABEL_STUDIO_EXPORT)

    if not LABEL_STUDIO_EXPORT_PATH.is_file():
        print(f"[ERRO] Ficheiro JSON não encontrado: {LABEL_STUDIO_EXPORT_PATH}")
        return

    with open(LABEL_STUDIO_EXPORT_PATH, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    DEST_ROOT.mkdir(parents=True, exist_ok=True)

    stats_copiados = {}
    nao_encontrados = []

    for task in tasks:
        annotations = task.get("annotations") or []
        if not annotations:
            continue

        # Assumimos 1 anotação e 1 resultado por tarefa (como no teu ficheiro)
        try:
            result = annotations[0]["result"][0]
            label_choice = result["value"]["choices"][0]
        except (KeyError, IndexError) as e:
            print(f"[AVISO] Estrutura de anotação inesperada na task {task.get('id')}: {e}")
            continue

        # Mapeia o label para a pasta
        dest_subdir = LABEL_MAP.get(label_choice)
        if dest_subdir is None:
            print(f"[AVISO] Label '{label_choice}' não está no LABEL_MAP, task {task.get('id')}, a ignorar.")
            continue

        file_upload_name = task.get("file_upload")
        if not file_upload_name:
            print(f"[AVISO] Task {task.get('id')} sem 'file_upload', a ignorar.")
            continue

        src_path = find_source_file(file_upload_name)

        if src_path is None:
            print(f"[NAO ENCONTRADO] Não foi possível localizar a imagem '{file_upload_name}' em SOURCE_DIRS.")
            nao_encontrados.append(file_upload_name)
            continue

        dest_dir = DEST_ROOT / dest_subdir
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_dir / src_path.name

        # Copia o ficheiro (podes trocar para shutil.move se quiseres mover em vez de copiar)
        shutil.copy2(src_path, dest_path)

        stats_copiados[dest_subdir] = stats_copiados.get(dest_subdir, 0) + 1
        print(f"[OK] {src_path} -> {dest_path} (label={label_choice})")

    print("\n=== RESUMO ===")
    if stats_copiados:
        for subdir, count in stats_copiados.items():
            print(f"  {subdir}: {count} ficheiros copiados")
    else:
        print("  Nenhum ficheiro copiado.")

    if nao_encontrados:
        print("\nFicheiros que não foram encontrados em nenhuma SOURCE_DIR:")
        for name in nao_encontrados:
            print("  -", name)


if __name__ == "__main__":
    main()
