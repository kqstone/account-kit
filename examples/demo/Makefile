# account-kit demo. No Docker.
#   make install
#   make run WEB=vue        # uvicorn :8000 (builds UI packages + selected SPA if present)
#   make dev                # uvicorn --reload (pair with vite proxy /api)
#   make smoke              # needs DEMO_TEST_DATABASE_URL

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/../..)
DEMO := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV := $(DEMO)/.venv
WEB ?= vue
PORT ?= 8000
HOST ?= 127.0.0.1
PY := $(VENV)/bin/python

.PHONY: install run dev smoke ui-packages

$(VENV)/bin/python:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -U pip

install: $(VENV)/bin/python
	$(VENV)/bin/pip install -e "$(ROOT)[captcha]" "uvicorn[standard]"

ui-packages:
	@if [ -f "$(ROOT)/packages/account-ui-vue/package.json" ]; then \
		(cd "$(ROOT)/packages/account-ui-vue" && npm ci); \
	fi
	@if [ -f "$(ROOT)/packages/account-ui-react/package.json" ]; then \
		(cd "$(ROOT)/packages/account-ui-react" && npm ci); \
	fi

run: install ui-packages
	@if [ -f "$(DEMO)/web-$(WEB)/package.json" ]; then \
		(cd "$(DEMO)/web-$(WEB)" && npm ci && npm run build); \
	else \
		echo "skip frontend build: $(DEMO)/web-$(WEB) is not present yet"; \
	fi
	cd "$(DEMO)" && DEMO_WEB=$(WEB) $(VENV)/bin/uvicorn server.app:create_app --factory --host $(HOST) --port $(PORT)

dev: install
	@echo "API  http://127.0.0.1:$(PORT)"
	@echo "Vite: cd web-$(WEB) && npm install && npm run dev  (proxy /api -> http://127.0.0.1:$(PORT))"
	cd "$(DEMO)" && DEMO_WEB=$(WEB) $(VENV)/bin/uvicorn server.app:create_app --factory --reload --host $(HOST) --port $(PORT)

smoke: install
	@if [ -z "$$DEMO_TEST_DATABASE_URL" ]; then \
		echo "set DEMO_TEST_DATABASE_URL (or DEMO_TEST_DB_HOST/PORT/USER/PASSWORD/NAME)"; \
		exit 1; \
	fi
	cd "$(ROOT)" && $(PY) -m pip install pytest pytest-asyncio httpx >/dev/null
	cd "$(ROOT)" && $(PY) -m pytest examples/demo/tests -q
