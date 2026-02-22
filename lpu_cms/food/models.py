from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from attendance.models import Student


# ─────────────────────────────────────────
# FOOD STALL
# Each physical stall on campus
# ─────────────────────────────────────────
class FoodStall(models.Model):
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    location    = models.CharField(max_length=100)  # e.g. "Block 32, Ground Floor"
    owner       = models.OneToOneField(User, on_delete=models.SET_NULL, null=True)
    photo       = models.ImageField(upload_to='stall_photos/', blank=True, null=True)
    is_open     = models.BooleanField(default=True)
    opens_at    = models.TimeField(default='08:00')
    closes_at   = models.TimeField(default='20:00')

    def __str__(self):
        return self.name


# ─────────────────────────────────────────
# CATEGORY
# Groups menu items — Snacks, Meals, Drinks
# ─────────────────────────────────────────
class Category(models.Model):
    name  = models.CharField(max_length=50)
    stall = models.ForeignKey(FoodStall, on_delete=models.CASCADE, related_name='categories')
    icon  = models.CharField(max_length=10, default='🍽')  # emoji icon

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self):
        return f"{self.name} — {self.stall.name}"


# ─────────────────────────────────────────
# MENU ITEM
# Individual food/drink item in a stall
# ─────────────────────────────────────────
class MenuItem(models.Model):
    stall       = models.ForeignKey(FoodStall, on_delete=models.CASCADE, related_name='menu_items')
    category    = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price       = models.DecimalField(max_digits=6, decimal_places=2)
    photo       = models.ImageField(upload_to='menu_photos/', blank=True, null=True)
    is_available = models.BooleanField(default=True)
    is_veg      = models.BooleanField(default=True)
    prep_time   = models.IntegerField(default=5, help_text='Preparation time in minutes')

    def __str__(self):
        return f"{self.name} — ₹{self.price}"


# ─────────────────────────────────────────
# BREAK TIME SLOT
# Pre-defined slots students can pick
# e.g. 10:30–11:00, 12:30–13:00
# ─────────────────────────────────────────
class BreakSlot(models.Model):
    stall      = models.ForeignKey(FoodStall, on_delete=models.CASCADE, related_name='slots')
    label      = models.CharField(max_length=50)   # e.g. "Morning Break"
    start_time = models.TimeField()
    end_time   = models.TimeField()
    max_orders = models.IntegerField(default=30)   # capacity per slot

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return f"{self.stall.name} | {self.label} ({self.start_time}–{self.end_time})"

    @property
    def current_order_count(self):
        """How many orders already booked for today in this slot"""
        today = timezone.now().date()
        return self.orders.filter(
            order_date=today,
            status__in=['P', 'C', 'R']
        ).count()

    @property
    def is_full(self):
        return self.current_order_count >= self.max_orders

    @property
    def slots_left(self):
        return max(0, self.max_orders - self.current_order_count)


# ─────────────────────────────────────────
# ORDER
# One order = one student's pre-order
# for a specific slot on a specific date
# ─────────────────────────────────────────
class Order(models.Model):

    STATUS_CHOICES = [
        ('P', 'Pending'),      # just placed
        ('C', 'Confirmed'),    # stall confirmed
        ('R', 'Ready'),        # food is ready for pickup
        ('X', 'Collected'),    # student picked up
        ('N', 'Cancelled'),    # cancelled
    ]

    student    = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='orders')
    stall      = models.ForeignKey(FoodStall, on_delete=models.CASCADE, related_name='orders')
    slot       = models.ForeignKey(BreakSlot, on_delete=models.CASCADE, related_name='orders')
    order_date = models.DateField(default=timezone.now)
    status     = models.CharField(max_length=1, choices=STATUS_CHOICES, default='P')
    total      = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    note       = models.TextField(blank=True, help_text='Special instructions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} — {self.student} @ {self.slot.label}"

    def calculate_total(self):
        """Recalculates and saves total from all order items"""
        total = sum(item.subtotal for item in self.items.all())
        self.total = total
        self.save()
        return total


# ─────────────────────────────────────────
# ORDER ITEM
# Individual line item within an order
# ─────────────────────────────────────────
class OrderItem(models.Model):
    order     = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity  = models.PositiveIntegerField(default=1)
    price     = models.DecimalField(max_digits=6, decimal_places=2)  # price at time of order

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name}"

    @property
    def subtotal(self):
        return self.price * self.quantity


# ─────────────────────────────────────────
# DEMAND TRACKER
# Records hourly order counts per stall
# Used by AI to predict peak times
# ─────────────────────────────────────────
class DemandRecord(models.Model):
    stall       = models.ForeignKey(FoodStall, on_delete=models.CASCADE)
    date        = models.DateField()
    hour        = models.IntegerField()          # 0–23
    order_count = models.IntegerField(default=0)
    day_of_week = models.IntegerField(default=0) # 0=Mon, 6=Sun

    class Meta:
        unique_together = ('stall', 'date', 'hour')
        ordering = ['date', 'hour']

    def __str__(self):
        return f"{self.stall.name} | {self.date} {self.hour}:00 — {self.order_count} orders"