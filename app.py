import os
import json
import sqlite3
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
from io import BytesIO

app = Flask(__name__)
DB_PATH = 'data.db'

# --- DATABASE SETUP ---
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    name TEXT NOT NULL,
                    FOREIGN KEY(group_id) REFERENCES groups(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    payer TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT,
                    participants TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(group_id) REFERENCES groups(id)
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settlements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    payer TEXT NOT NULL,
                    receiver TEXT NOT NULL,
                    amount REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(group_id) REFERENCES groups(id)
                )''')
    c.execute("SELECT id FROM groups WHERE name = 'Default'")
    if not c.fetchone():
        c.execute("INSERT INTO groups (name) VALUES ('Default')")
    conn.commit()
    conn.close()

init_db()

# --- CORE LOGIC ---
def optimize_debts(balances):
    creditors = [[name, bal] for name, bal in balances.items() if bal > 0]
    debtors = [[name, -bal] for name, bal in balances.items() if bal < 0]
    transactions = []
    i = j = 0
    while i < len(creditors) and j < len(debtors):
        c_name, c_amt = creditors[i]
        d_name, d_amt = debtors[j]
        settle_amt = min(c_amt, d_amt)
        if settle_amt > 0.01:
            transactions.append({"from": d_name, "to": c_name, "amount": round(settle_amt, 2)})
        creditors[i][1] -= settle_amt
        debtors[j][1] -= settle_amt
        if creditors[i][1] < 0.01: i += 1
        if debtors[j][1] < 0.01: j += 1
    return transactions

# --- API ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/groups', methods=['GET'])
def get_groups():
    conn = get_db_connection()
    groups = conn.execute('SELECT * FROM groups').fetchall()
    conn.close()
    return jsonify([dict(g) for g in groups])

@app.route('/create_group', methods=['POST'])
def create_group():
    name = request.json.get('name')
    if not name: return jsonify({"error": "Name required"}), 400
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO groups (name) VALUES (?)", (name,))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return jsonify({"id": new_id, "name": name})

@app.route('/group/<int:group_id>/people', methods=['GET', 'POST'])
def handle_people(group_id):
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.json.get('name')
        if name:
            conn.execute("INSERT INTO users (group_id, name) VALUES (?, ?)", (group_id, name))
            conn.commit()
    users = conn.execute("SELECT name FROM users WHERE group_id = ?", (group_id,)).fetchall()
    conn.close()
    return jsonify([u['name'] for u in users])

@app.route('/group/<int:group_id>/expenses', methods=['GET', 'POST'])
def handle_expenses(group_id):
    conn = get_db_connection()
    if request.method == 'POST':
        data = request.json
        conn.execute("INSERT INTO expenses (group_id, payer, amount, description, participants) VALUES (?, ?, ?, ?, ?)",
                     (group_id, data['payer'], float(data['amount']), data.get('description', ''), json.dumps(data['participants'])))
        conn.commit()
    expenses = conn.execute("SELECT * FROM expenses WHERE group_id = ? ORDER BY created_at DESC", (group_id,)).fetchall()
    conn.close()
    res = []
    for e in expenses:
        d = dict(e)
        d['participants'] = json.loads(d['participants'])
        res.append(d)
    return jsonify(res)

@app.route('/group/<int:group_id>/settle_debt', methods=['POST'])
def record_settlement(group_id):
    data = request.json
    conn = get_db_connection()
    conn.execute("INSERT INTO settlements (group_id, payer, receiver, amount) VALUES (?, ?, ?, ?)",
                 (group_id, data['from'], data['to'], float(data['amount'])))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

@app.route('/group/<int:group_id>/settlements', methods=['GET'])
def get_settlements(group_id):
    conn = get_db_connection()
    res = conn.execute("SELECT * FROM settlements WHERE group_id = ? ORDER BY created_at DESC", (group_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in res])

@app.route('/group/<int:group_id>/status')
def get_status(group_id):
    conn = get_db_connection()
    users = conn.execute("SELECT name FROM users WHERE group_id = ?", (group_id,)).fetchall()
    expenses = conn.execute("SELECT payer, amount, participants FROM expenses WHERE group_id = ?", (group_id,)).fetchall()
    settlements = conn.execute("SELECT payer, receiver, amount FROM settlements WHERE group_id = ?", (group_id,)).fetchall()
    conn.close()
    
    balances = {u['name']: 0.0 for u in users}
    total_spent = 0
    for e in expenses:
        amount = e['amount']
        total_spent += amount
        parts = json.loads(e['participants'])
        if parts:
            split = amount / len(parts)
            for p in parts:
                if p in balances: balances[p] -= split
            if e['payer'] in balances: balances[e['payer']] += amount
            
    for s in settlements:
        if s['payer'] in balances: balances[s['payer']] += s['amount']
        if s['receiver'] in balances: balances[s['receiver']] -= s['amount']
            
    highest_spender = max(balances.items(), key=lambda x: x[1], default=("None", 0))
    most_owed = min(balances.items(), key=lambda x: x[1], default=("None", 0))
    optimized = optimize_debts(balances)
    return jsonify({
        "balances": balances,
        "total_spent": round(total_spent, 2),
        "transaction_count": len(expenses),
        "optimized": optimized,
        "highest_spender": highest_spender[0],
        "most_owed_user": most_owed[0]
    })

# --- PDF GENERATION ---

def create_pdf_report(filename, title, data_rows, summary_data, graph_img_data=None):
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, spaceAfter=20, textColor=colors.HexColor("#2563eb"))
    header_style = ParagraphStyle('CustomHeader', parent=styles['Heading2'], fontSize=16, spaceBefore=15, spaceAfter=10)
    elements = []
    
    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Italic']))
    elements.append(Spacer(1, 0.2*inch))
    
    elements.append(Paragraph("Financial Summary", header_style))
    st_data = [["Metric", "Value"]]
    for k, v in summary_data.items():
        st_data.append([k, str(v).replace('₹', 'Rs.')])
    
    st_table = Table(st_data, colWidths=[2.5*inch, 2.5*inch])
    st_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f3f4f6")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 8),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold')
    ]))
    elements.append(st_table)
    
    if graph_img_data:
        try:
            elements.append(Paragraph("Debt Visualization Graph", header_style))
            img_data = base64.b64decode(graph_img_data.split(',')[1])
            img = Image(BytesIO(img_data), width=5*inch, height=3*inch)
            elements.append(img)
        except Exception as e:
            elements.append(Paragraph(f"[Graph Render Error: {str(e)}]", styles['Normal']))

    elements.append(Paragraph("Detailed Transactions", header_style))
    # Replace ₹ with Rs. in all rows to avoid black squares
    clean_rows = [[str(cell).replace('₹', 'Rs.') for cell in row] for row in data_rows]
    main_table = Table(clean_rows, hAlign='LEFT')
    main_table.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,0), 1, colors.black),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(main_table)
    doc.build(elements)

@app.route('/export/all/<int:group_id>', methods=['POST'])
def export_all(group_id):
    graph_img = request.json.get('graph_image')
    conn = get_db_connection()
    group = conn.execute("SELECT name FROM groups WHERE id = ?", (group_id,)).fetchone()
    users = conn.execute("SELECT name FROM users WHERE group_id = ?", (group_id,)).fetchall()
    expenses = conn.execute("SELECT * FROM expenses WHERE group_id = ?", (group_id,)).fetchall()
    settlements = conn.execute("SELECT * FROM settlements WHERE group_id = ?", (group_id,)).fetchall()
    conn.close()
    
    balances = {u['name']: 0.0 for u in users}
    total_spent = sum(e['amount'] for e in expenses)
    for e in expenses:
        parts = json.loads(e['participants'])
        split = e['amount'] / len(parts) if parts else 0
        for p in parts:
            if p in balances: balances[p] -= split
        if e['payer'] in balances: balances[e['payer']] += e['amount']
    for s in settlements:
        if s['payer'] in balances: balances[s['payer']] += s['amount']
        if s['receiver'] in balances: balances[s['receiver']] -= s['amount']
    
    summary = {"Group": group['name'], "Total Expenses": f"Rs. {total_spent:,.2f}", "Members": len(users), "Transactions": len(expenses) + len(settlements)}
    rows = [["User", "Net Balance (Rs.)"]]
    for name, bal in balances.items():
        rows.append([name, f"{bal:+.2f}"])
    
    filename = f"report_group_{group_id}.pdf"
    create_pdf_report(filename, f"Settlement Report - {group['name']}", rows, summary, graph_img)
    return jsonify({"file": filename})

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(filename, as_attachment=True)

@app.route('/export/user/<int:group_id>/<string:user_name>', methods=['POST'])
def export_user(group_id, user_name):
    conn = get_db_connection()
    expenses = conn.execute("SELECT * FROM expenses WHERE group_id = ?", (group_id,)).fetchall()
    settlements = conn.execute("SELECT * FROM settlements WHERE group_id = ?", (group_id,)).fetchall()
    conn.close()
    
    user_rows = []
    personal_spent = 0
    personal_owed = 0
    for e in expenses:
        parts = json.loads(e['participants'])
        if e['payer'] == user_name:
            user_rows.append([e['created_at'], e['description'] or "Exp", f"Paid Rs. {e['amount']:.2f}"])
            personal_spent += e['amount']
        elif user_name in parts:
            split = e['amount'] / len(parts)
            user_rows.append([e['created_at'], f"Shared ({e['payer']})", f"Owed Rs. {split:.2f}"])
            personal_owed += split
    for s in settlements:
        if s['payer'] == user_name: user_rows.append([s['created_at'], f"Payment to {s['receiver']}", f"Settled Rs. {s['amount']:.2f}"])
        elif s['receiver'] == user_name: user_rows.append([s['created_at'], f"Payment from {s['payer']}", f"Received Rs. {s['amount']:.2f}"])
            
    summary = {"User": user_name, "Paid/Settled": f"Rs. {personal_spent:.2f}", "Total Owed": f"Rs. {personal_owed:.2f}", "Net Position": f"Rs. {(personal_spent - personal_owed):+.2f}"}
    rows = [["Date", "Description", "Detail"]]
    rows.extend(user_rows)
    filename = f"report_{user_name}_{group_id}.pdf"
    create_pdf_report(filename, f"Personal Activity - {user_name}", rows, summary)
    return jsonify({"file": filename})

@app.route('/group/<int:group_id>', methods=['DELETE'])
def delete_group(group_id):
    conn = get_db_connection()
    # Cascading delete manually since we didn't use CASCADE in CREATE TABLE
    conn.execute("DELETE FROM users WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM expenses WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM settlements WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/group/<int:group_id>/reset', methods=['POST'])
def reset_group_data(group_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM expenses WHERE group_id = ?", (group_id,))
    conn.execute("DELETE FROM settlements WHERE group_id = ?", (group_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "reset"})

if __name__ == "__main__":
    app.run(debug=True, port=5000)