.PHONY: install test test-unit test-integration lint coverage clean

install:
	pip install -r requirements.txt

test:
	python -m pytest tests/ -v

test-unit:
	python -m pytest tests/unit -v --tb=short

test-integration:
	docker-compose -f docker-compose.test.yml up -d
	python -m pytest tests/integration -v
	docker-compose -f docker-compose.test.yml down

coverage:
	python -m pytest tests/unit --cov=src --cov-report=term-missing --cov-fail-under=80

lint:
	python -m ruff check src/ tests/
	az bicep lint infra/main.bicep

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .coverage htmlcov/ .pytest_cache/
