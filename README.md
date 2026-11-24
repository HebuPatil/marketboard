pip3 install yfinance pandas numpy
python3 run_all.py --force      # first build
python3 run_all.py              # every page, max 2 pulls per page per day, 6h apart
python3 run_all.py news --force # one page, ignoring the limit
python3 run_all.py --demo       # fake data, offline