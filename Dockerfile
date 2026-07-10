FROM python:3.12-slim

# ffmpeg: OBRIGATÓRIO para extração de frames (SceneFrameExtractor).
# Sem ele, get_frame / get_frame_by_query falham.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Instala o mcptube a partir do código do SEU fork (pyproject.toml já existe no repo).
# bgutil-ytdlp-pot-provider: plugin do yt-dlp que pede PO tokens ao container
# mcptube-pot (dependência de deploy, não do pacote — por isso não vai no pyproject).
# A versão DEVE casar com a imagem brainicism/... do docker-compose.yml — o upstream
# exige plugin e provider em versões iguais; atualize os dois juntos.
RUN pip install --no-cache-dir . bgutil-ytdlp-pot-provider==1.3.1

# Diretório único para SQLite + índice ChromaDB + frames em cache.
ENV MCPTUBE_DATA_DIR=/data
RUN mkdir -p /data
VOLUME /data

# A Smithery injeta a variável de ambiente PORT=8081 ao subir o container.
# Shell-form + exec: ${PORT} é expandido em runtime, e o exec repassa sinais
# (SIGTERM) direto ao processo mcptube (parada limpa do container).
EXPOSE 8081
CMD ["/bin/sh", "-c", "exec mcptube serve --host 0.0.0.0 --port ${PORT:-8081} --path /"]