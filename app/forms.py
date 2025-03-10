# app/forms.py
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.views import PasswordResetView
from django import forms
from .models import dish, City, User
User = get_user_model()
class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email','tabel_number']
        labels = {'email': 'Email'}

class updUserForm(forms.ModelForm):
    city = forms.ModelChoiceField(queryset=City.objects.all(), empty_label=None, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'city']

class DishForm(forms.ModelForm):
    class Meta:
        model = dish
        fields = ['dish_name', 'dish_price', 'category']
        widgets = {
            'dish_name': forms.TextInput(attrs={'class': 'form-control'}),
            'dish_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
        }
