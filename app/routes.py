from datetime import datetime
from flask import render_template, flash, redirect, url_for
from flask_login import current_user, login_user, logout_user, login_required
from app import app, models, db
from app.forms import SearchForm, LoginForm, RegistrationForm
from app.models import User, Record, UserRole


@app.route('/', methods=['GET', 'POST'])
@app.route('/index')
def index():
   form = SearchForm()
   return render_template(
      'index.html', 
      title='Главная', 
      year=datetime.now().year,
      form=form
      )
   
@app.route('/login', methods=['GET', 'POST'])
def login():
   if current_user.is_authenticated:
      return redirect(url_for('index'))
   form = LoginForm()
   if form.validate_on_submit():
      user = User.query.filter_by(username=form.username.data).first()
      if user is None or not user.check_password(form.password.data):
         flash('Неверный логин или пароль')
         return redirect(url_for('login'))
      login_user(user, remember=form.remember_me.data)
      return redirect(url_for('index'))
   return render_template(
      'login.html', 
      title='Вход', 
      form=form, 
      year=datetime.now().year
      )

@app.route('/logout')
def logout():
   logout_user()
   return redirect(url_for('index'))
   
@app.route('/register', methods=['GET', 'POST'])
def register():
   if current_user.is_authenticated:
      return redirect(url_for('index'))
   form = RegistrationForm()
   if form.validate_on_submit():
      user = User(username=form.username.data, email=form.email.data)
      user_role = UserRole(name=form.user_role.data)
      db.session.add(user_role)
      user.role.append(user_role)
      user.set_password(form.password.data)
      db.session.add(user)
      db.session.commit()
      flash('Регистрация прошла успешно')
      return redirect(url_for('login'))
   return render_template(
      'register.html', 
      title='Регистрация',
      form=form)

@app.route('/admin')
@login_required
def admin():
   return render_template(
      'admin_panel.html')

@app.route('/moderator')
@login_required
def moderator():
   return render_template(
      'moderator_panel.html')

@app.route('/search')
def search():
   records = Record.query.all()
   form = SearchForm()
   return render_template(
      'search.html', 
      title='Результаты поиска',
      year=datetime.now().year,
      records=records,
      form=form
      )

