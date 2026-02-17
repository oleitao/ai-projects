import cv2
from pathlib import Path
from datetime import datetime

# Pasta raiz do dataset de rostos autorizados
DATASET_ROOT = Path("dataset")
DATASET_ROOT.mkdir(exist_ok=True)

# Guarda 1 imagem a cada N frames enquanto está a gravar
SAVE_INTERVAL_FRAMES = 5  # ajusta conforme precisares


def recortar_rosto(frame, face_box, pad_ratio=0.2):
    """
    Recebe o frame e um bounding box (x,y,w,h), devolve o recorte com margem.
    """
    x, y, w, h = face_box

    pad_w = int(w * pad_ratio)
    pad_h = int(h * pad_ratio)

    x1 = max(0, x - pad_w)
    y1 = max(0, y - pad_h)
    x2 = min(frame.shape[1], x + w + pad_w)
    y2 = min(frame.shape[0], y + h + pad_h)

    return frame[y1:y2, x1:x2]


def guardar_imagem_dataset(face_crop, label):
    """
    Guarda um recorte de rosto na pasta dataset/<label>/ com timestamp.
    """
    subject_dir = DATASET_ROOT / label
    subject_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = subject_dir / f"{label}_{timestamp}.jpg"
    cv2.imwrite(str(filename), face_crop)
    return filename


def configurar_por_janela(face_crop, selected_index):
    """
    Janela OpenCV para:
      - mostrar o rosto
      - permitir escrever o nome do ator
      - ENTER -> confirma e começa aquisição
      - ESC   -> cancela

    Devolve o label (string) ou None se o utilizador cancelar.
    """
    window_name = "Configurar Dataset (ENTER=confirmar, ESC=cancelar)"
    default_label = f"person_{selected_index}"
    label = default_label  # podes mudar para "" se quiser começar vazio

    while True:
        preview = face_crop.copy()

        # Caixa preta com texto
        cv2.rectangle(preview, (5, 5), (preview.shape[1] - 5, 80), (0, 0, 0), -1)

        cv2.putText(
            preview,
            f"Rosto selecionado: {selected_index}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            preview,
            "Nome do ator:",
            (10, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            preview,
            label,
            (10, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

        cv2.imshow(window_name, preview)
        key = cv2.waitKey(0) & 0xFF

        # ENTER (13 ou 10) -> confirmar
        if key in (13, 10):
            label_clean = label.strip()
            if not label_clean:
                label_clean = default_label
            label_clean = label_clean.replace(" ", "_")
            cv2.destroyWindow(window_name)
            return label_clean

        # ESC -> cancelar
        if key == 27:
            cv2.destroyWindow(window_name)
            return None

        # BACKSPACE
        if key in (8, 127):
            label = label[:-1]
            continue

        # Caracteres imprimíveis
        if 32 <= key <= 126:
            label += chr(key)


def main():
    # Abre a câmera padrão
    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        print("Erro: não foi possível acessar a câmera.")
        return

    # Classificador de rostos
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    if face_cascade.empty():
        print("Erro: não foi possível carregar o classificador de rosto.")
        return

    selected_index = None   # índice de rosto atualmente selecionado (1..N)
    recording = False       # estamos a gravar automaticamente?
    recording_label = None  # nome do ator em aquisição
    frame_counter = 0       # frames desde início da aquisição
    saved_count = 0         # nº de imagens guardadas nesta sessão

    print("Iniciado.")
    print("Controlo via JANELA OpenCV (foco na janela de vídeo).")
    print("Teclas:")
    print("  1..9   -> selecionar índice de rosto no frame atual")
    print("  ESPAÇO -> abrir janela para nome do ator e iniciar aquisição")
    print("  P      -> parar aquisição")
    print("  q ou ESC -> sair.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Erro ao capturar frame da câmera.")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detecta rostos
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.3,
            minNeighbors=5,
            minSize=(30, 30)
        )

        # Escreve índices dos rostos (sem retângulo)
        for idx, (x, y, w, h) in enumerate(faces, start=1):
            label_txt = f"Rosto {idx}"
            cv2.putText(
                frame,
                label_txt,
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
                cv2.LINE_AA
            )

        # Inf. total de rostos
        cv2.putText(
            frame,
            f"Total de rostos: {len(faces)}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
            cv2.LINE_AA
        )

        # Índice selecionado
        if selected_index is not None:
            cv2.putText(
                frame,
                f"Indice selecionado: {selected_index}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA
            )

        # Estado da aquisição
        if recording and recording_label is not None:
            status_text = f"AQUISICAO: {recording_label} (Rosto {selected_index}) | imgs: {saved_count}"
            cv2.putText(
                frame,
                status_text,
                (10, 90),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
                cv2.LINE_AA
            )

        cv2.putText(
            frame,
            "1-9: indice | ESPACO: configurar+iniciar | P: parar | q/ESC: sair",
            (10, frame.shape[0] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA
        )

        cv2.imshow("Dataset de Rostos Autorizados - Webcam", frame)

        # AQUISIÇÃO AUTOMÁTICA
        if recording and recording_label is not None and selected_index is not None:
            if len(faces) >= selected_index:
                frame_counter += 1
                if frame_counter % SAVE_INTERVAL_FRAMES == 0:
                    face_box = faces[selected_index - 1]
                    face_crop = recortar_rosto(frame, face_box, pad_ratio=0.2)
                    filename = guardar_imagem_dataset(face_crop, recording_label)
                    saved_count += 1
                    print(f"[AUTO] Guardado: {filename}")
            else:
                # rosto com esse índice não encontrado neste frame
                pass

        key = cv2.waitKey(1) & 0xFF

        # q ou ESC -> sair
        if key == ord('q') or key == 27:
            break

        # 1..9 -> escolher índice do rosto
        if ord('1') <= key <= ord('9'):
            idx = key - ord('0')
            selected_index = idx
            print(f"[INFO] Índice selecionado: {selected_index}")

        # ESPAÇO -> configurar por janela (nome + confirmação) e iniciar aquisição
        if key == 32:  # barra de espaço
            if selected_index is None:
                print("[AVISO] Primeiro escolhe o índice do rosto (1..9) na janela de vídeo.")
            elif len(faces) < selected_index:
                print(
                    f"[AVISO] O índice {selected_index} não existe neste frame "
                    f"(apenas {len(faces)} rostos detetados)."
                )
            else:
                # congela o frame atual e abre janela de configuração
                face_box = faces[selected_index - 1]
                face_crop = recortar_rosto(frame, face_box, pad_ratio=0.2)
                label = configurar_por_janela(face_crop, selected_index)

                if label is None:
                    print("[INFO] Configuração cancelada.")
                else:
                    # guarda logo a primeira imagem
                    first_file = guardar_imagem_dataset(face_crop, label)
                    print(f"[INICIO] Primeira imagem guardada: {first_file}")

                    # ativa aquisição automática
                    recording = True
                    recording_label = label
                    frame_counter = 0
                    saved_count = 1

        # P -> parar aquisição
        if key in (ord('p'), ord('P')):
            if recording:
                print(
                    f"[INFO] Aquisição terminada para '{recording_label}'. "
                    f"Imagens guardadas nesta sessão: {saved_count}"
                )
            recording = False
            recording_label = None
            frame_counter = 0
            saved_count = 0

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
