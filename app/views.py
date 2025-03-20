# app/views.py
from django.urls import reverse

from myproject.passwords import EVERYPAY_API_SECRET, EVERYPAY_API_USERNAME
from myproject.settings import CALLBACK_URL, EVERYPAY_API_URL_CALLBACK, EVERYPAY_API_URL_INITIATE, EVERYPAY_API_URL_REFUND
from .forms import SignUpForm, updUserForm, DishForm
from .models import table_number, User, dish, weekday, menu, weekday, week, order, City, ArchivedOrder, Transaction
from django.shortcuts import HttpResponseRedirect, redirect, render
from django.http import HttpResponse, JsonResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum, F
from django.contrib import messages
from datetime import datetime, timedelta
from django.utils import timezone
from django.core.mail import EmailMessage
import json, csv, codecs, io, qrcode, base64
from decimal import Decimal, InvalidOperation
from isoweek import Week
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont 
from django.conf import settings
from django.core.management import call_command
import requests
import uuid
from django.db.models.functions import ExtractYear, ExtractMonth
from django.db.models import Count
# check done
# Tellimuse piiranguaeg
order_time = 15

def run_archive_expired_orders(request):
    call_command('archive_expired_orders')
    messages.success(request, 'Aegunud tellimuste arhiveerimise skript käivitatud.')
    return redirect('service')

    
def run_send_archived_orders_email(request):
    call_command('send_archived_orders_email')
    messages.success(request, 'Arhiveeritud tellimuste e-kirja saatmise skript käivitatud.')
    return redirect('service')


def run_send_orders_email(request):
    call_command('send_orders_email')
    messages.success(request, 'Tellimuste e-kirja saatmise skript käivitatud.')
    return redirect('service')


def run_tabel_number(request):
    call_command('tabel_number')
    messages.success(request, 'Tabelinumbri skript käivitatud.')
    return redirect('service')


def is_superadmin(user):
    return user.groups.filter(name='Superadmin').exists()

def is_manager(user):
    return user.groups.filter(name='Manager').exists()

def is_operator(user):
    return user.groups.filter(name='Operator').exists()

def is_client(user):
    return user.groups.filter(name='Client').exists()

def load_dishes(request):
    category_id = request.GET.get('category')
    dishes = dish.objects.filter(category_id=category_id).order_by('dish_name')
    return JsonResponse(list(dishes.values('id', 'dish_name')), safe=False)

def redirect_to_orders_page(user):
    if user.groups.filter(name='Client').exists():
        return redirect('orders')
    elif user.groups.filter(name='Operator').exists():
        return redirect('operator')
    elif user.groups.filter(name='Manager').exists():
        return redirect('createmenu')
    elif user.groups.filter(name='Superadmin').exists():
        return redirect('orders')
    else:
        return redirect('login')
    
# Teenus
@user_passes_test(lambda u: u.groups.filter(name='Superadmin').exists())    
def service(request):
    user_groups = request.user.groups.values_list('name', flat=True)
    # Kui kasutaja pole autentitud, suuna ta sisselogimislehele
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'
    name = request.user.first_name
    data = {
        'user_groups': user_groups,
        'qr_image': qr_image,
        'name': name,
    }
    return render(request, 'user/service.html', data)  

@user_passes_test(lambda u: u.groups.filter(name='Manager').exists())
def dishes(request):
    user_groups = request.user.groups.values_list('name', flat=True)
    # Sorteerimisparameetrite töötlemine
    sort_by = request.GET.get('sort_by', 'category')
    sort_order = request.GET.get('sort_order', 'asc')
    
    # Määrame sorteeringu suuna
    if sort_order == 'asc':
        sort_order_prefix = ''
    else:
        sort_order_prefix = '-'
    
    # Saame kõik road, võttes arvesse sorteeringut
    dishes = dish.objects.all().order_by(f'{sort_order_prefix}{sort_by}')
    
    if request.method == 'POST':
        form = DishForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dish')  # Ümbersuunamine samale lehele
    else:
        form = DishForm()
        
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'

    data = {
        'form': form, 
        'dishes': dishes, 
        'sort_by': sort_by, 
        'sort_order': sort_order,
        'user_groups': user_groups,
        'qr_image': qr_image
    }

    return render(request, 'user/dish.html', data)
pass

def dish_del(request):
    if request.method == 'POST':
        dish_id = request.POST.get('delete-id')
        if dish_id:
            try:
                dish_obj = dish.objects.get(id=dish_id)
                dish_obj.delete()
                messages.success(request, 'Roog kustutatud!')
            except dish.DoesNotExist:
                messages.error(request, 'Roogi ei leitud!')
        else:
            messages.error(request, 'Kustutamine ebaõnnestus, tõenäoliselt on seoseid!')
    return redirect('dish')

@csrf_exempt
def dish_update(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        print("Received data:", data)  # Lisame selle rea silumiseks
        dish_id = data.get('id')
        value = data.get('value')
        type = data.get('type')

        try:
            dish_obj = dish.objects.get(id=dish_id)
            if type == 'dish_name':
                dish_obj.dish_name = value
            elif type == 'dish_price':
                try:
                    value = Decimal(value)  # Teisendame stringi Decimaliks
                except InvalidOperation:
                    return JsonResponse({'status': 'error', 'message': 'Invalid price format'})
                dish_obj.dish_price = value
            dish_obj.save()
            return JsonResponse({'status': 'success'})
        except dish.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Dish not found'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'})

