"""Render the Markdown comparison as a standalone, default-style LaTeX article."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]

def escape(s):
    chars={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}
    return ''.join(chars.get(c,c) for c in s).replace('/', r'/\allowbreak{}')

def inline(s):
    pattern=r'(\[([^\]]+)\]\((https?://[^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`)'
    result=[];prev=0
    for m in re.finditer(pattern,s):
        result.append(escape(s[prev:m.start()]))
        if m.group(2):result.append(r'\href{'+m.group(3)+r'}{'+escape(m.group(2))+'}')
        elif m.group(4):result.append(r'\textbf{'+escape(m.group(4))+'}')
        else:result.append(r'\texttt{'+escape(m.group(5))+'}')
        prev=m.end()
    result.append(escape(s[prev:]));return ''.join(result)

def main():
    md=ROOT/'reports/cost_optimization_2026-10-01.md'
    lines=md.read_text().splitlines();out=[];i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('# '):i+=1;continue
        if line.startswith('## '):out.append(r'\section{'+inline(line[3:])+'}');i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[c.strip() for c in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[:\-]+',c) for c in cells):rows.append(cells)
                i+=1
            n=len(rows[0])
            widths=[.29,.12,.075,.075,.17,.17] if n==6 else [.34,.11,.11,.16,.18]
            rows[0]=[{'Successful images':'Success','Mean seconds/image':'Mean time (s)','Reference token cost':'Reference cost'}.get(c,c) for c in rows[0]]
            spec='@{}'+''.join(r'>{\raggedright\arraybackslash}p{'+str(round(w,3))+r'\linewidth}' for w in widths)+'@{}'
            out.extend([r'\begingroup\footnotesize',r'\setlength{\tabcolsep}{3pt}',r'\begin{longtable}{'+spec+'}',r'\toprule'])
            for index,row in enumerate(rows):
                out.append(' & '.join(inline(c) for c in row)+r' \\')
                if index==0:out.extend([r'\midrule',r'\endhead'])
            out.extend([r'\bottomrule',r'\end{longtable}',r'\endgroup']);continue
        if line.startswith('```'):
            out.append(r'\begin{verbatim}');i+=1
            while i<len(lines) and not lines[i].startswith('```'):out.append(lines[i]);i+=1
            out.append(r'\end{verbatim}');i+=1;continue
        if line.startswith('- '):
            out.append(r'\begin{itemize}')
            while i<len(lines) and lines[i].startswith('- '):out.append(r'\item '+inline(lines[i][2:]));i+=1
            out.append(r'\end{itemize}');continue
        out.append(inline(line));i+=1
    title=lines[0][2:]
    tex='\n'.join([r'\documentclass[11pt,a4paper]{article}',r'\usepackage[T1]{fontenc}',r'\usepackage{booktabs,longtable,array}',r'\usepackage[hidelinks]{hyperref}',r'\pagestyle{empty}',r'\title{'+escape(title)+'}',r'\author{}',r'\date{1 October 2026}',r'\begin{document}',r'\maketitle',r'\thispagestyle{empty}']+out+[r'\end{document}',''])
    (ROOT/'reports/chemeagle_cost_comparison_2026-10-01.tex').write_text(tex)

if __name__=='__main__':main()
