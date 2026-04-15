from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date, timedelta
import json, csv, io, os

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ledger.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)
db = SQLAlchemy(app)

# ── MODELS ────────────────────────────────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(64), nullable=False)
    monthly_salary = db.Column(db.Float, default=0)
    theme = db.Column(db.String(10), default='dark')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')
    budgets = db.relationship('Budget', backref='user', lazy=True, cascade='all, delete-orphan')
    goals = db.relationship('SavingGoal', backref='user', lazy=True, cascade='all, delete-orphan')
    reminders = db.relationship('Reminder', backref='user', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='user', lazy=True, cascade='all, delete-orphan')

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # income/expense
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, default='')
    tags = db.Column(db.String(200), default='')
    is_recurring = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'amount': self.amount,
            'type': self.type, 'category': self.category,
            'date': self.date.isoformat(), 'notes': self.notes,
            'tags': self.tags, 'is_recurring': self.is_recurring
        }

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, default=0)

    def to_dict(self):
        return {'id': self.id, 'category': self.category, 'amount': self.amount}

class SavingGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    target = db.Column(db.Float, nullable=False)
    saved = db.Column(db.Float, default=0)
    deadline = db.Column(db.Date, nullable=True)
    emoji = db.Column(db.String(10), default='🎯')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'target': self.target,
            'saved': self.saved, 'deadline': self.deadline.isoformat() if self.deadline else None,
            'emoji': self.emoji, 'created_at': self.created_at.isoformat()
        }

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, default=0)
    due_date = db.Column(db.Date, nullable=False)
    type = db.Column(db.String(20), default='bill')  # bill, loan, rent
    is_paid = db.Column(db.Boolean, default=False)
    repeat = db.Column(db.String(20), default='monthly')  # none, monthly, yearly
    notes = db.Column(db.Text, default='')

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'amount': self.amount,
            'due_date': self.due_date.isoformat(), 'type': self.type,
            'is_paid': self.is_paid, 'repeat': self.repeat, 'notes': self.notes
        }

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    emoji = db.Column(db.String(10), default='📦')
    color = db.Column(db.String(10), default='#a8e6a3')
    type = db.Column(db.String(10), default='expense')
    is_default = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'emoji': self.emoji,
                'color': self.color, 'type': self.type, 'is_default': self.is_default}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def hash_password(pw):
    h = 0
    for c in pw:
        h = (31 * h + ord(c)) & 0xFFFFFFFF
    return format(h, 'x')

DEFAULT_CATEGORIES = [
    ('Food', '🍜', '#a8e6a3', 'expense'), ('Transport', '🚇', '#7bb8f5', 'expense'),
    ('Shopping', '🛍', '#f5c842', 'expense'), ('Health', '💊', '#e87575', 'expense'),
    ('Entertainment', '🎬', '#c3a8e6', 'expense'), ('Salary', '💼', '#a8d4e6', 'income'),
    ('Rent', '🏠', '#f5a842', 'expense'), ('Loan', '🏦', '#e8a87c', 'expense'),
    ('Bill', '📋', '#f5c4a1', 'expense'), ('Savings', '💰', '#6ec6f5', 'expense'),
    ('Other', '📦', '#7a8a7d', 'expense'),
]

def seed_categories(user_id):
    for name, emoji, color, type in DEFAULT_CATEGORIES:
        cat = Category(user_id=user_id, name=name, emoji=emoji, color=color, type=type, is_default=True)
        db.session.add(cat)

# ── AUTH ROUTES ───────────────────────────────────────────────────────────────

@app.route('/api/signup', methods=['POST'])
def signup():
    d = request.json
    if User.query.filter_by(email=d['email']).first():
        return jsonify({'error': 'Email already registered'}), 400
    user = User(name=d['name'], email=d['email'], password_hash=hash_password(d['password']))
    db.session.add(user)
    db.session.flush()
    seed_categories(user.id)
    db.session.commit()
    return jsonify({'user': {'id': user.id, 'name': user.name, 'email': user.email,
                             'monthly_salary': user.monthly_salary, 'theme': user.theme}})

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    user = User.query.filter_by(email=d['email']).first()
    if not user or user.password_hash != hash_password(d['password']):
        return jsonify({'error': 'Incorrect email or password'}), 401
    return jsonify({'user': {'id': user.id, 'name': user.name, 'email': user.email,
                             'monthly_salary': user.monthly_salary, 'theme': user.theme}})