def index(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return redirect_to_orders_page(request.user)

@user_passes_test(lambda u: u.groups.filter(name='Operator').exists())
def operator(request):
    user_groups = request.user.groups.values_list('name', flat=True)
    # Kui kasutaja pole autentitud, suuna ta sisselogimislehele
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Saame praeguse kuupäeva ja kellaaja
    now = datetime.now()
    wn = now.isocalendar()[1]
    today = now.isoweekday()
    
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'

    # Määrame nädala päeva
    if today == 1:
        day = 'Esmaspäev'
    elif today == 2:
        day = 'Teisipäev'
    elif today == 3:
        day = 'Kolmapäev'
    elif today == 4:
        day = 'Neljapäev'
    elif today == 5:
        day = 'Reede'
    else:
        day = 'Puhkepäev'
    data = {
        'wn': wn,
        'today': day,
        'user_groups': user_groups,
        'qr_image': qr_image
    }
    
# vana andmete lõpp
    if request.method == 'POST':
        tabel_number = request.POST.get('tabel_number')
        
        # Teisendame tabelinumbri täisarvuks
        tabel_number = int(tabel_number)
        
        # Saame praeguse kuupäeva
        current_date = datetime.now()
        current_year = current_date.year
        current_week = current_date.isocalendar()[1]
        current_day = current_date.isocalendar()[2]
        total_price = 0
        # Genereerime tellimuse numbri tänase päeva ja sisestatud tabelinumbri alusel
        order_number = int(f"{current_year}{current_week:02d}{current_day:02d}{tabel_number:05d}")
        
        # Otsime genereeritud tellimuse numbri alusel tellimusi ja filtreerime ainult avatud tellimused
        orders = order.objects.filter(order_number=order_number)
        
        if not orders.exists():
            messages.error(request, f"Tellimuse tabelinumbri {tabel_number} jaoks tänase päeva kohta ei leitud või on juba suletud.")
        else:
            # Arvutame tellimuse kogumaksumuse
            total_price = sum(order_item.quantity * order_item.menu_id.dish_id.dish_price for order_item in orders)
    # Ekstraheerime aasta tellimuse numbrist    
        order_year = orders.first().order_number // 1000000000 if orders else None    
        return render(request, 'user/operator.html', {'orders': orders, 'wn': wn, 'today': day, 'total_price': total_price, 'order_year': order_year, 'qr_image': qr_image, 'user_groups': user_groups})
    else:
        return render(request, 'user/operator.html', data) 
pass

@user_passes_test(lambda u: u.groups.filter(name='Client').exists())
def update_order_status(request, order_number):
    try:
        # Saame kõik tellimused antud tellimuse numbriga
        orders = order.objects.filter(order_number=order_number)

        # Kontrollime, kas sellise numbriga tellimusi leidub
        if not orders.exists():
            raise Http404("Tellimus ei leitud.")
        
        # Muudame kõigi antud numbriga tellimuste staatust
        for order1 in orders:
            order1.open = False
            order1.save()
        
        messages.success(request, f"Tellimuse {order_number} staatus on edukalt muudetud 'täidetuks'.")
    except Http404:
        # Käitleme olukorda, kui tellimusi ei leitud
        messages.error(request, f"Tellimuse numbriga {order_number} ei leitud.")
    
    return redirect('operator')  # Suuname tellimuste lehele
pass

def createmenu(request):
    user_groups = request.user.groups.values_list('name', flat=True)
    # Kui kasutaja pole autentitud, suuna ta sisselogimislehele
    if not request.user.is_authenticated:
        return redirect('login')
    
    days = weekday.objects.all()
    soups = dish.objects.filter(category__category_name='Сupp')
    mains = dish.objects.filter(category__category_name='Pearoog')
    garnishes = dish.objects.filter(category__category_name='Lisand')
    salats = dish.objects.filter(category__category_name='Salat')
    menu_items = menu.objects.order_by('week_number', 'weekday_id', 'dish_id__category').select_related('week_number', 'weekday_id', 'dish_id__category','dish_id')
    all_dishes = dish.objects.all()
    weeks = week.objects.all()
    # Saame menüü tabelist kõik unikaalsed nädalad
    menu_weeks = list(menu.objects.values_list('week_number', flat=True).distinct().order_by('week_number'))

    # Saame praeguse ja järgmise aasta
    current_year = datetime.now().year
    next_year = current_year + 1

    # Saame praeguse nädala
    current_week = datetime.now().isocalendar()[1]
    # Saame järgmise nädala
    next_week = datetime.now().isocalendar()[1] + 1

    # Genereerime nädalate loendi valimiseks
    selected_weeks = []
    for i in range(8):
        week_number = (current_week + i - 1) % 52 + 1
        selected_weeks.append(week_number)
        
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'

    data = {
        'days': days,
        'soups': soups,
        'mains': mains,
        'garnishes': garnishes,
        'salats': salats,
        'menu_items': menu_items,
        'all_dishes': all_dishes,
        'weeks': weeks,
        'menu_weeks': menu_weeks,
        'current_year': current_year,
        'next_year': next_year,
        'current_week': current_week,
        'next_week': next_week,
        'selected_weeks': selected_weeks,
        'user_groups': user_groups,
        'qr_image': qr_image
    }
    return render(request, 'user/create_menu.html', data)

@csrf_exempt
def delete_menu_item(request, menu_item_id):
    if request.method == 'DELETE':
        try:
            menu_item = menu.objects.get(id=menu_item_id)
            menu_item.delete()
            return JsonResponse({'success': True})
        except menu.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Menüü elementi ei leitud'})
    return JsonResponse({'success': False, 'error': 'Päringu meetod on vale'})

@csrf_exempt
def replace_week_number(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        existing_week = data.get('existing_week')
        new_week = data.get('new_week')

        try:
            # Saame uue nädala objekti
            new_week_obj, created = week.objects.get_or_create(number=new_week)

            # Uuendame kõik kirjed olemasoleva nädala asemel uue nädala vastu
            menu.objects.filter(week_number__number=existing_week).update(week_number=new_week_obj)

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})

@csrf_exempt
def get_dishes_by_category(request, category_id):
    if request.method == 'GET':
        dishes = dish.objects.filter(category_id=category_id).values('id', 'dish_name')
        return JsonResponse({'dishes': list(dishes)})
    return JsonResponse({'success': False, 'error': 'Päringu meetod on vale'})

@csrf_exempt
def update_menu_item(request, id):
    if request.method == 'POST':
        data = json.loads(request.body)
        dish_id = data.get('dish_id')

        print(f"Received data: dish_id={dish_id}")

        try:
            menu_item = menu.objects.get(id=id)
            menu_item.dish_id_id = dish_id
            menu_item.save()
            return JsonResponse({'success': True})
        except menu.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Menüü elementi ei leitud'})
    return JsonResponse({'success': False, 'error': 'Päringu meetod on vale'})

def upd_menu(request):
    if not request.user.is_authenticated:
        return redirect('login')
    
    if request.method == 'POST':
        week_nr = request.POST.get('week_nr')
        day_nr = request.POST.get('day_nr')
        soup_id = request.POST.get('soup_id')
        main_id = request.POST.get('main_id')
        garnish_id = request.POST.get('garnish_id')
        salat_id = request.POST.get('salat_id')

        # Saame week ja weekday mudelite eksemplarid
        try:
            week_instance = week.objects.get(number=int(week_nr))
            weekday_instance = weekday.objects.get(id=int(day_nr))
        except (week.DoesNotExist, weekday.DoesNotExist):
            messages.error(request, 'Menüü loomise andmed on vigased.')
            return redirect('createmenu')

        # Loome uusi menu mudeli eksemplare, jättes tühjad väärtused vahele
        if soup_id and soup_id != 'Vali supp':
            try:
                soup_instance = dish.objects.get(id=int(soup_id))
                menu.objects.create(
                    week_number=week_instance,
                    weekday_id=weekday_instance,
                    dish_id=soup_instance
                )
            except dish.DoesNotExist:
                messages.error(request, 'Suppi jaoks vigane ID.')
        
        if main_id and main_id != 'Vali Pearoog':
            try:
                main_instance = dish.objects.get(id=int(main_id))
                menu.objects.create(
                    week_number=week_instance,
                    weekday_id=weekday_instance,
                    dish_id=main_instance
                )
            except dish.DoesNotExist:
                messages.error(request, 'Põhisöögi jaoks vigane ID.')
        
        if garnish_id and garnish_id != 'Vali lisand':
            try:
                garnish_instance = dish.objects.get(id=int(garnish_id))
                menu.objects.create(
                    week_number=week_instance,
                    weekday_id=weekday_instance,
                    dish_id=garnish_instance
                )
            except dish.DoesNotExist:
                messages.error(request, 'Lisandi jaoks vigane ID.')
        
        if salat_id and salat_id != 'Vali salat':
            try:
                salat_instance = dish.objects.get(id=int(salat_id))
                menu.objects.create(
                    week_number=week_instance,
                    weekday_id=weekday_instance,
                    dish_id=salat_instance
                )
            except dish.DoesNotExist:
                messages.error(request, 'Salati jaoks vigane ID.')

        messages.success(request, 'Menüü uuendatud!')
        return redirect('createmenu')
    
    return redirect('createmenu')
    
