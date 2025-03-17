# app/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, table_number, category, weekday, dish, week, menu, order, City, ArchivedOrder, Transaction
# Register your models here.
admin.site.register(User, UserAdmin)
admin.site.register(table_number)
admin.site.register(category)
admin.site.register(weekday)
admin.site.register(dish)
admin.site.register(week)
admin.site.register(menu)
admin.site.register(order)
admin.site.register(City)
admin.site.register(ArchivedOrder)
admin.site.register(Transaction)