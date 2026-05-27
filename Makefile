PYTHON ?= .venv/bin/python
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff
REPORT ?= reports/pytest-report.html
DOCKER ?= docker
IMAGE_NAME ?= geofeed-tools
IMAGE_TAG ?= local
LOCAL_IMAGE ?= $(IMAGE_NAME):$(IMAGE_TAG)
GHCR_IMAGE ?= ghcr.io/python-modules/geofeed-tools
DOCKERHUB_IMAGE ?= pythonmodules/geofeed-tools
BUILDER_IMAGE ?= python:3.13-slim
RUNTIME_IMAGE ?= gcr.io/distroless/python3-debian13:nonroot
DOCKER_RUN_FLAGS ?=
DOCKER_ARGS ?= --help

.PHONY: help lint test test-html test-integration clean-reports \
	docker-build docker-run docker-tag docker-push-ghcr docker-push-dockerhub docker-push-all

help:
	@echo "Available targets:"
	@echo "  make lint             Run Ruff lint checks"
	@echo "  make test             Run non-integration tests"
	@echo "  make test-html        Run non-integration tests and generate HTML report"
	@echo "  make test-integration Run integration tests (real HTTP requests)"
	@echo "  make clean-reports    Remove generated test reports"
	@echo "  make docker-build     Build the local Docker image ($(LOCAL_IMAGE))"
	@echo "  make docker-run       Run the local Docker image with DOCKER_ARGS"
	@echo "  make docker-tag       Tag the local image for GHCR and Docker Hub"
	@echo "  make docker-push-ghcr Push the tagged image to GHCR"
	@echo "  make docker-push-dockerhub Push the tagged image to Docker Hub"
	@echo "  make docker-push-all  Push the tagged image to both registries"
	@echo "                       Override BUILDER_IMAGE/RUNTIME_IMAGE to test other Python bases"

lint:
	$(RUFF) check src tests

test:
	$(PYTEST) -q -m "not integration" -o addopts=""

test-html:
	$(PYTEST) -q -m "not integration" -o addopts="" \
		--html=$(REPORT) --self-contained-html

test-integration:
	$(PYTEST) -v -m integration -o addopts=""

clean-reports:
	rm -rf reports

docker-build:
	$(DOCKER) build \
		--build-arg BUILDER_IMAGE=$(BUILDER_IMAGE) \
		--build-arg RUNTIME_IMAGE=$(RUNTIME_IMAGE) \
		-t $(LOCAL_IMAGE) .

docker-run: docker-build
	$(DOCKER) run --rm $(DOCKER_RUN_FLAGS) $(LOCAL_IMAGE) $(DOCKER_ARGS)

docker-tag: docker-build
	$(DOCKER) tag $(LOCAL_IMAGE) $(GHCR_IMAGE):$(IMAGE_TAG)
	$(DOCKER) tag $(LOCAL_IMAGE) $(DOCKERHUB_IMAGE):$(IMAGE_TAG)

docker-push-ghcr: docker-tag
	$(DOCKER) push $(GHCR_IMAGE):$(IMAGE_TAG)

docker-push-dockerhub: docker-tag
	$(DOCKER) push $(DOCKERHUB_IMAGE):$(IMAGE_TAG)

docker-push-all: docker-push-ghcr docker-push-dockerhub