def add_to_cart(request):
    if request.method == 'POST':
        dish_name = request.POST.get('dish_name')
        day = request.POST.get('day')
        week = request.POST.get('week')  # Lisame nädala numbri hankimise
        # Siin saab lisada loogikat roa ostukorvi lisamiseks
        messages.success(request, f'Roog "{dish_name}" lisatud ostukorvi {week}. nädala {day} päevaks.')
    return redirect('orders')

def submit_order(request):
    if request.method == 'POST':
        # Määra vaikimisi tühjad loendid
        cart_items = []
        quantities = []
        days = []
        cities = []
        weeks = []

        # Hangi ja parsige JSON andmed
        cart_items_data = request.POST.get('cart_items')
        quantities_data = request.POST.get('quantities')
        days_data = request.POST.get('days')
        cities_data = request.POST.get('cities')
        weeks_data = request.POST.get('weeks')
        
        # Kontrolli ja parsi iga andmeväli
        if cart_items_data:
            try:
                cart_items = json.loads(cart_items_data)
            except json.JSONDecodeError:
                return HttpResponse(status=400)  # Bad Request
        else:
            return HttpResponse(status=204)  # No Content

        if quantities_data:
            try:
                quantities = json.loads(quantities_data)
            except json.JSONDecodeError:
                return HttpResponse(status=400)  # Bad Request
        else:
            return HttpResponse(status=204)  # No Content

        if days_data:
            try:
                days = json.loads(days_data)
            except json.JSONDecodeError:
                return HttpResponse(status=400)  # Bad Request
        else:
            return HttpResponse(status=204)  # No Content

        if cities_data:
            try:
                cities = json.loads(cities_data)
            except json.JSONDecodeError:
                return HttpResponse(status=400)  # Bad Request
        else:
            return HttpResponse(status=204)  # No Content

        if weeks_data:
            try:
                weeks = json.loads(weeks_data)
            except json.JSONDecodeError:
                return HttpResponse(status=400)  # Bad Request
        else:
            return HttpResponse(status=2004)  # No Content

        # Kontrollime, kas kõik loendid on sama pikkusega
        if len(cart_items) != len(quantities) or \
           len(cart_items) != len(days) or \
           len(cart_items) != len(cities) or \
           len(cart_items) != len(weeks):
            return HttpResponse(status=400)  # Bad Request

        # Kogume kõik paarid nädal:päev ostukorvist
        cart_pairs = [f"{weeks[i]}:{days[i]}" for i in range(len(cart_items))]

        # Kogume kõik paarid nädal:päev kasutaja olemasolevatest tellimustest
        existing_orders = order.objects.filter(user_id=request.user)
        existing_pairs = set(f"{ord.menu_id.week_number.number}:{ord.menu_id.weekday_id.weekday_name}" for ord in existing_orders)

        # Kontrollime ostukorvis olevate ja olemasolevate tellimuste paaride lõikumist
        conflicting_pairs = set(cart_pairs) & existing_pairs
        if conflicting_pairs:
            # Koostame sõnumi, milles loetletakse conflicting_pairs
            conflicting_pairs_str = ', '.join(conflicting_pairs)
            messages.error(request, f"Nädala {conflicting_pairs_str} jaoks on juba tellimus olemas. Kustutage olemasolev tellimus selle päeva jaoks, kui soovite muuta või luua uue.")
            return redirect('orders')

        # Loome tellimused iga ostukorvi elemendi jaoks
        for i in range(len(cart_items)):
            dish_name = cart_items[i]
            quantity = int(quantities[i])
            day = days[i]
            city_id = cities[i]
            week = weeks[i]

            # Saame menu ja City mudelite eksemplarid
            try:
                menu_instance = menu.objects.get(dish_id__dish_name=dish_name, weekday_id__weekday_name=day, week_number__number=week)
                city_instance = City.objects.get(id=city_id)
            except (menu.DoesNotExist, City.DoesNotExist):
                messages.error(request, f"Vigased andmed roa \"{dish_name}\" jaoks päevaks {day}.")
                continue

            # Loome uue order mudeli eksemplari
            order.objects.create(
                user_id=request.user,
                menu_id=menu_instance,
                quantity=quantity,
                city=city_instance
            )
        # Kontrollime, kas ostukorv on tühi
        if len(cart_items) == 0:
            messages.error(request, "Ostukorv on tühi. Ei ole võimalik tellimust vormistada.")
            return redirect('orders')
        
        messages.success(request, "Tellimus on vormistatud.")
        return redirect('orders')
    
    return redirect('orders')

def menu_view(request, week):   
    # Saame menüü praeguse nädala ja aasta jaoks
    menu_items = menu.objects.filter(week_number__number=week).select_related('weekday_id', 'dish_id')
 
    # Kontrollime, kas andmed on olemas
    if not menu_items:
        print("no data for current week and year")
        return {}
    
    # Rühmitame menüü nädala päevade ja kategooriate kaupa
    grouped_menu = {}
    for item in menu_items:
        day = item.weekday_id.weekday_name
        category = item.dish_id.category.category_name
        dish_name = item.dish_id.dish_name
        dish_price = item.dish_id.dish_price
        
        if day not in grouped_menu:
            grouped_menu[day] = {}
        if category not in grouped_menu[day]:
            grouped_menu[day][category] = []
        
        grouped_menu[day][category].append((dish_name, dish_price))
    
    # Järjestame iga päeva kategooriad
    ordered_categories = ['Supp', 'Lisand', 'Pearoog', 'Salat']  # Määrake vajalik järjekord
    for day in grouped_menu:
        grouped_menu[day] = {category: grouped_menu[day].get(category, []) for category in ordered_categories}
        
    return grouped_menu

def menu_page(request):
    week = datetime.now().isocalendar()[1]
    grouped_menu = menu_view(request, week)
    return render(request, 'app/menu.html', {'grouped_menu': grouped_menu})

