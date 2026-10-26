"""Shared desktop launcher with local Tk assets and visible failure reporting."""
import ctypes
import os
from pathlib import Path
import runpy
import sys
import traceback

BASE = Path(__file__).resolve().parent
os.chdir(BASE)
# Relative paths also work when the host redirects the Documents directory.
os.environ['TCL_LIBRARY'] = 'runtime/tcl/tcl8.6'
os.environ['TK_LIBRARY'] = 'runtime/tcl/tk8.6'
sys.path.insert(0, str(BASE))
target = sys.argv[1] if len(sys.argv) > 1 else 'anime_pet.py'
try:
    if target not in ('anime_pet.py', 'adventure_game.py'):
        raise ValueError('Unknown launch target')
    runpy.run_path(str(BASE / target), run_name='__main__')
except Exception:
    log = BASE / '启动错误.log'
    log.write_text(traceback.format_exc(), encoding='utf-8')
    ctypes.windll.user32.MessageBoxW(None,
        '启动遇到问题，详细信息已保存到：\n' + str(log), '桌面宠物启动失败', 0x10)
    raise SystemExit(1)
