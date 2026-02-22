from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Sum
from collections import defaultdict
import json

from attendance.models import Student
from .models import FoodStall, MenuItem, BreakSlot, Order, OrderItem, DemandRecord,Category
from .forms import OrderForm, OrderStatusForm


# ─────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────

def get_student(user):
    try:
        return Student.objects.get(user=user)
    except Student.DoesNotExist:
        return None


def get_stall_owner(user):
    try:
        return FoodStall.objects.get(owner=user)
    except FoodStall.DoesNotExist:
        return None


def get_cart(request):
    """Cart stored in session as { 'item_id': quantity }"""
    return request.session.get('cart', {})


def save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True


def cart_total_items(request):
    cart = get_cart(request)
    return sum(cart.values())


def update_demand_record(stall):
    """
    Called every time an order is placed.
    Increments the demand counter for the current hour.
    Used later by AI to predict peak times.
    """
    now  = timezone.now()
    date = now.date()
    hour = now.hour

    record, created = DemandRecord.objects.get_or_create(
        stall=stall,
        date=date,
        hour=hour,
        defaults={'day_of_week': date.weekday(), 'order_count': 0}
    )
    record.order_count += 1
    record.save()


# ─────────────────────────────────────────────────────
# STALL LISTING — All stalls on campus
# ─────────────────────────────────────────────────────

@login_required
def stall_list(request):
    stalls = FoodStall.objects.filter(is_open=True)

    # Attach cart count to context for topbar badge
    context = {
        'stalls':     stalls,
        'cart_count': cart_total_items(request),
    }
    return render(request, 'food/stall_list.html', context)


# ─────────────────────────────────────────────────────
# STALL MENU — Browse items, add to cart
# ─────────────────────────────────────────────────────

@login_required
def stall_menu(request, stall_id):
    stall      = get_object_or_404(FoodStall, id=stall_id, is_open=True)
    categories = stall.categories.prefetch_related('menuitem_set').all()

    # Items not in any category
    uncategorized = stall.menu_items.filter(
        category__isnull=True,
        is_available=True
    )

    cart = get_cart(request)

    context = {
        'stall':         stall,
        'categories':    categories,
        'uncategorized': uncategorized,
        'cart':          cart,
        'cart_count':    cart_total_items(request),
    }
    return render(request, 'food/stall_menu.html', context)


# ─────────────────────────────────────────────────────
# CART — Add / Remove / Update
# ─────────────────────────────────────────────────────

@login_required
def add_to_cart(request, item_id):
    """AJAX — adds one item to session cart"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    item = get_object_or_404(MenuItem, id=item_id, is_available=True)
    cart = get_cart(request)

    key       = str(item_id)
    cart[key] = cart.get(key, 0) + 1
    save_cart(request, cart)

    return JsonResponse({
        'success':    True,
        'item_name':  item.name,
        'quantity':   cart[key],
        'cart_count': sum(cart.values()),
    })


@login_required
def remove_from_cart(request, item_id):
    """AJAX — removes one item from session cart"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    cart = get_cart(request)
    key  = str(item_id)

    if key in cart:
        cart[key] -= 1
        if cart[key] <= 0:
            del cart[key]
        save_cart(request, cart)

    return JsonResponse({
        'success':    True,
        'cart_count': sum(cart.values()),
    })


@login_required
def clear_cart(request):
    request.session['cart'] = {}
    request.session.modified = True
    messages.info(request, 'Cart cleared.')
    return redirect('food:stall_list')


# ─────────────────────────────────────────────────────
# CART PAGE — Review before checkout
# ─────────────────────────────────────────────────────

@login_required
def cart_view(request, stall_id):
    stall = get_object_or_404(FoodStall, id=stall_id)
    cart  = get_cart(request)

    if not cart:
        messages.info(request, 'Your cart is empty.')
        return redirect('food:stall_menu', stall_id=stall_id)

    # Build cart items list with full details
    cart_items = []
    grand_total = 0

    for item_id, qty in cart.items():
        try:
            item     = MenuItem.objects.get(id=int(item_id), stall=stall)
            subtotal = item.price * qty
            cart_items.append({
                'item':     item,
                'quantity': qty,
                'subtotal': subtotal,
            })
            grand_total += subtotal
        except MenuItem.DoesNotExist:
            continue

    if not cart_items:
        messages.error(request, 'No valid items in cart for this stall.')
        return redirect('food:stall_menu', stall_id=stall_id)

    form = OrderForm(stall)

    context = {
        'stall':       stall,
        'cart_items':  cart_items,
        'grand_total': grand_total,
        'form':        form,
        'cart_count':  cart_total_items(request),
    }
    return render(request, 'food/cart.html', context)