def get_user_orders(user):
    # Määrame praeguse nädala
    current_week = datetime.now().isocalendar()[1]
    current_year = datetime.now().year

    # Loogika aastavahetuse käsitlemiseks
    if current_week == 52:
        next_week = 1
    else:
        next_week = current_week + 1

    # Saame praeguse nädala tellimused
    user_orders = order.objects.order_by('menu_id', 'menu_id__weekday_id').filter(
        user_id=user,
        menu_id__week_number__number=current_week
    ).select_related('menu_id__dish_id', 'menu_id__weekday_id', 'city')

    # Lisame järgmise nädala tellimused
    next_week_orders = order.objects.order_by('menu_id', 'menu_id__weekday_id').filter(
        user_id=user,
        menu_id__week_number__number=next_week
    ).select_related('menu_id__dish_id', 'menu_id__weekday_id', 'city')

    # Ühendame praeguse ja järgmise nädala tellimused
    user_orders = user_orders.union(next_week_orders)

    current_time = datetime.now()

    if current_time.hour < order_time:
        cutoff_date = current_time.date() + timedelta(days=1)
    else:
        cutoff_date = current_time.date() + timedelta(days=2)

    grouped_orders = {}
    total_sum = 0
    for order_item in user_orders:
        week = order_item.menu_id.week_number.number
        order_number = order_item.order_number
        order_number_str = str(order_number).zfill(13)
        year = int(order_number_str[:4])
        week_num = int(order_number_str[4:6])
        day_num = int(order_number_str[6:8])

        if 1 <= week_num <= Week.last_week_of_year(year).week and 1 <= day_num <= 7:
            order_week_start = Week(year, week_num).monday()
            order_date = order_week_start + timedelta(days=day_num - 1)
        else:
            order_date = datetime.min.date()

        # Lisaloogika reede jaoks
        if current_time.weekday() == 4 and current_time.hour >= order_time:
            next_monday = current_time.date() + timedelta(days=(7 - current_time.weekday()))
            if order_date == next_monday:
                deletable = False
            else:
                deletable = order_date >= cutoff_date
        else:
            deletable = order_date >= cutoff_date

        city = order_item.city.name
        day_name = order_item.menu_id.weekday_id.weekday_name
        dish_name = order_item.menu_id.dish_id.dish_name
        quantity = order_item.quantity
        price = order_item.menu_id.dish_id.dish_price
        dish_total_price = quantity * price

        if week not in grouped_orders:
            grouped_orders[week] = {}
        if order_number not in grouped_orders[week]:
            grouped_orders[week][order_number] = {}
        if city not in grouped_orders[week][order_number]:
            grouped_orders[week][order_number][city] = {}
        if day_name not in grouped_orders[week][order_number][city]:
            grouped_orders[week][order_number][city][day_name] = {
                'deletable': deletable,
                'dishes': {}
            }
        dish_data = grouped_orders[week][order_number][city][day_name]['dishes'].setdefault(dish_name, {
            'quantity': 0,
            'total_price': 0
        })
        dish_data['quantity'] += quantity
        dish_data['total_price'] += dish_total_price
        total_sum += dish_total_price

         # Sorteerime nädalaid kasvavas järjekorras (või kahanevas, kui vajalik)
    sorted_weeks = sorted(grouped_orders.keys())  # Sorteerimine
    grouped_orders = {week: grouped_orders[week] for week in sorted_weeks}  # Kirjutame algse sõnastiku ümber

    return grouped_orders, total_sum

@user_passes_test(lambda u: u.groups.filter(name='Client').exists())
def orders(request):
    user_groups = request.user.groups.values_list('name', flat=True)
    if not request.user.is_authenticated:
        return redirect('login')
    user = request.user
    if user.blocked == True:
        return redirect('account')
    grouped_orders, total_sum = get_user_orders(user)
    cities = City.objects.all()
    week1 = datetime.now().isocalendar()[1]
    grouped_menu1 = menu_view(request, week1)  # Eeldame, et teil on funktsioon menüü saamiseks
    week2 = (datetime.now().isocalendar()[1] + 1)
    if week2 == 53: week2 = 1
    grouped_menu2 = menu_view(request, week2)
    current_weekday = (datetime.now().isocalendar()[2])  # Kui praegune aeg on alla 15 tunni, lubame tellimuse järgmiseks päevaks
    current_time = timezone.now()
    current_hour = current_time.hour + 2
    
    # QR-koodi genereerimine
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'

    # Kui praegune aeg ületab 15 tundi, blokeerime tellimuse järgmiseks päevaks
    if current_hour >= order_time:
        current_weekday = (datetime.now().isocalendar()[2] + 1)

    # Määrame päevad, mida kuvatakse vastavalt nädala tänasele päevale
    if current_weekday == 1:  # Esmaspäev
        days_to_show = ['Teisipäev', 'Kolmapäev', 'Neljapäev', 'Reede']
    elif current_weekday == 2:  # Teisipäev
        days_to_show = ['Kolmapäev', 'Neljapäev', 'Reede']
    elif current_weekday == 3:  # Kolmapäev
        days_to_show = ['Neljapäev', 'Reede']
    elif current_weekday == 4:  # Neljapäev
        days_to_show = ['Reede']
    elif current_weekday == 5:  # Reede
        days_to_show = []
    else:
        days_to_show = []

    # Filtreerime praeguse nädala menüü nende päevade alusel, mida näidata
    filtered_current_week_menu = {day: grouped_menu1[day] for day in days_to_show if day in grouped_menu1}

    # Määrame järgmise nädala päevad
    if datetime.now().isocalendar()[2] == 5 and current_hour >= order_time:  # Kui täna on reede ja aeg on üle 15 tunni
        days_to_show_next_week = ['Teisipäev', 'Kolmapäev', 'Neljapäev', 'Reede']
    else:
        days_to_show_next_week = ['Esmaspäev', 'Teisipäev', 'Kolmapäev', 'Neljapäev', 'Reede']

    # Filtreerime järgmise nädala menüü nende päevade alusel, mida näidata
    filtered_next_week_menu = {day: grouped_menu2[day] for day in days_to_show_next_week if day in grouped_menu2}

    context = {
        'grouped_orders': grouped_orders,
        'total_sum': total_sum,
        'cities': cities,
        'grouped_menu_cw': filtered_current_week_menu,
        'grouped_menu_nw': filtered_next_week_menu,
        'user_groups': user_groups,
        'qr_image': qr_image,
        'week1': week1,
        'week2': week2,
        'compare_day': weekday_order
    }
    return render(request, 'user/orders.html', context)
pass

