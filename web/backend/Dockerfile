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

# Install Python dependencies (project + web extras)
# Editable install so Path(__file__).parent resolves to src/ (needed for xslt/ and latexml/ paths)
RUN uv venv /app/.venv && \
    VIRTUAL_ENV=/app/.venv uv pip install -e '.[web]'

# Copy backend code
COPY web/backend/ web/backend/

# Create storage directory (mount a volume here for persistence)
RUN mkdir -p /app/storage

ENV PATH="/app/.venv/bin:$PATH"
ENV STORAGE_DIR=/app/storage

EXPOSE 8000

CMD ["uvicorn", "web.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