# ─────────────────────────────────────────────────────
# CHECKOUT — Place the order
# ─────────────────────────────────────────────────────

@login_required
def checkout(request, stall_id):
    stall   = get_object_or_404(FoodStall, id=stall_id)
    student = get_student(request.user)

    # Ensure student exists
    if not student:
        messages.error(request, 'Student profile not found.')
        return redirect('food:stall_list')

    # Ensure cart is not empty
    cart = get_cart(request)
    if not cart:
        messages.error(request, 'Your cart is empty.')
        return redirect('food:stall_menu', stall_id=stall_id)

    # Only allow POST
    if request.method != 'POST':
        return redirect('food:cart', stall_id=stall_id)

    form = OrderForm(stall, request.POST)

    # If form invalid → redirect safely
    if not form.is_valid():
        messages.error(request, 'Please correct the errors in the form.')
        return redirect('food:cart', stall_id=stall_id)

    slot = form.cleaned_data['slot']
    note = form.cleaned_data.get('note', '')

    # Check slot capacity
    if slot.is_full:
        messages.error(
            request,
            f'Sorry! {slot.label} is fully booked. '
            f'Please choose a different time slot.'
        )
        return redirect('food:cart', stall_id=stall_id)

    # Create order
    order = Order.objects.create(
        student=student,
        stall=stall,
        slot=slot,
        order_date=timezone.now().date(),
        note=note,
        status='P',
    )

    # Add order items
    grand_total = 0
    for item_id, qty in cart.items():
        try:
            item = MenuItem.objects.get(id=int(item_id), stall=stall)

            OrderItem.objects.create(
                order=order,
                menu_item=item,
                quantity=qty,
                price=item.price,
            )

            grand_total += item.price * qty

        except MenuItem.DoesNotExist:
            continue

    # Save total
    order.total = grand_total
    order.save()

    # Update demand analytics
    update_demand_record(stall)

    # Clear cart
    request.session['cart'] = {}
    request.session.modified = True

    messages.success(
        request,
        f'Order #{order.id} placed! '
        f'Pick up at {slot.label} ({slot.start_time.strftime("%I:%M %p")}). '
        f'Total: ₹{grand_total}'
    )

    return redirect('food:order_detail', order_id=order.id)

# ─────────────────────────────────────────────────────
# ORDER DETAIL — Student tracks their order
# ─────────────────────────────────────────────────────

@login_required
def order_detail(request, order_id):
    student = get_student(request.user)
    order   = get_object_or_404(Order, id=order_id, student=student)
    items   = order.items.select_related('menu_item').all()

    # Status progression for progress bar
    status_steps = {
        'P': 1, 'C': 2, 'R': 3, 'X': 4, 'N': 0
    }

    context = {
        'order':        order,
        'items':        items,
        'status_step':  status_steps.get(order.status, 1),
        'cart_count':   cart_total_items(request),
    }
    return render(request, 'food/order_detail.html', context)


# ─────────────────────────────────────────────────────
# STUDENT ORDER HISTORY
# ─────────────────────────────────────────────────────

@login_required
def my_orders(request):
    student = get_student(request.user)
    if not student:
        return redirect('food:stall_list')

    orders = Order.objects.filter(
        student=student
    ).select_related('stall', 'slot').order_by('-created_at')

    context = {
        'orders':     orders,
        'cart_count': cart_total_items(request),
    }
    return render(request, 'food/my_orders.html', context)


# ─────────────────────────────────────────────────────
# STALL OWNER DASHBOARD
# ─────────────────────────────────────────────────────

@login_required
def owner_dashboard(request):
    stall = get_stall_owner(request.user)
    if not stall:
        messages.error(request, 'No stall linked to your account.')
        return redirect('food:stall_list')

    today  = timezone.now().date()
    orders = Order.objects.filter(
        stall=stall,
        order_date=today
    ).select_related('student__user', 'slot').order_by('slot__start_time', '-created_at')

    # Group orders by slot for display
    slots_data = defaultdict(list)
    for order in orders:
        slots_data[order.slot].append(order)

    # Stats for today
    total_orders   = orders.count()
    pending        = orders.filter(status='P').count()
    confirmed      = orders.filter(status='C').count()
    ready          = orders.filter(status='R').count()
    collected      = orders.filter(status='X').count()
    total_revenue  = orders.filter(
        status__in=['C', 'R', 'X']
    ).aggregate(Sum('total'))['total__sum'] or 0

    context = {
        'stall':         stall,
        'slots_data':    dict(slots_data),
        'total_orders':  total_orders,
        'pending':       pending,
        'confirmed':     confirmed,
        'ready':         ready,
        'collected':     collected,
        'total_revenue': total_revenue,
        'today':         today,
    }
    return render(request, 'food/owner_dashboard.html', context)


