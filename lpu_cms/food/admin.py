from django.contrib import admin
from .models import FoodStall, Category, MenuItem, BreakSlot, Order, OrderItem, DemandRecord


class OrderItemInline(admin.TabularInline):
    model  = OrderItem
    extra  = 0
    fields = ['menu_item', 'quantity', 'price']


class MenuItemInline(admin.TabularInline):
    model  = MenuItem
    extra  = 0
    fields = ['name', 'price', 'is_available', 'is_veg']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = ['id', 'student', 'stall', 'slot', 'order_date', 'status', 'total']
    list_filter   = ['status', 'stall', 'order_date']
    search_fields = ['student__user__first_name', 'student__registration_no']
    inlines       = [OrderItemInline]


@admin.register(FoodStall)
class FoodStallAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'owner', 'is_open']
    inlines      = [MenuItemInline]


admin.site.register(Category)
admin.site.register(MenuItem)
admin.site.register(BreakSlot)
admin.site.register(OrderItem)
admin.site.register(DemandRecord)