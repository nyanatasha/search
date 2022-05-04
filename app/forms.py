from flask_wtf import FlaskForm
from wtforms_sqlalchemy.fields import QuerySelectMultipleField
from wtforms.widgets import ListWidget, CheckboxInput
from wtforms import StringField, SubmitField, BooleanField, PasswordField, SelectField, IntegerField
from wtforms.validators import ValidationError, DataRequired, Length, Email, EqualTo
from app.models import User, SourceDatabase, DocumentType
from app import db


class SearchForm(FlaskForm):
    search_request = StringField('', validators=[DataRequired()], render_kw={'placeholder': 'Поисковый запрос'})
    title = StringField('Заглавие', render_kw={'placeholder': 'Заглавие'})
    author = StringField('Автор', render_kw={'placeholder': 'Автор'})
    journal_title = StringField('Название журнала', render_kw={'placeholder': 'Название журнала'})
    isbn_issn_doi = StringField('ISBN/ISSN/DOI', render_kw={'placeholder': 'ISBN/ISSN/DOI'})
    keywords = StringField('Ключевые слова', render_kw={'placeholder': 'Ключевые слова'})
    submit = SubmitField('Найти')
    publishing_year_1 = IntegerField('Опубликован от')
    publishing_year_2 = IntegerField('До')
    source_database = QuerySelectMultipleField(
        'База данных',
        query_factory=lambda: SourceDatabase.query.all(),
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput()
    )
    document_type = QuerySelectMultipleField(
        'Тип документа',
        query_factory=lambda: DocumentType.query.all(),
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput()
    )

    def validate_publishing_year(self, publishing_year_1, publishing_year_2):
        if publishing_year_1.data > publishing_year_2.data:
            raise ValidationError('Год начала промежутка публикации должен быть меньше или равен году его окончания')


class RegistrationForm(FlaskForm):
    username = StringField('', [Length(min=4, max=25), DataRequired()], render_kw={'placeholder': 'Логин'})
    email = StringField('', [Length(min=6, max=35), DataRequired()], render_kw={'placeholder': 'Email'})
    password = PasswordField('', validators=[DataRequired()], render_kw={'placeholder': 'Пароль'})
    password2 = PasswordField(
        '',
        validators=[DataRequired(), EqualTo('password')],
        render_kw={'placeholder': 'Повторите пароль'}
    )
    user_role = SelectField(u'', choices=[('administrator', 'Администратор'), ('moderator', 'Модератор')],
                            validators=[DataRequired()])
    submit = SubmitField('Зарегистрироваться')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Пожалуйста, используйте другой логин')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Пожалуйста используйте другой Email')


class LoginForm(FlaskForm):
    username = StringField('', validators=[DataRequired()], render_kw={'placeholder': 'Логин'})
    password = PasswordField('', validators=[DataRequired()], render_kw={'placeholder': 'Пароль'})
    remember_me = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')
