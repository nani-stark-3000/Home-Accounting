from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///home_accounting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Data Models
class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    holder = db.Column(db.String(100), nullable=False)
    particulars = db.Column(db.Text, nullable=True)
    amount = db.Column(db.Float, default=0.0)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'income' or 'expense'

class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    purpose = db.Column(db.String(255), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)

    category = db.relationship('Category', backref=db.backref('incomes', lazy=True))
    account = db.relationship('Account', backref=db.backref('incomes', lazy=True))

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    purpose = db.Column(db.String(255), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)

    category = db.relationship('Category', backref=db.backref('expenses', lazy=True))
    account = db.relationship('Account', backref=db.backref('expenses', lazy=True))

# Daily Snapshot Model (to save reports)
class DailySnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), unique=True, nullable=False)
    total_income = db.Column(db.Float, nullable=False)
    total_expense = db.Column(db.Float, nullable=False)
    net_balances = db.Column(db.PickleType, nullable=False)  # Stores account balances

# Function to save daily snapshot automatically
def save_daily_snapshot():
    today = datetime.today().strftime('%Y-%m-%d')
    incomes = Income.query.filter_by(date=today).all()
    expenses = Expense.query.filter_by(date=today).all()
    accounts = Account.query.all()

    total_income = sum([i.amount for i in incomes])
    total_expense = sum([e.amount for e in expenses])
    net_balances = {account.name: account.amount for account in accounts}

    existing_snapshot = DailySnapshot.query.filter_by(date=today).first()
    if existing_snapshot:
        existing_snapshot.total_income = total_income
        existing_snapshot.total_expense = total_expense
        existing_snapshot.net_balances = net_balances
    else:
        snapshot = DailySnapshot(date=today, total_income=total_income, total_expense=total_expense, net_balances=net_balances)
        db.session.add(snapshot)
    db.session.commit()

# Routes
@app.route('/')
def dashboard():
    return render_template('dashboard.html')

from flask import render_template, request, redirect, url_for, flash
from datetime import datetime

@app.route('/add_record/<record_type>', methods=['GET', 'POST'])
def add_record(record_type):
    if record_type not in ['income', 'expense']:
        flash('Invalid record type!', 'danger')
        return redirect(url_for('dashboard'))  # Redirect to dashboard on invalid type

    if request.method == 'POST':
        try:
            amount = float(request.form['amount'])
            category_id = int(request.form['category'])
            purpose = request.form['purpose']
            account_id = int(request.form['account'])
            date = request.form.get('date', datetime.today().strftime('%Y-%m-%d'))

            account = Account.query.get(account_id)
            if not account:
                flash('Invalid account selected!', 'danger')
                return redirect(url_for('add_record', record_type=record_type))

            # 💡 Check account balance before adding an expense
            if record_type == 'expense':
                if account.amount < amount:
                    flash(f'Insufficient balance in {account.name}! Available: ₹{account.amount}', 'danger')
                    return redirect(url_for('add_record', record_type=record_type))

                new_record = Expense(amount=amount, category_id=category_id, purpose=purpose, account_id=account_id, date=date)
                account.amount -= amount  # Deduct from account for expense

            else:  # For income
                new_record = Income(amount=amount, category_id=category_id, purpose=purpose, account_id=account_id, date=date)
                account.amount += amount  # Add to account for income

            db.session.add(new_record)
            db.session.commit()

            flash(f'{record_type.capitalize()} added successfully!', 'success')
            return redirect(url_for('manage_records', record_type=record_type))

        except ValueError:
            flash('Invalid input! Please enter correct values.', 'danger')
            return redirect(url_for('add_record', record_type=record_type))

    # GET request: Load form with relevant categories and accounts
    categories = Category.query.filter_by(type=record_type).all()
    accounts = Account.query.all()
    today_date = datetime.today().strftime('%Y-%m-%d')

    return render_template('add_record.html',
                           categories=categories,
                           accounts=accounts,
                           record_type=record_type,
                           today_date=today_date)