# ─────────────────────────────────────────────────────
# UPDATE ORDER STATUS — Stall owner action
# ─────────────────────────────────────────────────────

@login_required
def update_order_status(request, order_id):
    """AJAX — stall owner updates order status"""
    stall = get_stall_owner(request.user)
    order = get_object_or_404(Order, id=order_id, stall=stall)

    if request.method == 'POST':
        data      = json.loads(request.body)
        new_status = data.get('status')

        valid = [s[0] for s in Order.STATUS_CHOICES]
        if new_status in valid:
            order.status = new_status
            order.save()
            return JsonResponse({
                'success': True,
                'status':  order.get_status_display(),
                'code':    order.status,
            })

    return JsonResponse({'success': False}, status=400)


# ─────────────────────────────────────────────────────
# DEMAND ANALYTICS — Peak time chart data
# ─────────────────────────────────────────────────────

@login_required
def demand_analytics(request):
    stall = get_stall_owner(request.user)
    if not stall:
        return redirect('food:stall_list')

    # Last 7 days hourly data
    from datetime import timedelta
    week_ago = timezone.now().date() - timedelta(days=7)

    records = DemandRecord.objects.filter(
        stall=stall,
        date__gte=week_ago
    ).order_by('date', 'hour')

    # Aggregate by hour across all days
    hourly_totals = defaultdict(int)
    for record in records:
        hourly_totals[record.hour] += record.order_count

    # Build chart data for 8am–8pm
    chart_labels = [f"{h}:00" for h in range(8, 21)]
    chart_data   = [hourly_totals.get(h, 0) for h in range(8, 21)]

    # Find peak hour
    peak_hour = max(hourly_totals, key=hourly_totals.get) if hourly_totals else 12
    peak_label = f"{peak_hour}:00 – {peak_hour+1}:00"

    # AI prediction — simple moving average prediction for next hour
    prediction = predict_next_hour(stall)

    context = {
        'stall':        stall,
        'chart_labels': json.dumps(chart_labels),
        'chart_data':   json.dumps(chart_data),
        'peak_hour':    peak_label,
        'prediction':   prediction,
        'total_week':   sum(chart_data),
    }
    return render(request, 'food/demand_analytics.html', context)


# ─────────────────────────────────────────────────────
# AI DEMAND PREDICTION
# Simple moving average over last 7 days
# ─────────────────────────────────────────────────────

def predict_next_hour(stall):
    """
    Predicts order volume for the next hour using
    a simple moving average of the same hour
    over the past 7 days.

    Theory (viva):
    - Moving average smooths out daily fluctuations
    - We look at same hour on past 7 days
    - Average gives expected demand for next occurrence
    - This is the foundation of time-series forecasting
    """
    from datetime import timedelta

    now       = timezone.now()
    next_hour = (now.hour + 1) % 24
    today     = now.date()

    # Collect same hour data for last 7 days
    past_counts = []
    for i in range(1, 8):
        past_date = today - timedelta(days=i)
        try:
            record = DemandRecord.objects.get(
                stall=stall,
                date=past_date,
                hour=next_hour
            )
            past_counts.append(record.order_count)
        except DemandRecord.DoesNotExist:
            past_counts.append(0)

    if not past_counts or sum(past_counts) == 0:
        return {
            'hour':       f"{next_hour}:00",
            'predicted':  0,
            'confidence': 'Low — not enough historical data yet',
            'advice':     'Keep tracking orders to improve predictions.',
        }

    avg = sum(past_counts) / len(past_counts)
    predicted = round(avg)

    # Confidence based on data variance
    variance = sum((x - avg) ** 2 for x in past_counts) / len(past_counts)

    if variance < 5:
        confidence = 'High'
        advice = f'Prepare approximately {predicted} orders for {next_hour}:00.'
    elif variance < 20:
        confidence = 'Medium'
        advice = f'Expect around {predicted} orders at {next_hour}:00. Slight variation possible.'
    else:
        confidence = 'Low'
        advice = f'Demand is unpredictable at {next_hour}:00. Keep buffer stock ready.'

    return {
        'hour':       f"{next_hour}:00",
        'predicted':  predicted,
        'confidence': confidence,
        'advice':     advice,
    }


# ─────────────────────────────────────────────────────
# SLOT AVAILABILITY API — AJAX
# ─────────────────────────────────────────────────────

