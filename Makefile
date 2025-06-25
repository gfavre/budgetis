PY = .venv/bin/python
MANAGE = $(PY) manage.py

setup:
	uv venv .venv && source .venv/bin/activate && uv install

run:
	$(MANAGE) runserver

migrate:
	$(MANAGE) migrate
