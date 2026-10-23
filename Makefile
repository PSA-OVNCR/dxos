# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
PYTHON ?= python
export PYTHONDONTWRITEBYTECODE = 1
# Hồ sơ: p16 (mặc định), p8, dev-lite (laptop, có fake-av). Ví dụ: make up PROFILE=dev-lite
PROFILE ?= p16
ENV_FILE ?= .env
COMPOSE = docker compose -p dxos --env-file $(ENV_FILE) -f deploy/compose.yaml -f deploy/compose.$(PROFILE).yaml

.PHONY: help dev-install lint test reuse check up down ps logs netcheck test-infra test-db-up test-integration pin-images pin-actions licenses \
	openapi web-check web-build web-live vuot-rao

help:
	@echo "make dev-install  - cài công cụ phát triển và các gói Python ở chế độ editable (phụ thuộc theo constraints.txt)"
	@echo "make lint         - ruff"
	@echo "make test         - test đơn vị (không cần Docker)"
	@echo "make reuse        - kiểm tra giấy phép từng tệp (REUSE)"
	@echo "make check        - lint + reuse + test"
	@echo "make up / down    - dựng / dừng stack; PROFILE=p16|p8|dev-lite (mặc định p16)"
	@echo "make ps / logs    - trạng thái / log các container"
	@echo "make netcheck     - kiểm tra ma trận mạng AT-01 trên stack đang chạy"
	@echo "make test-infra   - test sống (marker infra) trên stack đang chạy"
	@echo "make test-db-up   - dựng dịch vụ cho integration test (PostgreSQL :55432, OpenBao, SeaweedFS, Flowable :58080)"
	@echo "make test-integration - integration test (marker integration), cần make test-db-up"
	@echo "make pin-images   - ghim digest mọi image trong deploy/ (cần Docker có buildx)"
	@echo "make pin-actions  - ghim mọi uses: trong .github/workflows theo SHA commit (cần ra được github.com)"
	@echo "make licenses     - quét giấy phép gói Python (runtime) và npm; ngoại lệ ở LICENSES-THIRD-PARTY.md"
	@echo "make openapi      - sinh lại docs/api/openapi.json từ ứng dụng FastAPI (không cần dịch vụ)"
	@echo "make web-check    - workspace npm: typecheck + test + build (cần Node 22 và npm 11.6.2, đã chạy npm ci)"
	@echo "make web-build    - dựng các SPA trong container Node vào volume apps-static (cần Docker; digest đã ghim)"
	@echo "make web-live     - kiểm trình duyệt thật (Playwright) trên stack dev-lite đang chạy (cần Docker)"
	@echo "make vuot-rao     - bảng thử vượt rào (10 kịch bản tấn công) trên stack dev đang chạy; ARGS='--only V1,V3'"

dev-install:
	$(PYTHON) -m pip install -c constraints.txt -r requirements-dev.txt
	$(PYTHON) -m pip install -c constraints.txt -e libs/dxos-proof -e core -e witness -e cli

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
	docker compose -f deploy/compose.test.yaml up -d --wait core-db seaweedfs openbao flowable

test-integration:
	$(PYTHON) -m pytest -m integration -v

test-infra:
	$(PYTHON) -m pytest -m infra tests/infra -v

pin-images:
	$(PYTHON) ops/pin_images.py

pin-actions:
	$(PYTHON) ops/pin_actions.py

licenses:
	$(PYTHON) ops/license_scan.py

openapi:
	$(PYTHON) ops/openapi.py

netcheck:
	$(PYTHON) ops/netcheck.py --matrix deploy/network-matrix.yaml --project dxos

web-check:
	npm run check

web-build:
	bash ops/web_build_docker.sh

web-live:
	bash ops/web_live.sh

vuot-rao:
	$(PYTHON) ops/vuot_rao.py $(ARGS)
