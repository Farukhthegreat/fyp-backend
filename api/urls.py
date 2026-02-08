from django.urls import path

from .views import HealthView, DiagnoseView, HistoryView, HistoryDetailView, ProfileView

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('diagnose/', DiagnoseView.as_view(), name='diagnose'),
    path('history/', HistoryView.as_view(), name='history'),
    path('history/<int:pk>/', HistoryDetailView.as_view(), name='history-detail'),
]
