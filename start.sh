cd /home/container && if [ -f requirements.txt ]; then pip install --disable-pip-version-check -U --prefix .local -r requirements.txt; fi && chmod +x ./bin/challenge && exec python3 -u main.py
