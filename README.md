# 💸 SmartSettled  
### Directed Graphs & Flow Optimization for Expense Splitting

SmartSettled is a modern web application inspired by Splitwise that uses **Discrete Mathematics and Graph Theory** to efficiently split expenses among groups.

It minimizes the number of transactions using **graph-based optimization algorithms**, making group expense management simple and intelligent.

---

## 🚀 Features

- 👥 Create and manage multiple groups  
- ➕ Add members dynamically  
- 💸 Record shared expenses  
- ⚡ Automatic debt simplification (Minimum Cash Flow)  
- 📊 Analytics dashboard (charts & insights)  
- 🧠 Graph visualization of debts (nodes & edges)  
- 📄 Export detailed PDF reports (global & user-wise)  
- 🔄 Real-time updates with clean UI  

---

## 🧠 Discrete Mathematics Concepts Used

This project applies key concepts from Discrete Mathematics:

- **Graphs**  
  - Users → Nodes  
  - Transactions → Directed weighted edges  

- **Relations**  
  - Financial relationships between users  

- **Optimization Algorithms**  
  - Minimum Cash Flow Algorithm (Greedy approach)  
  - Reduces total number of transactions  

---

## ⚙️ Tech Stack

- **Backend:** Python (Flask)  
- **Frontend:** HTML, CSS, JavaScript  
- **Database:** SQLite  
- **Visualization:** Chart.js / Graph visualization  
- **PDF Generation:** ReportLab  

---

## 🏗️ How It Works

1. Users are added to a group  
2. Expenses are recorded with payer and participants  
3. System calculates net balances  
4. A graph is constructed:
   - Nodes → Users  
   - Edges → Money owed  
5. Optimization algorithm minimizes transactions  
6. Results are displayed and can be exported  

---

## 📸 Demo Flow

- Create group  
- Add members  
- Add expenses  
- View optimized settlements  
- Visualize graph  
- Export reports  


