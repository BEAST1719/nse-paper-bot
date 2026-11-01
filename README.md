# NSE Paper-Trading Bot (free, cloud, fake money)

1. Make a free account at github.com
2. New repository -> name it `nse-paper-bot` -> Public -> Create
3. "Add file -> Upload files": upload bot.py, requirements.txt, README.md
   Then "Add file -> Create new file", name it `.github/workflows/paper.yml`, paste the contents of paper.yml
4. Settings -> Actions -> General -> Workflow permissions -> "Read and write" -> Save
5. Actions tab -> "paper-trade" -> "Run workflow". It now also runs by itself every weekday at 4:30 PM IST.
6. Open `report.md` in the repo each day to see your fake portfolio.

Backtest first (free): open github.com/codespaces (or colab.research.google.com), then run
    pip install -r requirements.txt && python bot.py backtest
To trade more stocks: create `universe.txt` with NSE symbols (RELIANCE, TCS, ...), one per line.
