# Image for the API and for a Nebius Serverless Job. The job container is the sandbox.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl build-essential gcc g++ make pkg-config \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY examples ./examples
RUN pip install --no-cache-dir -e .
ENV SANDBOX=local WORKDIR=/tmp/polyglot
EXPOSE 8000
CMD ["uvicorn", "polyglot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