@app.route('/manage_records/<record_type>', methods=['GET', 'POST'])
def manage_records(record_type):
    if request.method == 'POST':
        try:
            record_id = int(request.form['record_id'])
            new_amount = float(request.form['amount'])
            new_category_id = int(request.form['category'])
            new_purpose = request.form['purpose']
            new_account_id = int(request.form['account'])
            new_date = request.form['date']

            # Fetch the record and accounts
            record = Income.query.get(record_id) if record_type == 'income' else Expense.query.get(record_id)
            old_account = Account.query.get(record.account_id)
            new_account = Account.query.get(new_account_id)

            if not new_account:
                flash('Invalid account selected!', 'danger')
                return redirect(url_for('manage_records', record_type=record_type))

            # Revert the old transaction effect
            if record_type == 'income':
                old_account.amount -= record.amount
            else:
                old_account.amount += record.amount

            # Check for sufficient funds before applying new changes (for expenses)
            if record_type == 'expense' and new_account.amount < new_amount:
                flash('Insufficient funds in the selected account!', 'danger')
                return redirect(url_for('manage_records', record_type=record_type))

            # Apply the new transaction effect
            if record_type == 'income':
                new_account.amount += new_amount
            else:
                new_account.amount -= new_amount

            # Update the record
            record.amount = new_amount
            record.category_id = new_category_id
            record.purpose = new_purpose
            record.account_id = new_account_id
            record.date = new_date

            db.session.commit()
            flash(f'{record_type.capitalize()} updated successfully!', 'success')
        except ValueError:
            flash('Invalid input! Please enter correct values.', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating record: {str(e)}', 'danger')

        return redirect(url_for('manage_records', record_type=record_type))

    records = Income.query.all() if record_type == 'income' else Expense.query.all()
    categories = Category.query.all()
    accounts = Account.query.all()
    return render_template('manage_records.html', record_type=record_type, records=records, categories=categories, accounts=accounts)

@app.route('/delete_record/<record_type>/<int:record_id>', methods=['POST'])
def delete_record(record_type, record_id):
    record = Income.query.get_or_404(record_id) if record_type == 'income' else Expense.query.get_or_404(record_id)
    account = Account.query.get(record.account_id)

    if not account:
        flash('Associated account not found!', 'danger')
        return redirect(url_for('manage_records', record_type=record_type))

    # Prevent deletion if it causes negative balance for expenses
    if record_type == 'expense' and (account.amount + record.amount) < 0:
        flash('Cannot delete this expense record as it would result in a negative account balance.', 'danger')
        return redirect(url_for('manage_records', record_type=record_type))

    # Adjust balance
    if record_type == 'income':
        account.amount -= record.amount
    else:
        account.amount += record.amount

    try:
        db.session.delete(record)
        db.session.commit()
        flash(f'{record_type.capitalize()} deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting record: {str(e)}', 'danger')

    return redirect(url_for('manage_records', record_type=record_type))

# Account Management
@app.route('/accounts', methods=['GET', 'POST'])
def manage_accounts():
    if request.method == 'POST':
        name = request.form['name']
        holder = request.form['holder']
        particulars = request.form.get('particulars', '')
        amount = float(request.form.get('amount', 0.0))

        new_account = Account(name=name, holder=holder, particulars=particulars, amount=amount)
        db.session.add(new_account)
        db.session.commit()
        flash('Account added successfully!', 'success')
        return redirect(url_for('manage_accounts'))

    accounts = Account.query.all()
    return render_template('manage_accounts.html', accounts=accounts)

@app.route('/delete_account/<int:account_id>', methods=['POST'])
def delete_account(account_id):
    account = Account.query.get_or_404(account_id)

    # Check if the account has any linked expenses or incomes
    if account.expenses or account.incomes:
        flash('Cannot delete account with existing transactions!', 'danger')
        return redirect(url_for('manage_accounts'))

    db.session.delete(account)
    db.session.commit()
    flash('Account deleted successfully!', 'success')
    return redirect(url_for('manage_accounts'))


# Category Management
@app.route('/categories', methods=['GET', 'POST'])
def manage_categories():
    if request.method == 'POST':
        name = request.form['name']
        type_ = request.form['type']
        new_category = Category(name=name, type=type_)
        db.session.add(new_category)
        db.session.commit()
        flash('Category added successfully!', 'success')
        return redirect(url_for('manage_categories'))

    categories = Category.query.all()
    return render_template('manage_categories.html', categories=categories)

@app.route('/delete_category/<int:category_id>', methods=['POST'])
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted successfully!', 'success')
    return redirect(url_for('manage_categories'))

# Route for Daily Report
@app.route('/daily_report', methods=['GET'])
def daily_report():
    today = datetime.today().strftime('%Y-%m-%d')
    save_daily_snapshot()  # Automatically save today's snapshot

    selected_date = request.args.get('date', today)

    # Fetch income and expenses for the selected date
    snapshot = DailySnapshot.query.filter_by(date=selected_date).first()
    
    if snapshot:
        incomes = Income.query.filter_by(date=selected_date).all()
        expenses = Expense.query.filter_by(date=selected_date).all()
        net_values = snapshot.net_balances
    else:
        incomes = []
        expenses = []
        net_values = {}

    return render_template('daily_report.html', 
                           selected_date=selected_date, 
                           incomes=incomes, 
                           expenses=expenses, 
                           net_values=net_values)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