# ── TRANSACTIONS ──────────────────────────────────────────────────────────────

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    uid = request.args.get('user_id')
    month = request.args.get('month')  # YYYY-MM
    q = Transaction.query.filter_by(user_id=uid)
    if month:
        y, m = map(int, month.split('-'))
        start = date(y, m, 1)
        end = date(y, m+1, 1) if m < 12 else date(y+1, 1, 1)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    txs = q.order_by(Transaction.date.desc()).all()
    return jsonify([t.to_dict() for t in txs])

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    d = request.json
    tx = Transaction(
        user_id=d['user_id'], name=d['name'], amount=float(d['amount']),
        type=d['type'], category=d['category'],
        date=date.fromisoformat(d['date']),
        notes=d.get('notes', ''), tags=d.get('tags', ''),
        is_recurring=d.get('is_recurring', False)
    )
    db.session.add(tx)
    db.session.commit()
    return jsonify(tx.to_dict()), 201

@app.route('/api/transactions/<int:tid>', methods=['DELETE'])
def delete_transaction(tid):
    tx = Transaction.query.get_or_404(tid)
    db.session.delete(tx)
    db.session.commit()
    return jsonify({'ok': True})

@app.route('/api/transactions/export', methods=['GET'])
def export_transactions():
    uid = request.args.get('user_id')
    month = request.args.get('month')
    q = Transaction.query.filter_by(user_id=uid)
    if month:
        y, m = map(int, month.split('-'))
        start = date(y, m, 1)
        end = date(y, m+1, 1) if m < 12 else date(y+1, 1, 1)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    txs = q.order_by(Transaction.date.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Description', 'Type', 'Category', 'Amount (₹)', 'Notes', 'Tags'])
    for t in txs:
        writer.writerow([t.date, t.name, t.type, t.category, t.amount, t.notes, t.tags])
    from flask import Response
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=ledger_export.csv'})

# ── WEEKLY ANALYSIS ───────────────────────────────────────────────────────────

@app.route('/api/weekly-analysis', methods=['GET'])
def weekly_analysis():
    uid = request.args.get('user_id')
    today = date.today()
    weeks = []
    for i in range(4):
        end = today - timedelta(days=i*7)
        start = end - timedelta(days=6)
        txs = Transaction.query.filter(
            Transaction.user_id == uid,
            Transaction.date >= start,
            Transaction.date <= end
        ).all()
        income = sum(t.amount for t in txs if t.type == 'income')
        expense = sum(t.amount for t in txs if t.type == 'expense')
        weeks.append({
            'week': f"{start.strftime('%d %b')} – {end.strftime('%d %b')}",
            'income': income, 'expense': expense, 'net': income - expense,
            'tx_count': len(txs)
        })
    return jsonify(list(reversed(weeks)))

# ── BUDGETS ───────────────────────────────────────────────────────────────────

@app.route('/api/budgets', methods=['GET'])
def get_budgets():
    uid = request.args.get('user_id')
    budgets = Budget.query.filter_by(user_id=uid).all()
    return jsonify([b.to_dict() for b in budgets])

@app.route('/api/budgets', methods=['POST'])
def save_budgets():
    d = request.json
    uid = d['user_id']
    Budget.query.filter_by(user_id=uid).delete()
    for item in d['budgets']:
        b = Budget(user_id=uid, category=item['category'], amount=item['amount'])
        db.session.add(b)
    db.session.commit()
    return jsonify({'ok': True})

# ── SAVING GOALS ──────────────────────────────────────────────────────────────

@app.route('/api/goals', methods=['GET'])
def get_goals():
    uid = request.args.get('user_id')
    goals = SavingGoal.query.filter_by(user_id=uid).all()
    return jsonify([g.to_dict() for g in goals])

@app.route('/api/goals', methods=['POST'])
def create_goal():
    d = request.json
    g = SavingGoal(
        user_id=d['user_id'], name=d['name'], target=float(d['target']),
        saved=float(d.get('saved', 0)),
        deadline=date.fromisoformat(d['deadline']) if d.get('deadline') else None,
        emoji=d.get('emoji', '🎯')
    )
    db.session.add(g)
    db.session.commit()
    return jsonify(g.to_dict()), 201

@app.route('/api/goals/<int:gid>', methods=['PUT'])
def update_goal(gid):
    g = SavingGoal.query.get_or_404(gid)
    d = request.json
    if 'saved' in d: g.saved = float(d['saved'])
    if 'name' in d: g.name = d['name']
    if 'target' in d: g.target = float(d['target'])
    if 'deadline' in d: g.deadline = date.fromisoformat(d['deadline']) if d['deadline'] else None
    if 'emoji' in d: g.emoji = d['emoji']
    db.session.commit()
    return jsonify(g.to_dict())

@app.route('/api/goals/<int:gid>', methods=['DELETE'])
def delete_goal(gid):
    g = SavingGoal.query.get_or_404(gid)
    db.session.delete(g)
    db.session.commit()
    return jsonify({'ok': True})

# ── REMINDERS ─────────────────────────────────────────────────────────────────

@app.route('/api/reminders', methods=['GET'])
def get_reminders():
    uid = request.args.get('user_id')
    reminders = Reminder.query.filter_by(user_id=uid).order_by(Reminder.due_date).all()
    return jsonify([r.to_dict() for r in reminders])

@app.route('/api/reminders', methods=['POST'])
def create_reminder():
    d = request.json
    r = Reminder(
        user_id=d['user_id'], title=d['title'], amount=float(d.get('amount', 0)),
        due_date=date.fromisoformat(d['due_date']), type=d.get('type', 'bill'),
        repeat=d.get('repeat', 'monthly'), notes=d.get('notes', '')
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201

@app.route('/api/reminders/<int:rid>', methods=['PUT'])
def update_reminder(rid):
    r = Reminder.query.get_or_404(rid)
    d = request.json
    if 'is_paid' in d:
        if d['is_paid'] and not r.is_paid and r.repeat in ['monthly', 'yearly']:
            next_date = r.due_date
            if r.repeat == 'monthly':
                month = next_date.month % 12 + 1
                year = next_date.year + (1 if next_date.month == 12 else 0)
                try:
                    next_date = next_date.replace(year=year, month=month)
                except ValueError:
                    next_date = next_date.replace(year=year, month=month, day=28)
            elif r.repeat == 'yearly':
                try:
                    next_date = next_date.replace(year=next_date.year + 1)
                except ValueError:
                    next_date = next_date.replace(year=next_date.year + 1, day=28)
            new_r = Reminder(user_id=r.user_id, title=r.title, amount=r.amount, due_date=next_date, type=r.type, repeat=r.repeat, notes=r.notes)
            db.session.add(new_r)
            r.repeat = 'none'
        r.is_paid = d['is_paid']
    if 'title' in d: r.title = d['title']
    if 'amount' in d: r.amount = float(d['amount'])
    if 'due_date' in d: r.due_date = date.fromisoformat(d['due_date'])
    if 'notes' in d: r.notes = d['notes']
    db.session.commit()
    return jsonify(r.to_dict())

@app.route('/api/reminders/<int:rid>', methods=['DELETE'])
def delete_reminder(rid):
    r = Reminder.query.get_or_404(rid)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'ok': True})

