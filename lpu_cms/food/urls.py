from django.urls import path
from . import views

app_name = 'food'

urlpatterns = [
    # Student facing
    path('',                            views.stall_list,          name='stall_list'),
    path('stall/<int:stall_id>/',       views.stall_menu,          name='stall_menu'),
    path('cart/<int:stall_id>/',        views.cart_view,           name='cart'),
    path('checkout/<int:stall_id>/',    views.checkout,            name='checkout'),
    path('orders/',                     views.my_orders,           name='my_orders'),
    path('orders/<int:order_id>/',      views.order_detail,        name='order_detail'),
    path('cart/clear/',                 views.clear_cart,          name='clear_cart'),

    # Stall owner
    path('owner/',                      views.owner_dashboard,     name='owner_dashboard'),
    path('owner/analytics/',            views.demand_analytics,    name='demand_analytics'),

    # AJAX
    path('api/cart/add/<int:item_id>/',    views.add_to_cart,         name='add_to_cart'),
    path('api/cart/remove/<int:item_id>/', views.remove_from_cart,    name='remove_from_cart'),
    path('api/order/<int:order_id>/status/', views.update_order_status, name='update_status'),
    path('api/slots/<int:stall_id>/',      views.slot_availability,   name='slot_availability'),
    # Menu management (stall owner)
path('menu/',                          views.manage_menu,     name='manage_menu'),
path('menu/add/',                      views.add_item,        name='add_item'),
path('menu/edit/<int:item_id>/',       views.edit_item,       name='edit_item'),
path('menu/toggle/<int:item_id>/',     views.toggle_item,     name='toggle_item'),
path('menu/delete/<int:item_id>/',     views.delete_item,     name='delete_item'),
path('menu/category/add/',             views.add_category,    name='add_category'),
path('menu/category/delete/<int:cat_id>/', views.delete_category, name='delete_category'),
]