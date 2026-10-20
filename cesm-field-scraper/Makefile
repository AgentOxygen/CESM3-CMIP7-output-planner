TAG ?= cesm3_0_alpha09e                # make build run TAG=cesm3_0_alpha11d OUT=out-alpha11d
OUT ?= out
IMAGE = cesm-field-scraper:$(TAG)

build:
	docker build -f docker/$(TAG).Dockerfile -t $(IMAGE) .

run:
	mkdir -p $(OUT)
	docker run --rm -u "$$(id -u):$$(id -g)" -v "$(CURDIR)/$(OUT):/out" $(IMAGE)

test:
	docker run --rm -v "$(CURDIR):/tool" -w /tool -e PYTHONDONTWRITEBYTECODE=1 python:3.12-slim \
	    sh -c "pip install -q --root-user-action=ignore pyyaml==6.0.2 pytest==8.3.4 && pytest -q -p no:cacheprovider"
