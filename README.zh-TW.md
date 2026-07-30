# pickbar

**零依賴的終端機光棒選單。單一檔案，Windows 與 POSIX 通吃，CJK 對齊正確。**

[English](README.md)

光棒，BBS 年代軟體的手感：反白亮條用方向鍵開，數字直接跳，Enter 定案。
`pickbar` 把這套帶進 Python 腳本，零依賴、單一模組、三個函式：

```python
from pickbar import pick, pick_multi, pick_dir

i = pick(["Install", "Update", "Exit"], title="[ setup ]")
# -> 選中的索引，取消回 None

idxs = pick_multi(["a.txt", "b.txt", "c/"], title="Select files:")
# -> 選中的索引們（Space 勾選，'a' 全選），取消回 None

path = pick_dir("Choose a directory:", allow_create=True)
# -> 邊打字邊過濾，'/' 或 '~' 開頭直接跳到該路徑
```

試玩：`python -m pickbar`

```
[ setup ]
   1. Install
▌  2. Update                                                                 ▐
   3. Exit
 ↑/↓ move · Enter select · Esc cancel
```

## 為什麼還要再造一個選單庫

現有選擇讓你三選二：

- 零依賴的（`simple-term-menu`、`pmenu`）不支援 Windows，前者官方文件
  明寫只支援 Linux 和 macOS。

- 支援 Windows 的（`InquirerPy`、`beaupy`、`questionary`）拖著
  `prompt_toolkit` 或 `rich` 一整串依賴。

- 東亞文字在多數庫裡對不齊；`console-menu` 在 Windows 上經
  `windows-curses` 有已知的 CJK 顯示問題。

`pickbar` 三個同時做到：只用標準庫，Windows VT 與 POSIX termios 都原生
處理，所有裁切與補齊都按顯示寬度（`unicodedata.east_asian_width`）計算，
`中文`、`日本語` 標籤和 ASCII 排在一起不歪，Windows 也一樣。

降級也降得誠實：stdin/stdout 不是 TTY（pipe、cron、CI）或終端機不支援
ANSI 時，每個選單自動退回傳統編號 `input()` 提示，回傳約定完全相同，
用了 pickbar 的腳本照樣可以被腳本呼叫。

## 安裝

```sh
pip install pickbar
```

或直接 vendor：把 `pickbar.py` 複製進你的專案。它就是一個檔案、只 import
標準庫，這正是設計目的。

需要 Python 3.8+。

## API

### `pick(options, title=None, *, index=0, keys=None, footer=None)`

單選。回傳選中的索引（`int`）、`keys` 對應值、或取消時 `None`。

- `options`：標籤清單，能 `str()` 的都行，多行標籤也支援。
- `index`：一開始亮在哪一列。
- `keys`：`{字元: 值}` 快捷鍵，按下該字元直接回傳對應值。
- `footer`：清單下方的提示列（預設會說明按鍵）。

按鍵：`↑`/`↓` 移動（循環）、數字跳光棒（Enter 確認；打數字不會直接選定，
避免誤按）、`Home`/`End`、`Enter` 選定、`Esc`/`q`/`0` 取消。Ctrl-C 丟出
`KeyboardInterrupt`，行為與 `input()` 一致。

### `pick_multi(options, title=None, *, footer=None)`

多選。`Space` 勾選目前列（並前進）、`a` 全選切換、`Enter` 確認、
`Esc`/`q` 取消。回傳依清單順序的選中索引（可能為空），取消回 `None`。

### `pick_dir(title=None, start=None, allow_create=False)`

檔案系統瀏覽。打字即過濾（不分大小寫）；輸入以 `/` 或 `~` 開頭就直接
跳到該路徑。`allow_create` 會多一個「在此新建子目錄」選項；目錄不會
真的建立，只回傳預定路徑，由呼叫端在套用時 mkdir。回傳選中路徑
（`str`），取消回 `None`。

## 行為細節

- 長清單在依終端機大小計算的視窗內捲動，邊界有 `↑`/`↓` 溢出標記；
  視窗以光棒所在列為中心生長，多行標籤也處理正確。

- POSIX 上整個選單期間持續持有 cbreak，快速連按不會把 `^[[A` 這類
  垃圾字元噴到畫面或漏給 shell；選單期間隱藏游標，結束一定復原。

- Windows 上用 `SetConsoleMode` 開 VT 處理；開不起來（古董 console）
  就自動走編號降級。

## 授權

MIT
