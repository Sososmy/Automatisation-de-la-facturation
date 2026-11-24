install:
	pip install -r requirements.txt
run:
	streamlit run src/app.py
test:
	python -m pytest -q
reset:
	python scripts/reset_data.py
scenarios:
	python scripts/run_scenarios.py
