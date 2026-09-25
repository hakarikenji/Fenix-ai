FROM python:3.11-slim
WORKDIR /app
# Free CPU Space = 2 vCPU / 16GB RAM. Set ENABLE_GGUF=1 in the Space settings
# to install the prebuilt CPU wheels for the fast quantized engine.
ARG ENABLE_GGUF=0
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$ENABLE_GGUF" = "1" ]; then \
      pip install --no-cache-dir llama-cpp-python \
      --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu ; \
    fi
COPY app.py .
EXPOSE 7860
CMD ["python", "app.py"]