@user_passes_test(lambda u: u.groups.filter(name='Client').exists())
def account(request):
    # Kasutaja autentimise kontroll
    if not request.user.is_authenticated:
        return redirect('login')

    # Saame kasutaja grupid
    user_groups = request.user.groups.values_list('name', flat=True)
    
    # QR-koodi genereerimine
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'

    # Saame linnade nimekirja
    cities = City.objects.all()

    # Arvutame tellimuste statistika
    order_stats = calculate_order_stats(request.user)

    # Koostame andmed mallile
    data = {
        'form': updUserForm(instance=request.user),
        'qr_image': qr_image,
        'cities': cities,
        'user_groups': user_groups,
        'order_stats': order_stats,
    }

    return render(request, 'user/account.html', data)
pass

@user_passes_test(lambda u: u.groups.filter(name='Client').exists())
def order_archive(request):
    # Kasutaja autentimise kontroll
    if not request.user.is_authenticated:
        return redirect('login')

    # Saame kasutaja grupid
    user_groups = request.user.groups.values_list('name', flat=True)

    # QR-koodi genereerimine
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'

    # Saame arhiveeritud tellimused
    archived_orders_data = get_archived_orders(request.user)

    # Töötleme roogade stringi
    for order in archived_orders_data['orders']:
        order['dishes'] = order['dishes'].split(',')

    # Saame praeguse aasta ja kuu
    current_year = datetime.now().year
    current_month = datetime.now().month

    # Saame linnade nimekirja
    cities = City.objects.all()

    # Saame aastad ja kuud arhiveeritud tellimuste filtreerimiseks
    years = archived_orders_data['years']
    months = archived_orders_data['months']

    # Arvutame tellimuste statistika
    order_stats = calculate_order_stats(request.user)
    data = {
        'archived_orders_data': archived_orders_data['orders'],
        'qr_image': qr_image,
        'years': years,
        'months': months,
        'cities': cities,
        'current_year': current_year,
        'current_month': current_month,
        'user_groups': user_groups,
        'order_stats': order_stats,
    }
    return render(request, 'user/order_archive.html', data)
pass

def delete_order(request, order_number):
    try:
        # Leiame kõik tellimused antud numbriga
        orders_to_delete = order.objects.filter(order_number=order_number)

        if not orders_to_delete.exists():
            messages.error(request, f"Tellimust numbriga {order_number} ei leitud.")
            return redirect('orders')

        # Saame kasutaja (eeldame, et kõik ühe numbriga tellimused kuuluvad ühele kasutajale)
        user = orders_to_delete.first().user_id

        # Arvutame tellimuste kogusumma
        total_amount = sum(
            order_item.quantity * order_item.menu_id.dish_id.dish_price
            for order_item in orders_to_delete
        )

        # Loome tehingu vahendite tagastamiseks
        Transaction.objects.create(
            user=user,
            amount=total_amount,
            transaction_type='deposit',
            description=f"Tagastamine tühistatud tellimuse {order_number} eest"
        )

        # Kustutame tellimused
        orders_to_delete.delete()

        messages.success(request, f"Tellimus numbriga {order_number} on edukalt kustutatud. Summa {total_amount:.2f} EUR on tagastatud.")
    except Exception as e:
        messages.error(request, f"Viga tellimuse kustutamisel: {str(e)}")

    return redirect('orders')

def upd_user(request):
    if request.method == "POST":
        fm = updUserForm(request.POST, instance=request.user)
        if fm.is_valid():
            fm.save()
            messages.success(request, 'Andmed uuendatud!')
            return redirect('account')
    return redirect('account') 

def upd_pswd(request):
    if request.method == 'POST':
        c_password = request.POST['current_password']
        new_password = request.POST['new_password']
        r_new_password = request.POST['retype_new_password']
        user = authenticate(username=request.user.username, password=c_password)
        if user is not None:
            if new_password == r_new_password:
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Parool on edukalt uuendatud!')
                
            else:
                messages.error(request, 'Paroolid ei kattu!')
        else:
            messages.error(request, 'Vale parool!')
            
    return redirect('account')

def sign_up(request):
    if request.method == "POST":
        fm = SignUpForm(request.POST)
        if fm.is_valid():
            user = fm.save()
            group = Group.objects.get(name='Client')
            user.groups.add(group)            
            return redirect('login')
    else:
        fm = SignUpForm()
    return render(request, 'registration/signup.html', {'form': fm})

@csrf_exempt
def check_tabel_number(request):
    if request.method == 'POST':
        tabel_number = request.POST.get("tabel_number")
        if not tabel_number:
            return JsonResponse({'error': 'Tabelinumber pole märgitud'}, status=400)

        # Kontrollime, kas tabelinumber eksisteerib table_number mudelis
        tabel_number_exists = table_number.objects.filter(tabel_number=tabel_number).exists()
        if not tabel_number_exists:
            return JsonResponse({'exists': True, 'message': 'Tabelinumber ei eksisteeri'})

        # Kontrollime, kas tabelinumber on kasutaja mudelis registreeritud
        tabel_number_user_exists = User.objects.filter(tabel_number=tabel_number).exists()
        if tabel_number_user_exists:
            return JsonResponse({'exists': True, 'message': 'Tabelinumber on juba registreeritud'})

        # Kui tabelinumber eksisteerib, kuid pole kasutaja mudelis registreeritud
        return JsonResponse({'exists': False, 'message': 'Registreerimine on saadaval'})
    else:
        return JsonResponse({'error': 'Meetod pole toetatud'}, status=405)

def calculate_vat(amount, vat_rate=22):
    """
    Arvutab käibemaksu summa (VAT) ja summa ilma maksuta.
    """
    vat = (amount * vat_rate) / (100 + vat_rate)
    amount_without_vat = amount - vat
    return amount_without_vat, vat

# Kirjastiili registreerimine kirillitsaga tugi
pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))

