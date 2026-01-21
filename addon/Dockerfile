FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    linux-headers-generic \
    libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# onnxruntime should have aarch64 wheels for standard Python images
RUN pip3 install \
    google-genai \
    numpy \
    scipy \
    onnxruntime \
    aiohttp \
    --break-system-packages

COPY . /app

# COPY run.sh /run.sh
# RUN chmod a+x /run.sh

# CMD [ "/run.sh" ]
CMD [ "python3", "/app/proxy.py" ]
