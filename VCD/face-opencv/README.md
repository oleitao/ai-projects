# Face OpenCV – Dataset de Rostos

Pequeno projeto para:

- capturar rostos via webcam com OpenCV
- organizar as imagens em pastas por ator/label
- anotar as imagens no Label Studio
- gerar um dataset filtrado (por exemplo, com/sem óculos)

Pensado como base para experiências de visão computacional (reconhecimento / classificação de rostos).

---

## Estrutura do projeto

- `main_webcam.py` – abre a webcam, deteta rostos e guarda recortes em `dataset/<label>/`.
- `filter_dataset.py` – lê o export JSON do Label Studio e copia as imagens anotadas para `dataset-filtrado/<subpasta>/`.
- `dataset/` – onde o `main_webcam.py` grava as imagens originais (por ator/label).
- `dataset-filtrado/` – destino das imagens filtradas por label (por exemplo `com_oculos` e `sem_oculos`).
- `project-35-at-2025-12-02-11-43-db3148c1.json` – exemplo de export de anotações do Label Studio.
- `requirements.txt` – dependências Python (OpenCV, NumPy).

> Nota: no repositório pode existir uma pasta `dataset-filtered`; o script usa por omissão `dataset-filtrado`. Ajusta o nome em `filter_dataset.py` (`DEST_ROOT`) se quiseres alinhar tudo.

---

## Pré‑requisitos

- Python 3.10+ (recomendado)
- Webcam funcional ligada ao computador
- Ambiente virtual (opcional, mas recomendado)

Instalação das dependências:

```bash
cd VCD/face-opencv
pip install -r requirements.txt
```

---

## 1. Capturar imagens com a webcam

1. Garante que estás na pasta do projeto:

   ```bash
   cd VCD/face-opencv
   ```

2. Executa o script:

   ```bash
   python main_webcam.py
   ```

3. Controlo na janela do OpenCV:
   - `1`..`9` – escolher o índice do rosto detetado no frame atual.
   - `ESPAÇO` – abre uma janela para escrever o nome do ator (label) e iniciar a aquisição automática.
   - `P` – parar a aquisição automática para o ator atual.
   - `q` ou `ESC` – sair do programa.

4. As imagens são guardadas em:
   - `dataset/<label>/<label>_<timestamp>.jpg`

Sugestão: usa labels descritivos, por exemplo `actor-pedro-dia`, `actor-pedro-noite`, `actor-pedro-sem_oculos`, etc.

---

## 2. Anotar no Label Studio

Fluxo típico:

1. Sobe as imagens de `dataset/` para um projeto no Label Studio.
2. Cria labels, por exemplo:
   - `Óculos` / `Oculos`
   - `Sem_Óculos` / `Sem_Oculos`
3. Anota as imagens (classificação de imagem simples já é suficiente).
4. Exporta o projeto em formato **JSON**.
5. Coloca o ficheiro exportado na raiz deste diretório (ou ajusta o caminho em `filter_dataset.py`).

Por omissão, o script espera um ficheiro com o nome:

- `LABEL_STUDIO_EXPORT = "project-35-at-2025-12-02-11-43-db3148c1.json"`

Podes alterar esta constante no topo de `filter_dataset.py` para apontar para o teu export.

---

## 3. Gerar o dataset filtrado

O `filter_dataset.py`:

- lê o export JSON do Label Studio
- para cada imagem anotada, descobre o ficheiro original em `dataset/...`
- copia a imagem para `dataset-filtrado/<subpasta>/` de acordo com a label

Mapeamento de labels (por omissão):

- `"Óculos"` ou `"Oculos"` → `dataset-filtrado/com_oculos`
- `"Sem_Óculos"` ou `"Sem_Oculos"` → `dataset-filtrado/sem_oculos`

Para executar:

```bash
cd VCD/face-opencv
python filter_dataset.py
```

No final o script imprime:

- quantas imagens foram copiadas por subpasta
- lista de ficheiros que não foram encontrados nas pastas de origem (`SOURCE_DIRS`)

Se mudares a estrutura da pasta `dataset/`, ajusta:

- `SOURCE_DIRS` – lista de diretórios onde o script procura as imagens originais
- `LABEL_MAP` – mapeamento label → subpasta de destino

---

## Próximos passos

Com o dataset em `dataset-filtrado/` já organizado, podes:

- treinar um classificador simples (por exemplo, com scikit-learn ou PyTorch)
- testar modelos de reconhecimento facial ou verificação de identidade
- criar um protótipo de sistema de acesso baseado na deteção de rosto/óculos

Este diretório foca‑se apenas na **aquisição e organização** dos dados; o treino do modelo fica em projetos separados.
