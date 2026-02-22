from django import forms
from .models import Order, OrderItem, MenuItem, BreakSlot


class OrderForm(forms.Form):
    """
    Student selects a break slot when placing an order.
    Items are handled separately via cart logic.
    """
    slot = forms.ModelChoiceField(
        queryset=BreakSlot.objects.none(),
        label='Pick-up Time Slot',
        empty_label='Select a break slot',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    note = forms.CharField(
        required=False,
        label='Special Instructions',
        widget=forms.Textarea(attrs={
            'class':       'form-control',
            'rows':        2,
            'placeholder': 'e.g. No onions, extra spicy...'
        })
    )

    def __init__(self, stall, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show slots for this stall that aren't full
        self.fields['slot'].queryset = BreakSlot.objects.filter(
            stall=stall
        )


class OrderStatusForm(forms.Form):
    """Stall owner updates order status"""
    STATUS_CHOICES = [
        ('P', 'Pending'),
        ('C', 'Confirmed'),
        ('R', 'Ready for Pickup'),
        ('X', 'Collected'),
        ('N', 'Cancelled'),
    ]
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )