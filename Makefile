.PHONY: setup lint test

setup:
	pip install pre-commit
	pre-commit install --hook-type pre-commit --hook-type pre-push

lint:
	pre-commit run black --all-files

test:
	python -m pytest --tb=short -q
