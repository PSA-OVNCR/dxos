# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
PYTHON ?= python
export PYTHONDONTWRITEBYTECODE = 1
# Hồ sơ: p16 (mặc định), p8, dev-lite (laptop, có fake-av). Ví dụ: make up PROFILE=dev-lite
PROFILE ?= p16
ENV_FILE ?= .env
COMPOSE = docker compose -p dxos --env-file $(ENV_FILE) -f deploy/compose.yaml -f deploy/compose.$(PROFILE).yaml

.PHONY: help dev-install lint test reuse check up down ps logs netcheck test-infra test-db-up test-integration pin-images

help:
	@echo "make dev-install  - cài công cụ phát triển và các gói Python ở chế độ editable"
	@echo "make lint         - ruff"
	@echo "make test         - test đơn vị (không cần Docker)"
	@echo "make reuse        - kiểm tra giấy phép từng tệp (REUSE)"
	@echo "make check        - lint + reuse + test"
	@echo "make up / down    - dựng / dừng stack; PROFILE=p16|p8|dev-lite (mặc định p16)"
	@echo "make ps / logs    - trạng thái / log các container"
	@echo "make netcheck     - kiểm tra ma trận mạng AT-01 trên stack đang chạy"
	@echo "make test-infra   - test sống (marker infra) trên stack đang chạy"
	@echo "make test-db-up   - dựng PostgreSQL cho integration test (127.0.0.1:55432)"
	@echo "make test-integration - integration test (marker integration), cần make test-db-up"
	@echo "make pin-images   - ghim digest mọi image trong deploy/ (cần Docker có buildx)"

dev-install:
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) -m pip install -e libs/dxos-proof -e core -e witness

lint:
	ruff check .

test:
	$(PYTHON) -m pytest -m "not integration and not infra"

reuse:
	reuse lint

check: lint reuse test

$(ENV_FILE):
	@echo "Chưa có $(ENV_FILE): chạy 'cp .env.example $(ENV_FILE)' rồi đổi mật khẩu." && exit 1

up: $(ENV_FILE)
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=100

test-db-up:
	docker compose -f deploy/compose.test.yaml up -d --wait core-db seaweedfs openbao

test-integration:
	$(PYTHON) -m pytest -m integration -v

test-infra:
	$(PYTHON) -m pytest -m infra tests/infra -v

pin-images:
	$(PYTHON) ops/pin_images.py

netcheck:
	$(PYTHON) ops/netcheck.py --matrix deploy/network-matrix.yaml --project dxos
