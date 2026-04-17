# TeX Live, LaTeXML, inkscape, poppler, python3, uv all baked into the base
# image. See web/backend/Dockerfile.base and the "Rebuilding the base image"
# section of README.md. Bump the date tag when refreshing system packages.
FROM ccsamsterdam/latex-jats-base:2026-04d

# Set up application — copy full project (backend imports src/latex_jats)
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/

# Install Python dependencies into venv; use PYTHONPATH for the project itself
# so Path(__file__) resolves to src/ (needed for sibling xslt/ and latexml/ dirs)
RUN uv venv /app/.venv && \
    VIRTUAL_ENV=/app/.venv uv pip install '.[web]'

# Copy backend code
COPY web/backend/ web/backend/

# Create storage directory (mount a volume here for persistence)
RUN mkdir -p /app/storage

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV STORAGE_DIR=/app/storage

EXPOSE 8000

CMD ["uvicorn", "web.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
