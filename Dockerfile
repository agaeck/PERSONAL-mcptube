FROM python:3.12-slim

# ffmpeg: OBRIGATÓRIO para extração de frames (SceneFrameExtractor).
# Sem ele, get_frame / get_frame_by_query falham.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Instala o mcptube a partir do código do SEU fork (pyproject.toml já existe no repo).
# Alternativa: troque por  pip install --no-cache-dir mcptube  se quiser fixar a
# versão publicada no PyPI em vez de buildar o source (mais estável, mas ignora
# qualquer modificação futura que você faça no fork).
RUN pip install --no-cache-dir .

# Diretório único para SQLite + índice ChromaDB + frames em cache.
ENV MCPTUBE_DATA_DIR=/data
RUN mkdir -p /data
VOLUME /data

# A Smithery injeta a variável de ambiente PORT=8081 ao subir o container.
# Shell-form + exec: ${PORT} é expandido em runtime, e o exec repassa sinais
# (SIGTERM) direto ao processo mcptube (parada limpa do container).
EXPOSE 8081
CMD ["/bin/sh", "-c", "exec mcptube serve --host 0.0.0.0 --port ${PORT:-8081} --path /"]