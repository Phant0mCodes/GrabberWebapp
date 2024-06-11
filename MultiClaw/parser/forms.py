from django import forms
from parser.models import GrabSettings, ShopwareShop

CLASS_ATTR = """bg-gray-50 border border-gray-300 rounded-lg text-gray-900 sm:text-sm focus:ring-primary-600 
focus:border-primary-600 block p-2.5 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white 
dark:focus:ring-blue-500 dark:focus:border-blue-500"""

CLASS_ATTR_2 = """bg-gray-50 border border-gray-300 rounded-e-lg text-gray-900 sm:text-sm focus:ring-primary-600 
focus:border-primary-600 block p-1 dark:bg-gray-700 dark:border-gray-600 dark:placeholder-gray-400 dark:text-white 
dark:focus:ring-blue-500 dark:focus:border-blue-500 w-full"""

LABEL_CLASS = ['text-white']


class SettingsForm(forms.ModelForm):

    class Meta:
        model = GrabSettings
        fields = "__all__"
        widgets = {
            'user': forms.HiddenInput(),
            'parser_name': forms.HiddenInput(),
            'parser_mode': forms.Select(),
            'category_urls': forms.Textarea(attrs={'placeholder': 'Please enter category URLs, one per line.', 'required': False}),
            'product_urls': forms.Textarea(attrs={'placeholder': 'Please enter product URLs, one per line.'}),
            'keywords': forms.Textarea(attrs={'placeholder': 'Please enter Keywords like you would entering in source shop.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parser_mode'].choices = [choice for choice in self.fields['parser_mode'].choices if choice[0] != '']
        for name, field in self.fields.items():
            field.widget.attrs['class'] = CLASS_ATTR
            if field.widget.__class__.__name__ == 'Textarea':
                field.widget.attrs.update({'cols': None})
                field.widget.attrs['class'] += ' w-full'
                
            if field.widget.__class__.__name__ == 'NumberInput':
                field.widget.attrs['class'] += ' w-24'
            

class ShopwareShopForm(forms.ModelForm):
    
    class Meta:
        model = ShopwareShop
        fields = "__all__"
        widgets = {
            'user': forms.HiddenInput(),
            'valid': forms.HiddenInput(),
            'password': forms.PasswordInput(),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'password':
                P_CLASS = CLASS_ATTR_2.split(' ')
                P_CLASS.remove('rounded-e-lg')
                field.widget.attrs.update({'class': ' '.join(P_CLASS)})
                field.widget.attrs.update({'required': False})
            else:
                field.widget.attrs.update({'class': CLASS_ATTR_2})
            self.fields['domain'].widget.attrs.update({'placeholder': 'example.com'})
            self.fields['username'].widget.attrs.update({'placeholder': 'Username'})
            self.fields['password'].widget.attrs.update({'placeholder': 'Password'})