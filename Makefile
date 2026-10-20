# SPDX-FileCopyrightText: 2026 DX-OS Trust Core contributors
# SPDX-License-Identifier: Apache-2.0
PYTHON ?= python
export PYTHONDONTWRITEBYTECODE = 1
COMPOSE = docker compose -p dxos -f deploy/compose.yaml -f deploy/compose.p16.yaml

.PHONY: help dev-install lint test reuse check up down netcheck

help:
	@echo "make dev-install  - cài công cụ phát triển và các gói Python ở chế độ editable"
	@echo "make lint         - ruff"
	@echo "make test         - test đơn vị (không cần Docker)"
	@echo "make reuse        - kiểm tra giấy phép từng tệp (REUSE)"
	@echo "make check        - lint + reuse + test"
	@echo "make up / down    - dựng / dừng stack (cần deploy/compose*.yaml, Plan 01 Task 4)"
	@echo "make netcheck     - kiểm tra ma trận mạng AT-01 (Plan 01 Task 4)"

dev-install:
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) -m pip install -e libs/dxos-proof

lint:
	ruff check .

test:
	$(PYTHON) -m pytest -m "not integration and not infra"

reuse:
	reuse lint

check: lint reuse test

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

netcheck:
	$(PYTHON) ops/netcheck.py --matrix deploy/network-matrix.yaml --project dxos