@login_required
def slot_availability(request, stall_id):
    """Returns JSON of slot availability for a stall"""
    stall = get_object_or_404(FoodStall, id=stall_id)
    slots = BreakSlot.objects.filter(stall=stall)

    data = [{
        'id':         slot.id,
        'label':      slot.label,
        'start_time': slot.start_time.strftime('%I:%M %p'),
        'end_time':   slot.end_time.strftime('%I:%M %p'),
        'slots_left': slot.slots_left,
        'is_full':    slot.is_full,
    } for slot in slots]

    return JsonResponse({'slots': data})
# ─────────────────────────────────────────────────────
# MENU MANAGEMENT — Stall Owner
# ─────────────────────────────────────────────────────

@login_required
def manage_menu(request):
    stall = get_stall_owner(request.user)
    if not stall:
        messages.error(request, 'No stall linked to your account.')
        return redirect('food:stall_list')

    menu_items = MenuItem.objects.filter(stall=stall).select_related('category').order_by('category__name', 'name')
    categories = Category.objects.filter(stall=stall)

    return render(request, 'food/manage_menu.html', {
        'stall':      stall,
        'menu_items': menu_items,
        'categories': categories,
    })


@login_required
def add_item(request):
    stall = get_stall_owner(request.user)
    if not stall or request.method != 'POST':
        return redirect('food:manage_menu')

    cat_id = request.POST.get('category')
    category = None
    if cat_id:
        try:
            category = Category.objects.get(id=cat_id, stall=stall)
        except Category.DoesNotExist:
            pass

    MenuItem.objects.create(
        stall        = stall,
        name         = request.POST.get('name', '').strip(),
        description  = request.POST.get('description', '').strip(),
        price        = request.POST.get('price', 0),
        prep_time    = request.POST.get('prep_time', 5),
        category     = category,
        is_veg       = 'is_veg' in request.POST,
        is_available = 'is_available' in request.POST,
        photo        = request.FILES.get('photo'),
    )
    messages.success(request, f'Item added successfully!')
    return redirect('food:manage_menu')


@login_required
def edit_item(request, item_id):
    stall = get_stall_owner(request.user)
    item  = get_object_or_404(MenuItem, id=item_id, stall=stall)

    if request.method != 'POST':
        return redirect('food:manage_menu')

    cat_id = request.POST.get('category')
    category = None
    if cat_id:
        try:
            category = Category.objects.get(id=cat_id, stall=stall)
        except Category.DoesNotExist:
            pass

    item.name         = request.POST.get('name', item.name).strip()
    item.description  = request.POST.get('description', '').strip()
    item.price        = request.POST.get('price', item.price)
    item.prep_time    = request.POST.get('prep_time', item.prep_time)
    item.category     = category
    item.is_veg       = 'is_veg' in request.POST
    item.is_available = 'is_available' in request.POST
    if request.FILES.get('photo'):
        item.photo = request.FILES['photo']
    item.save()

    messages.success(request, f'"{item.name}" updated.')
    return redirect('food:manage_menu')


@login_required
def toggle_item(request, item_id):
    """Flip is_available on/off"""
    stall = get_stall_owner(request.user)
    item  = get_object_or_404(MenuItem, id=item_id, stall=stall)

    if request.method == 'POST':
        item.is_available = not item.is_available
        item.save()
        state = 'available' if item.is_available else 'hidden'
        messages.success(request, f'"{item.name}" is now {state}.')

    return redirect('food:manage_menu')


@login_required
def delete_item(request, item_id):
    stall = get_stall_owner(request.user)
    item  = get_object_or_404(MenuItem, id=item_id, stall=stall)

    if request.method == 'POST':
        name = item.name
        item.delete()
        messages.success(request, f'"{name}" deleted.')

    return redirect('food:manage_menu')


@login_required
def add_category(request):
    stall = get_stall_owner(request.user)
    if not stall or request.method != 'POST':
        return redirect('food:manage_menu')

    name = request.POST.get('name', '').strip()
    icon = request.POST.get('icon', '🍽').strip()

    if name:
        Category.objects.get_or_create(stall=stall, name=name, defaults={'icon': icon})
        messages.success(request, f'Category "{name}" added.')

    return redirect('food:manage_menu')


@login_required
def delete_category(request, cat_id):
    stall = get_stall_owner(request.user)
    cat   = get_object_or_404(Category, id=cat_id, stall=stall)

    if request.method == 'POST':
        name = cat.name
        cat.delete()
        messages.success(request, f'Category "{name}" deleted.')

    return redirect('food:manage_menu')