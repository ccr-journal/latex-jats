FROM texlive/texlive:latest

ENV DEBIAN_FRONTEND=noninteractive

# System packages (TeX Live is already in the base image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # LaTeXML (0.8.8 from Debian repos — includes all Perl dependencies)
    latexml \
    # PDF figure conversion
    inkscape \
    # pdfinfo for page count detection
    poppler-utils \
    # Python
    python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set up application — copy full project (backend imports src/latex_jats)
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/

# Install Python dependencies into venv; use PYTHONPATH for the project itself
# so Path(__file__) resolves to src/ (needed for sibling xslt/ and latexml/ dirs)
RUN uv venv /app/.venv && \
    VIRTUAL_ENV=/app/.venv uv pip install lxml pyyaml 'fastapi>=0.111' 'uvicorn[standard]>=0.29' 'sqlmodel>=0.0.18' 'alembic>=1.13' 'python-multipart>=0.0.9'

# Copy backend code
COPY web/backend/ web/backend/

# Create storage directory (mount a volume here for persistence)
RUN mkdir -p /app/storage

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV STORAGE_DIR=/app/storage

EXPOSE 8000

CMD ["uvicorn", "web.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
