FROM node:20-alpine AS frontend-build

WORKDIR /app

# Install pnpm globally
RUN npm install -g pnpm

# Copy frontend source code
COPY frontend/ .

# Install frontend dependencies and build
RUN pnpm install && pnpm run build

# Backend build
FROM python:3.13-slim

RUN pip install uv

WORKDIR /app

# Copy backend files
COPY backend/ ./

# Copy frontend build to backend static directory
COPY --from=frontend-build /app/dist ./static

# Create __init__.py files for all directories containing Python files
RUN find . -name "*.py" -exec dirname {} \; | xargs -I {} touch {}/__init__.py

# Install dependencies using uv
RUN uv sync --frozen

# Activate virtual environment
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

ENV PYTHONPATH=/app

# Expose port
EXPOSE 5611

# Start the application
WORKDIR /app
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5611"]