# GitHub Python Files Notes

這份文件專門記錄 GitHub 上 Python 檔案的常用操作。

## 目前 Repo

GitHub:

```text
git@github.com:c224456k/dot-price-bot.git
```

本地路徑:

```text
/home/twnoc/liaob/DClab
```

主要 Python 檔案:

```text
TW_stock.py
DCbot.py
botreplie.py
keep_alive.py
lunch.py
```

## 更新到 GitHub

修改完 Python 檔案後，進入 repo:

```bash
cd /home/twnoc/liaob/DClab
```

查看狀態:

```bash
git status
```

加入要上傳的檔案，例如:

```bash
git add TW_stock.py
```

建立 commit:

```bash
git commit -m "Update TW stock script"
```

推送到 GitHub:

```bash
git push origin main
```

## 從 GitHub 更新本地

如果 GitHub 上有新版本，要拉回本地:

```bash
cd /home/twnoc/liaob/DClab
git pull
```

## 套件管理

Python 套件寫在:

```text
requirements.txt
```

目前常用套件:

```text
requests
yfinance
discord.py
google-generativeai
```

如果換新機器或環境，要先安裝:

```bash
python3 -m pip install -r requirements.txt
```

## 注意事項

不要上傳 Python 暫存檔:

```text
__pycache__/
*.pyc
```

不要把密碼、token、Discord webhook、API key 直接寫進公開 repo。

如果有新增機密資料，建議改用環境變數或 GitHub Secrets。

## 檔名提醒

固定使用:

```text
TW_stock.py
```

不要再使用之前拼錯的:

```text
TW-sotck.py
```
