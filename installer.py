"""Optional per-user setup wizard for the portable application."""
from pathlib import Path
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from install_support import install_package

def main():
    if '--install-dir' in sys.argv:
        import argparse
        parser=argparse.ArgumentParser(description='Install Zhixu without opening the wizard')
        parser.add_argument('--install-dir',required=True);parser.add_argument('--no-shortcut',action='store_true');parser.add_argument('--no-launch',action='store_true')
        options=parser.parse_args()
        archive=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'Zhixu-1.5.0-Windows-x64.zip'
        executable=install_package(archive,Path(options.install_dir),not options.no_shortcut)
        if not options.no_launch:subprocess.Popen([str(executable)],creationflags=subprocess.CREATE_NO_WINDOW)
        return
    window=tk.Tk();window.title('安装知序 1.5');window.geometry('590x330');window.resizable(False,False)
    style=ttk.Style();style.theme_use('clam');style.configure('TFrame',background='#f5f8f7');style.configure('TLabel',background='#f5f8f7',font=('Microsoft YaHei',10));style.configure('TCheckbutton',background='#f5f8f7',font=('Microsoft YaHei',10))
    frame=ttk.Frame(window,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='知序 · 让生活更有序',font=('Microsoft YaHei',19,'bold')).pack(anchor='w')
    ttk.Label(frame,text='选择安装位置。更新只替换程序，保留个人数据。').pack(anchor='w',pady=(10,16))
    folder=tk.StringVar(value=str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'Programs'/'Zhixu'))
    row=ttk.Frame(frame);row.pack(fill='x');entry=ttk.Entry(row,textvariable=folder,width=55);entry.pack(side='left',fill='x',expand=True)
    def browse():
        result=filedialog.askdirectory(title='选择知序安装目录',initialdir=str(Path.home()))
        if result:folder.set(result)
    browse_button=ttk.Button(row,text='浏览…',command=browse);browse_button.pack(side='left',padx=(8,0))
    shortcut=tk.BooleanVar(value=True);launch=tk.BooleanVar(value=True)
    ttk.Checkbutton(frame,text='创建桌面快捷方式',variable=shortcut).pack(anchor='w',pady=(18,5))
    ttk.Checkbutton(frame,text='安装完成后打开知序',variable=launch).pack(anchor='w')
    status=ttk.Label(frame,text='无需管理员权限。已有数据位置会继续使用。');status.pack(anchor='w',pady=(15,10))
    busy=False
    def close():
        if not busy:window.destroy()
    window.protocol('WM_DELETE_WINDOW',close)
    def install():
        nonlocal busy
        target=folder.get().strip();make_shortcut=shortcut.get();open_app=launch.get()
        busy=True;install_button.config(state='disabled');browse_button.config(state='disabled');entry.config(state='disabled');status.config(text='正在安装，请稍候…')
        def work():
            try:
                archive=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'Zhixu-1.5.0-Windows-x64.zip'
                executable=install_package(archive,Path(target),make_shortcut)
                def done():
                    nonlocal busy
                    busy=False
                    if open_app:subprocess.Popen([str(executable)],creationflags=subprocess.CREATE_NO_WINDOW)
                    messagebox.showinfo('安装完成','知序已安装。'+('桌面快捷方式已创建。' if make_shortcut else ''),parent=window);window.destroy()
                window.after(0,done)
            except Exception as error:
                detail=str(error)
                def failed():
                    nonlocal busy
                    busy=False;install_button.config(state='normal');browse_button.config(state='normal');entry.config(state='normal');status.config(text='安装未完成，请重试。')
                    messagebox.showerror('安装未完成',detail+'\n如旧版正在运行，请退出知序与后台后重试。',parent=window)
                window.after(0,failed)
        threading.Thread(target=work,daemon=True).start()
    install_button=ttk.Button(frame,text='安装',command=install);install_button.pack(anchor='e')
    window.mainloop()
if __name__=='__main__':main()
