from django.urls import path

from .views import (
    HealthView, DiagnoseView, HistoryView, HistoryDetailView, ProfileView,
    FeedCalculatorView, SupplierListView, SupplierDetailView,
    ExpertListView, ChatRoomListCreateView, ChatMessageListCreateView,
    TaskListView, TaskCompleteView, TaskSummaryView,
    ArticleListView, ArticleDetailView,
)

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
    path('chat/rooms/', ChatRoomListCreateView.as_view(), name='chat-rooms'),
    path('chat/rooms/<int:room_id>/messages/', ChatMessageListCreateView.as_view(), name='chat-messages'),

    # Tasks
    path('tasks/', TaskListView.as_view(), name='task-list'),
    path('tasks/<int:task_id>/complete/', TaskCompleteView.as_view(), name='task-complete'),
    path('tasks/summary/', TaskSummaryView.as_view(), name='task-summary'),

    # Education
    path('articles/', ArticleListView.as_view(), name='article-list'),
    path('articles/<int:pk>/', ArticleDetailView.as_view(), name='article-detail'),
]