# ── CATEGORIES ────────────────────────────────────────────────────────────────

@app.route('/api/categories', methods=['GET'])
def get_categories():
    uid = request.args.get('user_id')
    cats = Category.query.filter_by(user_id=uid).all()
    return jsonify([c.to_dict() for c in cats])

@app.route('/api/categories', methods=['POST'])
def add_category():
    d = request.json
    cat = Category(user_id=d['user_id'], name=d['name'],
                   emoji=d.get('emoji', '📦'), color=d.get('color', '#a8e6a3'),
                   type=d.get('type', 'expense'))
    db.session.add(cat)
    db.session.commit()
    return jsonify(cat.to_dict()), 201

@app.route('/api/categories/<int:cid>', methods=['PUT'])
def update_category(cid):
    cat = Category.query.get_or_404(cid)
    d = request.json
    if 'name' in d: cat.name = d['name']
    if 'emoji' in d: cat.emoji = d['emoji']
    if 'color' in d: cat.color = d['color']
    if 'type' in d: cat.type = d['type']
    db.session.commit()
    return jsonify(cat.to_dict())

@app.route('/api/categories/<int:cid>', methods=['DELETE'])
def delete_category(cid):
    cat = Category.query.get_or_404(cid)
    # Reassign all transactions using this category to 'Other'
    # so they don't become orphaned ghost entries on charts/views
    Transaction.query.filter_by(
        user_id=cat.user_id, category=cat.name
    ).update({'category': 'Other'})
    # Also clean up any budget entries for this category
    Budget.query.filter_by(
        user_id=cat.user_id, category=cat.name
    ).delete()
    db.session.delete(cat)
    db.session.commit()
    return jsonify({'ok': True})

# ── SETTINGS ──────────────────────────────────────────────────────────────────

@app.route('/api/settings', methods=['PUT'])
def update_settings():
    d = request.json
    user = User.query.get_or_404(d['user_id'])
    if 'monthly_salary' in d: user.monthly_salary = float(d['monthly_salary'])
    if 'theme' in d: user.theme = d['theme']
    db.session.commit()
    return jsonify({'ok': True, 'theme': user.theme, 'monthly_salary': user.monthly_salary})

# ── SERVE FRONTEND ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)
