from django.urls import path

from .views import (
    HealthView, DiagnoseView, HistoryView, HistoryDetailView, ProfileView,
    FeedCalculatorView, SupplierListView, SupplierDetailView,
    ExpertListView, ExpertDetailView, ChatRoomListCreateView, ChatMessageListCreateView,
    TaskListView, TaskCompleteView, TaskSummaryView,
    ArticleListView, ArticleDetailView,
    VaccinationListCreateView, VaccinationDetailView,
    MortalityListCreateView, MortalityDetailView,
    TreatmentListCreateView, TreatmentDetailView,
    FlockSummaryView, AnalyticsView,
    MarketRatesView, MarketRatesRegionView,
)
from .chatbot import ChatbotView

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('diagnose/', DiagnoseView.as_view(), name='diagnose'),
    path('history/', HistoryView.as_view(), name='history'),
    path('history/<int:pk>/', HistoryDetailView.as_view(), name='history-detail'),

    # Feed Calculator
    path('feed-calculator/', FeedCalculatorView.as_view(), name='feed-calculator'),

    # Marketplace
    path('suppliers/', SupplierListView.as_view(), name='supplier-list'),
    path('suppliers/<int:pk>/', SupplierDetailView.as_view(), name='supplier-detail'),

    # Experts & Chat
    path('experts/', ExpertListView.as_view(), name='expert-list'),
    path('experts/<int:pk>/', ExpertDetailView.as_view(), name='expert-detail'),
    path('chat/rooms/', ChatRoomListCreateView.as_view(), name='chat-rooms'),
    path('chat/rooms/<int:room_id>/messages/', ChatMessageListCreateView.as_view(), name='chat-messages'),

    # Tasks
    path('tasks/', TaskListView.as_view(), name='task-list'),
    path('tasks/<int:task_id>/complete/', TaskCompleteView.as_view(), name='task-complete'),
    path('tasks/summary/', TaskSummaryView.as_view(), name='task-summary'),

    # Education
    path('articles/', ArticleListView.as_view(), name='article-list'),
    path('articles/<int:pk>/', ArticleDetailView.as_view(), name='article-detail'),

    # Flock Health Records
    path('flock/vaccinations/', VaccinationListCreateView.as_view(), name='vaccination-list'),
    path('flock/vaccinations/<int:pk>/', VaccinationDetailView.as_view(), name='vaccination-detail'),
    path('flock/mortality/', MortalityListCreateView.as_view(), name='mortality-list'),
    path('flock/mortality/<int:pk>/', MortalityDetailView.as_view(), name='mortality-detail'),
    path('flock/treatments/', TreatmentListCreateView.as_view(), name='treatment-list'),
    path('flock/treatments/<int:pk>/', TreatmentDetailView.as_view(), name='treatment-detail'),
    path('flock/summary/', FlockSummaryView.as_view(), name='flock-summary'),

    # Analytics
    path('analytics/', AnalyticsView.as_view(), name='analytics'),

    # Market Rates (daily egg peti / broiler / feed). Primary path is Firestore,
    # this REST endpoint is a fallback for offline Firestore clients + web.
    path('market-rates/', MarketRatesView.as_view(), name='market-rates'),
    path('market-rates/<str:region_key>/', MarketRatesRegionView.as_view(), name='market-rates-region'),

    # AvianVet chatbot (Gemini-backed). POST-only; keeps the API key server-
    # side and injects per-user context (farm, latest diagnosis).
    path('assistant/', ChatbotView.as_view(), name='assistant'),
]
