# Agent 工程筆記

這是繁體中文技術文章的公開網站來源。網站使用 Python 在本機產生靜態檔案，再由 GitHub Pages 發布 `docs/`。

## 建置

```powershell
C:\Users\LittleCloud\.nanobot\venv\Scripts\python.exe -m pip install -r requirements.txt
C:\Users\LittleCloud\.nanobot\venv\Scripts\python.exe tools\build.py
C:\Users\LittleCloud\.nanobot\venv\Scripts\python.exe tools\check_site.py
```

`C:\Projects\Agent-products\` 中的 `product.md` 是文章權威副本。`content/posts/` 保存經發布程序確認的公開副本。
