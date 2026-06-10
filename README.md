# 時光影單

用熱門新片推薦已下檔老電影的 Flask 期末專題 MVP。

## 功能

- 熱門電影列表：優先使用 TMDb trending API，沒有 key 時使用本地備援資料。
- 台灣正在上映：使用 requests + BeautifulSoup 爬取開眼電影網本期首輪上映資料，失敗時使用備援清單。
- 高評分電影：首頁以本地電影資料排序，整張卡片可點擊進入詳細頁。
- 電影搜尋：優先使用 TMDb search API，沒有 key 時搜尋本地資料。
- 電影詳細頁：顯示海報、年份、評分、類型、簡介。
- 老電影推薦：用 pandas 計算類型、關鍵字、評分與年代加權。
- 分析圖表：用 Chart.js 顯示同類型的年份分布、同年份的類型分布。

## 本地執行

```powershell
C:\Users\weiwe\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:TMDB_API_KEY="你的 TMDb key"
python app.py
```

沒有 `TMDB_API_KEY` 也可以執行，網站會使用 `data/movies.csv` 的本地資料。
如果本機預設 Python 是 3.14，建議改用 Python 3.12 或 3.11 建立 venv，避免 pandas 需要從原始碼編譯。

## Render 部署

1. 將專案推到 GitHub。
2. 在 Render 建立 Web Service。
3. Build Command 使用 `pip install -r requirements.txt`。
4. Start Command 使用 `gunicorn app:app`。
5. Environment Variables 新增 `TMDB_API_KEY`。
