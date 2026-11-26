install:
	pip install -r requirements.txt
run:
	streamlit run src/app.py
test:
	python -m pytest -q
reset:
	python -m scripts.reset_data --confirm
scenarios:
	python -m scripts.run_scenarios
docker-up:
	docker compose up --build -d
docker-down:
	docker compose down
