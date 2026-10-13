from fpdf import FPDF
import re

SRC = "resume_sentinel.md"
OUT = r"C:\Users\Bhavesh\Downloads\Bhavesh_Chaudhary_Resume.pdf"

class PDF(FPDF):
    def header(self):
        pass
    def footer(self):
        self.set_y(-12)
        self.set_font("helvetica", "", 8)
        self.set_text_color(120)
        self.cell(0, 6, f"{self.page_no()}", align="C")

pdf = PDF(format="A4")
pdf.set_margins(16, 14, 16)
pdf.set_auto_page_break(True, 16)
pdf.add_page()

W = pdf.w - pdf.l_margin - pdf.r_margin

def clean(s):
    s = s.replace("**", "")
    s = s.replace("*", "")
    for a, b in (("\u2014", "-"), ("\u2013", "-"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'), ("\u2022", "-"), ("\u2192", "->")):
        s = s.replace(a, b)
    return s

def h1(text):
    pdf.set_font("helvetica", "B", 18)
    pdf.set_text_color(20)
    pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.5)

def subtitle(text):
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(80)
    pdf.cell(0, 4.8, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.5)

def contact(text):
    pdf.set_font("helvetica", "", 9.2)
    pdf.set_text_color(60)
    pdf.cell(0, 4.6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.5)

def h2(text):
    pdf.ln(1)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(30)
    pdf.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y()
    pdf.set_draw_color(60)
    pdf.set_line_width(0.4)
    pdf.line(pdf.l_margin, y, pdf.l_margin + W, y)
    pdf.ln(1.2)

def h3(text):
    pdf.set_font("helvetica", "B", 11)
    pdf.set_text_color(20)
    pdf.cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")

def tech(text):
    pdf.set_font("helvetica", "I", 8.8)
    pdf.set_text_color(90)
    pdf.multi_cell(W, 4.2, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.8)

def body(text):
    pdf.set_font("helvetica", "", 9.5)
    pdf.set_text_color(40)
    pdf.multi_cell(W, 4.5, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.8)

def bullet(text):
    pdf.set_font("helvetica", "", 9.2)
    pdf.set_text_color(40)
    pdf.multi_cell(W - 6, 4.5, "-  " + text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.6)

def table_row(a, b):
    pdf.set_font("helvetica", "B", 9.2)
    pdf.set_text_color(30)
    pdf.cell(36, 4.5, a)
    pdf.set_font("helvetica", "", 9.2)
    pdf.set_text_color(40)
    pdf.multi_cell(W - 36, 4.5, b, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.4)

with open(SRC, encoding="utf-8") as f:
    lines = f.read().splitlines()

i = 0
while i < len(lines):
    line = lines[i].rstrip()
    i += 1
    if not line.strip():
        continue
    if line.startswith("# ") and not line.startswith("##"):
        h1(clean(line[2:]))
    elif line.startswith("### "):
        h3(clean(line[4:]))
    elif line.startswith("## "):
        h2(clean(line[3:]))
    elif line.startswith("|"):
        # table header separator skip
        if set(line.replace("|", "").replace("-", "").strip()) <= {"" } or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells[0] == "Area":
            continue
        table_row(cells[0], cells[1])
    elif line.startswith("- "):
        bullet(clean(line[2:]))
    elif re.match(r"^\*.+\*$", line.strip()):
        tech(clean(line.strip()))
    elif line.startswith("**"):
        contact(clean(line))
    elif line.count("**") >= 2 and i <= 8:
        subtitle(clean(line))
    else:
        body(clean(line))

pdf.output(OUT)
print("Wrote", OUT)
