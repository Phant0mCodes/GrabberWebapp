# myapp/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import CustomUser

CLASS_ATTR = """bg-gray-50 border border-gray-300 text-gray-900 sm:text-sm rounded-lg focus:ring-primary-600 
focus:border-primary-600 block p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white 
dark:focus:ring-blue-500 dark:focus:border-blue-500 w-full"""

class CustomUserCreationForm(UserCreationForm):
    jabber_address = forms.CharField(max_length=255, required=False, help_text='Optional.')
    tos_accepted = forms.BooleanField(required=False, help_text='Optional.')

    class Meta:
        model = CustomUser
        fields = ('username', 'jabber_address', 'password1', 'password2', 'tos_accepted')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the class attribute for each field
        self.fields['username'].widget.attrs.update({
            'type': 'username', 'class': CLASS_ATTR, 'placeholder': "Your username"
            })
        self.fields['jabber_address'].widget.attrs.update({
            'class': CLASS_ATTR,
            'placeholder': "Jabber address (optional)"
            })
        self.fields['password1'].widget.attrs.update({'class': CLASS_ATTR, 'placeholder': "Your password"})
        self.fields['password2'].widget.attrs.update({'class': CLASS_ATTR, 'placeholder': "Your password"})


class CustomAuthForm(AuthenticationForm):
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set the class attribute for each field
        self.fields['username'].widget.attrs.update({
            'type': 'username', 'class': CLASS_ATTR, 'placeholder': "Your username"
            })

        self.fields['password'].widget.attrs.update({'class': CLASS_ATTR, 'placeholder': "Your password"})
