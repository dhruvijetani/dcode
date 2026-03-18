"""
D Code - AI-Powered Code Editor v2.0
======================================
Install:  pip install anthropic pygments
Run:      python3 dcode.py

New in v2.0:
  - Live Word Count & Code Stats panel
  - Code complexity indicator
  - Real-time function/class counter
  - Line breakdown chart
  - AI Code Review via stats
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import threading, os, sys, re, subprocess, time
from pathlib import Path
from collections import Counter

try:
    import anthropic
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

try:
    from pygments import lex
    from pygments.lexers import PythonLexer
    from pygments.token import Token
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False

try:
    import speech_recognition as sr
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

T = {
    "bg":"#0d0f14","panel":"#13151c","sidebar":"#0a0c10",
    "tab_on":"#1a1d27","tab_off":"#0f1117","border":"#1e2130",
    "accent":"#7c6af7","accent2":"#3ecfcf","accent3":"#f7736a",
    "accent4":"#ffd166","text":"#dde1f0","text_dim":"#5a607a",
    "text_hi":"#ffffff","cur_line":"#161926","select":"#2a2f4a",
    "gutter":"#0f1117","ln_color":"#2e3347","green":"#06d6a0",
    "red":"#f7736a","yellow":"#ffd166",
    "kw":"#c792ea","bi":"#82aaff","st":"#c3e88d","cm":"#546e7a",
    "nu":"#f78c6c","fn":"#82aaff","cl":"#ffcb6b","op":"#89ddff","dc":"#f78c6c",
}

if sys.platform == "win32":
    FN_MONO=("Consolas",13); FN_UI=("Segoe UI",10)
    FN_SM=("Segoe UI",9);    FN_XS=("Segoe UI",8)
else:
    FN_MONO=("Monospace",13); FN_UI=("Sans",10)
    FN_SM=("Sans",9);         FN_XS=("Sans",8)

def count_stats(code):
    lines=code.split("\n"); tl=len(lines)
    bl=sum(1 for l in lines if l.strip()=="")
    cl=sum(1 for l in lines if l.strip().startswith("#"))
    words=len(re.findall(r'\b\w+\b',code))
    funcs=len(re.findall(r'^\s*def\s+\w+',code,re.MULTILINE))
    classes=len(re.findall(r'^\s*class\s+\w+',code,re.MULTILINE))
    imports=len(re.findall(r'^(?:import|from)\s+',code,re.MULTILINE))
    branches=len(re.findall(r'\b(if|elif|else|for|while|try|except|with)\b',code))
    if branches<=5: cx=("Low",T["green"])
    elif branches<=15: cx=("Medium",T["yellow"])
    else: cx=("High",T["red"])
    SKIP={"self","def","class","import","from","return","if","else","for","while",
          "in","not","and","or","is","True","False","None","pass","try","except",
          "with","as","the","a","an"}
    wl=[w.lower() for w in re.findall(r'\b[a-zA-Z_]\w+\b',code)
        if w.lower() not in SKIP and len(w)>2]
    top=Counter(wl).most_common(5)
    ids=set(re.findall(r'\b[a-zA-Z_]\w+\b',code))
    return {"total_lines":tl,"code_lines":tl-bl-cl,"blank_lines":bl,
            "comment_lines":cl,"words":words,"chars":len(code),
            "chars_nsp":len(code.replace(" ","").replace("\n","")),
            "functions":funcs,"classes":classes,"imports":imports,
            "branches":branches,"complexity":cx,"top_words":top,
            "identifiers":len(ids)}

class DCode(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("D Code  v2.0"); self.geometry("1350x860")
        self.minsize(800,500); self.configure(bg=T["bg"])
        self.files={}; self.active=None
        self.ai_client=anthropic.Anthropic() if AI_AVAILABLE else None
        self.ai_visible=False; self.stats_visible=False
        self.xray_on=False; self.listening=False
        self.hint_win=None; self._hint_job=None; self._stats_job=None
        self._ui(); self._keys(); self._new_file()
        self.after(400,lambda:self.status_l.config(
            text="✓ D Code v2.0  |  F5=Run  |  Ctrl+Space=AI  |  F2=Stats"))

    def _ui(self):
        self._titlebar(); self._body(); self._statusbar()

    def _titlebar(self):
        bar=tk.Frame(self,bg=T["sidebar"],height=44)
        bar.pack(fill="x"); bar.pack_propagate(False)
        tk.Label(bar,text="⬡  D Code",bg=T["sidebar"],fg=T["accent"],
                 font=(FN_MONO[0],13,"bold"),padx=16).pack(side="left")
        for lbl,fn in [("File",self._menu_file),("Edit",self._menu_edit),("View",self._menu_view)]:
            w=tk.Label(bar,text=lbl,bg=T["sidebar"],fg=T["text_dim"],
                       font=FN_UI,padx=12,pady=12,cursor="hand2")
            w.pack(side="left")
            w.bind("<Button-1>",lambda e,f=fn:f())
            w.bind("<Enter>",lambda e,b=w:b.config(fg=T["text"]))
            w.bind("<Leave>",lambda e,b=w:b.config(fg=T["text_dim"]))
        right=tk.Frame(bar,bg=T["sidebar"]); right.pack(side="right",padx=8)
        self._tbtn(right,"▶  Run",self._run,T["accent2"])
        self._tbtn(right,"📊 Stats",self._toggle_stats,T["accent4"])
        self._tbtn(right,"🤖 AI",self._toggle_ai,T["accent"])
        if VOICE_AVAILABLE:
            self._tbtn(right,"🎙 Voice",self._toggle_voice,T["accent3"])

    def _tbtn(self,p,text,cmd,fg):
        b=tk.Label(p,text=text,bg=T["panel"],fg=fg,font=FN_SM,padx=10,pady=5,cursor="hand2")
        b.pack(side="right",padx=3)
        b.bind("<Button-1>",lambda e:cmd())
        b.bind("<Enter>",lambda e,x=b:x.config(bg=T["tab_on"]))
        b.bind("<Leave>",lambda e,x=b:x.config(bg=T["panel"]))
        return b

    def _body(self):
        self.pane=tk.PanedWindow(self,orient="horizontal",bg=T["border"],sashwidth=2)
        self.pane.pack(fill="both",expand=True)
        self._sidebar(); self._editor_area()
        self.ai_frame=tk.Frame(self.pane,bg=T["panel"],width=320)
        self.stats_frame=tk.Frame(self.pane,bg=T["panel"],width=280)

    def _sidebar(self):
        sb=tk.Frame(self.pane,bg=T["sidebar"],width=200)
        self.pane.add(sb,minsize=130)
        tk.Label(sb,text="EXPLORER",bg=T["sidebar"],fg=T["text_dim"],
                 font=FN_SM,anchor="w",padx=14,pady=8).pack(fill="x")
        bf=tk.Frame(sb,bg=T["sidebar"]); bf.pack(fill="x",padx=6,pady=2)
        for txt,fn in [("+ New",self._new_file),("📂 Open",self._open_file)]:
            b=tk.Label(bf,text=txt,bg=T["panel"],fg=T["text"],font=FN_SM,padx=8,pady=4,cursor="hand2")
            b.pack(side="left",padx=2); b.bind("<Button-1>",lambda e,f=fn:f())
        self.flist=tk.Listbox(sb,bg=T["sidebar"],fg=T["text"],font=FN_SM,
                               relief="flat",bd=0,highlightthickness=0,
                               selectbackground=T["select"],activestyle="none")
        self.flist.pack(fill="both",expand=True,padx=4,pady=4)
        self.flist.bind("<Double-Button-1>",self._sidebar_open)
        self.xray_btn=tk.Label(sb,text="☢  X-Ray Mode",bg=T["sidebar"],
                                fg=T["text_dim"],font=FN_SM,anchor="w",padx=14,pady=6,cursor="hand2")
        self.xray_btn.pack(fill="x",side="bottom")
        self.xray_btn.bind("<Button-1>",lambda e:self._toggle_xray())

    def _editor_area(self):
        ea=tk.Frame(self.pane,bg=T["bg"]); self.pane.add(ea,minsize=400)
        self.tabbar=tk.Frame(ea,bg=T["sidebar"],height=36)
        self.tabbar.pack(fill="x"); self.tabbar.pack_propagate(False)
        self.ed_frame=tk.Frame(ea,bg=T["bg"]); self.ed_frame.pack(fill="both",expand=True)

    def _statusbar(self):
        bar=tk.Frame(self,bg=T["sidebar"],height=24)
        bar.pack(fill="x",side="bottom"); bar.pack_propagate(False)
        self.status_l=tk.Label(bar,text="Ready",bg=T["sidebar"],fg=T["text_dim"],font=FN_SM,padx=10)
        self.status_l.pack(side="left")
        self.ai_status=tk.Label(bar,text="",bg=T["sidebar"],fg=T["accent"],font=FN_SM,padx=8)
        self.ai_status.pack(side="right")
        self.mini_stats=tk.Label(bar,text="",bg=T["sidebar"],fg=T["accent2"],font=FN_SM,padx=10)
        self.mini_stats.pack(side="right")
        self.status_r=tk.Label(bar,text="Python | UTF-8 | Ln 1 Col 1",
                                bg=T["sidebar"],fg=T["text_dim"],font=FN_SM,padx=10)
        self.status_r.pack(side="right")

    def _make_editor(self,path,content=""):
        frame=tk.Frame(self.ed_frame,bg=T["bg"])
        gutter=tk.Text(frame,width=4,bg=T["gutter"],fg=T["ln_color"],font=FN_MONO,
                       state="disabled",relief="flat",bd=0,highlightthickness=0,
                       padx=6,selectbackground=T["gutter"])
        gutter.pack(side="left",fill="y")
        tf=tk.Frame(frame,bg=T["bg"]); tf.pack(side="left",fill="both",expand=True)
        sy=tk.Scrollbar(tf,orient="vertical",bg=T["panel"],troughcolor=T["bg"],
                        activebackground=T["accent"],relief="flat",bd=0,width=8)
        sy.pack(side="right",fill="y")
        sx=tk.Scrollbar(frame,orient="horizontal",bg=T["panel"],troughcolor=T["bg"],
                        activebackground=T["accent"],relief="flat",bd=0)
        sx.pack(side="bottom",fill="x")
        txt=tk.Text(tf,bg=T["bg"],fg=T["text"],font=FN_MONO,insertbackground=T["accent"],
                    relief="flat",bd=0,padx=14,pady=10,selectbackground=T["select"],
                    highlightthickness=0,wrap="none",undo=True,maxundo=300,
                    yscrollcommand=sy.set,xscrollcommand=sx.set)
        txt.pack(fill="both",expand=True)
        sy.config(command=txt.yview); sx.config(command=txt.xview)
        txt.insert("1.0",content)
        self._setup_tags(txt)
        ed={"frame":frame,"text":txt,"gutter":gutter,"path":path,"saved":True}
        txt.bind("<KeyRelease>",lambda e,d=ed:self._on_key(e,d))
        txt.bind("<ButtonRelease>",lambda e,d=ed:self._update_pos(d))
        txt.bind("<Tab>",self._handle_tab)
        txt.bind("<Return>",lambda e,d=ed:self._smart_newline(e,d))
        txt.bind("<Control-space>",lambda e,d=ed:self._ai_complete(e,d))
        txt.bind("<Control-slash>",lambda e,d=ed:self._comment(e,d))
        self.after(60,lambda:self._highlight(ed))
        self.after(100,lambda:self._update_gutter(ed))
        return ed

    def _setup_tags(self,txt):
        for tag,fg in [("kw",T["kw"]),("bi",T["bi"]),("st",T["st"]),
                       ("nu",T["nu"]),("fn",T["fn"]),("cl",T["cl"]),
                       ("op",T["op"]),("dc",T["dc"])]:
            txt.tag_configure(tag,foreground=fg)
        txt.tag_configure("cm",foreground=T["cm"],font=(FN_MONO[0],FN_MONO[1],"italic"))
        txt.tag_configure("hl",background=T["cur_line"])
        txt.tag_configure("found",background=T["accent"],foreground=T["bg"])
        txt.tag_configure("ghost",foreground=T["accent2"])
        txt.tag_configure("xdim",foreground=T["text_dim"])
        txt.tag_configure("xhi",foreground=T["text_hi"],font=(FN_MONO[0],FN_MONO[1],"bold"))

    def _add_tab(self,path,ed):
        name=os.path.basename(path) or "untitled"
        tf=tk.Frame(self.tabbar,bg=T["tab_off"],padx=1); tf.pack(side="left",fill="y")
        lbl=tk.Label(tf,text=f"  {name}  ",bg=T["tab_off"],fg=T["text_dim"],font=FN_SM,pady=10,cursor="hand2")
        lbl.pack(side="left")
        cls=tk.Label(tf,text="×",bg=T["tab_off"],fg=T["text_dim"],font=FN_UI,pady=10,padx=4,cursor="hand2")
        cls.pack(side="left")
        ed["tab"]=tf; ed["tab_lbl"]=lbl; ed["tab_cls"]=cls
        for w in (tf,lbl,cls): w.bind("<Button-1>",lambda e,p=path:self._switch(p))
        cls.bind("<Button-1>",lambda e,p=path:self._close(p))
        for w in (tf,lbl,cls):
            w.bind("<Enter>",lambda e,f=tf,c=cls:[f.config(bg=T["tab_on"]),c.config(bg=T["tab_on"])])
            w.bind("<Leave>",lambda e,f=tf,c=cls,p=path:self._tab_leave(f,c,p))

    def _tab_leave(self,tf,cls,path):
        bg=T["tab_on"] if self.active==path else T["tab_off"]
        tf.config(bg=bg); cls.config(bg=bg)

    def _switch(self,path):
        if self.active and self.active in self.files:
            old=self.files[self.active]
            old["frame"].pack_forget()
            old["tab"].config(bg=T["tab_off"])
            old["tab_lbl"].config(bg=T["tab_off"],fg=T["text_dim"])
            old["tab_cls"].config(bg=T["tab_off"])
        self.active=path; ed=self.files[path]
        ed["frame"].pack(fill="both",expand=True)
        ed["tab"].config(bg=T["tab_on"])
        ed["tab_lbl"].config(bg=T["tab_on"],fg=T["text_hi"])
        ed["tab_cls"].config(bg=T["tab_on"])
        ed["text"].focus_set(); self._update_pos(ed); self._refresh_mini_stats(ed)

    def _set_tab_title(self,ed,saved=True):
        name=os.path.basename(ed["path"]) or "untitled"
        ed["tab_lbl"].config(text=f"  {'  ' if saved else '● '}{name}  ")

    def _new_file(self):
        n=sum(1 for p in self.files if "untitled" in p)
        path=f"untitled-{n+1}.py"
        ed=self._make_editor(path,"# Welcome to D Code v2.0\n\n")
        self.files[path]=ed; self._add_tab(path,ed); self._switch(path)

    def _open_file(self,path=None):
        if not path:
            path=filedialog.askopenfilename(filetypes=[("Python","*.py"),("All Files","*.*")])
        if not path: return
        if path in self.files: self._switch(path); return
        try: content=Path(path).read_text(encoding="utf-8",errors="replace")
        except Exception as ex: messagebox.showerror("Error",str(ex)); return
        ed=self._make_editor(path,content); self.files[path]=ed
        self._add_tab(path,ed); self._switch(path); self._refresh_flist()

    def _save(self,save_as=False):
        if not self.active: return
        path=self.active
        if save_as or "untitled" in path:
            path=filedialog.asksaveasfilename(defaultextension=".py",
                filetypes=[("Python","*.py"),("All Files","*.*")])
            if not path: return
        ed=self.files[self.active]
        try: Path(path).write_text(ed["text"].get("1.0","end-1c"),encoding="utf-8")
        except Exception as ex: messagebox.showerror("Error",str(ex)); return
        if path!=self.active:
            self.files[path]=self.files.pop(self.active); self.active=path; ed["path"]=path
        ed["saved"]=True; self._set_tab_title(ed,saved=True)
        self.status_l.config(text=f"Saved → {os.path.basename(path)}"); self._refresh_flist()

    def _close(self,path):
        if path not in self.files: return
        ed=self.files[path]
        if not ed["saved"]:
            ans=messagebox.askyesnocancel("Unsaved",f"Save {os.path.basename(path)}?")
            if ans is None: return
            if ans: self._save()
        ed["tab"].destroy(); ed["frame"].destroy(); del self.files[path]
        if self.active==path:
            self.active=None; rem=list(self.files.keys())
            if rem: self._switch(rem[-1])

    def _sidebar_open(self,e):
        sel=self.flist.curselection()
        if sel: self._open_file(self.flist.get(sel[0]))

    def _refresh_flist(self):
        self.flist.delete(0,"end")
        for p in self.files: self.flist.insert("end",p)

    def _run(self):
        if not self.active: return
        ed=self.files[self.active]; code=ed["text"].get("1.0","end-1c")
        path=self.active
        if "untitled" in path:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".py",mode="w",delete=False,encoding="utf-8") as f:
                f.write(code); path=f.name
        self._ensure_output()
        self.out_txt.config(state="normal"); self.out_txt.delete("1.0","end")
        self.out_txt.insert("end",f"▶  Running {os.path.basename(path)}…\n\n","info")
        start=time.time()
        def go():
            try:
                r=subprocess.run([sys.executable,path],capture_output=True,text=True,timeout=30)
                el=round(time.time()-start,2)
                self.after(0,lambda:self._show_output(r.stdout,r.stderr,el))
            except subprocess.TimeoutExpired:
                self.after(0,lambda:self._show_output("","⏱ Timed out (30s)\n",30))
            except Exception as ex:
                self.after(0,lambda:self._show_output("",str(ex),0))
        threading.Thread(target=go,daemon=True).start()

    def _ensure_output(self):
        if hasattr(self,"out_panel") and self.out_panel.winfo_exists(): return
        self.out_panel=tk.Frame(self.ed_frame,bg=T["panel"],height=190)
        self.out_panel.pack(fill="x",side="bottom"); self.out_panel.pack_propagate(False)
        hdr=tk.Frame(self.out_panel,bg=T["sidebar"]); hdr.pack(fill="x")
        tk.Label(hdr,text=" OUTPUT",bg=T["sidebar"],fg=T["text_dim"],font=FN_SM,padx=8,pady=4).pack(side="left")
        self.run_time_lbl=tk.Label(hdr,text="",bg=T["sidebar"],fg=T["accent2"],font=FN_SM,padx=8)
        self.run_time_lbl.pack(side="left")
        cx=tk.Label(hdr,text="✕",bg=T["sidebar"],fg=T["text_dim"],font=FN_SM,padx=8,cursor="hand2")
        cx.pack(side="right"); cx.bind("<Button-1>",lambda e:self.out_panel.destroy())
        self.out_txt=tk.Text(self.out_panel,bg=T["panel"],fg=T["text"],font=(FN_MONO[0],11),
                              relief="flat",bd=0,padx=10,highlightthickness=0)
        self.out_txt.pack(fill="both",expand=True)
        self.out_txt.tag_configure("info",foreground=T["accent2"])
        self.out_txt.tag_configure("err",foreground=T["accent3"])

    def _show_output(self,out,err,elapsed):
        self.out_txt.config(state="normal")
        if out: self.out_txt.insert("end",out)
        if err: self.out_txt.insert("end",err,"err")
        if not out and not err: self.out_txt.insert("end","✓ Done — no output.\n","info")
        if hasattr(self,"run_time_lbl"): self.run_time_lbl.config(text=f"  ⏱ {elapsed}s")
        self.out_txt.see("end")

    # ── STATS PANEL ────────────────────────────────────────────────────────────
    def _toggle_stats(self):
        if self.stats_visible:
            self.pane.forget(self.stats_frame); self.stats_visible=False
        else:
            self._build_stats_panel(); self.pane.add(self.stats_frame,minsize=240)
            self.stats_visible=True
            if self.active: self._refresh_stats(self.files[self.active])

    def _build_stats_panel(self):
        for w in self.stats_frame.winfo_children(): w.destroy()
        hdr=tk.Frame(self.stats_frame,bg=T["sidebar"]); hdr.pack(fill="x")
        tk.Label(hdr,text="📊  Code Stats",bg=T["sidebar"],fg=T["accent4"],
                 font=FN_SM,padx=12,pady=8).pack(side="left")
        canvas=tk.Canvas(self.stats_frame,bg=T["panel"],highlightthickness=0)
        sb=tk.Scrollbar(self.stats_frame,orient="vertical",command=canvas.yview,
                        bg=T["panel"],troughcolor=T["bg"],relief="flat",bd=0,width=6)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); canvas.pack(fill="both",expand=True)
        self.stats_inner=tk.Frame(canvas,bg=T["panel"])
        self.stats_win_id=canvas.create_window((0,0),window=self.stats_inner,anchor="nw")
        canvas.bind("<Configure>",lambda e:canvas.itemconfig(self.stats_win_id,width=e.width))
        self.stats_inner.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))

    def _srow(self,par,lbl,val,color=None,big=False):
        row=tk.Frame(par,bg=T["panel"]); row.pack(fill="x",padx=12,pady=2)
        tk.Label(row,text=lbl,bg=T["panel"],fg=T["text_dim"],font=FN_XS,anchor="w").pack(side="left")
        fnt=(FN_SM[0],FN_SM[1]+1,"bold") if big else FN_SM
        tk.Label(row,text=str(val),bg=T["panel"],fg=color or T["text"],font=fnt,anchor="e").pack(side="right")

    def _sbar(self,par,lbl,val,mx,color):
        row=tk.Frame(par,bg=T["panel"]); row.pack(fill="x",padx=12,pady=3)
        tk.Label(row,text=lbl,bg=T["panel"],fg=T["text_dim"],font=FN_XS,width=14,anchor="w").pack(side="left")
        bf=tk.Frame(row,bg=T["bg"],height=10,width=100); bf.pack(side="left",padx=4); bf.pack_propagate(False)
        pct=min(val/max(mx,1),1.0)
        tk.Frame(bf,bg=color,width=int(100*pct),height=10).pack(side="left")
        tk.Label(row,text=str(val),bg=T["panel"],fg=T["text"],font=FN_XS).pack(side="left",padx=4)

    def _div(self,par,title=""):
        tk.Frame(par,bg=T["border"],height=1).pack(fill="x",padx=8,pady=6)
        if title:
            tk.Label(par,text=title,bg=T["panel"],fg=T["accent"],
                     font=(FN_SM[0],FN_SM[1],"bold"),anchor="w",padx=12).pack(fill="x")

    def _refresh_stats(self,ed):
        if not self.stats_visible: return
        if not hasattr(self,"stats_inner"): return
        for w in self.stats_inner.winfo_children(): w.destroy()
        code=ed["text"].get("1.0","end-1c"); s=count_stats(code)

        tk.Label(self.stats_inner,text="OVERVIEW",bg=T["panel"],fg=T["text_dim"],
                 font=FN_XS,anchor="w",padx=12,pady=6).pack(fill="x")
        self._srow(self.stats_inner,"Total Lines",s["total_lines"],T["accent2"],big=True)
        self._srow(self.stats_inner,"Code Lines",s["code_lines"],T["text"])
        self._srow(self.stats_inner,"Blank Lines",s["blank_lines"],T["text_dim"])
        self._srow(self.stats_inner,"Comment Lines",s["comment_lines"],T["cm"])

        self._div(self.stats_inner,"WORDS & CHARS")
        self._srow(self.stats_inner,"Word Count",s["words"],T["accent"],big=True)
        self._srow(self.stats_inner,"Characters",s["chars"],T["text"])
        self._srow(self.stats_inner,"Chars (no space)",s["chars_nsp"],T["text_dim"])

        self._div(self.stats_inner,"STRUCTURE")
        self._srow(self.stats_inner,"Functions",s["functions"],T["fn"],big=True)
        self._srow(self.stats_inner,"Classes",s["classes"],T["cl"])
        self._srow(self.stats_inner,"Imports",s["imports"],T["kw"])
        self._srow(self.stats_inner,"Identifiers",s["identifiers"],T["text_dim"])

        self._div(self.stats_inner,"COMPLEXITY")
        self._srow(self.stats_inner,"Branches",s["branches"],T["text"])
        cn,cc=s["complexity"]
        self._srow(self.stats_inner,"Level",cn,cc,big=True)
        bf=tk.Frame(self.stats_inner,bg=T["panel"]); bf.pack(fill="x",padx=12,pady=4)
        tr=tk.Frame(bf,bg=T["bg"],height=14); tr.pack(fill="x"); tr.pack_propagate(False)
        pct=min(s["branches"]/30.0,1.0)
        tk.Frame(tr,bg=cc,width=int(230*pct),height=14).pack(side="left")

        if s["top_words"]:
            self._div(self.stats_inner,"TOP IDENTIFIERS")
            mx=s["top_words"][0][1] if s["top_words"] else 1
            cols=[T["accent"],T["accent2"],T["accent3"],T["accent4"],T["green"]]
            for i,(word,count) in enumerate(s["top_words"]):
                self._sbar(self.stats_inner,word,count,mx,cols[i%len(cols)])

        self._div(self.stats_inner,"LINE BREAKDOWN")
        total=max(s["total_lines"],1)
        segs=[("Code",s["code_lines"],T["accent2"]),
              ("Comments",s["comment_lines"],T["cm"]),
              ("Blank",s["blank_lines"],T["text_dim"])]
        br=tk.Frame(self.stats_inner,bg=T["panel"]); br.pack(fill="x",padx=12,pady=6)
        ch=tk.Frame(br,bg=T["bg"],height=18); ch.pack(fill="x")
        for _,val,color in segs:
            w=int(230*val/total)
            if w>0: tk.Frame(ch,bg=color,width=w,height=18).pack(side="left")
        leg=tk.Frame(self.stats_inner,bg=T["panel"]); leg.pack(fill="x",padx=12,pady=2)
        for lbl,val,color in segs:
            pv=round(val/total*100)
            tk.Label(leg,text="■",bg=T["panel"],fg=color,font=FN_XS).pack(side="left")
            tk.Label(leg,text=f"{lbl} {pv}%  ",bg=T["panel"],fg=T["text_dim"],font=FN_XS).pack(side="left")

        self._div(self.stats_inner)
        tk.Label(self.stats_inner,text=f"Updated {time.strftime('%H:%M:%S')}",
                 bg=T["panel"],fg=T["text_dim"],font=FN_XS,anchor="e",padx=12,pady=4).pack(fill="x")

    def _refresh_mini_stats(self,ed):
        try:
            code=ed["text"].get("1.0","end-1c")
            words=len(re.findall(r'\b\w+\b',code))
            lines=code.count("\n")+1
            funcs=len(re.findall(r'^\s*def\s+\w+',code,re.MULTILINE))
            self.mini_stats.config(text=f"W:{words}  L:{lines}  ƒ:{funcs}")
        except Exception: pass

    def _highlight(self,ed):
        txt=ed["text"]; code=txt.get("1.0","end-1c")
        for tag in ("kw","bi","st","cm","nu","fn","cl","op","dc"):
            txt.tag_remove(tag,"1.0","end")
        if PYGMENTS_AVAILABLE:
            tag_map={Token.Keyword:"kw",Token.Keyword.Namespace:"kw",
                     Token.Name.Builtin:"bi",Token.Name.Function:"fn",
                     Token.Name.Class:"cl",Token.Name.Decorator:"dc",
                     Token.Literal.String:"st",Token.Literal.String.Double:"st",
                     Token.Literal.String.Single:"st",Token.Literal.String.Doc:"cm",
                     Token.Comment:"cm",Token.Comment.Single:"cm",
                     Token.Literal.Number:"nu",Token.Literal.Number.Integer:"nu",
                     Token.Literal.Number.Float:"nu",Token.Operator:"op",Token.Punctuation:"op"}
            try:
                pos=0
                for ttype,val in lex(code,PythonLexer()):
                    tag=tag_map.get(ttype)
                    if tag: txt.tag_add(tag,f"1.0+{pos}c",f"1.0+{pos+len(val)}c")
                    pos+=len(val)
            except Exception: pass
        else:
            for tag,pat in [
                ("kw",r"\b(def|class|import|from|return|if|elif|else|for|while|try|except|finally|with|as|pass|break|continue|lambda|yield|raise|in|not|and|or|is|del|global|nonlocal|assert|async|await|True|False|None)\b"),
                ("bi",r"\b(print|len|range|type|int|float|str|list|dict|set|tuple|open|input|enumerate|zip|map|filter|super|self)\b"),
                ("cm",r"#[^\n]*"),("st",r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"]*"|\'[^\']*\')'),
                ("nu",r"\b\d+(\.\d+)?\b"),("dc",r"@\w+")]:
                for m in re.finditer(pat,code,re.MULTILINE):
                    txt.tag_add(tag,f"1.0+{m.start()}c",f"1.0+{m.end()}c")
        txt.tag_remove("hl","1.0","end")
        try:
            ln=txt.index("insert").split(".")[0]; txt.tag_add("hl",f"{ln}.0",f"{ln}.end+1c")
        except Exception: pass

    def _update_gutter(self,ed):
        txt=ed["text"]; g=ed["gutter"]
        lines=int(txt.index("end-1c").split(".")[0])
        g.config(state="normal"); g.delete("1.0","end")
        g.insert("1.0","\n".join(str(i) for i in range(1,lines+1)))
        g.config(state="disabled")
        try: g.yview_moveto(txt.yview()[0])
        except Exception: pass

    def _on_key(self,e,ed):
        ed["saved"]=False; self._set_tab_title(ed,saved=False)
        self._highlight(ed); self._update_gutter(ed)
        self._update_pos(ed); self._refresh_mini_stats(ed)
        if self._stats_job: self.after_cancel(self._stats_job)
        self._stats_job=self.after(600,lambda:self._refresh_stats(ed))
        if self._hint_job: self.after_cancel(self._hint_job)
        self._hint_job=self.after(1200,lambda:self._auto_hint(ed))

    def _handle_tab(self,e):
        w=e.widget
        if w.tag_ranges("sel"):
            s=int(w.index("sel.first").split(".")[0])
            n=int(w.index("sel.last").split(".")[0])
            for ln in range(s,n+1): w.insert(f"{ln}.0","    ")
        else: w.insert("insert","    ")
        return "break"

    def _smart_newline(self,e,ed):
        txt=ed["text"]; ln=txt.index("insert").split(".")[0]
        line=txt.get(f"{ln}.0",f"{ln}.end")
        indent=len(line)-len(line.lstrip())
        extra=4 if line.rstrip().endswith(":") else 0
        txt.insert("insert","\n"+" "*(indent+extra))
        self._update_gutter(ed); return "break"

    def _comment(self,e,ed):
        txt=ed["text"]
        try: s=int(txt.index("sel.first").split(".")[0]); n=int(txt.index("sel.last").split(".")[0])
        except tk.TclError: s=n=int(txt.index("insert").split(".")[0])
        for ln in range(s,n+1):
            line=txt.get(f"{ln}.0",f"{ln}.end")
            new=re.sub(r"^(\s*)# ?",r"\1",line) if re.match(r"^\s*#",line) else re.sub(r"^(\s*)",r"\1# ",line)
            txt.delete(f"{ln}.0",f"{ln}.end"); txt.insert(f"{ln}.0",new)
        return "break"

    def _update_pos(self,ed):
        try:
            idx=ed["text"].index("insert"); ln,col=idx.split(".")
            self.status_r.config(text=f"Python | UTF-8 | Ln {ln} Col {int(col)+1}")
        except Exception: pass

    def _keys(self):
        self.bind_all("<Control-s>",lambda e:self._save())
        self.bind_all("<Control-S>",lambda e:self._save(True))
        self.bind_all("<Control-n>",lambda e:self._new_file())
        self.bind_all("<Control-o>",lambda e:self._open_file())
        self.bind_all("<Control-w>",lambda e:self.active and self._close(self.active))
        self.bind_all("<F5>",lambda e:self._run())
        self.bind_all("<F2>",lambda e:self._toggle_stats())
        self.bind_all("<Control-f>",lambda e:self._find())
        self.bind_all("<Control-equal>",lambda e:self._zoom(1))
        self.bind_all("<Control-minus>",lambda e:self._zoom(-1))

    def _toggle_ai(self):
        if self.ai_visible: self.pane.forget(self.ai_frame); self.ai_visible=False
        else: self._build_ai_panel(); self.pane.add(self.ai_frame,minsize=270); self.ai_visible=True

    def _build_ai_panel(self):
        for w in self.ai_frame.winfo_children(): w.destroy()
        hdr=tk.Frame(self.ai_frame,bg=T["sidebar"]); hdr.pack(fill="x")
        tk.Label(hdr,text="🤖  AI Assistant",bg=T["sidebar"],fg=T["accent"],
                 font=FN_SM,padx=12,pady=8).pack(side="left")
        self.ai_chat=tk.Text(self.ai_frame,bg=T["bg"],fg=T["text"],font=FN_SM,
                              relief="flat",bd=0,padx=10,pady=8,wrap="word",
                              highlightthickness=0,state="disabled")
        self.ai_chat.pack(fill="both",expand=True,padx=6,pady=6)
        self.ai_chat.tag_configure("u",foreground=T["accent2"])
        self.ai_chat.tag_configure("a",foreground=T["text"])
        self.ai_chat.tag_configure("d",foreground=T["text_dim"])
        actions=tk.Frame(self.ai_frame,bg=T["panel"]); actions.pack(fill="x",padx=6)
        for lbl,fn in [("✨ Explain",self._ai_explain),("🐛 Fix Bugs",self._ai_fix),
                       ("📝 Docstrings",self._ai_docs),("🔄 Refactor",self._ai_refactor),
                       ("📊 AI Review",self._ai_review)]:
            b=tk.Label(actions,text=lbl,bg=T["tab_off"],fg=T["text"],font=FN_SM,padx=8,pady=5,cursor="hand2")
            b.pack(fill="x",pady=2)
            b.bind("<Button-1>",lambda e,f=fn:f())
            b.bind("<Enter>",lambda e,x=b:x.config(bg=T["tab_on"]))
            b.bind("<Leave>",lambda e,x=b:x.config(bg=T["tab_off"]))
        inp_f=tk.Frame(self.ai_frame,bg=T["panel"]); inp_f.pack(fill="x",padx=6,pady=8)
        self.ai_inp=tk.Entry(inp_f,bg=T["bg"],fg=T["text"],font=FN_SM,relief="flat",bd=4,
                              insertbackground=T["accent"],highlightthickness=1,highlightcolor=T["accent"])
        self.ai_inp.pack(side="left",fill="x",expand=True)
        self.ai_inp.insert(0,"Ask anything…")
        self.ai_inp.bind("<FocusIn>",lambda e:self.ai_inp.delete(0,"end") if self.ai_inp.get()=="Ask anything…" else None)
        self.ai_inp.bind("<Return>",lambda e:self._ai_ask())
        sb=tk.Label(inp_f,text="→",bg=T["accent"],fg=T["text_hi"],font=FN_UI,padx=10,pady=4,cursor="hand2")
        sb.pack(side="right",padx=(4,0)); sb.bind("<Button-1>",lambda e:self._ai_ask())
        if not AI_AVAILABLE:
            self._ai_log("⚠ anthropic not found.\nRun: pip install anthropic\nSet: ANTHROPIC_API_KEY\n","d")

    def _ai_log(self,msg,tag="a"):
        self.ai_chat.config(state="normal"); self.ai_chat.insert("end",msg+"\n",tag)
        self.ai_chat.see("end"); self.ai_chat.config(state="disabled")

    def _code(self):
        return self.files[self.active]["text"].get("1.0","end-1c") if self.active else ""

    def _ai_call(self,prompt,label="AI"):
        if not AI_AVAILABLE: self._ai_log("⚠ AI not available.","d"); return
        self.ai_status.config(text="⟳ Thinking…"); self._ai_log(f"You: {label}","u")
        def go():
            try:
                r=self.ai_client.messages.create(model="claude-sonnet-4-20250514",max_tokens=1024,
                    messages=[{"role":"user","content":prompt}])
                self.after(0,lambda:self._ai_log(f"AI: {r.content[0].text}\n"))
            except Exception as ex:
                self.after(0,lambda:self._ai_log(f"Error: {ex}","d"))
            finally:
                self.after(0,lambda:self.ai_status.config(text=""))
        threading.Thread(target=go,daemon=True).start()

    def _ai_explain(self): self._ai_call(f"Explain this Python code briefly:\n\n```python\n{self._code()}\n```","Explain")
    def _ai_fix(self): self._ai_call(f"Fix bugs, show corrected code:\n\n```python\n{self._code()}\n```","Fix Bugs")
    def _ai_docs(self): self._ai_call(f"Add docstrings to all functions/classes:\n\n```python\n{self._code()}\n```","Docstrings")
    def _ai_refactor(self): self._ai_call(f"Refactor to be more Pythonic:\n\n```python\n{self._code()}\n```","Refactor")

    def _ai_review(self):
        code=self._code(); s=count_stats(code)
        self._ai_call(
            f"Review this Python code and give 3 specific improvements.\n"
            f"Stats: {s['total_lines']} lines, {s['functions']} functions, "
            f"{s['classes']} classes, complexity={s['complexity'][0]}\n\n"
            f"```python\n{code[:1500]}\n```","AI Review")

    def _ai_ask(self):
        q=self.ai_inp.get().strip()
        if not q or q=="Ask anything…": return
        self.ai_inp.delete(0,"end")
        c=self._code()
        self._ai_call(f"Code:\n```python\n{c}\n```\n\nQuestion: {q}" if c else q,q[:40])

    def _ai_complete(self,e,ed):
        if not AI_AVAILABLE: return "break"
        txt=ed["text"]; ln=txt.index("insert").split(".")[0]
        ctx=txt.get("1.0",f"{ln}.end"); self.ai_status.config(text="⟳ Completing…")
        def go():
            try:
                r=self.ai_client.messages.create(model="claude-sonnet-4-20250514",max_tokens=150,
                    messages=[{"role":"user","content":f"Complete this Python code. Return ONLY the completion:\n\n```python\n{ctx}\n```"}])
                comp=re.sub(r"^```python\n?","",r.content[0].text.strip())
                comp=re.sub(r"```$","",comp).strip()
                if comp: self.after(0,lambda:self._insert_ghost(txt,comp))
            except Exception: pass
            finally: self.after(0,lambda:self.ai_status.config(text=""))
        threading.Thread(target=go,daemon=True).start(); return "break"

    def _insert_ghost(self,txt,comp):
        txt.insert("insert",comp); end=txt.index("insert"); ln,col=end.split(".")
        start=f"{ln}.{int(col)-len(comp.split(chr(10))[-1])}"; txt.tag_add("ghost",start,end)
        self.after(700,lambda:txt.tag_remove("ghost","1.0","end"))

    def _auto_hint(self,ed):
        if not AI_AVAILABLE: return
        txt=ed["text"]; ln=int(txt.index("insert").split(".")[0])
        snip=txt.get(f"{max(1,ln-2)}.0",f"{ln}.end")
        if len(snip.strip())<12: return
        def go():
            try:
                r=self.ai_client.messages.create(model="claude-sonnet-4-20250514",max_tokens=50,
                    messages=[{"role":"user","content":f"One short coding hint (max 10 words), no preamble:\n\n```python\n{snip}\n```"}])
                hint=r.content[0].text.strip()
                if hint: self.after(0,lambda:self._show_hint(txt,hint))
            except Exception: pass
        threading.Thread(target=go,daemon=True).start()

    def _show_hint(self,txt,hint):
        if self.hint_win:
            try: self.hint_win.destroy()
            except Exception: pass
        try:
            bb=txt.bbox("insert")
            if not bb: return
            x,y,_,h=bb; rx=txt.winfo_rootx()+x; ry=txt.winfo_rooty()+y+h+4
        except Exception: return
        w=tk.Toplevel(self); w.wm_overrideredirect(True)
        w.wm_geometry(f"+{rx}+{ry}"); w.configure(bg=T["panel"])
        try: w.attributes("-alpha",0.92)
        except Exception: pass
        try: w.attributes("-topmost",True)
        except Exception: pass
        tk.Label(w,text=f"💡 {hint}",bg=T["panel"],fg=T["accent2"],font=FN_SM,padx=10,pady=5).pack()
        self.hint_win=w; self.after(4000,lambda:w.destroy() if w.winfo_exists() else None)

    def _toggle_xray(self):
        self.xray_on=not self.xray_on
        self.xray_btn.config(fg=T["accent"] if self.xray_on else T["text_dim"],
                              text="☢  X-Ray ✓" if self.xray_on else "☢  X-Ray Mode")
        if self.active: self._apply_xray(self.files[self.active])

    def _apply_xray(self,ed):
        txt=ed["text"]; txt.tag_remove("xdim","1.0","end"); txt.tag_remove("xhi","1.0","end")
        if not self.xray_on: return
        dp=[r"^import ",r"^from .+ import",r"^\s*pass\s*$",r"^\s*#",r"^\s*$"]
        hp=[r"^\s*def ",r"^\s*class ",r"^\s*if ",r"^\s*elif ",r"^\s*for ",r"^\s*while ",r"^\s*return ",r"^\s*raise "]
        for ln,line in enumerate(txt.get("1.0","end-1c").split("\n"),1):
            tag=None
            for p in dp:
                if re.match(p,line): tag="xdim"; break
            if not tag:
                for p in hp:
                    if re.match(p,line): tag="xhi"; break
            if tag: txt.tag_add(tag,f"{ln}.0",f"{ln}.end")

    def _toggle_voice(self):
        if self.listening: self.listening=False; self.ai_status.config(text="")
        else:
            self.listening=True; self.ai_status.config(text="🎙 Listening…")
            threading.Thread(target=self._voice_loop,daemon=True).start()

    def _voice_loop(self):
        rec=sr.Recognizer()
        try:
            with sr.Microphone() as src:
                rec.adjust_for_ambient_noise(src,0.5)
                while self.listening:
                    try:
                        audio=rec.listen(src,timeout=5,phrase_time_limit=8)
                        cmd=rec.recognize_google(audio).lower()
                        self.after(0,lambda c=cmd:self._voice_cmd(c))
                    except (sr.WaitTimeoutError,sr.UnknownValueError): pass
                    except Exception: break
        except Exception:
            self.after(0,lambda:messagebox.showinfo("Voice","Microphone not available."))
        self.listening=False; self.after(0,lambda:self.ai_status.config(text=""))

    def _voice_cmd(self,cmd):
        if not self.active: return
        txt=self.files[self.active]["text"]
        acts={"new line":lambda:txt.insert("insert","\n"),"save":self._save,
              "run":self._run,"undo":txt.edit_undo,"redo":txt.edit_redo,"show stats":self._toggle_stats}
        for k,fn in acts.items():
            if k in cmd:
                fn(); self.ai_status.config(text=f"✓ {k}")
                self.after(2000,lambda:self.ai_status.config(text="🎙 Listening…")); return
        if cmd.startswith("type "): txt.insert("insert",cmd[5:])
        elif (cmd.startswith("write ") or cmd.startswith("create ")) and AI_AVAILABLE:
            def go():
                try:
                    r=self.ai_client.messages.create(model="claude-sonnet-4-20250514",max_tokens=300,
                        messages=[{"role":"user","content":f"Write Python code for: {cmd}\nReturn ONLY the code."}])
                    code=re.sub(r"^```python\n?","",r.content[0].text.strip())
                    code=re.sub(r"```$","",code).strip()
                    self.after(0,lambda:txt.insert("insert","\n"+code+"\n"))
                except Exception: pass
            threading.Thread(target=go,daemon=True).start()

    def _menu_file(self):
        m=tk.Menu(self,tearoff=0,bg=T["panel"],fg=T["text"],activebackground=T["select"],bd=0)
        m.add_command(label="New File    Ctrl+N",command=self._new_file)
        m.add_command(label="Open File   Ctrl+O",command=self._open_file)
        m.add_separator()
        m.add_command(label="Save        Ctrl+S",command=self._save)
        m.add_command(label="Save As…  Ctrl+Shift+S",command=lambda:self._save(True))
        m.add_separator(); m.add_command(label="Exit",command=self.quit)
        try: m.tk_popup(self.winfo_pointerx(),self.winfo_pointery())
        finally: m.grab_release()

    def _menu_edit(self):
        m=tk.Menu(self,tearoff=0,bg=T["panel"],fg=T["text"],activebackground=T["select"],bd=0)
        m.add_command(label="Undo  Ctrl+Z",command=lambda:self.active and self.files[self.active]["text"].edit_undo())
        m.add_command(label="Redo  Ctrl+Y",command=lambda:self.active and self.files[self.active]["text"].edit_redo())
        m.add_separator(); m.add_command(label="Find  Ctrl+F",command=self._find)
        try: m.tk_popup(self.winfo_pointerx(),self.winfo_pointery())
        finally: m.grab_release()

    def _menu_view(self):
        m=tk.Menu(self,tearoff=0,bg=T["panel"],fg=T["text"],activebackground=T["select"],bd=0)
        m.add_command(label="Zoom In   Ctrl+=",command=lambda:self._zoom(1))
        m.add_command(label="Zoom Out  Ctrl+-",command=lambda:self._zoom(-1))
        m.add_separator()
        m.add_command(label="Toggle AI Panel",command=self._toggle_ai)
        m.add_command(label="Toggle Stats  F2",command=self._toggle_stats)
        m.add_command(label="Toggle X-Ray",command=self._toggle_xray)
        try: m.tk_popup(self.winfo_pointerx(),self.winfo_pointery())
        finally: m.grab_release()

    def _find(self):
        if not self.active: return
        top=tk.Toplevel(self); top.title("Find"); top.geometry("380x56")
        top.configure(bg=T["panel"]); top.resizable(False,False)
        tk.Label(top,text="Find:",bg=T["panel"],fg=T["text"],font=FN_SM).pack(side="left",padx=8)
        e=tk.Entry(top,bg=T["bg"],fg=T["text"],font=FN_SM,insertbackground=T["accent"],relief="flat",bd=4)
        e.pack(side="left",fill="x",expand=True,padx=4); e.focus_set()
        def do_find():
            txt=self.files[self.active]["text"]; txt.tag_remove("found","1.0","end")
            term=e.get()
            if not term: return
            i="1.0"
            while True:
                i=txt.search(term,i,nocase=True,stopindex="end")
                if not i: break
                txt.tag_add("found",i,f"{i}+{len(term)}c"); i=f"{i}+{len(term)}c"
        tk.Button(top,text="Find",command=do_find,bg=T["accent"],fg=T["text_hi"],
                  font=FN_SM,relief="flat").pack(side="right",padx=8)
        e.bind("<Return>",lambda ev:do_find())

    def _zoom(self,d):
        size=FN_MONO[1]+d
        if self.active:
            try:
                cur=self.files[self.active]["text"].cget("font")
                if isinstance(cur,tuple): size=cur[1]+d
            except Exception: pass
        if not (8<=size<=28): return
        for ed in self.files.values():
            ed["text"].config(font=(FN_MONO[0],size))
            ed["gutter"].config(font=(FN_MONO[0],size))

def main():
    app=DCode(); app.mainloop()

if __name__=="__main__":
    main()