def create_pdf_receipt(order_number, user_username, dishes, total_amount, city_name, status, user_first_name, user_last_name):
    currency = "EUR"
    # Loome puhvr PDF-faili jaoks
    buffer = BytesIO()
    y = 300
    x = 10
    b = 180
    c = 215
    d = 255
    e = 300

    p = canvas.Canvas(buffer, pagesize=(e + 25, y + 40))
    # Lisame logoga tšeki ülemisse ossa
    logo_path = "app/static/img/logo.jpg"
    logo_width = 150  # Logoga laius
    logo_height = 30  # Logoga kõrgus

    # Tšeki pealkiri
    p.drawImage(logo_path, x, y, width=logo_width, height=logo_height)
    y -= x
    p.setFont("DejaVuSans", 6)
    p.drawString(x, y, "OÜ Aquaphor International")
    y -= x
    p.drawString(x, y, "Reg. nr. 11207974")
    y -= x
    p.drawString(x, y, "L. Tolstoi tn 2a, Sillamäe")
    y -= x * 3
    p.setFont("DejaVuSans", 8)
    p.drawString(x, y, f"Ostutšekk {order_number}")
    y -= x
    p.drawString(x, y, f"Kasutaja: {user_first_name} {user_last_name}")
    y -= x
    p.drawString(x, y, f"Kasutajanimi: {user_username}")
    y -= x
    p.drawString(x, y, f"Linn: {city_name}")
    y -= x
    p.drawString(x, y, f"Staatus: {status}")
    y -= x * 3   
    p.drawString(x, y, "Kaubad")
    p.drawCentredString(b, y, "Kogus")
    p.drawCentredString(c, y, "KM-ta")
    p.drawCentredString(d, y, "KM 20%")
    p.drawCentredString(e, y, "Summa")
    y -= x 
    p.drawString(x, y, "____________________________________________________________________________")
    y -= x 
    
    # Roogade loend koos maksude eraldi näitamisega
    if dishes:  # Kontrollime, et dishes string pole tühi
        # Kui string sisaldab komasid, jagame selleks
        if ", " in dishes:
            dish_list = dishes.split(", ")
        else:
            # Kui string sisaldab ainult ühte rooga, töötleme seda kui ühte elementi
            dish_list = [dishes]

        for dish in dish_list:
            try:
                # Püüame jagada string roa nime ja koguse ning hinna teabe kaupa
                dish_name, quantity_and_price = dish.rsplit(" (", 1)
                quantity_and_price = quantity_and_price.replace(")", "")  # Eemaldame ")"

                # Jagame koguse ja hinna
                quantity, price = quantity_and_price.split(" tk. ")
                price, currency = price.split(" ")  # Jagame hinna ja valuuta

                # Teisendame andmed nõutud tüüpidesse
                quantity = int(quantity)  # Teisendame koguse arvuks
                price = Decimal(price)  # Teisendame hinna arvuks

                total_dish_price = quantity * price

                # Arvutame iga rea maksud
                amount_without_vat, vat = calculate_vat(total_dish_price)

                # Kuvame roa teabe
                p.drawString(x, y, f"{dish_name}")
                p.drawCentredString(b, y, f"{quantity}")
                p.drawCentredString(c, y, f"{amount_without_vat:.2f}")
                p.drawCentredString(d, y, f"{vat:.2f}")
                p.drawCentredString(e, y, f"{total_dish_price:.2f}")
                y -= x
            except ValueError:
                # Kui jagamine ebaõnnestub, kuvame roa 'nagu on'
                p.drawString(x, y, dish)
                y -= x
    else:
        p.drawString(x, y, "no data :(")
        y -= x
    p.drawString(x, y, "____________________________________________________________________________")
    # Kogusumma maksudega eraldi näidates
    y -= x
    total_amount_without_vat, total_vat = calculate_vat(total_amount)
    p.drawRightString(c, y, f"Summa km-ta:")
    p.drawString(d, y, f"{total_amount_without_vat:.2f} {currency}")
    y -= x
    p.drawRightString(c, y, f"Km 20%:")
    p.drawString(d, y, f"{total_vat:.2f} {currency}")
    y -= x
    p.drawRightString(c, y, f"Summa km-ga:")
    p.drawString(d, y, f"{total_amount:.2f} {currency}")
    y -= x * 4
    p.setFont("DejaVuSans", 8)
    p.drawCentredString(b, y, "See on test.")
    y -= x
    p.drawCentredString(b, y, "Testimise lõppemisel kõik tellimused kustutakse.")
    # Lõpetame PDF loomise
    p.showPage()
    p.save()

    # Tagastame puhvriga PDF-faili
    buffer.seek(0)
    return buffer

@csrf_exempt
def send_receipt(request, order_number):
    if request.method == 'POST':
        try:
            # Saame arhiveeritud tellimuse vastavalt numbrile
            archived_order = ArchivedOrder.objects.get(order_number=order_number)

            # Saame kasutaja objekti arhiveeritud tellimuse kasutajanime alusel
            user = User.objects.get(tabel_number=archived_order.user_tabel_number)

            # Saame tšeki andmed
            user_username = user.username
            user_first_name = user.first_name
            user_last_name = user.last_name
            dishes = archived_order.dishes
            total_amount = archived_order.total_amount
            city_name = archived_order.city_name
            status = archived_order.get_status_display()

            # Loome tšeki PDF
            pdf_buffer = create_pdf_receipt(order_number, user_username, dishes, total_amount, city_name, status, user_first_name, user_last_name)

            # Saatke kiri manusega
            email = EmailMessage(
                subject=f'Ostutšekk {order_number}',
                body='',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],  # Kasutame kasutaja e-posti User mudelist
            )
            email.attach(f'Ostutšekk {order_number}.pdf', pdf_buffer.getvalue(), 'application/pdf')

            email.send()

            return JsonResponse({'status': 'success', 'message': 'Tšekk saadetud e-postiga.'})
        except ArchivedOrder.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Tellimust ei leitud.'})
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Kasutajat ei leitud.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f"Viga kirja saatmisel: {str(e)}"})
    return JsonResponse({'status': 'error', 'message': 'Vale päringu meetod.'})

def archive_order(request):
    if request.method == 'POST':
        order_number = request.POST.get('order_number')
        status = int(request.POST.get('status', 3))  # Vaikimisi staatus on 3 (aegunud)
        if order_number:
            # Hangi tellimus ja arhiveeri see määratud staatusega
            order_items = order.objects.filter(order_number=order_number)
            if order_items.exists():
                user = order_items.first().user_id
                city = order_items.first().city
                total_amount = sum(order_item.quantity * order_item.menu_id.dish_id.dish_price for order_item in order_items)

                dish_list = []
                for order_item in order_items:
                    dish = order_item.menu_id.dish_id
                    # Lisame roa hinna stringi
                    dish_list.append(f"{dish.dish_name} ({order_item.quantity} tk. {dish.dish_price} EUR)")

                dishes_str = ', '.join(dish_list)

                # Loome arhiveeritud tellimuse
                ArchivedOrder.objects.create(
                    order_number=order_number,
                    user_tabel_number=user.tabel_number,
                    user_username=user.username,
                    dishes=dishes_str,
                    city_name=city.name,
                    total_amount=total_amount,
                    status=status
                )

                # Kustutame algse tellimuse
                order_items.delete()

                send_receipt(request, order_number)
                
                # Koostame sõnumi vastavalt staatusele
                if status == 1:
                    status_str = 'Tellimus väljastatud'
                elif status == 3:
                    status_str = 'Aegunud'
                else:
                    status_str = 'Tundmatu staatus'
                    
                messages.success(request, f"Tellimus {order_number} arhiveeriti edukalt staatusega \"{status_str}\".")
            else:
                messages.error(request, f"Tellimust numbriga {order_number} ei leitud.")
        else:
            messages.error(request, "Tellimuse number pole märgitud.")
    return redirect('operator')

weekday_order = {
    'Esmaspäev': 1,
    'Teisipäev': 2,
    'Kolmapäev': 3,
    'Neljapäev': 4,
    'Reede': 5,
}

