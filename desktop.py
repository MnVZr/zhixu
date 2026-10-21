"""Windows tray lifecycle and one running instance per data directory."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse
from urllib.request import urlopen
import webbrowser

def brand_windows(url):
    """Apply our own icon and taskbar identity to the Edge app window."""
    if sys.platform != 'win32': return
    import ctypes as ct
    from ctypes import wintypes as wt
    user=ct.windll.user32
    user.SendMessageW.argtypes=[wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM]
    user.LoadImageW.argtypes=[wt.HINSTANCE,wt.LPCWSTR,wt.UINT,ct.c_int,ct.c_int,wt.UINT]
    user.LoadImageW.restype=wt.HANDLE
    assets=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'web'
    icon=user.LoadImageW(None,str(assets/'zhixu.ico'),1,0,0,0x10|0x40)
    if not icon: return
    class GUID(ct.Structure):
        _fields_=[('a',wt.DWORD),('b',wt.WORD),('c',wt.WORD),('d',ct.c_ubyte*8)]
    class Key(ct.Structure):
        _fields_=[('fmtid',GUID),('pid',wt.DWORD)]
    class Variant(ct.Structure):
        _fields_=[('vt',wt.WORD),('reserved',wt.WORD*3),('value',ct.c_void_p),('padding',ct.c_void_p)]
    def guid(text):
        g=GUID();ct.windll.ole32.CLSIDFromString(text,ct.byref(g));return g
    iid=guid('{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}')
    fmtid=guid('{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}')
    shell=ct.windll.shell32
    shell.SHGetPropertyStoreForWindow.argtypes=[wt.HWND,ct.POINTER(GUID),ct.POINTER(ct.c_void_p)]
    ct.windll.ole32.CoInitialize(None)
    def identity(hwnd):
        store=ct.c_void_p()
        if shell.SHGetPropertyStoreForWindow(hwnd,ct.byref(iid),ct.byref(store))<0:return
        table=ct.cast(store,ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        set_value=ct.WINFUNCTYPE(ct.c_long,ct.c_void_p,ct.POINTER(Key),ct.POINTER(Variant))(table[6])
        try:
            icon_resource=str(Path(sys.executable))+',0' if getattr(sys,'frozen',False) else str(assets/'zhixu.ico')
            command='"'+str(Path(sys.executable))+'"' if getattr(sys,'frozen',False) else '"'+sys.executable+'" "'+str(Path(__file__).parent/'app.py')+'"'
            for pid,text in [(5,'Zhixu.Desktop'),(2,command),(3,icon_resource),(4,'知序')]:
                value=ct.create_unicode_buffer(text);variant=Variant();variant.vt=31;variant.value=ct.cast(value,ct.c_void_p).value
                result=set_value(store,ct.byref(Key(fmtid,pid)),ct.byref(variant))
                if result<0: raise OSError('任务栏标识设置失败：'+hex(result & 0xffffffff))
            ct.WINFUNCTYPE(ct.c_long,ct.c_void_p)(table[7])(store)
        finally:ct.WINFUNCTYPE(wt.ULONG,ct.c_void_p)(table[2])(store)
    callback_type=ct.WINFUNCTYPE(wt.BOOL,wt.HWND,wt.LPARAM)
    seen=set()
    @callback_type
    def visit(hwnd,_):
        title=ct.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,512)
        if title.value.startswith('知序 1.4') and user.IsWindowVisible(hwnd):
            user.SendMessageW(hwnd,0x80,0,icon);user.SendMessageW(hwnd,0x80,1,icon)
            if hwnd not in seen:identity(hwnd);seen.add(hwnd)
        return True
    # Edge first creates the window and subsequently installs its favicon.
    try:
        for _ in range(60):user.EnumWindows(visit,0);time.sleep(.5)
    finally:ct.windll.ole32.CoUninitialize()

def launch_window(url):
    edge=next((p for p in [Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe'] if p.exists()),None)
    if edge:
        subprocess.Popen([str(edge),'--app='+url,'--new-window','--window-size=1200,800'])
        threading.Thread(target=brand_windows,args=(url,),daemon=True).start()
    else: webbrowser.open(url)

def instance_guard(data):
    data.mkdir(parents=True,exist_ok=True)
    handle=(data/'instance.lock').open('a+b')
    if handle.seek(0,2)==0: handle.write(b'0');handle.flush()
    handle.seek(0)
    if sys.platform!='win32': return handle
    import msvcrt
    try:
        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        return handle
    except OSError:
        handle.close()
        for _ in range(30):
            try:
                runtime=json.loads((data/'runtime.json').read_text(encoding='utf-8'))
                url=runtime['url']
                if urlparse(url).hostname!='127.0.0.1': raise ValueError('无效本机地址')
                with urlopen(url+'api/info',timeout=.5) as r: json.load(r)
                launch_window(url)
                return None
            except Exception: time.sleep(.1)
        raise RuntimeError('知序已在运行，请从系统托盘打开，或退出旧窗口后重试')

def start_tray(assets,url,stop_event):
    vendor=Path(__file__).parent/'work'/'vendor'
    if vendor.exists(): sys.path.insert(0,str(vendor))
    import pystray
    from pystray._util import win32
    from PIL import Image
    ready=threading.Event()
    def setup(icon):
        icon.visible=True
        ready.set()
    def exit_app(icon,item):
        stop_event.set()
    class LocalUserIcon(pystray.Icon):
        def _create_window(self,atom):
            # This app runs as the current user; no elevated-message filter is needed.
            return win32.CreateWindowEx(0,atom,None,win32.WS_POPUP,0,0,0,0,0,None,win32.GetModuleHandle(None),None)
    icon=LocalUserIcon('Zhixu',Image.open(assets/'zhixu.ico'),'知序 1.4 · 让生活更有序',pystray.Menu(
        pystray.MenuItem('打开知序',lambda icon,item:launch_window(url),default=True),
        pystray.MenuItem('退出知序（停止提醒和顺延）',exit_app)))
    # Child threads inherit daemon status, so a failed shell integration cannot
    # keep an otherwise stopped application alive.
    threading.Thread(target=lambda:icon.run_detached(setup),daemon=True).start()
    if not ready.wait(5):
        icon.stop()
        raise RuntimeError('系统托盘未就绪')
    return icon
