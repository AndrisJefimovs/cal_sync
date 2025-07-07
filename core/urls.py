from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('caldav/configure/', views.configure_caldav, name='configure_caldav'),
    path('binding/configure/', views.configure_binding, name='configure_binding'),
]
