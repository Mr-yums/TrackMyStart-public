from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class RegisterForm(FlaskForm):
    display_name = StringField("Pseudo", validators=[DataRequired(), Length(2, 40)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField(
        "Mot de passe", validators=[DataRequired(), Length(8, 128)]
    )
    confirm = PasswordField(
        "Confirmation",
        validators=[
            DataRequired(),
            EqualTo("password", message="Les mots de passe diffèrent."),
        ],
    )
    terms = BooleanField(
        "J'accepte les conditions d'utilisation", validators=[DataRequired()]
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Mot de passe", validators=[DataRequired()])
    remember = BooleanField("Se souvenir de moi")


class ForgotForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Length(max=255)])


class ResetForm(FlaskForm):
    password = PasswordField(
        "Nouveau mot de passe", validators=[DataRequired(), Length(8, 128)]
    )
    confirm = PasswordField(
        "Confirmation",
        validators=[
            DataRequired(),
            EqualTo("password", message="Les mots de passe diffèrent."),
        ],
    )


class ChangePasswordForm(FlaskForm):
    current = PasswordField("Mot de passe actuel", validators=[DataRequired()])
    password = PasswordField(
        "Nouveau mot de passe", validators=[DataRequired(), Length(8, 128)]
    )
    confirm = PasswordField(
        "Confirmation",
        validators=[
            DataRequired(),
            EqualTo("password", message="Les mots de passe diffèrent."),
        ],
    )
