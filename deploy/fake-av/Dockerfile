# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
# fake-av: CHỈ DÙNG KHI PHÁT TRIỂN (hồ sơ dev-lite). Không có trong p8/p16 (AT-24).
FROM python:3.12-slim
LABEL dxos.dev-only="true"
WORKDIR /app
COPY fake_av.py /app/fake_av.py
USER nobody
EXPOSE 3310
CMD ["python", "/app/fake_av.py"]
