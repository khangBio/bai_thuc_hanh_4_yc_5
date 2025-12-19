import os
import uuid
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, send_file, redirect, url_for, flash

import pdfkit

APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(APP_DIR, "uploads")
OUTPUT_DIR = os.path.join(APP_DIR, "outputs")
STATIC_DIR = os.path.join(APP_DIR, "static")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = "dev-secret"  # đổi khi deploy thật


def make_chart(df: pd.DataFrame, x_col: str, y_col: str, out_png_path: str):
    """Vẽ biểu đồ line/scatter đơn giản để minh họa."""
    plt.figure()
    # nếu x là numeric thì sort để chart mượt hơn
    try:
        df2 = df.sort_values(by=x_col)
    except Exception:
        df2 = df

    plt.plot(df2[x_col], df2[y_col], marker="o")
    plt.xlabel(x_col)
    plt.ylabel(y_col)
    plt.title(f"{y_col} theo {x_col}")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(out_png_path, dpi=150)
    plt.close()


def build_summary(df: pd.DataFrame):
    """Sinh thống kê mô tả ngắn gọn."""
    summary = {
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "missing_total": int(df.isna().sum().sum()),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Thống kê numeric
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    desc_html = None
    if numeric_cols:
        desc = df[numeric_cols].describe().round(3)
        desc_html = desc.to_html(classes="table table-small", border=0)

    # Gợi ý cặp cột để vẽ chart: ưu tiên numeric-numeric; nếu không có thì None
    x_col = y_col = None
    if len(numeric_cols) >= 2:
        x_col, y_col = numeric_cols[0], numeric_cols[1]
    elif len(numeric_cols) == 1:
        # nếu chỉ có 1 numeric, thử lấy 1 cột khác làm x
        other_cols = [c for c in df.columns if c != numeric_cols[0]]
        if other_cols:
            x_col, y_col = other_cols[0], numeric_cols[0]

    return summary, desc_html, x_col, y_col


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        f = request.files.get("csv_file")
        if not f or f.filename.strip() == "":
            flash("Bạn chưa chọn file CSV.")
            return redirect(url_for("index"))

        if not f.filename.lower().endswith(".csv"):
            flash("Chỉ hỗ trợ file .csv")
            return redirect(url_for("index"))

        file_id = uuid.uuid4().hex
        csv_path = os.path.join(UPLOAD_DIR, f"{file_id}.csv")
        f.save(csv_path)

        return redirect(url_for("preview_report", file_id=file_id))

    return """
    <!doctype html>
    <html lang="vi">
    <head>
      <meta charset="utf-8"/>
      <title>CSV → PDF Report</title>
      <style>
        body{font-family:Arial; max-width:780px; margin:40px auto; padding:0 16px;}
        .card{border:1px solid #ddd; border-radius:12px; padding:18px;}
        button{padding:10px 14px; border-radius:10px; border:0; cursor:pointer;}
        input{padding:10px; width:100%;}
        .msg{color:#b00020;}
      </style>
    </head>
    <body>
      <h2>Ứng dụng: Đọc CSV → Xuất báo cáo PDF</h2>
      <div class="card">
        <form method="post" enctype="multipart/form-data">
          <label><b>Chọn file CSV</b></label><br/><br/>
          <input type="file" name="csv_file" accept=".csv" required />
          <br/><br/>
          <button type="submit">Tải lên & Xem báo cáo</button>
        </form>
      </div>
    </body>
    </html>
    """


@app.route("/report/<file_id>", methods=["GET"])
def preview_report(file_id):
    csv_path = os.path.join(UPLOAD_DIR, f"{file_id}.csv")
    if not os.path.exists(csv_path):
        return "Không tìm thấy file. Vui lòng upload lại.", 404

    # đọc CSV
    df = pd.read_csv(csv_path)

    summary, desc_html, x_col, y_col = build_summary(df)

    # lấy 30 dòng đầu cho bảng (tránh PDF quá dài)
    preview_df = df.head(30)
    preview_html = preview_df.to_html(classes="table", index=False, border=0)

    # tạo chart (nếu có cột phù hợp)
    chart_rel = None
    if x_col and y_col:
        chart_filename = f"chart_{file_id}.png"
        chart_path = os.path.join(STATIC_DIR, chart_filename)
        make_chart(df, x_col, y_col, chart_path)
        chart_rel = f"/static/{chart_filename}"

    return render_template(
        "report.html",
        title="BÁO CÁO PHÂN TÍCH DỮ LIỆU (TỪ CSV)",
        summary=summary,
        preview_table_html=preview_html,
        desc_table_html=desc_html,
        chart_url=chart_rel,
        file_id=file_id,
    )


@app.route("/download/<file_id>.pdf", methods=["GET"])
def download_pdf(file_id):
    csv_path = os.path.join(UPLOAD_DIR, f"{file_id}.csv")
    if not os.path.exists(csv_path):
        return "Không tìm thấy file. Vui lòng upload lại.", 404

    # Render HTML bằng Jinja rồi convert sang PDF
    df = pd.read_csv(csv_path)
    summary, desc_html, x_col, y_col = build_summary(df)
    preview_html = df.head(30).to_html(classes="table", index=False, border=0)

    chart_rel = None
    if x_col and y_col:
        chart_filename = f"chart_{file_id}.png"
        chart_path = os.path.join(STATIC_DIR, chart_filename)
        make_chart(df, x_col, y_col, chart_path)
        chart_rel = f"/static/{chart_filename}"

    html = render_template(
        "report.html",
        title="BÁO CÁO PHÂN TÍCH DỮ LIỆU (TỪ CSV)",
        summary=summary,
        preview_table_html=preview_html,
        desc_table_html=desc_html,
        chart_url=chart_rel,
        file_id=file_id,
        for_pdf=True,  # optional flag
    )

    out_pdf_path = os.path.join(OUTPUT_DIR, f"report_{file_id}.pdf")

    # Cấu hình pdfkit: trỏ đúng tới wkhtmltopdf nếu cần
    # Windows ví dụ:
    # config = pdfkit.configuration(wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe")
    config = None

    options = {
        "encoding": "UTF-8",
        "page-size": "A4",
        "margin-top": "12mm",
        "margin-right": "12mm",
        "margin-bottom": "12mm",
        "margin-left": "12mm",
        # Cho phép load ảnh/css local (quan trọng)
        "enable-local-file-access": None,
    }

    # base_url giúp wkhtmltopdf resolve /static/... khi render
    pdfkit.from_string(
        html,
        out_pdf_path,
        options=options,
        configuration=config,
        css=os.path.join(STATIC_DIR, "style.css"),
    )

    return send_file(out_pdf_path, as_attachment=True, download_name="output_report.pdf")


if __name__ == "__main__":
    app.run(debug=True)