def get_all_user_orders(user):
    user_orders = order.objects.filter(user_id=user).values('order_number').annotate(
        total_price=Sum(F('quantity') * F('menu_id__dish_id__dish_price'))
    ).order_by('order_number')

    orders_data = []
    years = set()
    weeks = set()
    total_sum = 0
    current_time = datetime.now()
    current_year = current_time.year
    current_week = current_time.isocalendar()[1]
    current_day = current_time.isocalendar()[2]
    current_hour = current_time.hour
    
    for order_item in user_orders:
        order_number_str = str(order_item['order_number'])
        year = int(order_number_str[:4])
        week = int(order_number_str[4:6])
        day = int(order_number_str[6:8])
        is_today = False
        years.add(year)
        weeks.add(week)

        order_details = order.objects.filter(order_number=order_item['order_number']).values(
            'menu_id__dish_id__dish_name', 'quantity', 'city__name', 'menu_id__weekday_id__weekday_name'
        )

        is_open = order.objects.filter(order_number=order_item['order_number'], open=True).exists()

        is_expired = (year < current_year) or (year == current_year and week < current_week) or (year == current_year and week == current_week and day < current_day)

        if year == current_year and week == current_week and day == current_day:
            is_today = True

        order_data = {
            'order_number': order_item['order_number'],
            'year': year,
            'week': week,
            'day': day,
            'total_price': order_item['total_price'],
            'details': order_details,
            'is_open': is_open,
            'is_expired': is_expired,
            'is_today': is_today,
        }
        orders_data.append(order_data)
        total_sum += order_item['total_price']

    return orders_data, total_sum, years, weeks

def get_current_week_orders(user):
    current_week = datetime.now().isocalendar()[1]
    user_orders = order.objects.filter(user_id=user, menu_id__week_number__number=current_week).select_related('menu_id__dish_id', 'menu_id__weekday_id', 'city')
    
    grouped_orders = {}
    total_sum = 0
    for order_item in user_orders:
        day = order_item.menu_id.weekday_id.weekday_name
        city = order_item.city.name
        dish_name = order_item.menu_id.dish_id.dish_name
        quantity = order_item.quantity
        price = order_item.menu_id.dish_id.dish_price
        
        key = f"{day}:{city}"
        if key not in grouped_orders:
            grouped_orders[key] = {}
        if dish_name not in grouped_orders[key]:
            grouped_orders[key][dish_name] = 0
        grouped_orders[key][dish_name] += quantity
        total_sum += quantity * price

    return grouped_orders, total_sum

def get_archived_orders(user):
    archived_orders = ArchivedOrder.objects.filter(user_tabel_number=user.tabel_number)
    orders = []
    years = set()
    months = set()

    for order in archived_orders:
        order_number_str = str(order.order_number)
        year = int(order_number_str[:4])
        month = order.archived_at.month if order.archived_at else None
        years.add(year)
        months.add(month)
        orders.append({
            'order_number': order.order_number,
            'dishes': order.dishes,
            'city_name': order.city_name,
            'total_amount': order.total_amount,
            'archived_at': order.archived_at,
            'month': month,
            'status': order.status
        })
    return {
        'orders': orders,
        'years': list(years),
        'months': list(months),
    }

def calculate_order_stats(user):
    # Saame kõik kasutaja praegused tellimused ja filtreerime unikaalsed tellimuse numbrid
    current_orders = order.objects.filter(user_id=user).values('order_number').distinct()
    
    # Saame kõik kasutaja arhiveeritud tellimused
    archived_orders = ArchivedOrder.objects.filter(user_tabel_number=user.tabel_number)
    
    # Kõigi tellimuste arv
    total_orders = current_orders.count() + archived_orders.count()
    
    # Tulevaste tellimuste arv (praegustest tellimustest)
    current_time = datetime.now()
    current_year = current_time.year
    current_week = current_time.isocalendar()[1]
    current_day = current_time.isocalendar()[2]
    
    future_orders = 0
    for order_item in current_orders:
        order_number_str = str(order_item['order_number'])
        year = int(order_number_str[:4])
        week = int(order_number_str[4:6])
        day = int(order_number_str[6:8])
        
        if (year > current_year) or (year == current_year and week > current_week) or (year == current_year and week == current_week and day > current_day):
            future_orders += 1
    
    # Makstud tellimuste arv (arhiveeritud tellimused staatusega 1)
    closed_orders = archived_orders.filter(status=1).count()
    
    # Aegunud tellimuste arv (arhiveeritud tellimused staatusega 3)
    expired_orders = archived_orders.filter(status=3).count()
    
    return {
        'total_orders': total_orders,
        'closed_orders': closed_orders,
        'expired_orders': expired_orders,
        'future_orders': future_orders,
    }

def generate_qr_image(tabel_number):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(tabel_number)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()

