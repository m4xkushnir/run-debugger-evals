PY ?= .venv/bin/python

.PHONY: data test run report

data:
	$(PY) data/build_dataset.py

test:
	$(PY) -m pytest -q

run:
	$(PY) -m harness.run --models haiku,sonnet --repeats 5
	$(PY) -m harness.run --models opus --repeats 2
	$(PY) -m harness.run --models haiku,sonnet --repeats 1 --variant no_json

report:
	$(PY) -m harness.report > /dev/null
