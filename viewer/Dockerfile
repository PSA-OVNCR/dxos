# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
#
# Image Viewer (S2): chỉ RAM, không ghi đĩa, không bí mật. Chạy được trên hệ tệp gốc chỉ đọc (Task 8 bật read_only).
# Build từ thư mục gốc repo (cần constraints.txt):
#   docker build -f viewer/Dockerfile -t dxos-viewer .
# Tệp bỏ qua khi build: viewer/Dockerfile.dockerignore.

FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# constraints.txt ghim phiên bản mọi phụ thuộc runtime (Plan 04 Task 1); không cần apt: PDFium nằm trong wheel pypdfium2.
COPY constraints.txt /tmp/src/constraints.txt
COPY viewer /tmp/src/viewer
RUN pip install -c /tmp/src/constraints.txt /tmp/src/viewer \
 && rm -rf /tmp/src \
 && useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin dxos

# Không chạy bằng root.
USER 10001:10001
WORKDIR /
EXPOSE 8000

CMD ["uvicorn", "dxos_viewer.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