@csrf_exempt
def initiate_payment(request, user_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            amount = data.get('amount')

            if not amount:
                return JsonResponse({"error": "Amount is required"}, status=400)

            try:
                amount = float(amount)  # Teisendame amount floatiks
                if amount <= 0:
                    return JsonResponse({"error": "Amount must be greater than 0"}, status=400)
            except ValueError:
                return JsonResponse({"error": "Invalid amount format"}, status=400)

            # Koostame payloadi EveryPay jaoks
            nonce = str(uuid.uuid4())
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            table_number = request.user.tabel_number
            user_email = request.user.email
            order_reference = f"{user_id}-{table_number}-{nonce}"

            payload = {
                "account_name": "EUR3D1",
                "nonce": nonce,
                "timestamp": timestamp,
                "amount": amount,
                "order_reference": order_reference,
                "customer_url": CALLBACK_URL,
                "api_username": EVERYPAY_API_USERNAME,
                "email": user_email,
                "customer_ip": request.META.get('REMOTE_ADDR'),
                "locale": "et",
                "billing_city": "Sillamäe",
                "billing_country": "EE",
                "billing_line1": "L.Tolstoi 2A",
                "billing_postcode": "40231",
                "request_token": False,  # Uurige True, kui vaja salvestada token
                "token_agreement": "unscheduled" if False else None,  # Uurige, kui request_token=True
            }

            # Koostame Basic Auth
            auth_string = f"{EVERYPAY_API_USERNAME}:{EVERYPAY_API_SECRET}"
            auth_bytes = auth_string.encode('ascii')
            base64_auth = base64.b64encode(auth_bytes).decode('ascii')

            headers = {
                "Authorization": f"Basic {base64_auth}",
                "Content-Type": "application/json",
            }

            # Saadame päringu EveryPay-le
            response = requests.post(EVERYPAY_API_URL_INITIATE, json=payload, headers=headers)

            if response.status_code == 201:
                payment_data = response.json()
                return JsonResponse({"payment_link": payment_data.get("payment_link")})
            else:
                # Logime vea
                print(f"Error response: {response.content}")
                return JsonResponse({"error": "Payment initiation failed", "details": response.content.decode('utf-8')}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Invalid request method"}, status=400)

import logging

logger = logging.getLogger(__name__)

@csrf_exempt
def callback(request):
    if request.method == 'GET':
        payment_reference = request.GET.get('payment_reference')
        order_reference = request.GET.get('order_reference')

        if not payment_reference:
            return HttpResponse("Payment reference is missing", status=400)

        # Kontrollime makse staatust EveryPay API kaudu
        auth_string = f"{EVERYPAY_API_USERNAME}:{EVERYPAY_API_SECRET}"
        auth_bytes = auth_string.encode('ascii')
        base64_auth = base64.b64encode(auth_bytes).decode('ascii')

        headers = {
            "Authorization": f"Basic {base64_auth}",
            "Content-Type": "application/json",
        }

        params = {
            "api_username": EVERYPAY_API_USERNAME,
        }

        response = requests.get(f"{EVERYPAY_API_URL_CALLBACK}/{payment_reference}", headers=headers, params=params)

        if response.status_code == 200:
            payment_data = response.json()
            payment_status = payment_data.get("payment_state")

            if payment_status == "settled":
                # Makse edukas, uuendame kasutaja saldot
                user_id = order_reference.split('-')[0]  # Ekstraheerime user_id order_reference'ist
                amount = payment_data.get("initial_amount")

                try:
                    user = User.objects.get(id=user_id)

                    # Loome tehingu kirje
                    transaction, created = Transaction.objects.get_or_create(
                        payment_reference=payment_reference,
                        defaults={
                            'user': user,
                            'amount': amount,
                            'transaction_type': 'deposit',
                            'description': f"Sissemakse pangakontolt (EveryPay link {payment_reference})",
                        }
                    )
                    if not created:
                        logger.warning(f"Transaction with payment reference {payment_reference} already exists.")

                    # Lisame sõnumi eduka makse kohta
                    messages.success(request, "Makse edukalt töödeldud. Teie saldo uuendatud.")

                    # Suuname kasutaja tasakaalu lehele
                    return HttpResponseRedirect(reverse('balance'))  # Asendage 'account' oma URL-i nimega
                except User.DoesNotExist:
                    return HttpResponse("User not found", status=404)
            else:
                messages.error(request, f"Makse staatus {payment_status}")
                return HttpResponseRedirect(reverse('balance'))
               # return HttpResponse(f"Payment status is {payment_status}", status=400)
        else:
            return HttpResponse("Failed to fetch payment details", status=400)
    return HttpResponse("Invalid request method", status=400)

@user_passes_test(lambda u: u.groups.filter(name='Client').exists())
def balance(request):
    if not request.user.is_authenticated:
        return redirect('login')

    # Saame kasutaja grupid
    user_groups = request.user.groups.values_list('name', flat=True)
    
    # QR-koodi genereerimine
    if request.user.is_authenticated and hasattr(request.user, 'tabel_number'):
        qr_image = generate_qr_image(request.user.tabel_number)
    else:
        qr_image = '00000'

    user = request.user
    transactions = Transaction.objects.filter(user=user).order_by('-created_at')

    # Ekstraheerime unikaalsed aastad ja kuud tehingutest
    unique_years = (
        transactions.annotate(year=ExtractYear('created_at'))
        .values('year')
        .annotate(count=Count('id'))
        .order_by('-year')
    )
    unique_months = (
        transactions.annotate(month=ExtractMonth('created_at'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )

    # Teisendame QuerySeti loenditeks
    years_list = [entry['year'] for entry in unique_years]
    months_list = [entry['month'] for entry in unique_months]

    data = {
        'user': user,
        'transactions': transactions,
        'qr_image': qr_image,
        'user_groups': user_groups,
        'unique_years': years_list,
        'unique_months': months_list,
    }

    return render(request, 'user/balance.html', data)

@csrf_exempt
def initiate_refund(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            data = json.loads(request.body)
            transaction_id = data.get('transaction_id')
            amount_str = data.get('amount')
            if amount_str:
                amount_str = amount_str.replace(',', '.')

            amount = Decimal(amount_str)

            # Kontrollime saadaolevat saldot
            if amount > user.balance:
                return JsonResponse({'success': False, 'error': 'Tagastamiseks pole piisavalt raha.'}, status=400)

            # Tagastuse algatamine läbi EveryPay API
            refund_response = initiate_refund_via_everypay(user, amount, transaction_id)

            if refund_response.get('payment_state') == 'refunded':
                deposit_transaction = user.transactions.get(id=transaction_id, transaction_type='deposit')
                payment_reference = deposit_transaction.payment_reference
                # Loome tagastuse tehingu
                Transaction.objects.create(
                    user=user,
                    amount=amount,
                    transaction_type='refund',
                    description=f"Tagasimakse pangakontole (EveryPay link {payment_reference})"
                )
                # Uuendame täiendamise tehingut: eemaldame payment_reference
                
                deposit_transaction.payment_reference = None
                deposit_transaction.save()
                user.balance -= amount
                user.save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': refund_response.get('error')}, status=400)

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'success': False, 'error': 'Meetod pole lubatud.'}, status=405)

def initiate_refund_via_everypay(user, amount, transaction_id):
    """
    Algatab vahendite tagastuse läbi EveryPay API, kasutades konkreetset täiendamise tehingut payment_reference abil.
    :param user: Kasutaja objekt, kes tagastust taotleb.
    :param amount: Tagastuse summa.
    :param transaction_id: Tehingu ID, mille alusel tagastus teostatakse.
    :return: Vastus EveryPay API-lt.
    """
    try:
        # Saame tehingu ID alusel
        deposit = user.transactions.get(id=transaction_id, transaction_type='deposit', payment_reference__isnull=False)
    except Transaction.DoesNotExist:
        raise ValueError("Tagastuse tehingut ei leitud.")

    # Andmete ettevalmistamine päringu jaoks
    payload = {
        "api_username": EVERYPAY_API_USERNAME,
        "amount": str(amount),  # Tagastuse summa
        "timestamp": datetime.utcnow().isoformat() + "Z",  # Praegune aeg ISO 8601 formaadis
        "payment_reference": deposit.payment_reference,
        "nonce": "unique_nonce_" + datetime.utcnow().isoformat()  # Unikaalne nonce
    }

    # Saadame tagastuse päringu
    response = requests.post(
        EVERYPAY_API_URL_REFUND,
        json=payload,
        auth=(EVERYPAY_API_USERNAME, EVERYPAY_API_SECRET),
        headers={"Content-Type": "application/json"}
    )

    # Töötleme vastust
    if response.status_code == 201:
        return response.json()  # Edukas tagastus
    else:
        error_message = response.json().get('error', {}).get('message', 'Tundmatu viga')
        raise Exception(f"Viga vahendite tagastamisel: {error_message}")

